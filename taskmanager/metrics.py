"""
Metrics collection using Prometheus client
"""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, start_http_server
import time
from typing import Dict, Optional
import threading


class TaskMetrics:
    """
    Metrics for a task execution.
    """

    def __init__(self, task_id: str, operator_id: str, registry: Optional[CollectorRegistry] = None):
        """
        Args:
            task_id: Task identifier
            operator_id: Operator identifier
            registry: Prometheus registry (None for default)
        """
        self.task_id = task_id
        self.operator_id = operator_id
        self.registry = registry

        # Records processed counter
        self.records_processed = Counter(
            'records_processed_total',
            'Total number of records processed',
            ['task', 'operator'],
            registry=registry
        )

        # Processing latency histogram
        self.processing_latency = Histogram(
            'processing_latency_seconds',
            'Processing latency in seconds',
            ['operator'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=registry
        )

        # Checkpoint duration histogram
        self.checkpoint_duration = Histogram(
            'checkpoint_duration_seconds',
            'Checkpoint duration in seconds',
            ['job'],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=registry
        )

        # Backpressure gauge
        self.backpressure_ratio = Gauge(
            'backpressure_ratio',
            'Backpressure ratio (0.0 to 1.0)',
            ['task'],
            registry=registry
        )

        # Watermark lag gauge
        self.watermark_lag = Gauge(
            'watermark_lag_ms',
            'Watermark lag in milliseconds',
            ['task'],
            registry=registry
        )

        # State size gauge
        self.state_size_bytes = Gauge(
            'state_size_bytes',
            'State size in bytes',
            ['task', 'operator'],
            registry=registry
        )

        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Local values for gRPC retrieval
        self._records_processed_val = 0
        self._processing_latency_val = 0.0
        self._backpressure_ratio_val = 0.0
        self._checkpoint_duration_val = 0
        self._state_size_val = 0

    def record_processed(self):
        """Record a processed record"""
        with self.lock:
            self._records_processed_val += 1
            
        self.records_processed.labels(
            task=self.task_id,
            operator=self.operator_id
        ).inc()

    def observe_latency(self, latency_seconds: float):
        """
        Record processing latency.

        Args:
            latency_seconds: Latency in seconds
        """
        with self.lock:
            # Simple moving average
            alpha = 0.1
            self._processing_latency_val = (
                alpha * (latency_seconds * 1000) + (1 - alpha) * self._processing_latency_val
            )

        self.processing_latency.labels(
            operator=self.operator_id
        ).observe(latency_seconds)

    def observe_checkpoint_duration(self, duration_seconds: float, job_id: str):
        """
        Record checkpoint duration.

        Args:
            duration_seconds: Duration in seconds
            job_id: Job identifier
        """
        with self.lock:
            self._checkpoint_duration_val = int(duration_seconds * 1000)

        self.checkpoint_duration.labels(
            job=job_id
        ).observe(duration_seconds)

    def set_backpressure(self, ratio: float):
        """
        Set backpressure ratio.

        Args:
            ratio: Backpressure ratio (0.0 to 1.0)
        """
        with self.lock:
            self._backpressure_ratio_val = ratio

        self.backpressure_ratio.labels(
            task=self.task_id
        ).set(ratio)

    def set_watermark_lag(self, lag_ms: int):
        """
        Set watermark lag.

        Args:
            lag_ms: Lag in milliseconds
        """
        self.watermark_lag.labels(
            task=self.task_id
        ).set(lag_ms)

    def set_state_size(self, size_bytes: int):
        """
        Set state size.

        Args:
            size_bytes: Size in bytes
        """
        with self.lock:
            self._state_size_val = size_bytes

        self.state_size_bytes.labels(
            task=self.task_id,
            operator=self.operator_id
        ).set(size_bytes)

    def get_metrics_dict(self) -> Dict:
        """Get current metrics as dictionary"""
        with self.lock:
            return {
                'records_processed': self._records_processed_val,
                'processing_latency_ms': self._processing_latency_val,
                'backpressure_ratio': self._backpressure_ratio_val,
                'checkpoint_duration_ms': self._checkpoint_duration_val,
                'state_size_bytes': self._state_size_val
            }


class MetricsServer:
    """
    Prometheus metrics HTTP server.
    """

    def __init__(self, port: int = 9090):
        """
        Args:
            port: Port to serve metrics on
        """
        self.port = port
        self.server = None

    def start(self):
        """Start metrics server"""
        try:
            start_http_server(self.port)
            print(f"Metrics server started on port {self.port}")
        except Exception as e:
            print(f"Failed to start metrics server: {e}")

    def stop(self):
        """Stop metrics server"""
        # Prometheus client doesn't provide a stop method
        # The server runs in a daemon thread
        pass


class AggregatedMetrics:
    """
    Aggregated metrics across multiple tasks.
    """

    def __init__(self):
        """Initialize aggregated metrics"""
        self.task_metrics: Dict[str, Dict] = {}
        self.lock = threading.Lock()

    def update_task_metrics(
        self,
        task_id: str,
        records_processed: int = 0,
        avg_latency_ms: float = 0.0,
        backpressure_ratio: float = 0.0
    ):
        """
        Update metrics for a task.

        Args:
            task_id: Task identifier
            records_processed: Number of records processed
            avg_latency_ms: Average processing latency in milliseconds
            backpressure_ratio: Backpressure ratio
        """
        with self.lock:
            if task_id not in self.task_metrics:
                self.task_metrics[task_id] = {
                    'records_processed': 0,
                    'avg_latency_ms': 0.0,
                    'backpressure_ratio': 0.0,
                }

            metrics = self.task_metrics[task_id]
            metrics['records_processed'] += records_processed
            # Exponential moving average for latency
            alpha = 0.3
            metrics['avg_latency_ms'] = (
                alpha * avg_latency_ms + (1 - alpha) * metrics['avg_latency_ms']
            )
            metrics['backpressure_ratio'] = backpressure_ratio

    def get_task_metrics(self, task_id: str) -> Optional[Dict]:
        """
        Get metrics for a task.

        Args:
            task_id: Task identifier

        Returns:
            Metrics dictionary or None
        """
        with self.lock:
            return self.task_metrics.get(task_id, {}).copy()

    def get_all_metrics(self) -> Dict[str, Dict]:
        """
        Get all task metrics.

        Returns:
            Dictionary of task metrics
        """
        with self.lock:
            return {
                task_id: metrics.copy()
                for task_id, metrics in self.task_metrics.items()
            }

    def get_throughput(self) -> float:
        """
        Calculate overall throughput (records/second).

        Returns:
            Throughput
        """
        with self.lock:
            total_records = sum(
                metrics['records_processed']
                for metrics in self.task_metrics.values()
            )
            # This is cumulative; for rate, we'd need time tracking
            return float(total_records)

    def get_avg_latency(self) -> float:
        """
        Calculate average latency across all tasks.

        Returns:
            Average latency in milliseconds
        """
        with self.lock:
            if not self.task_metrics:
                return 0.0

            latencies = [
                metrics['avg_latency_ms']
                for metrics in self.task_metrics.values()
            ]
            return sum(latencies) / len(latencies)

    def get_max_backpressure(self) -> float:
        """
        Get maximum backpressure across all tasks.

        Returns:
            Maximum backpressure ratio
        """
        with self.lock:
            if not self.task_metrics:
                return 0.0

            ratios = [
                metrics['backpressure_ratio']
                for metrics in self.task_metrics.values()
            ]
            return max(ratios)
