"""
Unit tests for stream operators
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.serialization import StreamRecord
from common.watermarks import Watermark
from taskmanager.operators.stateless import MapOperator, FilterOperator, FlatMapOperator
from taskmanager.operators.stateful import WindowOperator, TumblingWindow, AggregateOperator


class TestStatelessOperators(unittest.TestCase):
    """Test stateless operators"""

    def test_map_operator(self):
        """Test MapOperator transforms values correctly"""
        operator = MapOperator(lambda x: x * 2)
        record = StreamRecord(value=5)

        results = operator.process_element(record)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].value, 10)

    def test_filter_operator(self):
        """Test FilterOperator filters correctly"""
        operator = FilterOperator(lambda x: x > 5)

        # Should pass
        record1 = StreamRecord(value=10)
        results1 = operator.process_element(record1)
        self.assertEqual(len(results1), 1)

        # Should filter out
        record2 = StreamRecord(value=3)
        results2 = operator.process_element(record2)
        self.assertEqual(len(results2), 0)

    def test_flatmap_operator(self):
        """Test FlatMapOperator produces multiple outputs"""
        operator = FlatMapOperator(lambda x: x.split())
        record = StreamRecord(value="hello world test")

        results = operator.process_element(record)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].value, "hello")
        self.assertEqual(results[1].value, "world")
        self.assertEqual(results[2].value, "test")


class TestWindowOperator(unittest.TestCase):
    """Test windowing operators"""

    def test_tumbling_window_assignment(self):
        """Test tumbling window assigns records correctly"""
        window_assigner = TumblingWindow(10000)  # 10 second windows

        # Timestamp 5000 should go to window [0, 10000)
        windows = window_assigner.assign_windows(5000)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].start, 0)
        self.assertEqual(windows[0].end, 10000)

        # Timestamp 15000 should go to window [10000, 20000)
        windows = window_assigner.assign_windows(15000)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].start, 10000)
        self.assertEqual(windows[0].end, 20000)

    def test_window_triggering(self):
        """Test window triggers on watermark"""
        operator = WindowOperator(
            window_assigner=TumblingWindow(10000),
            reduce_func=lambda a, b: a + b
        )

        # Add records to window [0, 10000)
        operator.process_element(StreamRecord(value=1, key="key1", timestamp=1000))
        operator.process_element(StreamRecord(value=2, key="key1", timestamp=2000))
        operator.process_element(StreamRecord(value=3, key="key1", timestamp=3000))

        # Watermark at 10000 should trigger window
        watermark = Watermark(10000)
        results = operator.process_watermark(watermark)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].value, 6)  # 1 + 2 + 3
        self.assertEqual(results[0].key, "key1")


class TestAggregateOperator(unittest.TestCase):
    """Test aggregation operators"""

    def test_sum_aggregation(self):
        """Test sum aggregation"""
        operator = AggregateOperator("sum")

        # Process values
        r1 = operator.process_element(StreamRecord(value=10, key="k1"))
        self.assertEqual(r1[0].value, 10)

        r2 = operator.process_element(StreamRecord(value=20, key="k1"))
        self.assertEqual(r2[0].value, 30)

        r3 = operator.process_element(StreamRecord(value=5, key="k1"))
        self.assertEqual(r3[0].value, 35)

    def test_count_aggregation(self):
        """Test count aggregation"""
        operator = AggregateOperator("count")

        r1 = operator.process_element(StreamRecord(value=100, key="k1"))
        self.assertEqual(r1[0].value, 1)

        r2 = operator.process_element(StreamRecord(value=200, key="k1"))
        self.assertEqual(r2[0].value, 2)

    def test_avg_aggregation(self):
        """Test average aggregation"""
        operator = AggregateOperator("avg")

        operator.process_element(StreamRecord(value=10, key="k1"))
        operator.process_element(StreamRecord(value=20, key="k1"))
        r3 = operator.process_element(StreamRecord(value=30, key="k1"))

        self.assertEqual(r3[0].value, 20.0)  # (10 + 20 + 30) / 3


if __name__ == '__main__':
    unittest.main()
