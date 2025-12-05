"""
TaskExecutor - Core execution engine for TaskManager
Hosts gRPC server, manages task execution, handles checkpoints and barrier alignment
"""
import grpc
from concurrent import futures
import threading
import time
import pickle
from typing import Dict, List, Optional
from collections import defaultdict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.config import Config
from common.serialization import StreamRecord
from common.watermarks import Watermark

# Import generated proto files
from common.protobuf import stream_processing_pb2
from common.protobuf import stream_processing_pb2_grpc
from taskmanager.grpc_service import TaskManagerServiceImpl

from taskmanager.operators.base import StreamOperator, OperatorChain
from taskmanager.state.rocksdb_backend import RocksDBStateBackend, InMemoryStateBackend
from taskmanager.network.buffer_pool import BufferPool
from taskmanager.network.flow_control import NetworkFlowController
from taskmanager.metrics import TaskMetrics, MetricsServer


class Task:
    """
    Represents a running task with its operator and state.
    """

    def __init__(
        self,
        task_id: str,
        operator: StreamOperator,
        state_backend,
        upstream_tasks: List[str],
        downstream_tasks: List[str]
    ):
        """
        Args:
            task_id: Unique task identifier
            operator: The operator(s) to execute (may be OperatorChain)
            state_backend: State backend for checkpointing
            upstream_tasks: List of upstream task IDs
            downstream_tasks: List of downstream task IDs
        """
        self.task_id = task_id
        self.operator = operator
        self.state_backend = state_backend
        self.upstream_tasks = upstream_tasks
        self.downstream_tasks = downstream_tasks

        # Barrier alignment state
        self.barriers: Dict[int, Dict[str, bool]] = defaultdict(lambda: {})  # checkpoint_id -> {upstream -> received}
        self.buffered_records: Dict[int, List] = defaultdict(list)  # checkpoint_id -> records

        # Metrics
        self.metrics = TaskMetrics(task_id, operator.operator_id)

        # Running state
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def start(self):
        """Start task execution"""
        with self.lock:
            if self.running:
                return

            self.running = True
            self.operator.open()
            
            # Start execution thread
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def run(self):
        """Main execution loop"""
        try:
            # Check if we have a source operator
            source_operator = None
            is_chain = isinstance(self.operator, OperatorChain)
            
            if is_chain:
                if hasattr(self.operator.operators[0], 'read_records'):
                    source_operator = self.operator.operators[0]
            elif hasattr(self.operator, 'read_records'):
                source_operator = self.operator

            # If source, run poll loop
            if source_operator:
                print(f"Task {self.task_id} starting source loop")
                while self.running:
                    # Read records
                    records = source_operator.read_records()
                    
                    for record_tuple in records:
                        # record_tuple is (record, partition, offset)
                        record = record_tuple[0]
                        
                        # Process through remaining operators
                        if is_chain:
                            # Skip source (first operator)
                            current_records = [record]
                            for op in self.operator.operators[1:]:
                                next_records = []
                                for r in current_records:
                                    next_records.extend(op.process_element(r))
                                current_records = next_records
                                
                                # Record metrics for this operator
                                # Note: This is simplified, ideally we record for each op
                        else:
                            # Single source, just emit to downstream
                            # TODO: Implement network emission
                            pass
                            
                        # Update metrics
                        self.metrics.record_processed()
                    
                    # Sleep briefly to avoid busy loop if no records
                    if not records:
                        time.sleep(0.01)
                        
            else:
                # Downstream task - wait for input
                # In a real system, this would listen on a queue/socket
                print(f"Task {self.task_id} waiting for input (push-based)")
                while self.running:
                    time.sleep(1)

        except Exception as e:
            print(f"Task {self.task_id} failed: {e}")
            import traceback
            traceback.print_exc()
            self.running = False

    def stop(self):
        """Stop task execution"""
        with self.lock:
            if not self.running:
                return

            self.running = False
            self.operator.close()

    def process_record(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Process a stream record through the operator.

        Args:
            record: Input record

        Returns:
            List of output records
        """
        if not self.running:
            return []

        try:
            start_time = time.time()

            # Process through operator
            results = self.operator.process_element(record)

            # Record metrics
            latency = time.time() - start_time
            self.metrics.record_processed()
            self.metrics.observe_latency(latency)

            return results

        except Exception as e:
            print(f"Error processing record in task {self.task_id}: {e}")
            return []

    def process_watermark(self, watermark: Watermark) -> List[StreamRecord]:
        """
        Process a watermark through the operator.

        Args:
            watermark: Watermark to process

        Returns:
            List of triggered records (e.g., window results)
        """
        if not self.running:
            return []

        try:
            return self.operator.process_watermark(watermark)
        except Exception as e:
            print(f"Error processing watermark in task {self.task_id}: {e}")
            return []

    def process_barrier(
        self,
        checkpoint_id: int,
        upstream_id: str
    ) -> Optional[bytes]:
        """
        Process a checkpoint barrier with alignment.

        Args:
            checkpoint_id: Checkpoint identifier
            upstream_id: ID of upstream task that sent barrier

        Returns:
            Snapshot bytes if barrier is aligned, None otherwise
        """
        with self.lock:
            # Mark barrier received from this upstream
            self.barriers[checkpoint_id][upstream_id] = True

            # Check if all upstreams have sent barriers
            all_received = all(
                self.barriers[checkpoint_id].get(upstream, False)
                for upstream in self.upstream_tasks
            )

            if all_received:
                # All barriers aligned - snapshot state
                try:
                    snapshot = self.operator.snapshot_state()

                    # Clean up barrier tracking
                    del self.barriers[checkpoint_id]
                    if checkpoint_id in self.buffered_records:
                        del self.buffered_records[checkpoint_id]

                    return snapshot

                except Exception as e:
                    print(f"Error snapshotting state in task {self.task_id}: {e}")
                    return None

            return None

    def restore_from_checkpoint(self, state_data: bytes):
        """
        Restore task state from checkpoint.

        Args:
            state_data: Serialized state data
        """
        try:
            self.operator.restore_state(state_data)
            print(f"Task {self.task_id} restored from checkpoint")
        except Exception as e:
            print(f"Error restoring task {self.task_id}: {e}")


class TaskExecutor:
    """
    TaskExecutor manages task lifecycle and hosts the TaskManager gRPC service.
    """

    def __init__(
        self,
        task_manager_id: str,
        jobmanager_host: str = Config.JOBMANAGER_HOST,
        jobmanager_port: int = Config.JOBMANAGER_RPC_PORT,
        rpc_port: int = Config.TASKMANAGER_RPC_PORT,
        task_slots: int = Config.TASK_SLOTS
    ):
        """
        Args:
            task_manager_id: Unique TaskManager identifier
            jobmanager_host: JobManager host
            jobmanager_port: JobManager RPC port
            rpc_port: Port for TaskManager gRPC server
            task_slots: Number of concurrent task slots
        """
        self.task_manager_id = task_manager_id
        self.jobmanager_host = jobmanager_host
        self.jobmanager_port = jobmanager_port
        self.rpc_port = rpc_port
        self.task_slots = task_slots

        # Task management
        self.tasks: Dict[str, Task] = {}
        self.tasks_lock = threading.Lock()

        # Network components
        self.buffer_pool = BufferPool()
        self.flow_controller = NetworkFlowController()

        # State backend base path
        self.state_path = "/tmp/taskmanager_state"
        os.makedirs(self.state_path, exist_ok=True)

        # gRPC server
        self.grpc_server: Optional[grpc.Server] = None

        # Heartbeat thread
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.running = False

        # Metrics server
        self.metrics_server = MetricsServer(Config.METRICS_PORT)

    def start(self):
        """Start TaskExecutor"""
        print(f"Starting TaskExecutor {self.task_manager_id}")

        # Start metrics server
        self.metrics_server.start()

        # Start gRPC server
        self._start_grpc_server()

        # Start heartbeat
        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

        print(f"TaskExecutor {self.task_manager_id} started on port {self.rpc_port}")

    def stop(self):
        """Stop TaskExecutor"""
        print(f"Stopping TaskExecutor {self.task_manager_id}")

        self.running = False

        # Stop all tasks
        with self.tasks_lock:
            for task in self.tasks.values():
                task.stop()

        # Stop gRPC server
        if self.grpc_server:
            self.grpc_server.stop(grace=5)

        print(f"TaskExecutor {self.task_manager_id} stopped")

    def _start_grpc_server(self):
        """Start gRPC server for TaskManager service"""
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.task_slots * 2)
        )

        # Register TaskManager gRPC service
        service_impl = TaskManagerServiceImpl(self)
        stream_processing_pb2_grpc.add_TaskManagerServiceServicer_to_server(
            service_impl, self.grpc_server
        )

        self.grpc_server.add_insecure_port(f'[::]:{self.rpc_port}')
        self.grpc_server.start()
        print(f"gRPC server started on port {self.rpc_port}")

    def deploy_task(
        self,
        task_id: str,
        serialized_operator: bytes,
        upstream_tasks: List[str],
        downstream_tasks: List[str],
        checkpoint_path: Optional[str] = None,
        checkpoint_id: Optional[int] = None
    ) -> bool:
        """
        Deploy a new task.

        Args:
            task_id: Unique task identifier
            serialized_operator: Pickled operator
            upstream_tasks: List of upstream task IDs
            downstream_tasks: List of downstream task IDs
            checkpoint_path: Optional checkpoint path for recovery
            checkpoint_id: Optional checkpoint ID for recovery

        Returns:
            True if deployment successful
        """
        try:
            with self.tasks_lock:
                # Check available slots
                if len(self.tasks) >= self.task_slots:
                    print(f"No available task slots (max: {self.task_slots})")
                    return False

                # Deserialize operator
                operator = pickle.loads(serialized_operator)

                # Create state backend
                if Config.STATE_BACKEND == "rocksdb":
                    state_backend = RocksDBStateBackend(self.state_path, task_id)
                else:
                    state_backend = InMemoryStateBackend(task_id)

                # Set state backend on operator
                operator.set_state_backend(state_backend)

                # Restore from checkpoint if provided
                if checkpoint_path and checkpoint_id is not None:
                    state_data = self._load_checkpoint(checkpoint_path, task_id)
                    if state_data:
                        operator.restore_state(state_data)

                # Create and start task
                task = Task(
                    task_id,
                    operator,
                    state_backend,
                    upstream_tasks,
                    downstream_tasks
                )
                task.start()

                self.tasks[task_id] = task

                print(f"Deployed task {task_id}")
                return True

        except Exception as e:
            print(f"Error deploying task {task_id}: {e}")
            return False

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            task_id: Task identifier

        Returns:
            True if cancellation successful
        """
        try:
            with self.tasks_lock:
                if task_id not in self.tasks:
                    print(f"Task {task_id} not found")
                    return False

                task = self.tasks[task_id]
                task.stop()
                del self.tasks[task_id]

                print(f"Cancelled task {task_id}")
                return True

        except Exception as e:
            print(f"Error cancelling task {task_id}: {e}")
            return False

    def trigger_checkpoint(self, checkpoint_id: int) -> Dict[str, bytes]:
        """
        Trigger checkpoint on all tasks.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            Dictionary of task_id -> snapshot bytes
        """
        snapshots = {}

        with self.tasks_lock:
            for task_id, task in self.tasks.items():
                try:
                    # For sources, barriers come from coordinator
                    # For other tasks, barriers come from upstream
                    # Here we simulate by directly snapshotting
                    snapshot = task.operator.snapshot_state()
                    snapshots[task_id] = snapshot

                except Exception as e:
                    print(f"Error checkpointing task {task_id}: {e}")

        return snapshots

    def _load_checkpoint(self, checkpoint_path: str, task_id: str) -> Optional[bytes]:
        """
        Load checkpoint data from storage (S3, GCS, or local).

        Args:
            checkpoint_path: Path to checkpoint
            task_id: Task identifier

        Returns:
            Checkpoint data or None
        """
        storage_backend = Config.STORAGE_BACKEND.lower()
        
        # Try GCS first if configured
        if storage_backend == "gcs":
            try:
                from google.cloud import storage as gcs_storage
                gcs_client = gcs_storage.Client()
                bucket_name = Config.get_gcs_bucket()
                bucket = gcs_client.bucket(bucket_name)
                
                # Parse checkpoint path to get blob name
                # checkpoint_path format: gs://bucket/prefix/job-{job_id}/chk-{checkpoint_id}/tm-{task_manager_id}
                # We need: prefix/job-{job_id}/chk-{checkpoint_id}/tm-{task_manager_id}/{task_id}.bin
                if checkpoint_path.startswith('gs://'):
                    checkpoint_path = checkpoint_path[5:]
                if checkpoint_path.startswith(bucket_name + '/'):
                    checkpoint_path = checkpoint_path[len(bucket_name) + 1:]
                
                blob_name = f"{checkpoint_path}/{task_id}.bin"
                blob = bucket.blob(blob_name)
                
                if blob.exists():
                    checkpoint_data = blob.download_as_bytes()
                    print(f"Loaded checkpoint for {task_id} from GCS: {len(checkpoint_data)} bytes")
                    return checkpoint_data
            except ImportError:
                print("google-cloud-storage not available, trying other backends...")
            except Exception as e:
                print(f"Failed to load checkpoint from GCS: {e}, trying other storage...")
        
        # Try S3 if configured
        if storage_backend == "s3":
            try:
                if boto3:
                    s3_client = boto3.client('s3')
                    bucket = Config.get_s3_bucket()
                    key = f"{checkpoint_path}/{task_id}/state"

                    response = s3_client.get_object(Bucket=bucket, Key=key)
                    checkpoint_data = response['Body'].read()
                    print(f"Loaded checkpoint for {task_id} from S3: {len(checkpoint_data)} bytes")
                    return checkpoint_data
            except Exception as e:
                print(f"Failed to load checkpoint from S3: {e}, trying local storage...")

        # Fallback to local storage
        try:
            local_path = f"/tmp/checkpoints/{checkpoint_path}/{task_id}_state.pkl"
            if os.path.exists(local_path):
                with open(local_path, 'rb') as f:
                    checkpoint_data = f.read()
                print(f"Loaded checkpoint for {task_id} from local: {len(checkpoint_data)} bytes")
                return checkpoint_data
        except Exception as e:
            print(f"Failed to load checkpoint from local storage: {e}")

        print(f"No checkpoint found for {task_id}")
        return None

    def _heartbeat_loop(self):
        """Send periodic heartbeats to JobManager"""
        while self.running:
            try:
                self._send_heartbeat()
            except Exception as e:
                print(f"Error sending heartbeat: {e}")

            time.sleep(Config.HEARTBEAT_INTERVAL / 1000.0)

    def _send_heartbeat(self):
        """Send heartbeat to JobManager via HTTP"""
        import urllib.request
        import json
        
        with self.tasks_lock:
            available_slots = self.task_slots - len(self.tasks)

            # Collect metrics from all tasks
            task_metrics = []
            for task_id, task in self.tasks.items():
                metrics = task.metrics.get_metrics_dict()
                task_metrics.append({
                    'task_id': task_id,
                    'status': 'running',
                    'records_processed': metrics['records_processed'],
                    'processing_latency_ms': metrics['processing_latency_ms'],
                    'backpressure_ratio': metrics['backpressure_ratio']
                })

        # Build heartbeat payload
        heartbeat_data = {
            'task_manager_id': self.task_manager_id,
            'host': os.environ.get('HOSTNAME', 'localhost'),
            'port': self.rpc_port,
            'available_slots': available_slots,
            'total_slots': self.task_slots,
            'task_metrics': task_metrics,
            'timestamp': time.time() * 1000
        }

        # Send heartbeat to JobManager via HTTP
        try:
            url = f"http://{self.jobmanager_host}:{Config.JOBMANAGER_REST_PORT}/taskmanagers/heartbeat"
            data = json.dumps(heartbeat_data).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    pass  # Heartbeat successful
        except Exception as e:
            # Silently fail heartbeat - will retry on next interval
            pass

    def get_metrics(self) -> dict:
        """
        Get metrics for all tasks.

        Returns:
            Dictionary of metrics
        """
        metrics = {}

        with self.tasks_lock:
            for task_id, task in self.tasks.items():
                # Collect task metrics
                metrics[task_id] = {
                    'task_id': task_id,
                    'operator_id': task.operator.operator_id,
                    'running': task.running,
                }

        return metrics


def main():
    """Main entry point for TaskManager"""
    import argparse

    parser = argparse.ArgumentParser(description='TaskManager for Stream Processing')
    parser.add_argument('--task-manager-id', required=True, help='TaskManager ID')
    parser.add_argument('--jobmanager-host', default=Config.JOBMANAGER_HOST, help='JobManager host')
    parser.add_argument('--jobmanager-port', type=int, default=Config.JOBMANAGER_RPC_PORT, help='JobManager RPC port')
    parser.add_argument('--rpc-port', type=int, default=Config.TASKMANAGER_RPC_PORT, help='TaskManager RPC port')
    parser.add_argument('--task-slots', type=int, default=Config.TASK_SLOTS, help='Number of task slots')

    args = parser.parse_args()

    executor = TaskExecutor(
        task_manager_id=args.task_manager_id,
        jobmanager_host=args.jobmanager_host,
        jobmanager_port=args.jobmanager_port,
        rpc_port=args.rpc_port,
        task_slots=args.task_slots
    )

    try:
        executor.start()

        # Keep running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
        executor.stop()


if __name__ == '__main__':
    main()
