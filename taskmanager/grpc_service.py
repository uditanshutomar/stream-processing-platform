"""
gRPC Service Implementation for TaskManager
Implements the TaskManagerService defined in stream_processing.proto
"""
import grpc
import pickle
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.protobuf import stream_processing_pb2
from common.protobuf import stream_processing_pb2_grpc


class TaskManagerServiceImpl(stream_processing_pb2_grpc.TaskManagerServiceServicer):
    """
    gRPC service implementation for TaskManager.
    Handles task deployment, cancellation, metrics, and heartbeats.
    """

    def __init__(self, task_executor):
        """
        Args:
            task_executor: TaskExecutor instance that manages task execution
        """
        self.task_executor = task_executor

    def DeployTask(self, request, context):
        """
        Deploy a new task to this TaskManager.
        
        Args:
            request: DeployTaskRequest with task deployment info
            context: gRPC context
            
        Returns:
            DeployTaskResponse with success status
        """
        try:
            task_deployment = request.task_deployment
            
            success = self.task_executor.deploy_task(
                task_id=task_deployment.task_id,
                serialized_operator=task_deployment.serialized_operator,
                upstream_tasks=list(task_deployment.upstream_tasks),
                downstream_tasks=list(task_deployment.downstream_tasks),
                checkpoint_path=task_deployment.checkpoint_path if task_deployment.checkpoint_path else None,
                checkpoint_id=task_deployment.checkpoint_id if task_deployment.checkpoint_id > 0 else None
            )
            
            if success:
                return stream_processing_pb2.DeployTaskResponse(
                    success=True,
                    message=f"Task {task_deployment.task_id} deployed successfully"
                )
            else:
                return stream_processing_pb2.DeployTaskResponse(
                    success=False,
                    message=f"Failed to deploy task {task_deployment.task_id}: no available slots"
                )
                
        except Exception as e:
            return stream_processing_pb2.DeployTaskResponse(
                success=False,
                message=f"Error deploying task: {str(e)}"
            )

    def CancelTask(self, request, context):
        """
        Cancel a running task.
        
        Args:
            request: CancelTaskRequest with task_id
            context: gRPC context
            
        Returns:
            CancelTaskResponse with success status
        """
        try:
            task_id = request.task_id
            
            if task_id in self.task_executor.tasks:
                self.task_executor.tasks[task_id].stop()
                del self.task_executor.tasks[task_id]
                self.task_executor.available_slots += 1
                
                return stream_processing_pb2.CancelTaskResponse(success=True)
            else:
                return stream_processing_pb2.CancelTaskResponse(success=False)
                
        except Exception as e:
            print(f"Error canceling task: {e}")
            return stream_processing_pb2.CancelTaskResponse(success=False)

    def GetMetrics(self, request, context):
        """
        Get metrics for a specific task.
        
        Args:
            request: GetMetricsRequest with task_id
            context: gRPC context
            
        Returns:
            GetMetricsResponse with TaskMetrics
        """
        try:
            task_id = request.task_id
            
            if task_id in self.task_executor.tasks:
                task = self.task_executor.tasks[task_id]
                metrics_dict = task.metrics.get_metrics_dict()
                
                return stream_processing_pb2.GetMetricsResponse(
                    metrics=stream_processing_pb2.TaskMetrics(
                        task_id=task_id,
                        records_processed=metrics_dict['records_processed'],
                        processing_latency_ms=metrics_dict['processing_latency_ms'],
                        backpressure_ratio=metrics_dict['backpressure_ratio'],
                        checkpoint_duration_ms=metrics_dict['checkpoint_duration_ms']
                    )
                )
            else:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Task {task_id} not found")
                return stream_processing_pb2.GetMetricsResponse()
                
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return stream_processing_pb2.GetMetricsResponse()

    def Heartbeat(self, request, context):
        """
        Handle heartbeat from JobManager or respond with status.
        
        Args:
            request: HeartbeatRequest with TaskManager status
            context: gRPC context
            
        Returns:
            HeartbeatResponse
        """
        try:
            # Log heartbeat reception
            print(f"Received heartbeat from {request.task_manager_id}, slots: {request.available_slots}")
            
            return stream_processing_pb2.HeartbeatResponse(acknowledged=True)
            
        except Exception as e:
            print(f"Error processing heartbeat: {e}")
            return stream_processing_pb2.HeartbeatResponse(acknowledged=False)
