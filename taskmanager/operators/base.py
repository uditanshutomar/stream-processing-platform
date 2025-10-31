"""
Base operator interface for stream processing
"""
from abc import ABC, abstractmethod
from typing import List, Any, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from common.serialization import StreamRecord
from common.watermarks import Watermark


class StreamOperator(ABC):
    """
    Base interface for all stream operators.
    Defines the contract for processing elements, watermarks, and state management.
    """

    def __init__(self, operator_id: str = ""):
        """
        Args:
            operator_id: Unique identifier for this operator
        """
        self.operator_id = operator_id
        self.state_backend = None

    def set_state_backend(self, state_backend):
        """Set the state backend for this operator"""
        self.state_backend = state_backend

    @abstractmethod
    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Process a single stream element.

        Args:
            record: The input stream record

        Returns:
            List of output stream records (can be empty, one, or many)
        """
        pass

    def process_watermark(self, watermark: Watermark) -> List[StreamRecord]:
        """
        Process a watermark.

        Args:
            watermark: The watermark to process

        Returns:
            List of records triggered by this watermark (e.g., window results)
        """
        return []

    def snapshot_state(self) -> bytes:
        """
        Snapshot the operator's state for checkpointing.

        Returns:
            Serialized state as bytes
        """
        return b""

    def restore_state(self, state: bytes):
        """
        Restore the operator's state from a checkpoint.

        Args:
            state: Serialized state bytes
        """
        pass

    def open(self):
        """
        Initialize the operator. Called before processing starts.
        """
        pass

    def close(self):
        """
        Clean up resources. Called when processing stops.
        """
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.operator_id})"


class OperatorChain:
    """
    Chains multiple operators together for execution as a single task.
    This is a key optimization to avoid serialization overhead.
    """

    def __init__(self, operators: List[StreamOperator]):
        """
        Args:
            operators: List of operators to chain in order
        """
        if not operators:
            raise ValueError("OperatorChain requires at least one operator")

        self.operators = operators
        self.operator_id = f"chain_{'-'.join(op.operator_id for op in operators)}"

    def set_state_backend(self, state_backend):
        """Set state backend for all operators in the chain"""
        for operator in self.operators:
            operator.set_state_backend(state_backend)

    def process_element(self, record: StreamRecord) -> List[StreamRecord]:
        """
        Process an element through the entire chain.

        Args:
            record: Input stream record

        Returns:
            List of output records from the final operator
        """
        records = [record]

        # Process through each operator in the chain
        for operator in self.operators:
            next_records = []
            for rec in records:
                next_records.extend(operator.process_element(rec))
            records = next_records

            # Early exit if no records remain
            if not records:
                break

        return records

    def process_watermark(self, watermark: Watermark) -> List[StreamRecord]:
        """
        Process a watermark through the chain.

        Args:
            watermark: The watermark to process

        Returns:
            List of records triggered by the watermark
        """
        records = []

        # Process watermark through each operator
        for operator in self.operators:
            triggered_records = operator.process_watermark(watermark)
            if triggered_records:
                # Process triggered records through remaining operators
                for rec in triggered_records:
                    # Find the index of current operator
                    idx = self.operators.index(operator)
                    # Process through remaining operators
                    temp_records = [rec]
                    for next_op in self.operators[idx + 1:]:
                        next_temp = []
                        for temp_rec in temp_records:
                            next_temp.extend(next_op.process_element(temp_rec))
                        temp_records = next_temp
                    records.extend(temp_records)

        return records

    def snapshot_state(self) -> bytes:
        """
        Snapshot state of all operators in the chain.

        Returns:
            Serialized state containing all operator states
        """
        import pickle
        states = {}
        for i, operator in enumerate(self.operators):
            state = operator.snapshot_state()
            if state:
                states[i] = state
        return pickle.dumps(states)

    def restore_state(self, state: bytes):
        """
        Restore state for all operators in the chain.

        Args:
            state: Serialized chain state
        """
        if not state:
            return

        import pickle
        states = pickle.loads(state)
        for i, operator_state in states.items():
            if i < len(self.operators):
                self.operators[i].restore_state(operator_state)

    def open(self):
        """Open all operators in the chain"""
        for operator in self.operators:
            operator.open()

    def close(self):
        """Close all operators in the chain"""
        for operator in self.operators:
            operator.close()

    def __repr__(self):
        return f"OperatorChain([{', '.join(str(op) for op in self.operators)}])"
