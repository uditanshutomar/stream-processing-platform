"""
Buffer pool for efficient memory management in data transfer
"""
import threading
from typing import Optional, List
from collections import deque
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.config import Config


class MemoryBuffer:
    """
    A fixed-size memory buffer for data transfer.
    """

    def __init__(self, size: int):
        """
        Args:
            size: Buffer size in bytes
        """
        self.size = size
        self.data = bytearray(size)
        self.position = 0
        self.limit = 0

    def write(self, data: bytes) -> int:
        """
        Write data to buffer.

        Args:
            data: Data to write

        Returns:
            Number of bytes written
        """
        available = self.size - self.position
        to_write = min(len(data), available)

        if to_write > 0:
            self.data[self.position:self.position + to_write] = data[:to_write]
            self.position += to_write
            self.limit = max(self.limit, self.position)

        return to_write

    def read(self, length: Optional[int] = None) -> bytes:
        """
        Read data from buffer.

        Args:
            length: Number of bytes to read (None for all available)

        Returns:
            Read data
        """
        if length is None:
            length = self.limit - self.position

        to_read = min(length, self.limit - self.position)
        data = bytes(self.data[self.position:self.position + to_read])
        self.position += to_read

        return data

    def remaining(self) -> int:
        """Get remaining bytes to read"""
        return self.limit - self.position

    def available_space(self) -> int:
        """Get available space for writing"""
        return self.size - self.position

    def reset(self):
        """Reset buffer for reuse"""
        self.position = 0
        self.limit = 0

    def flip(self):
        """Flip buffer from write mode to read mode"""
        self.limit = self.position
        self.position = 0


class BufferPool:
    """
    Pool of reusable memory buffers to prevent frequent allocation.
    This is critical for high-throughput data transfer.
    """

    def __init__(
        self,
        buffer_size: int = Config.BUFFER_SIZE,
        pool_size: int = Config.BUFFER_POOL_SIZE
    ):
        """
        Args:
            buffer_size: Size of each buffer in bytes
            pool_size: Number of buffers in the pool
        """
        self.buffer_size = buffer_size
        self.pool_size = pool_size

        # Available buffers
        self.available_buffers: deque[MemoryBuffer] = deque()

        # Initialize pool
        for _ in range(pool_size):
            self.available_buffers.append(MemoryBuffer(buffer_size))

        # Lock for thread safety
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

        # Statistics
        self.allocated_count = 0
        self.deallocated_count = 0
        self.wait_count = 0

    def acquire(self, timeout: Optional[float] = None) -> Optional[MemoryBuffer]:
        """
        Acquire a buffer from the pool.

        Args:
            timeout: Maximum time to wait in seconds (None for indefinite)

        Returns:
            MemoryBuffer or None if timeout
        """
        with self.condition:
            # Wait for available buffer
            while not self.available_buffers:
                self.wait_count += 1
                if not self.condition.wait(timeout):
                    return None  # Timeout

            # Get buffer from pool
            buffer = self.available_buffers.popleft()
            buffer.reset()
            self.allocated_count += 1

            return buffer

    def release(self, buffer: MemoryBuffer):
        """
        Release a buffer back to the pool.

        Args:
            buffer: Buffer to release
        """
        with self.condition:
            buffer.reset()
            self.available_buffers.append(buffer)
            self.deallocated_count += 1

            # Notify waiting threads
            self.condition.notify()

    def available(self) -> int:
        """Get number of available buffers"""
        with self.lock:
            return len(self.available_buffers)

    def get_statistics(self) -> dict:
        """
        Get pool statistics.

        Returns:
            Dictionary with statistics
        """
        with self.lock:
            return {
                'buffer_size': self.buffer_size,
                'pool_size': self.pool_size,
                'available': len(self.available_buffers),
                'allocated_count': self.allocated_count,
                'deallocated_count': self.deallocated_count,
                'wait_count': self.wait_count,
            }


class NetworkBuffer:
    """
    Higher-level buffer for network data transfer with metadata.
    """

    def __init__(self, buffer: MemoryBuffer, buffer_pool: BufferPool):
        """
        Args:
            buffer: Underlying memory buffer
            buffer_pool: Pool to return buffer to
        """
        self.buffer = buffer
        self.buffer_pool = buffer_pool
        self.sequence_number = 0
        self.is_event = True  # True for data, False for control messages

    def write_data(self, data: bytes) -> int:
        """Write data to buffer"""
        return self.buffer.write(data)

    def read_data(self, length: Optional[int] = None) -> bytes:
        """Read data from buffer"""
        return self.buffer.read(length)

    def remaining(self) -> int:
        """Get remaining data"""
        return self.buffer.remaining()

    def flip(self):
        """Prepare buffer for reading"""
        self.buffer.flip()

    def release(self):
        """Return buffer to pool"""
        self.buffer_pool.release(self.buffer)

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically release buffer"""
        self.release()
