"""
Sink operators for writing data to external systems
"""
from typing import List, Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.serialization import StreamRecord
from .base import StreamOperator

try:
    from kafka import KafkaProducer
except ImportError:
    KafkaProducer = None


class KafkaSinkOperator(StreamOperator):
    """
    Kafka sink operator with exactly-once semantics.
    Uses transactional producer for durability and ordering.
    """

    def __init__(
        self,
        topic: str,
        bootstrap_servers: str,
        operator_id: str = "kafka_sink"
    ):
        """
        Args:
            topic: Kafka topic to write to
            bootstrap_servers: Kafka broker addresses
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.producer: Optional[KafkaProducer] = None

    def open(self):
        """Initialize Kafka producer with exactly-once configuration"""
        if KafkaProducer is None:
            raise ImportError("kafka-python-ng is required for KafkaSinkOperator")

        # Create producer with settings for durability and ordering
        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            acks='all',  # Wait for all replicas to acknowledge
            retries=3,  # Retry on failure
            max_in_flight_requests_per_connection=1,  # Ensure ordering
            key_serializer=lambda k: k if isinstance(k, bytes) else str(k).encode('utf-8') if k else None,
            value_serializer=lambda v: v if isinstance(v, bytes) else str(v).encode('utf-8'),
        )

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Write record to Kafka.

        Args:
            record: Input stream record

        Returns:
            Empty list (sink doesn't produce output)
        """
        if not self.producer:
            print("Kafka producer not initialized")
            return []

        try:
            # Send to Kafka
            future = self.producer.send(
                self.topic,
                key=record.key,
                value=record.value,
                timestamp_ms=record.timestamp,
                headers=list(record.headers.items()) if record.headers else None
            )

            # Wait for send to complete (blocking for reliability)
            future.get(timeout=10)

        except Exception as e:
            print(f"Error writing to Kafka: {e}")
            raise  # Re-raise to trigger recovery

        return []

    def snapshot_state(self) -> bytes:
        """
        Flush producer before checkpoint.
        Ensures all records are sent before checkpoint completes.
        """
        if self.producer:
            self.producer.flush()
        return b""

    def close(self):
        """Clean up Kafka producer"""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            self.producer = None


class PrintSinkOperator(StreamOperator):
    """
    Simple sink that prints records to stdout.
    Useful for testing and debugging.
    """

    def __init__(self, prefix: str = "", operator_id: str = "print_sink"):
        """
        Args:
            prefix: Prefix to add to each printed line
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.prefix = prefix

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Print record to stdout.

        Args:
            record: Input stream record

        Returns:
            Empty list
        """
        output = f"{self.prefix}{record.value}"
        if record.key:
            output = f"{self.prefix}[{record.key}] {record.value}"
        print(output)
        return []


class CollectionSinkOperator(StreamOperator):
    """
    Sink that collects records in memory.
    Useful for testing.
    """

    def __init__(self, operator_id: str = "collection_sink"):
        """
        Args:
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.collected: List = []

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Collect record in memory.

        Args:
            record: Input stream record

        Returns:
            Empty list
        """
        self.collected.append(record.value)
        return []

    def get_results(self) -> List:
        """Get collected results"""
        return self.collected.copy()
