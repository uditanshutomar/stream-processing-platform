"""
ResourceManager - Manages TaskManager resources and health
"""
import threading
import time
import pickle
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.config import Config
from jobmanager.grpc_client import TaskManagerClient, TaskManagerClientPool


class TaskManagerStatus(Enum):
    """Status of a TaskManager"""
    REGISTERED = "registered"
    ACTIVE = "active"
    LOST = "lost"
    DEAD = "dead"


@dataclass
class TaskManagerInfo:
    """Information about a registered TaskManager"""
    task_manager_id: str
    host: str
    port: int
    task_slots: int
    available_slots: int
    last_heartbeat: float
    status: TaskManagerStatus = TaskManagerStatus.REGISTERED

    def is_healthy(self, timeout_ms: int = Config.HEARTBEAT_TIMEOUT) -> bool:
        """Check if TaskManager is healthy based on heartbeat"""
        elapsed_ms = (time.time() - self.last_heartbeat) * 1000
        return elapsed_ms < timeout_ms


class ResourceManager:
    """
    Manages TaskManager resources and monitors health.
    Maintains inventory of available task slots and detects failures.
    """

    def __init__(self, heartbeat_timeout_ms: int = Config.HEARTBEAT_TIMEOUT):
        """
        Args:
            heartbeat_timeout_ms: Heartbeat timeout in milliseconds
        """
        self.heartbeat_timeout_ms = heartbeat_timeout_ms

        # TaskManager registry
        self.task_managers: Dict[str, TaskManagerInfo] = {}
        self.lock = threading.Lock()

        # Monitoring thread
        self.monitoring_thread: Optional[threading.Thread] = None
        self.running = False

        # Callbacks for failures
        self.failure_callbacks: List[callable] = []

        # gRPC client pool for TaskManager communication
        self.client_pool = TaskManagerClientPool()

    def start(self):
        """Start resource manager"""
        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitoring_thread.start()
        print("ResourceManager started")

    def stop(self):
        """Stop resource manager"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        # Close all gRPC connections
        self.client_pool.close_all()
        print("ResourceManager stopped")

    def register_task_manager(
        self,
        task_manager_id: str,
        host: str,
        port: int,
        task_slots: int
    ) -> bool:
        """
        Register a new TaskManager.

        Args:
            task_manager_id: Unique TaskManager identifier
            host: TaskManager host
            port: TaskManager RPC port
            task_slots: Number of task slots

        Returns:
            True if registration successful
        """
        with self.lock:
            if task_manager_id in self.task_managers:
                print(f"TaskManager {task_manager_id} already registered")
                return False

            info = TaskManagerInfo(
                task_manager_id=task_manager_id,
                host=host,
                port=port,
                task_slots=task_slots,
                available_slots=task_slots,
                last_heartbeat=time.time(),
                status=TaskManagerStatus.REGISTERED
            )

            self.task_managers[task_manager_id] = info
            print(f"Registered TaskManager {task_manager_id} with {task_slots} slots")
            return True

    def unregister_task_manager(self, task_manager_id: str) -> bool:
        """
        Unregister a TaskManager.

        Args:
            task_manager_id: TaskManager identifier

        Returns:
            True if unregistration successful
        """
        with self.lock:
            if task_manager_id not in self.task_managers:
                return False

            del self.task_managers[task_manager_id]
            print(f"Unregistered TaskManager {task_manager_id}")
            return True

    def update_heartbeat(
        self,
        task_manager_id: str,
        available_slots: int
    ) -> bool:
        """
        Update heartbeat from a TaskManager.

        Args:
            task_manager_id: TaskManager identifier
            available_slots: Number of available task slots

        Returns:
            True if update successful
        """
        with self.lock:
            if task_manager_id not in self.task_managers:
                print(f"TaskManager {task_manager_id} not registered")
                return False

            info = self.task_managers[task_manager_id]
            info.last_heartbeat = time.time()
            info.available_slots = available_slots
            info.status = TaskManagerStatus.ACTIVE

            return True

    def allocate_slot(self, task_manager_id: str) -> bool:
        """
        Allocate a task slot on a TaskManager.

        Args:
            task_manager_id: TaskManager identifier

        Returns:
            True if allocation successful
        """
        with self.lock:
            if task_manager_id not in self.task_managers:
                return False

            info = self.task_managers[task_manager_id]
            if info.available_slots <= 0:
                return False

            info.available_slots -= 1
            return True

    def release_slot(self, task_manager_id: str) -> bool:
        """
        Release a task slot on a TaskManager.

        Args:
            task_manager_id: TaskManager identifier

        Returns:
            True if release successful
        """
        with self.lock:
            if task_manager_id not in self.task_managers:
                return False

            info = self.task_managers[task_manager_id]
            if info.available_slots >= info.task_slots:
                return False

            info.available_slots += 1
            return True

    def get_available_task_managers(self) -> List[TaskManagerInfo]:
        """
        Get TaskManagers with available slots.

        Returns:
            List of TaskManagerInfo with available slots
        """
        with self.lock:
            return [
                info for info in self.task_managers.values()
                if info.available_slots > 0 and info.is_healthy(self.heartbeat_timeout_ms)
            ]

    def get_task_manager(self, task_manager_id: str) -> Optional[TaskManagerInfo]:
        """
        Get TaskManager info.

        Args:
            task_manager_id: TaskManager identifier

        Returns:
            TaskManagerInfo or None
        """
        with self.lock:
            return self.task_managers.get(task_manager_id)

    def get_all_task_managers(self) -> List[TaskManagerInfo]:
        """
        Get all registered TaskManagers.

        Returns:
            List of TaskManagerInfo
        """
        with self.lock:
            return list(self.task_managers.values())

    def get_total_slots(self) -> int:
        """Get total number of slots across all TaskManagers"""
        with self.lock:
            return sum(info.task_slots for info in self.task_managers.values())

    def get_available_slots(self) -> int:
        """Get total available slots across all TaskManagers"""
        with self.lock:
            return sum(
                info.available_slots
                for info in self.task_managers.values()
                if info.is_healthy(self.heartbeat_timeout_ms)
            )

    def deploy_task_via_grpc(
        self,
        task_manager_id: str,
        task_id: str,
        operator,
        upstream_tasks: List[str],
        downstream_tasks: List[str],
        checkpoint_path: str = "",
        checkpoint_id: int = 0
    ) -> tuple:
        """
        Deploy a task to a TaskManager using gRPC.
        
        Args:
            task_manager_id: Target TaskManager ID
            task_id: Unique task identifier
            operator: Operator to deploy (will be pickled)
            upstream_tasks: List of upstream task IDs
            downstream_tasks: List of downstream task IDs
            checkpoint_path: Optional checkpoint path for recovery
            checkpoint_id: Optional checkpoint ID for recovery
            
        Returns:
            Tuple of (success, message)
        """
        tm_info = self.get_task_manager(task_manager_id)
        if not tm_info:
            return False, f"TaskManager {task_manager_id} not found"

        try:
            # Get or create gRPC client
            client = self.client_pool.get_client(
                task_manager_id,
                tm_info.host,
                tm_info.port
            )

            # Serialize operator
            serialized_operator = pickle.dumps(operator)

            # Deploy via gRPC
            success, message = client.deploy_task(
                task_id=task_id,
                serialized_operator=serialized_operator,
                upstream_tasks=upstream_tasks,
                downstream_tasks=downstream_tasks,
                checkpoint_path=checkpoint_path,
                checkpoint_id=checkpoint_id
            )

            if success:
                print(f"Deployed task {task_id} to {task_manager_id} via gRPC")
            else:
                print(f"Failed to deploy task {task_id}: {message}")

            return success, message

        except Exception as e:
            return False, f"gRPC deployment error: {str(e)}"

    def register_failure_callback(self, callback: callable):
        """
        Register a callback for TaskManager failures.

        Args:
            callback: Function to call with task_manager_id when failure detected
        """
        self.failure_callbacks.append(callback)

    def _monitoring_loop(self):
        """Monitor TaskManager health"""
        while self.running:
            self._check_health()
            time.sleep(Config.HEARTBEAT_INTERVAL / 1000.0)

    def _check_health(self):
        """Check health of all TaskManagers"""
        failed_task_managers = []

        with self.lock:
            for task_manager_id, info in self.task_managers.items():
                if not info.is_healthy(self.heartbeat_timeout_ms):
                    if info.status != TaskManagerStatus.LOST:
                        print(f"TaskManager {task_manager_id} lost (missed heartbeat)")
                        info.status = TaskManagerStatus.LOST
                        failed_task_managers.append(task_manager_id)

        # Notify callbacks outside of lock
        for task_manager_id in failed_task_managers:
            for callback in self.failure_callbacks:
                try:
                    callback(task_manager_id)
                except Exception as e:
                    print(f"Error in failure callback: {e}")

    def get_statistics(self) -> dict:
        """
        Get resource statistics.

        Returns:
            Dictionary with statistics
        """
        with self.lock:
            active_count = sum(
                1 for info in self.task_managers.values()
                if info.status == TaskManagerStatus.ACTIVE
            )
            
            # Calculate inline to avoid deadlock (don't call methods that also acquire lock)
            total_slots = sum(info.task_slots for info in self.task_managers.values())
            available_slots = sum(
                info.available_slots
                for info in self.task_managers.values()
                if info.is_healthy(self.heartbeat_timeout_ms)
            )

            return {
                'total_task_managers': len(self.task_managers),
                'active_task_managers': active_count,
                'total_slots': total_slots,
                'available_slots': available_slots,
                'utilization': 1.0 - (available_slots / max(total_slots, 1)),
            }
