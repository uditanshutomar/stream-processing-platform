"""
Unit tests for source operators.
"""
import unittest
from unittest import mock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from taskmanager.operators.sources import KafkaSourceOperator


class TestKafkaSourceOperator(unittest.TestCase):
    """Tests for KafkaSourceOperator internals."""

    def test_commit_offsets_uses_offset_metadata(self):
        """Verify commit_offsets wraps offsets with OffsetAndMetadata."""
        operator = KafkaSourceOperator(
            topic="test-topic",
            bootstrap_servers="localhost:9092",
            group_id="test-group"
        )
        operator.consumer = mock.Mock()
        operator.current_offsets = {0: 15}

        with mock.patch("taskmanager.operators.sources.TopicPartition") as mock_tp, \
                mock.patch("taskmanager.operators.sources.OffsetAndMetadata") as mock_oam:
            mock_tp.return_value = "tp-0"
            mock_oam.return_value = "oam-0"

            operator.commit_offsets()

        operator.consumer.commit.assert_called_once_with(offsets={"tp-0": "oam-0"})
        mock_oam.assert_called_once_with(15, "")


if __name__ == '__main__':
    unittest.main()
