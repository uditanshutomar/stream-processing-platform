"""
Credit-based flow control to prevent backpressure
"""
import threading
from typing import Dict, Optional
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.config import Config


class FlowControlGate:
    """
    Credit-based flow control gate.
    Downstream tasks grant credits to upstream senders.
    Senders can only transmit when they have credits.
    """

    def __init__(
        self,
        initial_credits: int = Config.CREDIT_INITIAL,
        min_credits: int = Config.CREDIT_MIN
    ):
        """
        Args:
            initial_credits: Initial number of credits
            min_credits: Minimum credits before requesting more
        """
        self.initial_credits = initial_credits
        self.min_credits = min_credits
        self.credits = initial_credits

        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

        # Statistics
        self.credits_granted = 0
        self.credits_consumed = 0
        self.wait_time_ms = 0
        self.wait_count = 0

    def acquire_credits(self, amount: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Acquire credits to send data.

        Args:
            amount: Number of credits to acquire
            timeout: Maximum time to wait in seconds

        Returns:
            True if credits acquired, False if timeout
        """
        start_time = time.time()

        with self.condition:
            while self.credits < amount:
                self.wait_count += 1
                if timeout is not None:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0 or not self.condition.wait(remaining):
                        return False
                else:
                    self.condition.wait()

            # Consume credits
            self.credits -= amount
            self.credits_consumed += amount

            wait_time = time.time() - start_time
            self.wait_time_ms += wait_time * 1000

            return True

    def grant_credits(self, amount: int):
        """
        Grant credits (called by receiver after processing data).

        Args:
            amount: Number of credits to grant
        """
        with self.condition:
            self.credits += amount
            self.credits_granted += amount

            # Notify waiting senders
            self.condition.notify_all()

    def get_credits(self) -> int:
        """Get current number of credits"""
        with self.lock:
            return self.credits

    def needs_credit_announcement(self) -> bool:
        """Check if receiver should announce more credits"""
        with self.lock:
            return self.credits < self.min_credits

    def reset(self):
        """Reset to initial credits"""
        with self.condition:
            self.credits = self.initial_credits
            self.condition.notify_all()

    def get_statistics(self) -> dict:
        """
        Get flow control statistics.

        Returns:
            Dictionary with statistics
        """
        with self.lock:
            avg_wait_time = (
                self.wait_time_ms / self.wait_count if self.wait_count > 0 else 0
            )

            return {
                'credits': self.credits,
                'credits_granted': self.credits_granted,
                'credits_consumed': self.credits_consumed,
                'wait_count': self.wait_count,
                'avg_wait_time_ms': avg_wait_time,
            }


class BackpressureMonitor:
    """
    Monitors backpressure in the data flow.
    High backpressure indicates slow downstream processing.
    """

    def __init__(self, window_size: int = 100):
        """
        Args:
            window_size: Number of samples for moving average
        """
        self.window_size = window_size
        self.wait_times: list = []
        self.lock = threading.Lock()

    def record_wait_time(self, wait_time_ms: float):
        """
        Record a wait time sample.

        Args:
            wait_time_ms: Wait time in milliseconds
        """
        with self.lock:
            self.wait_times.append(wait_time_ms)

            # Keep only recent samples
            if len(self.wait_times) > self.window_size:
                self.wait_times.pop(0)

    def get_backpressure_ratio(self) -> float:
        """
        Get backpressure ratio (0.0 to 1.0).
        Higher values indicate more backpressure.

        Returns:
            Backpressure ratio
        """
        with self.lock:
            if not self.wait_times:
                return 0.0

            # Calculate ratio of samples with significant wait time
            significant_waits = sum(1 for wt in self.wait_times if wt > 1.0)
            return significant_waits / len(self.wait_times)

    def get_avg_wait_time(self) -> float:
        """
        Get average wait time.

        Returns:
            Average wait time in milliseconds
        """
        with self.lock:
            if not self.wait_times:
                return 0.0
            return sum(self.wait_times) / len(self.wait_times)


class NetworkFlowController:
    """
    Manages flow control for multiple channels (task connections).
    """

    def __init__(self):
        """Initialize flow controller"""
        self.gates: Dict[str, FlowControlGate] = {}
        self.monitors: Dict[str, BackpressureMonitor] = {}
        self.lock = threading.Lock()

    def create_channel(self, channel_id: str) -> FlowControlGate:
        """
        Create a flow control gate for a channel.

        Args:
            channel_id: Unique channel identifier

        Returns:
            FlowControlGate for the channel
        """
        with self.lock:
            if channel_id not in self.gates:
                self.gates[channel_id] = FlowControlGate()
                self.monitors[channel_id] = BackpressureMonitor()

            return self.gates[channel_id]

    def get_gate(self, channel_id: str) -> Optional[FlowControlGate]:
        """
        Get flow control gate for a channel.

        Args:
            channel_id: Channel identifier

        Returns:
            FlowControlGate or None if not found
        """
        with self.lock:
            return self.gates.get(channel_id)

    def get_monitor(self, channel_id: str) -> Optional[BackpressureMonitor]:
        """
        Get backpressure monitor for a channel.

        Args:
            channel_id: Channel identifier

        Returns:
            BackpressureMonitor or None if not found
        """
        with self.lock:
            return self.monitors.get(channel_id)

    def remove_channel(self, channel_id: str):
        """
        Remove a channel.

        Args:
            channel_id: Channel identifier
        """
        with self.lock:
            if channel_id in self.gates:
                del self.gates[channel_id]
            if channel_id in self.monitors:
                del self.monitors[channel_id]

    def get_overall_backpressure(self) -> float:
        """
        Get overall backpressure across all channels.

        Returns:
            Average backpressure ratio
        """
        with self.lock:
            if not self.monitors:
                return 0.0

            ratios = [monitor.get_backpressure_ratio() for monitor in self.monitors.values()]
            return sum(ratios) / len(ratios)

    def get_statistics(self) -> dict:
        """
        Get flow control statistics for all channels.

        Returns:
            Dictionary with statistics
        """
        with self.lock:
            stats = {}
            for channel_id, gate in self.gates.items():
                monitor = self.monitors.get(channel_id)
                stats[channel_id] = {
                    'gate': gate.get_statistics(),
                    'backpressure_ratio': monitor.get_backpressure_ratio() if monitor else 0.0,
                    'avg_wait_time_ms': monitor.get_avg_wait_time() if monitor else 0.0,
                }

            return stats
