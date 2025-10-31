"""
Stateful stream operators including windowing and aggregations
"""
from typing import List, Callable, Any, Dict, Optional
from enum import Enum
from collections import defaultdict
import pickle
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.serialization import StreamRecord
from common.watermarks import Watermark
from .base import StreamOperator


class Window:
    """Base window class"""

    def __init__(self, start: int, end: int):
        """
        Args:
            start: Window start timestamp (inclusive)
            end: Window end timestamp (exclusive)
        """
        self.start = start
        self.end = end

    def __hash__(self):
        return hash((self.start, self.end))

    def __eq__(self, other):
        if not isinstance(other, Window):
            return False
        return self.start == other.start and self.end == other.end

    def __repr__(self):
        return f"Window({self.start}, {self.end})"


class TumblingWindow:
    """Non-overlapping fixed-size windows"""

    def __init__(self, size_ms: int):
        """
        Args:
            size_ms: Window size in milliseconds
        """
        self.size = size_ms

    def assign_windows(self, timestamp: int) -> List[Window]:
        """Assign timestamp to a tumbling window"""
        start = (timestamp // self.size) * self.size
        end = start + self.size
        return [Window(start, end)]


class SlidingWindow:
    """Overlapping fixed-size windows"""

    def __init__(self, size_ms: int, slide_ms: int):
        """
        Args:
            size_ms: Window size in milliseconds
            slide_ms: Slide interval in milliseconds
        """
        self.size = size_ms
        self.slide = slide_ms

    def assign_windows(self, timestamp: int) -> List[Window]:
        """Assign timestamp to all overlapping sliding windows"""
        windows = []
        # Find all windows this timestamp belongs to
        last_start = (timestamp // self.slide) * self.slide
        first_start = last_start - self.size + self.slide

        start = first_start
        while start <= last_start:
            end = start + self.size
            if start <= timestamp < end:
                windows.append(Window(start, end))
            start += self.slide

        return windows


class KeyedProcessOperator(StreamOperator):
    """
    Stateful operator that maintains per-key state.
    """

    def __init__(
        self,
        process_func: Callable[[Any, Any], List[Any]],
        operator_id: str = "keyed_process"
    ):
        """
        Args:
            process_func: Function that takes (key, value) and returns list of outputs
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.process_func = process_func
        self.state: Dict[Any, Any] = {}

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Process element with per-key state access.

        Args:
            record: Input stream record

        Returns:
            List of output records
        """
        try:
            key = record.key
            if key is None:
                raise ValueError("KeyedProcessOperator requires keyed records")

            # Get or initialize state for this key
            key_state = self.state.get(key)

            # Process with state
            results = self.process_func(key, record.value, key_state)

            # Update state (assuming process_func may modify state)
            if key_state is not None:
                self.state[key] = key_state

            return [record.with_value(result) for result in results]
        except Exception as e:
            print(f"Error in KeyedProcessOperator: {e}")
            return []

    def snapshot_state(self) -> bytes:
        """Snapshot the keyed state"""
        return pickle.dumps(self.state)

    def restore_state(self, state: bytes):
        """Restore the keyed state"""
        if state:
            self.state = pickle.loads(state)


class WindowOperator(StreamOperator):
    """
    Windowing operator that groups elements into windows and applies aggregation.
    """

    def __init__(
        self,
        window_assigner,  # TumblingWindow or SlidingWindow
        reduce_func: Optional[Callable[[Any, Any], Any]] = None,
        operator_id: str = "window"
    ):
        """
        Args:
            window_assigner: Window assignment strategy
            reduce_func: Optional reduce function for aggregation
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.window_assigner = window_assigner
        self.reduce_func = reduce_func
        # Store window state: (key, window) -> list of elements
        self.window_state: Dict[tuple, List[Any]] = defaultdict(list)
        self.watermark_timestamp = 0

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Add element to appropriate windows.

        Args:
            record: Input stream record

        Returns:
            Empty list (results emitted on watermark)
        """
        try:
            key = record.key
            timestamp = record.timestamp

            # Assign to windows
            windows = self.window_assigner.assign_windows(timestamp)

            # Add to each window's state
            for window in windows:
                window_key = (key, window)
                self.window_state[window_key].append(record.value)

            return []
        except Exception as e:
            print(f"Error in WindowOperator.process_element: {e}")
            return []

    def process_watermark(self, watermark: Watermark) -> List[StreamRecord]:
        """
        Trigger windows that are complete based on watermark.

        Args:
            watermark: The watermark

        Returns:
            List of window results
        """
        try:
            results = []
            self.watermark_timestamp = watermark.timestamp

            # Find windows to trigger
            windows_to_trigger = []
            for (key, window) in list(self.window_state.keys()):
                # Trigger if window end is before or at watermark
                if window.end <= watermark.timestamp:
                    windows_to_trigger.append((key, window))

            # Process triggered windows
            for key, window in windows_to_trigger:
                window_key = (key, window)
                elements = self.window_state[window_key]

                if elements:
                    # Apply reduce function if provided
                    if self.reduce_func:
                        result = elements[0]
                        for elem in elements[1:]:
                            result = self.reduce_func(result, elem)
                    else:
                        result = elements

                    # Create output record
                    output_record = StreamRecord(
                        value=result,
                        key=key,
                        timestamp=window.end
                    )
                    results.append(output_record)

                # Remove triggered window from state
                del self.window_state[window_key]

            return results
        except Exception as e:
            print(f"Error in WindowOperator.process_watermark: {e}")
            return []

    def snapshot_state(self) -> bytes:
        """Snapshot window state"""
        state = {
            'window_state': dict(self.window_state),
            'watermark_timestamp': self.watermark_timestamp
        }
        return pickle.dumps(state)

    def restore_state(self, state: bytes):
        """Restore window state"""
        if state:
            restored = pickle.loads(state)
            self.window_state = defaultdict(list, restored['window_state'])
            self.watermark_timestamp = restored['watermark_timestamp']


class AggregateOperator(StreamOperator):
    """
    Aggregation operator supporting sum, count, avg, min, max.
    """

    def __init__(
        self,
        agg_func: str,  # "sum", "count", "avg", "min", "max"
        operator_id: str = "aggregate"
    ):
        """
        Args:
            agg_func: Aggregation function name
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.agg_func = agg_func
        # State: key -> aggregation state
        self.state: Dict[Any, Dict[str, Any]] = {}

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Update aggregation state for the key.

        Args:
            record: Input stream record

        Returns:
            List containing updated aggregate
        """
        try:
            key = record.key
            value = record.value

            if key not in self.state:
                self.state[key] = {'count': 0, 'sum': 0, 'min': None, 'max': None}

            state = self.state[key]
            state['count'] += 1

            if self.agg_func in ['sum', 'avg']:
                state['sum'] += value

            if self.agg_func == 'min':
                if state['min'] is None or value < state['min']:
                    state['min'] = value

            if self.agg_func == 'max':
                if state['max'] is None or value > state['max']:
                    state['max'] = value

            # Calculate result
            if self.agg_func == 'sum':
                result = state['sum']
            elif self.agg_func == 'count':
                result = state['count']
            elif self.agg_func == 'avg':
                result = state['sum'] / state['count'] if state['count'] > 0 else 0
            elif self.agg_func == 'min':
                result = state['min']
            elif self.agg_func == 'max':
                result = state['max']
            else:
                raise ValueError(f"Unknown aggregation function: {self.agg_func}")

            return [record.with_value(result)]
        except Exception as e:
            print(f"Error in AggregateOperator: {e}")
            return []

    def snapshot_state(self) -> bytes:
        """Snapshot aggregation state"""
        return pickle.dumps(self.state)

    def restore_state(self, state: bytes):
        """Restore aggregation state"""
        if state:
            self.state = pickle.loads(state)


class JoinOperator(StreamOperator):
    """
    Stream-stream join operator with time bounds.
    """

    def __init__(
        self,
        time_bound_ms: int,
        join_func: Callable[[Any, Any], Any],
        operator_id: str = "join"
    ):
        """
        Args:
            time_bound_ms: Maximum time difference for joining events
            join_func: Function to join two values
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.time_bound = time_bound_ms
        self.join_func = join_func
        # Buffer for left and right streams: key -> list of (timestamp, value)
        self.left_buffer: Dict[Any, List[tuple]] = defaultdict(list)
        self.right_buffer: Dict[Any, List[tuple]] = defaultdict(list)
        self.is_left_stream = True  # Track which stream this is

    def set_stream_side(self, is_left: bool):
        """Set whether this operator processes left or right stream"""
        self.is_left_stream = is_left

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Join elements from two streams within time bound.

        Args:
            record: Input stream record

        Returns:
            List of joined records
        """
        try:
            key = record.key
            timestamp = record.timestamp
            value = record.value

            results = []

            if self.is_left_stream:
                # Add to left buffer
                self.left_buffer[key].append((timestamp, value))

                # Try to join with right buffer
                for right_ts, right_val in self.right_buffer.get(key, []):
                    if abs(timestamp - right_ts) <= self.time_bound:
                        joined = self.join_func(value, right_val)
                        results.append(record.with_value(joined))
            else:
                # Add to right buffer
                self.right_buffer[key].append((timestamp, value))

                # Try to join with left buffer
                for left_ts, left_val in self.left_buffer.get(key, []):
                    if abs(timestamp - left_ts) <= self.time_bound:
                        joined = self.join_func(left_val, value)
                        results.append(record.with_value(joined).with_timestamp(left_ts))

            return results
        except Exception as e:
            print(f"Error in JoinOperator: {e}")
            return []

    def process_watermark(self, watermark: Watermark) -> List[StreamRecord]:
        """
        Clean up old buffered elements based on watermark.

        Args:
            watermark: The watermark

        Returns:
            Empty list
        """
        try:
            # Remove elements that are too old to join
            cutoff = watermark.timestamp - self.time_bound

            for key in list(self.left_buffer.keys()):
                self.left_buffer[key] = [
                    (ts, val) for ts, val in self.left_buffer[key]
                    if ts >= cutoff
                ]
                if not self.left_buffer[key]:
                    del self.left_buffer[key]

            for key in list(self.right_buffer.keys()):
                self.right_buffer[key] = [
                    (ts, val) for ts, val in self.right_buffer[key]
                    if ts >= cutoff
                ]
                if not self.right_buffer[key]:
                    del self.right_buffer[key]

            return []
        except Exception as e:
            print(f"Error in JoinOperator.process_watermark: {e}")
            return []

    def snapshot_state(self) -> bytes:
        """Snapshot join buffers"""
        state = {
            'left_buffer': dict(self.left_buffer),
            'right_buffer': dict(self.right_buffer),
            'is_left_stream': self.is_left_stream
        }
        return pickle.dumps(state)

    def restore_state(self, state: bytes):
        """Restore join buffers"""
        if state:
            restored = pickle.loads(state)
            self.left_buffer = defaultdict(list, restored['left_buffer'])
            self.right_buffer = defaultdict(list, restored['right_buffer'])
            self.is_left_stream = restored['is_left_stream']
