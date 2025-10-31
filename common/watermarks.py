"""
Watermark generation and handling for event time processing
"""
import time
from typing import Optional
from abc import ABC, abstractmethod


class Watermark:
    """Represents a watermark in the event stream"""

    def __init__(self, timestamp: int):
        """
        Args:
            timestamp: Watermark timestamp in milliseconds
        """
        self.timestamp = timestamp

    def __repr__(self):
        return f"Watermark(timestamp={self.timestamp})"

    def __eq__(self, other):
        if not isinstance(other, Watermark):
            return False
        return self.timestamp == other.timestamp

    def __lt__(self, other):
        if not isinstance(other, Watermark):
            return NotImplemented
        return self.timestamp < other.timestamp


class WatermarkGenerator(ABC):
    """Base class for watermark generation strategies"""

    @abstractmethod
    def on_event(self, event_timestamp: int) -> Optional[Watermark]:
        """
        Called for each event to potentially generate a watermark

        Args:
            event_timestamp: Timestamp of the current event

        Returns:
            Watermark if one should be emitted, None otherwise
        """
        pass

    @abstractmethod
    def on_periodic_emit(self) -> Optional[Watermark]:
        """
        Called periodically to generate a watermark

        Returns:
            Watermark if one should be emitted, None otherwise
        """
        pass


class BoundedOutOfOrdernessWatermarkGenerator(WatermarkGenerator):
    """
    Generates watermarks assuming bounded out-of-orderness.
    Watermark = max_event_timestamp - max_out_of_orderness
    """

    def __init__(self, max_out_of_orderness_ms: int = 5000):
        """
        Args:
            max_out_of_orderness_ms: Maximum expected out-of-orderness in milliseconds
        """
        self.max_out_of_orderness = max_out_of_orderness_ms
        self.max_timestamp = 0

    def on_event(self, event_timestamp: int) -> Optional[Watermark]:
        """Update max timestamp but don't emit watermark on every event"""
        if event_timestamp > self.max_timestamp:
            self.max_timestamp = event_timestamp
        return None

    def on_periodic_emit(self) -> Optional[Watermark]:
        """Emit watermark based on max seen timestamp"""
        if self.max_timestamp == 0:
            return None
        watermark_timestamp = self.max_timestamp - self.max_out_of_orderness
        return Watermark(watermark_timestamp)


class PeriodicWatermarkEmitter:
    """
    Emits watermarks periodically using a WatermarkGenerator
    """

    def __init__(
        self,
        watermark_generator: WatermarkGenerator,
        interval_ms: int = 200
    ):
        """
        Args:
            watermark_generator: The watermark generation strategy
            interval_ms: Interval between watermark emissions in milliseconds
        """
        self.watermark_generator = watermark_generator
        self.interval_ms = interval_ms
        self.last_emit_time = 0

    def on_event(self, event_timestamp: int) -> Optional[Watermark]:
        """
        Process an event and potentially emit a watermark

        Args:
            event_timestamp: Timestamp of the current event

        Returns:
            Watermark if one should be emitted, None otherwise
        """
        # Let generator track the event
        self.watermark_generator.on_event(event_timestamp)

        # Check if it's time to emit
        current_time = int(time.time() * 1000)
        if current_time - self.last_emit_time >= self.interval_ms:
            self.last_emit_time = current_time
            return self.watermark_generator.on_periodic_emit()

        return None


class MonotonousTimestampExtractor:
    """Extracts timestamps from events ensuring monotonicity"""

    def __init__(self):
        self.last_timestamp = 0

    def extract_timestamp(self, event_timestamp: int) -> int:
        """
        Extract timestamp ensuring it's monotonically increasing

        Args:
            event_timestamp: The event's timestamp

        Returns:
            Monotonically increasing timestamp
        """
        if event_timestamp > self.last_timestamp:
            self.last_timestamp = event_timestamp
            return event_timestamp
        return self.last_timestamp


class WatermarkStrategy:
    """
    Defines watermark generation strategy for a source
    """

    def __init__(
        self,
        max_out_of_orderness_ms: int = 5000,
        interval_ms: int = 200
    ):
        """
        Args:
            max_out_of_orderness_ms: Maximum expected out-of-orderness
            interval_ms: Interval between watermark emissions
        """
        self.max_out_of_orderness_ms = max_out_of_orderness_ms
        self.interval_ms = interval_ms

    def create_watermark_emitter(self) -> PeriodicWatermarkEmitter:
        """Create a watermark emitter with this strategy"""
        generator = BoundedOutOfOrdernessWatermarkGenerator(
            self.max_out_of_orderness_ms
        )
        return PeriodicWatermarkEmitter(generator, self.interval_ms)


# Predefined strategies
class WatermarkStrategies:
    """Common watermark strategies"""

    @staticmethod
    def bounded_out_of_orderness(max_out_of_orderness_ms: int = 5000) -> WatermarkStrategy:
        """
        Create a bounded out-of-orderness watermark strategy

        Args:
            max_out_of_orderness_ms: Maximum expected out-of-orderness

        Returns:
            WatermarkStrategy instance
        """
        return WatermarkStrategy(max_out_of_orderness_ms=max_out_of_orderness_ms)

    @staticmethod
    def no_watermarks() -> WatermarkStrategy:
        """Create a strategy that doesn't generate watermarks"""
        return WatermarkStrategy(max_out_of_orderness_ms=0, interval_ms=0)
