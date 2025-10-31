"""
Source operators for reading data from external systems
"""
from typing import List, Optional, Dict
import sys
import os
import pickle
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.serialization import StreamRecord
from common.watermarks import WatermarkStrategy, PeriodicWatermarkEmitter
from .base import StreamOperator

try:
    from kafka import KafkaConsumer
    from kafka.structs import TopicPartition, OffsetAndMetadata
except ImportError:
    KafkaConsumer = None
    TopicPartition = None
    OffsetAndMetadata = None


class KafkaSourceOperator(StreamOperator):
    """
    Kafka source operator with exactly-once semantics.
    Manages consumer offsets as part of checkpoint state.
    """

    def __init__(
        self,
        topic: str,
        bootstrap_servers: str,
        group_id: str,
        watermark_strategy: Optional[WatermarkStrategy] = None,
        operator_id: str = "kafka_source"
    ):
        """
        Args:
            topic: Kafka topic to consume from
            bootstrap_servers: Kafka broker addresses
            group_id: Consumer group ID
            watermark_strategy: Strategy for watermark generation
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.watermark_strategy = watermark_strategy

        self.consumer: Optional[KafkaConsumer] = None
        self.watermark_emitter: Optional[PeriodicWatermarkEmitter] = None
        self.current_offsets: Dict[int, int] = {}  # partition -> offset
        self.running = False

    def open(self):
        """Initialize Kafka consumer"""
        if KafkaConsumer is None:
            raise ImportError("kafka-python-ng is required for KafkaSourceOperator")

        # Create consumer with manual offset management for exactly-once
        self.consumer = KafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=False,  # Critical for exactly-once
            auto_offset_reset='earliest',
            key_deserializer=lambda k: k,
            value_deserializer=lambda v: v,
        )

        # Initialize watermark emitter if strategy provided
        if self.watermark_strategy:
            self.watermark_emitter = self.watermark_strategy.create_watermark_emitter()

        self.running = True

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Source operators don't process incoming elements.
        They generate elements by reading from Kafka.
        """
        return []

    def read_records(self, max_records: int = 100) -> List[tuple]:
        """
        Read records from Kafka and generate watermarks.

        Args:
            max_records: Maximum number of records to read

        Returns:
            List of tuples: (StreamRecord or Watermark, partition, offset)
        """
        if not self.consumer or not self.running:
            return []

        results = []

        try:
            # Poll for records
            messages = self.consumer.poll(timeout_ms=100, max_records=max_records)

            for topic_partition, records in messages.items():
                partition = topic_partition.partition

                for record in records:
                    # Extract timestamp (use Kafka timestamp if available)
                    timestamp = record.timestamp if record.timestamp else int(time.time() * 1000)

                    # Create stream record
                    stream_record = StreamRecord(
                        key=record.key,
                        value=record.value,
                        timestamp=timestamp,
                        headers=dict(record.headers) if record.headers else {}
                    )

                    results.append((stream_record, partition, record.offset))

                    # Update offset tracking
                    self.current_offsets[partition] = record.offset + 1

                    # Generate watermark if configured
                    if self.watermark_emitter:
                        watermark = self.watermark_emitter.on_event(timestamp)
                        if watermark:
                            results.append((watermark, partition, record.offset))

        except Exception as e:
            print(f"Error reading from Kafka: {e}")

        return results

    def snapshot_state(self) -> bytes:
        """
        Snapshot Kafka offsets for exactly-once semantics.
        This ensures we can resume from the exact position after recovery.
        """
        state = {
            'offsets': self.current_offsets.copy()
        }
        return pickle.dumps(state)

    def restore_state(self, state: bytes):
        """
        Restore Kafka offsets from checkpoint.
        Seek consumer to the restored positions.
        """
        if not state or not self.consumer:
            return

        try:
            restored = pickle.loads(state)
            self.current_offsets = restored['offsets']

            # Seek to restored offsets
            for partition, offset in self.current_offsets.items():
                tp = TopicPartition(self.topic, partition)
                self.consumer.seek(tp, offset)

            print(f"Restored Kafka offsets: {self.current_offsets}")
        except Exception as e:
            print(f"Error restoring Kafka state: {e}")

    def commit_offsets(self):
        """
        Commit current offsets to Kafka.
        Called after checkpoint completion.
        """
        if not self.consumer:
            return

        if not TopicPartition or not OffsetAndMetadata:
            print("Kafka client not available; skipping offset commit.")
            return

        try:
            # Build offset dict for Kafka
            offsets = {}
            for partition, offset in self.current_offsets.items():
                tp = TopicPartition(self.topic, partition)
                offsets[tp] = OffsetAndMetadata(offset, "")

            if offsets:
                self.consumer.commit(offsets=offsets)
                print(f"Committed Kafka offsets: {self.current_offsets}")
        except Exception as e:
            print(f"Error committing Kafka offsets: {e}")

    def close(self):
        """Clean up Kafka consumer"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            self.consumer = None


class CollectionSourceOperator(StreamOperator):
    """
    Simple source that reads from an in-memory collection.
    Useful for testing.
    """

    def __init__(
        self,
        collection: List,
        operator_id: str = "collection_source"
    ):
        """
        Args:
            collection: List of elements to emit
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.collection = collection
        self.index = 0

    def read_records(self, max_records: int = 100) -> List[tuple]:
        """
        Read records from collection.

        Args:
            max_records: Maximum number of records to read

        Returns:
            List of tuples: (StreamRecord, partition, offset)
        """
        results = []
        count = 0

        while self.index < len(self.collection) and count < max_records:
            value = self.collection[self.index]
            record = StreamRecord(
                value=value,
                timestamp=int(time.time() * 1000)
            )
            results.append((record, 0, self.index))
            self.index += 1
            count += 1

        return results

    def snapshot_state(self) -> bytes:
        """Snapshot current index"""
        return pickle.dumps({'index': self.index})

    def restore_state(self, state: bytes):
        """Restore index"""
        if state:
            restored = pickle.loads(state)
            self.index = restored['index']

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Collection source does not process incoming elements.
        It's a source that emits records via read_records, so return an empty list.
        """
        return []
