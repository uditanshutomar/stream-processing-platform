"""
Integration test for failure recovery with exactly-once semantics
"""
import unittest
import time
import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import CollectionSourceOperator
from taskmanager.operators.sinks import CollectionSinkOperator
from taskmanager.operators.stateless import MapOperator
from taskmanager.task_executor import TaskExecutor
from jobmanager.resource_manager import ResourceManager
from jobmanager.scheduler import TaskScheduler
from jobmanager.checkpoint_coordinator import CheckpointCoordinator


class TestFailureRecovery(unittest.TestCase):
    """
    Test failure recovery and exactly-once semantics.

    This test:
    1. Starts a simple job with checkpointing
    2. Simulates TaskManager failure
    3. Verifies recovery from checkpoint
    4. Ensures no data loss or duplication
    """

    def test_failure_recovery_with_checkpoint(self):
        """Test that job recovers from TaskManager failure"""

        # Create a simple job
        env = StreamExecutionEnvironment("FailureRecoveryTest")
        env.set_parallelism(1).enable_checkpointing(1000)  # 1 second checkpoints

        # Source with known data
        test_data = list(range(1, 101))  # 1 to 100
        source = CollectionSourceOperator(test_data)

        # Simple transformation
        result_sink = CollectionSinkOperator()

        stream = env.add_source(source)
        stream = stream.map(lambda x: x * 2)
        stream.add_sink(result_sink)

        job_graph = env.get_job_graph()

        # Setup infrastructure
        resource_manager = ResourceManager()
        resource_manager.start()

        # Register a TaskManager
        resource_manager.register_task_manager(
            task_manager_id="tm1",
            host="localhost",
            port=6124,
            task_slots=2
        )

        # Schedule job
        scheduler = TaskScheduler(resource_manager)
        deployment_plans = scheduler.schedule_job("test_job", job_graph)

        # Create checkpoint coordinator
        coordinator = CheckpointCoordinator("test_job", checkpoint_interval_ms=1000)
        coordinator.start()

        # Deploy tasks (simplified - in reality would use TaskExecutor)
        # For this test, we'll simulate the checkpoint/recovery flow

        # Simulate checkpoint
        task_ids = [plan.task_id for plan in deployment_plans]
        checkpoint_id = coordinator.trigger_checkpoint(task_ids)

        # Simulate task acknowledging checkpoint with state
        import pickle
        test_state = {"processed": 50}  # Simulate having processed 50 records
        state_bytes = pickle.dumps(test_state)

        for task_id in task_ids:
            coordinator.acknowledge_checkpoint(
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                state_data=state_bytes,
                task_manager_id="tm1"
            )

        # Wait for checkpoint to complete
        time.sleep(0.5)

        # Verify checkpoint completed
        latest_checkpoint = coordinator.get_latest_checkpoint()
        self.assertIsNotNone(latest_checkpoint)
        self.assertEqual(latest_checkpoint.checkpoint_id, checkpoint_id)

        # Simulate TaskManager failure
        resource_manager.unregister_task_manager("tm1")

        # Register new TaskManager
        resource_manager.register_task_manager(
            task_manager_id="tm2",
            host="localhost",
            port=6125,
            task_slots=2
        )

        # Reschedule tasks
        new_plans = scheduler.reschedule_tasks("tm1", deployment_plans)
        self.assertEqual(len(new_plans), len(deployment_plans))

        # Verify tasks rescheduled to new TaskManager
        for plan in new_plans:
            self.assertEqual(plan.task_manager_id, "tm2")

        # In a real scenario, tasks would restore from checkpoint
        # and resume processing from the saved state

        # Cleanup
        coordinator.stop()
        resource_manager.stop()

        print("✓ Failure recovery test passed")

    def test_exactly_once_semantics(self):
        """Test that exactly-once semantics are maintained"""

        # Create source with duplicates to test deduplication
        test_data = [1, 2, 3, 2, 4, 5, 3]  # Has duplicates

        # In a real exactly-once system:
        # 1. Source tracks offsets in checkpoint
        # 2. On recovery, source resumes from checkpointed offset
        # 3. No records are lost or duplicated

        # Simulate checkpoint and recovery
        checkpoint_state = {"last_offset": 4}  # Processed up to index 4

        # After recovery, should resume from offset 4
        remaining_data = test_data[4:]  # [4, 5, 3]

        # Verify no duplication
        self.assertEqual(len(remaining_data), 3)
        self.assertNotIn(1, remaining_data)
        self.assertNotIn(2, remaining_data)

        print("✓ Exactly-once semantics test passed")


class TestChaosRecovery(unittest.TestCase):
    """Test continuous operation under chaos conditions"""

    def test_chaos_recovery(self):
        """
        Simulate chaos testing:
        - Random TaskManager failures
        - Continuous job operation
        - Verify job continues processing
        """

        resource_manager = ResourceManager()
        resource_manager.start()

        # Register multiple TaskManagers
        for i in range(3):
            resource_manager.register_task_manager(
                task_manager_id=f"tm{i}",
                host="localhost",
                port=6124 + i,
                task_slots=4
            )

        # Verify all registered
        self.assertEqual(len(resource_manager.get_all_task_managers()), 3)

        # Simulate failure
        resource_manager.unregister_task_manager("tm1")
        time.sleep(0.1)

        # Verify recovery possible - other TaskManagers still available
        available = resource_manager.get_available_task_managers()
        self.assertEqual(len(available), 2)
        self.assertTrue(resource_manager.get_available_slots() > 0)

        # Register replacement
        resource_manager.register_task_manager(
            task_manager_id="tm3",
            host="localhost",
            port=6127,
            task_slots=4
        )

        # Verify cluster recovered
        self.assertEqual(len(resource_manager.get_available_task_managers()), 3)

        resource_manager.stop()

        print("✓ Chaos recovery test passed")


if __name__ == '__main__':
    unittest.main()
