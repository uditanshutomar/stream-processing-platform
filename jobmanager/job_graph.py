"""
JobGraph - Represents the logical DAG of operators and data flow
"""
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import pickle
import time


class EdgeType(Enum):
    """Type of edge between operators"""
    FORWARD = "forward"  # One-to-one
    REBALANCE = "rebalance"  # Round-robin
    SHUFFLE = "shuffle"  # Hash-based partitioning
    BROADCAST = "broadcast"  # Send to all


@dataclass
class JobVertex:
    """Represents a vertex (operator) in the job graph"""
    vertex_id: str
    operator: Any  # StreamOperator instance
    parallelism: int = 1
    operator_name: str = ""

    def __post_init__(self):
        if not self.operator_name:
            self.operator_name = self.operator.__class__.__name__


@dataclass
class JobEdge:
    """Represents an edge (data flow) between vertices"""
    source_vertex_id: str
    target_vertex_id: str
    edge_type: EdgeType = EdgeType.FORWARD


class JobGraph:
    """
    Directed Acyclic Graph representing a stream processing job.
    Captures operators, their dependencies, and execution properties.
    """

    def __init__(self, job_name: str):
        """
        Args:
            job_name: Name of the job
        """
        self.job_name = job_name
        self.vertices: Dict[str, JobVertex] = {}
        self.edges: List[JobEdge] = []
        self.sources: List[str] = []  # Source vertex IDs
        self.sinks: List[str] = []  # Sink vertex IDs

        # Configuration
        self.config: Dict[str, Any] = {}

    def add_vertex(self, vertex: JobVertex):
        """
        Add a vertex to the graph.

        Args:
            vertex: JobVertex to add
        """
        self.vertices[vertex.vertex_id] = vertex

    def add_edge(self, edge: JobEdge):
        """
        Add an edge to the graph.

        Args:
            edge: JobEdge to add
        """
        if edge.source_vertex_id not in self.vertices:
            raise ValueError(f"Source vertex {edge.source_vertex_id} not found")
        if edge.target_vertex_id not in self.vertices:
            raise ValueError(f"Target vertex {edge.target_vertex_id} not found")

        self.edges.append(edge)

    def set_source(self, vertex_id: str):
        """Mark a vertex as a source"""
        if vertex_id not in self.vertices:
            raise ValueError(f"Vertex {vertex_id} not found")
        if vertex_id not in self.sources:
            self.sources.append(vertex_id)

    def set_sink(self, vertex_id: str):
        """Mark a vertex as a sink"""
        if vertex_id not in self.vertices:
            raise ValueError(f"Vertex {vertex_id} not found")
        if vertex_id not in self.sinks:
            self.sinks.append(vertex_id)

    def get_upstream_vertices(self, vertex_id: str) -> List[str]:
        """
        Get upstream vertices for a given vertex.

        Args:
            vertex_id: Vertex ID

        Returns:
            List of upstream vertex IDs
        """
        return [
            edge.source_vertex_id
            for edge in self.edges
            if edge.target_vertex_id == vertex_id
        ]

    def get_downstream_vertices(self, vertex_id: str) -> List[str]:
        """
        Get downstream vertices for a given vertex.

        Args:
            vertex_id: Vertex ID

        Returns:
            List of downstream vertex IDs
        """
        return [
            edge.target_vertex_id
            for edge in self.edges
            if edge.source_vertex_id == vertex_id
        ]

    def topological_sort(self) -> List[str]:
        """
        Get vertices in topological order.

        Returns:
            List of vertex IDs in topological order
        """
        # Calculate in-degrees
        in_degree = {vid: 0 for vid in self.vertices}
        for edge in self.edges:
            in_degree[edge.target_vertex_id] += 1

        # Queue of vertices with no incoming edges
        queue = [vid for vid, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            vertex_id = queue.pop(0)
            result.append(vertex_id)

            # Reduce in-degree for downstream vertices
            for downstream in self.get_downstream_vertices(vertex_id):
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    queue.append(downstream)

        if len(result) != len(self.vertices):
            raise ValueError("Graph contains a cycle")

        return result

    def identify_chainable_operators(self) -> List[List[str]]:
        """
        Identify sequences of operators that can be chained together.
        Operators can be chained if:
        1. They have a one-to-one (FORWARD) connection
        2. The downstream operator has only one input
        3. Both are stateless or the chain preserves semantics

        Returns:
            List of chains (each chain is a list of vertex IDs)
        """
        chains = []
        visited = set()

        for vertex_id in self.topological_sort():
            if vertex_id in visited:
                continue

            # Start a new chain
            chain = [vertex_id]
            visited.add(vertex_id)

            # Try to extend the chain forward
            current = vertex_id
            while True:
                downstream = self.get_downstream_vertices(current)

                # Can only chain if there's exactly one downstream
                if len(downstream) != 1:
                    break

                next_vertex = downstream[0]

                # Check if edge is FORWARD
                edge = next(
                    (e for e in self.edges
                     if e.source_vertex_id == current and e.target_vertex_id == next_vertex),
                    None
                )

                if not edge or edge.edge_type != EdgeType.FORWARD:
                    break

                # Check if next vertex has only one input
                upstream = self.get_upstream_vertices(next_vertex)
                if len(upstream) != 1:
                    break

                # Can chain - add to chain
                chain.append(next_vertex)
                visited.add(next_vertex)
                current = next_vertex

            chains.append(chain)

        return chains

    def serialize(self) -> bytes:
        """
        Serialize the job graph.

        Returns:
            Serialized bytes
        """
        return pickle.dumps(self)

    @staticmethod
    def deserialize(data: bytes) -> 'JobGraph':
        """
        Deserialize a job graph.

        Args:
            data: Serialized bytes

        Returns:
            JobGraph instance
        """
        return pickle.loads(data)

    def get_statistics(self) -> dict:
        """
        Get graph statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            'job_name': self.job_name,
            'num_vertices': len(self.vertices),
            'num_edges': len(self.edges),
            'num_sources': len(self.sources),
            'num_sinks': len(self.sinks),
            'total_parallelism': sum(v.parallelism for v in self.vertices.values()),
        }

    def __repr__(self):
        stats = self.get_statistics()
        return (
            f"JobGraph(name={self.job_name}, "
            f"vertices={stats['num_vertices']}, "
            f"edges={stats['num_edges']}, "
            f"parallelism={stats['total_parallelism']})"
        )


class StreamExecutionEnvironment:
    """
    Entry point for defining stream processing jobs.
    Provides a fluent API for building job graphs.
    """

    def __init__(self, job_name: str = "StreamJob"):
        """
        Args:
            job_name: Name of the job
        """
        self.job_name = job_name
        self.job_graph = JobGraph(job_name)
        self.parallelism = 1
        self.checkpoint_interval = 10000  # ms
        self.vertex_counter = 0

    def set_parallelism(self, parallelism: int) -> 'StreamExecutionEnvironment':
        """
        Set default parallelism for operators.

        Args:
            parallelism: Default parallelism

        Returns:
            Self for chaining
        """
        self.parallelism = parallelism
        return self

    def enable_checkpointing(self, interval_ms: int) -> 'StreamExecutionEnvironment':
        """
        Enable checkpointing with given interval.

        Args:
            interval_ms: Checkpoint interval in milliseconds

        Returns:
            Self for chaining
        """
        self.checkpoint_interval = interval_ms
        self.job_graph.config['checkpoint_interval'] = interval_ms
        return self

    def add_source(self, source_operator: Any) -> 'DataStream':
        """
        Add a source operator.

        Args:
            source_operator: Source operator instance

        Returns:
            DataStream for chaining
        """
        vertex_id = self._generate_vertex_id()
        vertex = JobVertex(
            vertex_id=vertex_id,
            operator=source_operator,
            parallelism=self.parallelism
        )

        self.job_graph.add_vertex(vertex)
        self.job_graph.set_source(vertex_id)

        return DataStream(self, vertex_id)

    def _generate_vertex_id(self) -> str:
        """Generate unique vertex ID"""
        self.vertex_counter += 1
        return f"vertex_{self.vertex_counter}"

    def get_job_graph(self) -> JobGraph:
        """
        Get the constructed job graph.

        Returns:
            JobGraph instance
        """
        return self.job_graph

    def execute(self) -> str:
        """
        Submit the job for execution.

        Returns:
            Job ID
        """
        # In a real implementation, this would submit to JobManager
        # For now, return a dummy job ID
        return f"job_{self.job_name}_{int(time.time())}"


class DataStream:
    """
    Represents a stream of data with transformations.
    Provides fluent API for building operator chains.
    """

    def __init__(self, env: StreamExecutionEnvironment, vertex_id: str):
        """
        Args:
            env: Execution environment
            vertex_id: ID of the vertex producing this stream
        """
        self.env = env
        self.vertex_id = vertex_id

    def map(self, map_func: Callable) -> 'DataStream':
        """Apply map transformation"""
        from taskmanager.operators.stateless import MapOperator

        operator = MapOperator(map_func)
        return self._add_operator(operator, EdgeType.FORWARD)

    def filter(self, filter_func: Callable) -> 'DataStream':
        """Apply filter transformation"""
        from taskmanager.operators.stateless import FilterOperator

        operator = FilterOperator(filter_func)
        return self._add_operator(operator, EdgeType.FORWARD)

    def flat_map(self, flatmap_func: Callable) -> 'DataStream':
        """Apply flatmap transformation"""
        from taskmanager.operators.stateless import FlatMapOperator

        operator = FlatMapOperator(flatmap_func)
        return self._add_operator(operator, EdgeType.FORWARD)

    def key_by(self, key_selector: Callable) -> 'KeyedStream':
        """Partition by key"""
        from taskmanager.operators.stateless import KeyByOperator

        operator = KeyByOperator(key_selector)
        new_stream = self._add_operator(operator, EdgeType.SHUFFLE)
        return KeyedStream(self.env, new_stream.vertex_id)

    def add_sink(self, sink_operator: Any):
        """Add sink operator"""
        vertex_id = self.env._generate_vertex_id()
        vertex = JobVertex(
            vertex_id=vertex_id,
            operator=sink_operator,
            parallelism=self.env.parallelism
        )

        self.env.job_graph.add_vertex(vertex)
        self.env.job_graph.set_sink(vertex_id)

        edge = JobEdge(
            source_vertex_id=self.vertex_id,
            target_vertex_id=vertex_id,
            edge_type=EdgeType.FORWARD
        )
        self.env.job_graph.add_edge(edge)

    def _add_operator(self, operator: Any, edge_type: EdgeType) -> 'DataStream':
        """Add an operator to the graph"""
        vertex_id = self.env._generate_vertex_id()
        vertex = JobVertex(
            vertex_id=vertex_id,
            operator=operator,
            parallelism=self.env.parallelism
        )

        self.env.job_graph.add_vertex(vertex)

        edge = JobEdge(
            source_vertex_id=self.vertex_id,
            target_vertex_id=vertex_id,
            edge_type=edge_type
        )
        self.env.job_graph.add_edge(edge)

        return DataStream(self.env, vertex_id)


class KeyedStream(DataStream):
    """
    Keyed stream with stateful operations.
    """

    def window(self, window_assigner) -> 'WindowedStream':
        """Apply windowing"""
        return WindowedStream(self.env, self.vertex_id, window_assigner)

    def reduce(self, reduce_func: Callable) -> DataStream:
        """Apply reduce aggregation"""
        from taskmanager.operators.stateful import WindowOperator
        from taskmanager.operators.stateful import TumblingWindow

        # Use a simple tumbling window for reduce
        operator = WindowOperator(TumblingWindow(1000), reduce_func)
        return self._add_operator(operator, EdgeType.FORWARD)


class WindowedStream:
    """
    Windowed stream for time-based aggregations.
    """

    def __init__(self, env: StreamExecutionEnvironment, vertex_id: str, window_assigner):
        """
        Args:
            env: Execution environment
            vertex_id: Source vertex ID
            window_assigner: Window assignment strategy
        """
        self.env = env
        self.vertex_id = vertex_id
        self.window_assigner = window_assigner

    def reduce(self, reduce_func: Callable) -> DataStream:
        """Apply reduce to windows"""
        from taskmanager.operators.stateful import WindowOperator

        operator = WindowOperator(self.window_assigner, reduce_func)
        return self._add_operator(operator, EdgeType.FORWARD)

    def _add_operator(self, operator: Any, edge_type: EdgeType) -> DataStream:
        """Add operator to graph"""
        vertex_id = self.env._generate_vertex_id()
        vertex = JobVertex(
            vertex_id=vertex_id,
            operator=operator,
            parallelism=self.env.parallelism
        )

        self.env.job_graph.add_vertex(vertex)

        edge = JobEdge(
            source_vertex_id=self.vertex_id,
            target_vertex_id=vertex_id,
            edge_type=edge_type
        )
        self.env.job_graph.add_edge(edge)

        return DataStream(self.env, vertex_id)
