"""
CheckpointCoordinator - Manages distributed snapshots for fault tolerance
Implements Chandy-Lamport algorithm with barrier alignment
"""
import threading
import time
import json
from typing import Dict, Set, Optional, List
from dataclasses import dataclass
from enum import Enum
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.config import Config

try:
    import boto3
except ImportError:
    boto3 = None

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None


class CheckpointStatus(Enum):
    """Status of a checkpoint"""
    TRIGGERING = "triggering"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CheckpointMetadata:
    """Metadata for a checkpoint"""
    checkpoint_id: int
    job_id: str
    timestamp: int
    status: CheckpointStatus
    task_states: Dict[str, str]  # task_id -> S3 path
    metadata_path: str
    kafka_offsets: Dict[str, Dict[int, int]]  # topic -> partition -> offset


class CheckpointCoordinator:
    """
    Coordinates distributed snapshots across all tasks.

    Process:
    1. Trigger checkpoint by injecting barriers at sources
    2. Track barrier progress via acknowledgments from tasks
    3. Upload state snapshots to S3
    4. Atomically commit metadata to PostgreSQL when all tasks ack
    """

    def __init__(
        self,
        job_id: str,
        checkpoint_interval_ms: int = Config.CHECKPOINT_INTERVAL,
        checkpoint_timeout_ms: int = Config.CHECKPOINT_TIMEOUT
    ):
        """
        Args:
            job_id: Job identifier
            checkpoint_interval_ms: Interval between checkpoints
            checkpoint_timeout_ms: Timeout for checkpoint completion
        """
        self.job_id = job_id
        self.checkpoint_interval_ms = checkpoint_interval_ms
        self.checkpoint_timeout_ms = checkpoint_timeout_ms

        # Checkpoint state
        self.current_checkpoint_id = 0
        self.pending_checkpoints: Dict[int, CheckpointMetadata] = {}
        self.completed_checkpoints: Dict[int, CheckpointMetadata] = {}
        self.pending_acks: Dict[int, Set[str]] = {}  # checkpoint_id -> set of task_ids

        # Lock for thread safety
        self.lock = threading.Lock()

        # Checkpoint thread
        self.checkpoint_thread: Optional[threading.Thread] = None
        self.running = False

        # S3 client
        self.s3_client = None
        if boto3:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                region_name=Config.AWS_REGION
            )

        # PostgreSQL connection
        self.pg_conn = None
        if psycopg2:
            try:
                self.pg_conn = psycopg2.connect(
                    Config.get_postgres_connection_string()
                )
                self._init_database()
            except Exception as e:
                print(f"Failed to connect to PostgreSQL: {e}")

    def start(self):
        """Start checkpoint coordinator"""
        self.running = True
        self.checkpoint_thread = threading.Thread(
            target=self._checkpoint_loop,
            daemon=True
        )
        self.checkpoint_thread.start()
        print(f"CheckpointCoordinator started for job {self.job_id}")

    def stop(self):
        """Stop checkpoint coordinator"""
        self.running = False
        if self.checkpoint_thread:
            self.checkpoint_thread.join(timeout=5)

        if self.pg_conn:
            self.pg_conn.close()

        print(f"CheckpointCoordinator stopped for job {self.job_id}")

    def trigger_checkpoint(self, task_ids: List[str]) -> int:
        """
        Trigger a new checkpoint.

        Args:
            task_ids: List of all task IDs in the job

        Returns:
            Checkpoint ID
        """
        with self.lock:
            self.current_checkpoint_id += 1
            checkpoint_id = self.current_checkpoint_id
            timestamp = int(time.time() * 1000)

            # Create checkpoint metadata
            metadata = CheckpointMetadata(
                checkpoint_id=checkpoint_id,
                job_id=self.job_id,
                timestamp=timestamp,
                status=CheckpointStatus.TRIGGERING,
                task_states={},
                metadata_path=self._get_metadata_path(checkpoint_id),
                kafka_offsets={}
            )

            self.pending_checkpoints[checkpoint_id] = metadata
            self.pending_acks[checkpoint_id] = set(task_ids)

            print(f"Triggered checkpoint {checkpoint_id} for {len(task_ids)} tasks")

            # In a real implementation, would send checkpoint barriers to source tasks via gRPC
            # For now, just transition to IN_PROGRESS
            metadata.status = CheckpointStatus.IN_PROGRESS

            return checkpoint_id

    def acknowledge_checkpoint(
        self,
        checkpoint_id: int,
        task_id: str,
        state_data: bytes,
        task_manager_id: str
    ) -> bool:
        """
        Acknowledge checkpoint completion from a task.

        Args:
            checkpoint_id: Checkpoint identifier
            task_id: Task identifier
            state_data: Serialized state data
            task_manager_id: TaskManager identifier

        Returns:
            True if acknowledgment accepted
        """
        # Validate checkpoint outside of lock
        with self.lock:
            if checkpoint_id not in self.pending_checkpoints:
                print(f"Unknown checkpoint {checkpoint_id}")
                return False

            if checkpoint_id not in self.pending_acks:
                print(f"Checkpoint {checkpoint_id} already completed or timed out")
                return False

            if task_id not in self.pending_acks[checkpoint_id]:
                print(f"Unexpected ack from task {task_id} for checkpoint {checkpoint_id}")
                return False

        # Upload state to S3 without holding the lock (improves concurrency)
        state_path = self._upload_state(
            checkpoint_id,
            task_id,
            task_manager_id,
            state_data
        )

        if state_path:
            # Now acquire lock to update metadata
            with self.lock:
                # Double-check checkpoint still exists
                if checkpoint_id not in self.pending_checkpoints:
                    print(f"Checkpoint {checkpoint_id} was removed during upload")
                    return False

                # Record state path
                metadata = self.pending_checkpoints[checkpoint_id]
                metadata.task_states[task_id] = state_path

                # Remove from pending
                if task_id in self.pending_acks[checkpoint_id]:
                    self.pending_acks[checkpoint_id].remove(task_id)

                print(f"Acknowledged checkpoint {checkpoint_id} from task {task_id}")

                # Check if all tasks have acknowledged
                if checkpoint_id in self.pending_acks and not self.pending_acks[checkpoint_id]:
                    self._complete_checkpoint(checkpoint_id)

            return True
        else:
            print(f"Failed to upload state for task {task_id}")
            return False

    def _complete_checkpoint(self, checkpoint_id: int):
        """
        Complete a checkpoint after all tasks acknowledged.

        Args:
            checkpoint_id: Checkpoint identifier
        """
        metadata = self.pending_checkpoints[checkpoint_id]
        metadata.status = CheckpointStatus.COMPLETED

        # Commit metadata to PostgreSQL
        if self._commit_checkpoint_metadata(metadata):
            print(f"Completed checkpoint {checkpoint_id}")
            self.completed_checkpoints[checkpoint_id] = metadata
        else:
            print(f"Failed to commit metadata for checkpoint {checkpoint_id}")
            metadata.status = CheckpointStatus.FAILED

        # Clean up pending
        del self.pending_checkpoints[checkpoint_id]
        del self.pending_acks[checkpoint_id]

    def get_latest_checkpoint(self) -> Optional[CheckpointMetadata]:
        """
        Get the latest completed checkpoint.

        Returns:
            CheckpointMetadata or None
        """
        with self.lock:
            if not self.completed_checkpoints:
                # Try to load from database
                return self._load_latest_checkpoint_from_db()

            latest_id = max(self.completed_checkpoints.keys())
            return self.completed_checkpoints[latest_id]

    def _checkpoint_loop(self):
        """Periodic checkpoint triggering"""
        while self.running:
            try:
                # In a real implementation, would get task IDs from ExecutionGraph
                # For now, skip actual triggering

                # Check for timed out checkpoints
                self._check_checkpoint_timeouts()
            except Exception as e:
                print(f"Error in checkpoint loop: {e}")

            time.sleep(self.checkpoint_interval_ms / 1000.0)

    def _check_checkpoint_timeouts(self):
        """Check for and handle timed out checkpoints"""
        current_time = time.time() * 1000  # Convert to milliseconds
        timed_out_checkpoints = []

        with self.lock:
            for checkpoint_id, metadata in list(self.pending_checkpoints.items()):
                elapsed_ms = current_time - metadata.timestamp

                if elapsed_ms > self.checkpoint_timeout_ms:
                    print(f"Checkpoint {checkpoint_id} timed out after {elapsed_ms}ms")
                    metadata.status = CheckpointStatus.FAILED
                    timed_out_checkpoints.append(checkpoint_id)

            # Clean up timed out checkpoints
            for checkpoint_id in timed_out_checkpoints:
                del self.pending_checkpoints[checkpoint_id]
                if checkpoint_id in self.pending_acks:
                    del self.pending_acks[checkpoint_id]

    def _upload_state(
        self,
        checkpoint_id: int,
        task_id: str,
        task_manager_id: str,
        state_data: bytes
    ) -> Optional[str]:
        """
        Upload state snapshot to S3.

        Args:
            checkpoint_id: Checkpoint identifier
            task_id: Task identifier
            task_manager_id: TaskManager identifier
            state_data: State data to upload

        Returns:
            S3 path or None on failure
        """
        if not self.s3_client:
            # Save locally for testing
            local_path = f"/tmp/checkpoints/{self.job_id}/chk-{checkpoint_id}/{task_manager_id}/{task_id}.bin"
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(state_data)
            return local_path

        try:
            # Parse S3 path
            s3_path = Config.S3_CHECKPOINT_PATH
            if s3_path.startswith('s3://'):
                s3_path = s3_path[5:]

            bucket, prefix = s3_path.split('/', 1)
            key = f"{prefix}/job-{self.job_id}/chk-{checkpoint_id}/tm-{task_manager_id}/{task_id}.bin"

            # Upload to S3
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=state_data
            )

            return f"s3://{bucket}/{key}"

        except Exception as e:
            print(f"Error uploading state to S3: {e}")
            return None

    def _get_metadata_path(self, checkpoint_id: int) -> str:
        """Get S3 path for checkpoint metadata"""
        s3_path = Config.S3_CHECKPOINT_PATH
        return f"{s3_path}/job-{self.job_id}/chk-{checkpoint_id}/metadata.json"

    def _init_database(self):
        """Initialize database schema"""
        if not self.pg_conn:
            return

        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        checkpoint_id BIGINT PRIMARY KEY,
                        job_id VARCHAR(256) NOT NULL,
                        timestamp BIGINT NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        task_states JSONB NOT NULL,
                        metadata_path TEXT NOT NULL,
                        kafka_offsets JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_checkpoints_job_id
                    ON checkpoints(job_id, checkpoint_id DESC)
                """)
                self.pg_conn.commit()
        except Exception as e:
            print(f"Error initializing database: {e}")

    def _ensure_db_connection(self) -> bool:
        """
        Ensure database connection is active, reconnect if necessary.

        Returns:
            True if connection is active
        """
        if not psycopg2:
            return False

        try:
            # Test if connection is alive
            if self.pg_conn and not self.pg_conn.closed:
                with self.pg_conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return True
        except Exception:
            pass

        # Try to reconnect
        try:
            if self.pg_conn:
                self.pg_conn.close()

            self.pg_conn = psycopg2.connect(
                Config.get_postgres_connection_string()
            )
            self._init_database()
            print("Reconnected to PostgreSQL")
            return True
        except Exception as e:
            print(f"Failed to reconnect to PostgreSQL: {e}")
            self.pg_conn = None
            return False

    def _commit_checkpoint_metadata(self, metadata: CheckpointMetadata) -> bool:
        """
        Atomically commit checkpoint metadata to PostgreSQL.

        Args:
            metadata: CheckpointMetadata to commit

        Returns:
            True if commit successful
        """
        if not psycopg2:
            # Mock success for testing
            return True

        # Ensure connection is active
        if not self._ensure_db_connection():
            return False

        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO checkpoints
                    (checkpoint_id, job_id, timestamp, status, task_states, metadata_path, kafka_offsets)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (checkpoint_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        task_states = EXCLUDED.task_states
                """, (
                    metadata.checkpoint_id,
                    metadata.job_id,
                    metadata.timestamp,
                    metadata.status.value,
                    json.dumps(metadata.task_states),
                    metadata.metadata_path,
                    json.dumps(metadata.kafka_offsets)
                ))
                self.pg_conn.commit()
                return True
        except Exception as e:
            print(f"Error committing checkpoint metadata: {e}")
            if self.pg_conn:
                self.pg_conn.rollback()
            return False

    def _load_latest_checkpoint_from_db(self) -> Optional[CheckpointMetadata]:
        """Load latest checkpoint from database"""
        if not psycopg2:
            return None

        # Ensure connection is active
        if not self._ensure_db_connection():
            return None

        try:
            with self.pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT * FROM checkpoints
                    WHERE job_id = %s AND status = %s
                    ORDER BY checkpoint_id DESC
                    LIMIT 1
                """, (self.job_id, CheckpointStatus.COMPLETED.value))

                row = cur.fetchone()
                if not row:
                    return None

                return CheckpointMetadata(
                    checkpoint_id=row['checkpoint_id'],
                    job_id=row['job_id'],
                    timestamp=row['timestamp'],
                    status=CheckpointStatus(row['status']),
                    task_states=json.loads(row['task_states']),
                    metadata_path=row['metadata_path'],
                    kafka_offsets=json.loads(row['kafka_offsets']) if row['kafka_offsets'] else {}
                )
        except Exception as e:
            print(f"Error loading checkpoint from database: {e}")
            return None
