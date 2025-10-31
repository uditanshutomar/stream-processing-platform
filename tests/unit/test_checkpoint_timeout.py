"""
Unit tests for checkpoint timeout handling
"""
import unittest
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from jobmanager.checkpoint_coordinator import CheckpointCoordinator, CheckpointStatus


class TestCheckpointTimeout(unittest.TestCase):
    """Test checkpoint timeout functionality"""

    def test_checkpoint_timeout_cleanup(self):
        """Test that timed out checkpoints are cleaned up"""
        # Create coordinator with short timeout (1 second)
        # Use short interval so timeout check runs frequently
        coordinator = CheckpointCoordinator(
            job_id="test_timeout_job",
            checkpoint_interval_ms=500,  # Check every 500ms
            checkpoint_timeout_ms=1000  # 1 second timeout
        )
        coordinator.start()

        # Trigger a checkpoint
        task_ids = ["task1", "task2", "task3"]
        checkpoint_id = coordinator.trigger_checkpoint(task_ids)

        # Verify checkpoint is pending
        self.assertIn(checkpoint_id, coordinator.pending_checkpoints)
        self.assertIn(checkpoint_id, coordinator.pending_acks)
        self.assertEqual(len(coordinator.pending_acks[checkpoint_id]), 3)

        # Wait for timeout (2 seconds to ensure check runs)
        time.sleep(2.0)

        # Verify checkpoint was cleaned up
        self.assertNotIn(checkpoint_id, coordinator.pending_checkpoints)
        self.assertNotIn(checkpoint_id, coordinator.pending_acks)
        self.assertEqual(len(coordinator.completed_checkpoints), 0)

        coordinator.stop()
        print("✓ Checkpoint timeout cleanup test passed")

    def test_partial_acknowledgment_timeout(self):
        """Test timeout with partial acknowledgments"""
        coordinator = CheckpointCoordinator(
            job_id="test_partial_timeout",
            checkpoint_interval_ms=500,  # Check every 500ms
            checkpoint_timeout_ms=1000
        )
        coordinator.start()

        # Trigger checkpoint
        task_ids = ["task1", "task2", "task3"]
        checkpoint_id = coordinator.trigger_checkpoint(task_ids)

        # Acknowledge only one task
        import pickle
        test_state = {"data": "test"}
        state_bytes = pickle.dumps(test_state)

        coordinator.acknowledge_checkpoint(
            checkpoint_id=checkpoint_id,
            task_id="task1",
            state_data=state_bytes,
            task_manager_id="tm1"
        )

        # Verify one ack removed
        self.assertEqual(len(coordinator.pending_acks[checkpoint_id]), 2)

        # Wait for timeout (2 seconds to ensure check runs)
        time.sleep(2.0)

        # Verify checkpoint was cleaned up (not completed due to missing acks)
        self.assertNotIn(checkpoint_id, coordinator.pending_checkpoints)
        self.assertNotIn(checkpoint_id, coordinator.pending_acks)
        self.assertEqual(len(coordinator.completed_checkpoints), 0)

        coordinator.stop()
        print("✓ Partial acknowledgment timeout test passed")

    def test_completed_checkpoint_not_affected_by_timeout(self):
        """Test that completed checkpoints are not affected by timeout check"""
        coordinator = CheckpointCoordinator(
            job_id="test_completed",
            checkpoint_interval_ms=5000,
            checkpoint_timeout_ms=1000
        )
        coordinator.start()

        # Trigger checkpoint
        task_ids = ["task1", "task2"]
        checkpoint_id = coordinator.trigger_checkpoint(task_ids)

        # Acknowledge all tasks quickly
        import pickle
        test_state = {"data": "test"}
        state_bytes = pickle.dumps(test_state)

        for task_id in task_ids:
            coordinator.acknowledge_checkpoint(
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                state_data=state_bytes,
                task_manager_id="tm1"
            )

        # Verify checkpoint completed
        time.sleep(0.2)
        self.assertIn(checkpoint_id, coordinator.completed_checkpoints)
        self.assertNotIn(checkpoint_id, coordinator.pending_checkpoints)

        # Wait past timeout
        time.sleep(1.5)

        # Verify checkpoint still in completed
        self.assertIn(checkpoint_id, coordinator.completed_checkpoints)

        coordinator.stop()
        print("✓ Completed checkpoint not affected by timeout test passed")

    def test_concurrent_acknowledgments_with_timeout(self):
        """Test thread safety of acknowledgments during timeout checks"""
        import threading

        coordinator = CheckpointCoordinator(
            job_id="test_concurrent",
            checkpoint_interval_ms=200,  # Frequent timeout checks
            checkpoint_timeout_ms=2000
        )
        coordinator.start()

        # Trigger checkpoint
        task_ids = [f"task{i}" for i in range(10)]
        checkpoint_id = coordinator.trigger_checkpoint(task_ids)

        # Acknowledge tasks concurrently
        import pickle
        test_state = {"data": "test"}
        state_bytes = pickle.dumps(test_state)

        def acknowledge_task(task_id):
            time.sleep(0.1)  # Small delay
            coordinator.acknowledge_checkpoint(
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                state_data=state_bytes,
                task_manager_id="tm1"
            )

        threads = []
        for task_id in task_ids:
            thread = threading.Thread(target=acknowledge_task, args=(task_id,))
            thread.start()
            threads.append(thread)

        # Wait for all acknowledgments
        for thread in threads:
            thread.join()

        # Verify checkpoint completed
        time.sleep(0.5)
        self.assertIn(checkpoint_id, coordinator.completed_checkpoints)

        coordinator.stop()
        print("✓ Concurrent acknowledgments with timeout test passed")


if __name__ == '__main__':
    unittest.main()
