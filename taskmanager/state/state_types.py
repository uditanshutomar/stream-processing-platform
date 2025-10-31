"""
User-facing state abstractions backed by RocksDB
"""
import pickle
from typing import Any, Optional, List, Callable, TypeVar, Generic
from abc import ABC, abstractmethod

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


class State(ABC):
    """Base class for all state types"""

    def __init__(self, state_backend, key: Any):
        """
        Args:
            state_backend: The state backend (RocksDB or in-memory)
            key: The key for this state
        """
        self.state_backend = state_backend
        self.key = pickle.dumps(key)

    @abstractmethod
    def clear(self):
        """Clear the state"""
        pass


class ValueState(State, Generic[T]):
    """
    State that holds a single value per key.
    """

    def get(self) -> Optional[T]:
        """
        Get the current value.

        Returns:
            The value or None if not set
        """
        value_bytes = self.state_backend.get(self.key)
        if value_bytes is None:
            return None
        return pickle.loads(value_bytes)

    def update(self, value: T):
        """
        Update the value.

        Args:
            value: New value
        """
        value_bytes = pickle.dumps(value)
        self.state_backend.put(self.key, value_bytes)

    def clear(self):
        """Clear the value"""
        self.state_backend.delete(self.key)


class ListState(State, Generic[T]):
    """
    State that holds a list of values per key.
    """

    def get(self) -> List[T]:
        """
        Get all values.

        Returns:
            List of values (empty list if not set)
        """
        value_bytes = self.state_backend.get(self.key)
        if value_bytes is None:
            return []
        return pickle.loads(value_bytes)

    def add(self, value: T):
        """
        Add a value to the list.

        Args:
            value: Value to add
        """
        current = self.get()
        current.append(value)
        self.state_backend.put(self.key, pickle.dumps(current))

    def add_all(self, values: List[T]):
        """
        Add multiple values to the list.

        Args:
            values: Values to add
        """
        current = self.get()
        current.extend(values)
        self.state_backend.put(self.key, pickle.dumps(current))

    def update(self, values: List[T]):
        """
        Replace the list with new values.

        Args:
            values: New list of values
        """
        self.state_backend.put(self.key, pickle.dumps(values))

    def clear(self):
        """Clear the list"""
        self.state_backend.delete(self.key)


class MapState(State, Generic[K, V]):
    """
    State that holds a map of key-value pairs per key.
    """

    def get(self, key: K) -> Optional[V]:
        """
        Get value for a map key.

        Args:
            key: Map key

        Returns:
            Value or None if not found
        """
        map_data = self._get_map()
        return map_data.get(key)

    def put(self, key: K, value: V):
        """
        Put a key-value pair in the map.

        Args:
            key: Map key
            value: Map value
        """
        map_data = self._get_map()
        map_data[key] = value
        self._put_map(map_data)

    def remove(self, key: K):
        """
        Remove a key from the map.

        Args:
            key: Map key to remove
        """
        map_data = self._get_map()
        if key in map_data:
            del map_data[key]
            self._put_map(map_data)

    def contains(self, key: K) -> bool:
        """
        Check if map contains a key.

        Args:
            key: Map key

        Returns:
            True if key exists
        """
        map_data = self._get_map()
        return key in map_data

    def items(self):
        """
        Get all key-value pairs.

        Returns:
            Iterator of (key, value) tuples
        """
        map_data = self._get_map()
        return map_data.items()

    def keys(self):
        """
        Get all keys.

        Returns:
            Iterator of keys
        """
        map_data = self._get_map()
        return map_data.keys()

    def values(self):
        """
        Get all values.

        Returns:
            Iterator of values
        """
        map_data = self._get_map()
        return map_data.values()

    def clear(self):
        """Clear the map"""
        self.state_backend.delete(self.key)

    def _get_map(self) -> dict:
        """Internal: Get the map data"""
        value_bytes = self.state_backend.get(self.key)
        if value_bytes is None:
            return {}
        return pickle.loads(value_bytes)

    def _put_map(self, map_data: dict):
        """Internal: Put the map data"""
        self.state_backend.put(self.key, pickle.dumps(map_data))


class ReducingState(State, Generic[T]):
    """
    State that applies a reduce function to aggregate values.
    """

    def __init__(self, state_backend, key: Any, reduce_func: Callable[[T, T], T]):
        """
        Args:
            state_backend: The state backend
            key: The key for this state
            reduce_func: Function to reduce two values into one
        """
        super().__init__(state_backend, key)
        self.reduce_func = reduce_func

    def get(self) -> Optional[T]:
        """
        Get the current reduced value.

        Returns:
            The reduced value or None if not set
        """
        value_bytes = self.state_backend.get(self.key)
        if value_bytes is None:
            return None
        return pickle.loads(value_bytes)

    def add(self, value: T):
        """
        Add a value, applying the reduce function.

        Args:
            value: Value to add
        """
        current = self.get()
        if current is None:
            new_value = value
        else:
            new_value = self.reduce_func(current, value)

        self.state_backend.put(self.key, pickle.dumps(new_value))

    def clear(self):
        """Clear the state"""
        self.state_backend.delete(self.key)


class AggregatingState(State, Generic[T]):
    """
    State that applies custom aggregation logic.
    """

    def __init__(
        self,
        state_backend,
        key: Any,
        add_func: Callable[[Any, T], Any],
        get_func: Callable[[Any], Any],
        initial_value: Any = None
    ):
        """
        Args:
            state_backend: The state backend
            key: The key for this state
            add_func: Function to add a value to accumulator
            get_func: Function to get result from accumulator
            initial_value: Initial accumulator value
        """
        super().__init__(state_backend, key)
        self.add_func = add_func
        self.get_func = get_func
        self.initial_value = initial_value

    def get(self) -> Any:
        """
        Get the aggregated result.

        Returns:
            The aggregated result
        """
        accumulator = self._get_accumulator()
        return self.get_func(accumulator)

    def add(self, value: T):
        """
        Add a value to the aggregation.

        Args:
            value: Value to add
        """
        accumulator = self._get_accumulator()
        new_accumulator = self.add_func(accumulator, value)
        self._put_accumulator(new_accumulator)

    def clear(self):
        """Clear the state"""
        self.state_backend.delete(self.key)

    def _get_accumulator(self) -> Any:
        """Internal: Get the accumulator"""
        value_bytes = self.state_backend.get(self.key)
        if value_bytes is None:
            return self.initial_value
        return pickle.loads(value_bytes)

    def _put_accumulator(self, accumulator: Any):
        """Internal: Put the accumulator"""
        self.state_backend.put(self.key, pickle.dumps(accumulator))


class StateDescriptor:
    """
    Descriptor for creating state instances.
    """

    def __init__(self, name: str, state_type: type):
        """
        Args:
            name: Name of the state
            state_type: Type of state (ValueState, ListState, etc.)
        """
        self.name = name
        self.state_type = state_type
        self.additional_params = {}

    def with_reduce_function(self, reduce_func: Callable):
        """Set reduce function for ReducingState"""
        self.additional_params['reduce_func'] = reduce_func
        return self

    def with_aggregator(self, add_func: Callable, get_func: Callable, initial_value: Any = None):
        """Set aggregator functions for AggregatingState"""
        self.additional_params['add_func'] = add_func
        self.additional_params['get_func'] = get_func
        self.additional_params['initial_value'] = initial_value
        return self

    def create_state(self, state_backend, key: Any):
        """Create a state instance"""
        return self.state_type(state_backend, key, **self.additional_params)
