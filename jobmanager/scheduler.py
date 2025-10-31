"""
TaskScheduler - Maps logical JobGraph to physical execution plan
Implements operator chaining and bin-packing task placement
"""
import pickle
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import JobGraph, JobVertex, EdgeType
from jobmanager.resource_manager import ResourceManager, TaskManagerInfo
from taskmanager.operators.base import OperatorChain


@dataclass
class TaskDeploymentPlan:
    """Plan for deploying a task"""
    task_id: str
    task_manager_id: str
    operator_chain: Any  # Chained or single operator (OperatorChain or individual operator)
    upstream_tasks: List[str]
    downstream_tasks: List[str]
    parallelism_index: int


class TaskScheduler:
    """
    Schedules tasks from JobGraph to TaskManagers.

    Key optimizations:
    1. Operator chaining: Fuses compatible operators to avoid serialization
    2. Bin-packing: Efficient task placement to minimize resource waste
    """

    def __init__(self, resource_manager: ResourceManager):
        """
        Args:
            resource_manager: ResourceManager instance
        """
        self.resource_manager = resource_manager

    def schedule_job(
        self,
        job_id: str,
        job_graph: JobGraph,
        checkpoint_info: Optional[dict] = None
    ) -> List[TaskDeploymentPlan]:
        """
        Create a deployment plan for a job.

        Args:
            job_id: Job identifier
            job_graph: JobGraph to schedule
            checkpoint_info: Optional checkpoint information for recovery

        Returns:
            List of TaskDeploymentPlans
        """
        # Step 1: Identify chains of operators
        chains = job_graph.identify_chainable_operators()
        print(f"Identified {len(chains)} operator chains")

        # Step 2: Create physical tasks from chains
        physical_tasks = self._create_physical_tasks(job_id, job_graph, chains)
        print(f"Created {len(physical_tasks)} physical tasks")

        # Step 3: Allocate tasks to TaskManagers using bin-packing
        deployment_plans = self._allocate_tasks(physical_tasks)
        print(f"Allocated {len(deployment_plans)} tasks to TaskManagers")

        return deployment_plans

    def _create_physical_tasks(
        self,
        job_id: str,
        job_graph: JobGraph,
        chains: List[List[str]]
    ) -> List[dict]:
        """
        Create physical tasks from operator chains.

        Args:
            job_id: Job identifier
            job_graph: JobGraph
            chains: List of operator chains

        Returns:
            List of physical task specifications
        """
        physical_tasks = []
        chain_id = 0

        for chain in chains:
            chain_id += 1

            # Get operators in the chain
            operators = [job_graph.vertices[vid].operator for vid in chain]

            # Create chained operator if more than one
            if len(operators) > 1:
                chained_operator = OperatorChain(operators)
                operator_to_deploy = chained_operator
                print(f"Chained {len(operators)} operators: {[op.__class__.__name__ for op in operators]}")
            else:
                operator_to_deploy = operators[0]

            # Determine parallelism (use max in chain)
            parallelism = max(
                job_graph.vertices[vid].parallelism
                for vid in chain
            )

            # Find upstream and downstream tasks (outside the chain)
            first_vertex = chain[0]
            last_vertex = chain[-1]

            upstream_vertices = [
                vid for vid in job_graph.get_upstream_vertices(first_vertex)
                if vid not in chain
            ]

            downstream_vertices = [
                vid for vid in job_graph.get_downstream_vertices(last_vertex)
                if vid not in chain
            ]

            # Create physical tasks with parallelism
            for i in range(parallelism):
                task_id = f"{job_id}_chain{chain_id}_parallel{i}"

                physical_tasks.append({
                    'task_id': task_id,
                    'operator': operator_to_deploy,
                    'upstream_vertices': upstream_vertices,
                    'downstream_vertices': downstream_vertices,
                    'parallelism_index': i,
                    'parallelism': parallelism,
                })

        return physical_tasks

    def _allocate_tasks(
        self,
        physical_tasks: List[dict]
    ) -> List[TaskDeploymentPlan]:
        """
        Allocate physical tasks to TaskManagers using bin-packing.

        Args:
            physical_tasks: List of physical task specifications

        Returns:
            List of TaskDeploymentPlans
        """
        deployment_plans = []

        # Get available TaskManagers sorted by available slots (descending)
        available_tms = sorted(
            self.resource_manager.get_available_task_managers(),
            key=lambda tm: tm.available_slots,
            reverse=True
        )

        if not available_tms:
            raise RuntimeError("No available TaskManagers for scheduling")

        # Bin-packing: Assign tasks to TaskManagers
        tm_index = 0

        for task_spec in physical_tasks:
            # Find TaskManager with available slot
            while tm_index < len(available_tms):
                tm = available_tms[tm_index]

                if tm.available_slots > 0:
                    # Allocate slot
                    if self.resource_manager.allocate_slot(tm.task_manager_id):
                        # Create deployment plan
                        plan = TaskDeploymentPlan(
                            task_id=task_spec['task_id'],
                            task_manager_id=tm.task_manager_id,
                            operator_chain=task_spec['operator'],
                            upstream_tasks=self._resolve_task_ids(
                                task_spec['upstream_vertices'],
                                task_spec['parallelism_index'],
                                task_spec['parallelism']
                            ),
                            downstream_tasks=self._resolve_task_ids(
                                task_spec['downstream_vertices'],
                                task_spec['parallelism_index'],
                                task_spec['parallelism']
                            ),
                            parallelism_index=task_spec['parallelism_index']
                        )

                        deployment_plans.append(plan)
                        tm.available_slots -= 1
                        break
                else:
                    tm_index += 1

            else:
                raise RuntimeError(f"No available slots for task {task_spec['task_id']}")

        return deployment_plans

    def _resolve_task_ids(
        self,
        vertex_ids: List[str],
        parallelism_index: int,
        parallelism: int
    ) -> List[str]:
        """
        Resolve vertex IDs to actual task IDs considering parallelism.
        For simplicity, we use round-robin mapping.

        Args:
            vertex_ids: List of vertex IDs
            parallelism_index: Index of current parallel instance
            parallelism: Total parallelism

        Returns:
            List of task IDs
        """
        # Simplified: Map to all parallel instances
        # In production, would consider partitioning scheme
        return [f"{vid}_parallel{parallelism_index}" for vid in vertex_ids]

    def reschedule_tasks(
        self,
        failed_task_manager_id: str,
        current_plans: List[TaskDeploymentPlan]
    ) -> List[TaskDeploymentPlan]:
        """
        Reschedule tasks from a failed TaskManager.

        Args:
            failed_task_manager_id: ID of failed TaskManager
            current_plans: Current deployment plans

        Returns:
            New deployment plans for rescheduled tasks
        """
        # Find tasks on failed TaskManager
        failed_tasks = [
            plan for plan in current_plans
            if plan.task_manager_id == failed_task_manager_id
        ]

        if not failed_tasks:
            return []

        print(f"Rescheduling {len(failed_tasks)} tasks from failed TaskManager {failed_task_manager_id}")

        # Create new plans for failed tasks
        new_plans = []
        available_tms = self.resource_manager.get_available_task_managers()

        if not available_tms:
            raise RuntimeError("No available TaskManagers for rescheduling")

        for i, failed_plan in enumerate(failed_tasks):
            # Round-robin assignment
            tm = available_tms[i % len(available_tms)]

            if self.resource_manager.allocate_slot(tm.task_manager_id):
                new_plan = TaskDeploymentPlan(
                    task_id=failed_plan.task_id,
                    task_manager_id=tm.task_manager_id,
                    operator_chain=failed_plan.operator_chain,
                    upstream_tasks=failed_plan.upstream_tasks,
                    downstream_tasks=failed_plan.downstream_tasks,
                    parallelism_index=failed_plan.parallelism_index
                )
                new_plans.append(new_plan)
            else:
                raise RuntimeError(f"Failed to allocate slot for task {failed_plan.task_id}")

        return new_plans


class ExecutionGraph:
    """
    Represents the physical execution plan with deployed tasks.
    """

    def __init__(self, job_id: str, deployment_plans: List[TaskDeploymentPlan]):
        """
        Args:
            job_id: Job identifier
            deployment_plans: List of deployment plans
        """
        self.job_id = job_id
        self.deployment_plans = deployment_plans

        # Build task lookup
        self.tasks: Dict[str, TaskDeploymentPlan] = {
            plan.task_id: plan for plan in deployment_plans
        }

        # Build TaskManager mapping
        self.task_manager_tasks: Dict[str, List[str]] = {}
        for plan in deployment_plans:
            if plan.task_manager_id not in self.task_manager_tasks:
                self.task_manager_tasks[plan.task_manager_id] = []
            self.task_manager_tasks[plan.task_manager_id].append(plan.task_id)

    def get_tasks_on_task_manager(self, task_manager_id: str) -> List[str]:
        """Get tasks running on a specific TaskManager"""
        return self.task_manager_tasks.get(task_manager_id, [])

    def get_all_task_ids(self) -> List[str]:
        """Get all task IDs"""
        return list(self.tasks.keys())

    def get_deployment_plan(self, task_id: str) -> Optional[TaskDeploymentPlan]:
        """Get deployment plan for a task"""
        return self.tasks.get(task_id)
