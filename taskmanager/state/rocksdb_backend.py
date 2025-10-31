"""
RocksDB-based state backend for fault-tolerant state management
"""
import os
import shutil
import pickle
from typing import Optional, Any
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.config import Config

try:
    import rocksdb
except ImportError:
    rocksdb = None


class RocksDBStateBackend:
    """
    State backend implementation using RocksDB for persistent state storage.
    Provides efficient snapshot and restore capabilities for checkpointing.
    """

    def __init__(self, base_path: str, operator_id: str):
        """
        Args:
            base_path: Base directory for RocksDB storage
            operator_id: Unique operator identifier
        """
        if rocksdb is None:
            raise ImportError("python-rocksdb is required for RocksDBStateBackend")

        self.operator_id = operator_id
        self.db_path = os.path.join(base_path, f"rocksdb_{operator_id}")
        self.db: Optional[rocksdb.DB] = None

        # Ensure directory exists
        os.makedirs(self.db_path, exist_ok=True)

        # Configure RocksDB options
        self.options = rocksdb.Options()
        self.options.create_if_missing = True
        self.options.write_buffer_size = Config.ROCKSDB_WRITE_BUFFER_SIZE
        self.options.max_write_buffer_number = Config.ROCKSDB_MAX_WRITE_BUFFERS

        # Configure block cache
        block_cache = rocksdb.LRUCache(Config.ROCKSDB_BLOCK_CACHE_SIZE)
        table_options = rocksdb.BlockBasedTableFactory(block_cache=block_cache)
        self.options.table_factory = table_options

        # Open database
        self.db = rocksdb.DB(self.db_path, self.options)

    def get(self, key: bytes) -> Optional[bytes]:
        """
        Get value for key.

        Args:
            key: Key to lookup

        Returns:
            Value bytes or None if not found
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        return self.db.get(key)

    def put(self, key: bytes, value: bytes):
        """
        Store key-value pair.

        Args:
            key: Key bytes
            value: Value bytes
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        self.db.put(key, value)

    def delete(self, key: bytes):
        """
        Delete key-value pair.

        Args:
            key: Key to delete
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        self.db.delete(key)

    def snapshot(self) -> bytes:
        """
        Create a snapshot of the entire state.

        Returns:
            Serialized snapshot data
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        snapshot_data = {}

        # Iterate over all key-value pairs
        it = self.db.iterkeys()
        it.seek_to_first()

        for key in it:
            value = self.db.get(key)
            if value is not None:
                snapshot_data[key] = value

        # Serialize snapshot
        return pickle.dumps(snapshot_data)

    def restore(self, snapshot_data: bytes):
        """
        Restore state from snapshot.

        Args:
            snapshot_data: Serialized snapshot data
        """
        if not self.db:
            raise RuntimeError("Database not initialized")

        if not snapshot_data:
            return

        # Deserialize snapshot
        snapshot = pickle.loads(snapshot_data)

        # Write batch for efficiency
        batch = rocksdb.WriteBatch()

        for key, value in snapshot.items():
            batch.put(key, value)

        self.db.write(batch)

    def clear(self):
        """Clear all state"""
        if not self.db:
            return

        # Close and delete database
        self.close()
        shutil.rmtree(self.db_path, ignore_errors=True)

        # Recreate
        os.makedirs(self.db_path, exist_ok=True)
        self.db = rocksdb.DB(self.db_path, self.options)

    def close(self):
        """Close the database"""
        if self.db:
            del self.db
            self.db = None

    def __del__(self):
        """Cleanup on deletion"""
        self.close()


class InMemoryStateBackend:
    """
    In-memory state backend for testing or when persistence is not needed.
    """

    def __init__(self, operator_id: str):
        """
        Args:
            operator_id: Unique operator identifier
        """
        self.operator_id = operator_id
        self.state: dict = {}

    def get(self, key: bytes) -> Optional[bytes]:
        """Get value for key"""
        return self.state.get(key)

    def put(self, key: bytes, value: bytes):
        """Store key-value pair"""
        self.state[key] = value

    def delete(self, key: bytes):
        """Delete key"""
        if key in self.state:
            del self.state[key]

    def snapshot(self) -> bytes:
        """Create snapshot"""
        return pickle.dumps(self.state)

    def restore(self, snapshot_data: bytes):
        """Restore from snapshot"""
        if snapshot_data:
            self.state = pickle.loads(snapshot_data)

    def clear(self):
        """Clear all state"""
        self.state.clear()

    def close(self):
        """No-op for in-memory backend"""
        pass
