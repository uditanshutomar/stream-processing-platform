"""
Serialization utilities for stream processing
"""
import pickle
import json
from typing import Any, Optional
from abc import ABC, abstractmethod


class Serializer(ABC):
    """Base class for serialization"""

    @abstractmethod
    def serialize(self, obj: Any) -> bytes:
        """Serialize object to bytes"""
        pass

    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to object"""
        pass


class PickleSerializer(Serializer):
    """Pickle-based serialization"""

    def serialize(self, obj: Any) -> bytes:
        """Serialize using pickle"""
        return pickle.dumps(obj)

    def deserialize(self, data: bytes) -> Any:
        """Deserialize using pickle"""
        return pickle.loads(data)


class JSONSerializer(Serializer):
    """JSON-based serialization"""

    def __init__(self, encoding: str = "utf-8"):
        self.encoding = encoding

    def serialize(self, obj: Any) -> bytes:
        """Serialize using JSON"""
        json_str = json.dumps(obj)
        return json_str.encode(self.encoding)

    def deserialize(self, data: bytes) -> Any:
        """Deserialize using JSON"""
        json_str = data.decode(self.encoding)
        return json.loads(json_str)


class StringSerializer(Serializer):
    """String serialization"""

    def __init__(self, encoding: str = "utf-8"):
        self.encoding = encoding

    def serialize(self, obj: Any) -> bytes:
        """Serialize string to bytes"""
        if isinstance(obj, bytes):
            return obj
        return str(obj).encode(self.encoding)

    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to string"""
        return data.decode(self.encoding)


class SerializationSchema:
    """Schema for serializing/deserializing records"""

    def __init__(
        self,
        key_serializer: Optional[Serializer] = None,
        value_serializer: Optional[Serializer] = None
    ):
        """
        Args:
            key_serializer: Serializer for keys (default: PickleSerializer)
            value_serializer: Serializer for values (default: PickleSerializer)
        """
        self.key_serializer = key_serializer or PickleSerializer()
        self.value_serializer = value_serializer or PickleSerializer()

    def serialize_key(self, key: Any) -> bytes:
        """Serialize a key"""
        if key is None:
            return b""
        return self.key_serializer.serialize(key)

    def deserialize_key(self, data: bytes) -> Any:
        """Deserialize a key"""
        if not data:
            return None
        return self.key_serializer.deserialize(data)

    def serialize_value(self, value: Any) -> bytes:
        """Serialize a value"""
        if value is None:
            return b""
        return self.value_serializer.serialize(value)

    def deserialize_value(self, data: bytes) -> Any:
        """Deserialize a value"""
        if not data:
            return None
        return self.value_serializer.deserialize(data)


# Predefined schemas
class Schemas:
    """Common serialization schemas"""

    STRING = SerializationSchema(
        key_serializer=StringSerializer(),
        value_serializer=StringSerializer()
    )

    JSON = SerializationSchema(
        key_serializer=StringSerializer(),
        value_serializer=JSONSerializer()
    )

    PICKLE = SerializationSchema(
        key_serializer=PickleSerializer(),
        value_serializer=PickleSerializer()
    )


class StreamRecord:
    """Represents a record in the stream"""

    def __init__(
        self,
        value: Any,
        key: Optional[Any] = None,
        timestamp: Optional[int] = None,
        headers: Optional[dict] = None
    ):
        """
        Args:
            value: The record value
            key: Optional key for partitioning
            timestamp: Event timestamp in milliseconds
            headers: Optional metadata headers
        """
        self.value = value
        self.key = key
        self.timestamp = timestamp or int(time.time() * 1000)
        self.headers = headers or {}

    def with_value(self, value: Any) -> 'StreamRecord':
        """Create a new record with a different value"""
        return StreamRecord(
            value=value,
            key=self.key,
            timestamp=self.timestamp,
            headers=self.headers
        )

    def with_key(self, key: Any) -> 'StreamRecord':
        """Create a new record with a different key"""
        return StreamRecord(
            value=self.value,
            key=key,
            timestamp=self.timestamp,
            headers=self.headers
        )

    def with_timestamp(self, timestamp: int) -> 'StreamRecord':
        """Create a new record with a different timestamp"""
        return StreamRecord(
            value=self.value,
            key=self.key,
            timestamp=timestamp,
            headers=self.headers
        )

    def __repr__(self):
        return f"StreamRecord(key={self.key}, value={self.value}, timestamp={self.timestamp})"


import time
