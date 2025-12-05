"""
gRPC Client for JobManager to communicate with TaskManagers
"""
import grpc
import pickle
from typing import Optional, List, Dict
from concurrent import futures
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.protobuf import stream_processing_pb2
from common.protobuf import stream_processing_pb2_grpc


class TaskManagerClient:
    """
    gRPC client for communicating with TaskManagers.
    Provides methods for task deployment, cancellation, and monitoring.
    """

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        """
        Args:
            host: TaskManager hostname
            port: TaskManager gRPC port
            timeout: Default timeout for RPC calls in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.channel = None
        self.stub = None

    def connect(self) -> bool:
        """
        Establish connection to TaskManager.
        
        Returns:
            True if connection successful
        """
        try:
            target = f"{self.host}:{self.port}"
            self.channel = grpc.insecure_channel(target)
            self.stub = stream_processing_pb2_grpc.TaskManagerServiceStub(self.channel)
            
            # Test connection with a short timeout
            grpc.channel_ready_future(self.channel).result(timeout=5)
            print(f"Connected to TaskManager at {target}")
            return True
            
        except Exception as e:
            print(f"Failed to connect to TaskManager at {self.host}:{self.port}: {e}")
            return False

    def close(self):
        """Close the gRPC channel"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None

    def deploy_task(
        self,
        task_id: str,
        serialized_operator: bytes,
        upstream_tasks: List[str],
        downstream_tasks: List[str],
        parallelism: int = 1,
        checkpoint_path: str = "",
        checkpoint_id: int = 0
    ) -> tuple[bool, str]:
        """
        Deploy a task to the TaskManager.
        
        Args:
            task_id: Unique task identifier
            serialized_operator: Pickled operator
            upstream_tasks: List of upstream task IDs
            downstream_tasks: List of downstream task IDs
            parallelism: Task parallelism
            checkpoint_path: Optional checkpoint path for recovery
            checkpoint_id: Optional checkpoint ID for recovery
            
        Returns:
            Tuple of (success, message)
        """
        if not self.stub:
            return False, "Not connected"

        try:
            task_deployment = stream_processing_pb2.TaskDeployment(
                task_id=task_id,
                serialized_operator=serialized_operator,
                upstream_tasks=upstream_tasks,
                downstream_tasks=downstream_tasks,
                parallelism=parallelism,
                checkpoint_path=checkpoint_path,
                checkpoint_id=checkpoint_id
            )

            request = stream_processing_pb2.DeployTaskRequest(
                task_deployment=task_deployment
            )

            response = self.stub.DeployTask(request, timeout=self.timeout)
            return response.success, response.message

        except grpc.RpcError as e:
            return False, f"RPC error: {e.code()} - {e.details()}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.
        
        Args:
            task_id: Task to cancel
            
        Returns:
            True if cancellation successful
        """
        if not self.stub:
            return False

        try:
            request = stream_processing_pb2.CancelTaskRequest(task_id=task_id)
            response = self.stub.CancelTask(request, timeout=self.timeout)
            return response.success

        except Exception as e:
            print(f"Error canceling task: {e}")
            return False

    def get_metrics(self, task_id: str) -> Optional[Dict]:
        """
        Get metrics for a specific task.
        
        Args:
            task_id: Task to get metrics for
            
        Returns:
            Dictionary of metrics or None
        """
        if not self.stub:
            return None

        try:
            request = stream_processing_pb2.GetMetricsRequest(task_id=task_id)
            response = self.stub.GetMetrics(request, timeout=self.timeout)
            
            if response.metrics:
                return {
                    'task_id': response.metrics.task_id,
                    'records_processed': response.metrics.records_processed,
                    'processing_latency_ms': response.metrics.processing_latency_ms,
                    'backpressure_ratio': response.metrics.backpressure_ratio,
                    'checkpoint_duration_ms': response.metrics.checkpoint_duration_ms
                }
            return None

        except Exception as e:
            print(f"Error getting metrics: {e}")
            return None

    def heartbeat(
        self,
        task_manager_id: str,
        available_slots: int,
        task_metrics: List[Dict] = None
    ) -> bool:
        """
        Send heartbeat to TaskManager (or receive acknowledgment).
        
        Args:
            task_manager_id: TaskManager ID
            available_slots: Number of available slots
            task_metrics: List of task metrics dictionaries
            
        Returns:
            True if heartbeat acknowledged
        """
        if not self.stub:
            return False

        try:
            metrics = []
            if task_metrics:
                for m in task_metrics:
                    metrics.append(stream_processing_pb2.TaskMetrics(
                        task_id=m.get('task_id', ''),
                        records_processed=m.get('records_processed', 0),
                        processing_latency_ms=m.get('processing_latency_ms', 0.0),
                        backpressure_ratio=m.get('backpressure_ratio', 0.0),
                        checkpoint_duration_ms=m.get('checkpoint_duration_ms', 0)
                    ))

            request = stream_processing_pb2.HeartbeatRequest(
                task_manager_id=task_manager_id,
                available_slots=available_slots,
                metrics=metrics
            )

            response = self.stub.Heartbeat(request, timeout=self.timeout)
            return response.acknowledged

        except Exception as e:
            print(f"Heartbeat failed: {e}")
            return False


class TaskManagerClientPool:
    """
    Pool of gRPC clients for multiple TaskManagers.
    """

    def __init__(self):
        self.clients: Dict[str, TaskManagerClient] = {}

    def get_client(self, task_manager_id: str, host: str, port: int) -> TaskManagerClient:
        """
        Get or create a client for a TaskManager.
        
        Args:
            task_manager_id: TaskManager identifier
            host: TaskManager hostname
            port: TaskManager gRPC port
            
        Returns:
            TaskManagerClient instance
        """
        if task_manager_id not in self.clients:
            client = TaskManagerClient(host, port)
            if client.connect():
                self.clients[task_manager_id] = client
            else:
                raise RuntimeError(f"Failed to connect to TaskManager {task_manager_id}")

        return self.clients[task_manager_id]

    def close_all(self):
        """Close all client connections"""
        for client in self.clients.values():
            client.close()
        self.clients.clear()
