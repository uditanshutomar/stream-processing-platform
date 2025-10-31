"""
Stateless stream operators
"""
from typing import List, Callable, Any
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.serialization import StreamRecord
from .base import StreamOperator


class MapOperator(StreamOperator):
    """
    One-to-one transformation operator.
    Applies a function to each element and emits the result.
    """

    def __init__(self, map_func: Callable[[Any], Any], operator_id: str = "map"):
        """
        Args:
            map_func: Function to apply to each element
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.map_func = map_func

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Apply map function to the record value.

        Args:
            record: Input stream record

        Returns:
            List containing the transformed record
        """
        try:
            result = self.map_func(record.value)
            return [record.with_value(result)]
        except Exception as e:
            # In production, this should be logged and handled appropriately
            print(f"Error in MapOperator: {e}")
            return []


class FilterOperator(StreamOperator):
    """
    Filtering operator.
    Only emits elements that satisfy the predicate.
    """

    def __init__(self, filter_func: Callable[[Any], bool], operator_id: str = "filter"):
        """
        Args:
            filter_func: Predicate function to test elements
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.filter_func = filter_func

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Filter record based on predicate.

        Args:
            record: Input stream record

        Returns:
            List containing the record if predicate is true, empty list otherwise
        """
        try:
            if self.filter_func(record.value):
                return [record]
            return []
        except Exception as e:
            print(f"Error in FilterOperator: {e}")
            return []


class FlatMapOperator(StreamOperator):
    """
    One-to-many transformation operator.
    Applies a function that returns an iterable and emits all results.
    """

    def __init__(
        self,
        flatmap_func: Callable[[Any], List[Any]],
        operator_id: str = "flatmap"
    ):
        """
        Args:
            flatmap_func: Function that returns an iterable of results
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.flatmap_func = flatmap_func

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Apply flatmap function and emit all results.

        Args:
            record: Input stream record

        Returns:
            List of output records (one for each result)
        """
        try:
            results = self.flatmap_func(record.value)
            return [record.with_value(result) for result in results]
        except Exception as e:
            print(f"Error in FlatMapOperator: {e}")
            return []


class KeyByOperator(StreamOperator):
    """
    Re-partitioning operator that assigns keys to records.
    """

    def __init__(
        self,
        key_selector: Callable[[Any], Any],
        operator_id: str = "keyby"
    ):
        """
        Args:
            key_selector: Function to extract key from value
            operator_id: Unique operator identifier
        """
        super().__init__(operator_id)
        self.key_selector = key_selector

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Assign key to record.

        Args:
            record: Input stream record

        Returns:
            List containing the record with assigned key
        """
        try:
            key = self.key_selector(record.value)
            return [record.with_key(key)]
        except Exception as e:
            print(f"Error in KeyByOperator: {e}")
            return []
