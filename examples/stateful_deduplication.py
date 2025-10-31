"""
Stateful Deduplication Example
Demonstrates: Keyed state, stateful processing
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from taskmanager.operators.stateful import KeyedProcessOperator
from common.watermarks import WatermarkStrategies
from common.config import Config


def deduplication_process_function(key, value, state):
    """
    Deduplication logic using keyed state.

    Args:
        key: Record key (user_id)
        value: Record value (event data)
        state: Keyed state (set of seen event IDs)

    Returns:
        List of events (empty if duplicate)
    """
    event_id = value.get('event_id')

    # Initialize state if needed
    if state is None:
        state = set()

    # Check if event already seen
    if event_id in state:
        # Duplicate - filter out
        return []

    # New event - add to state and emit
    state.add(event_id)

    # Limit state size to prevent unbounded growth
    if len(state) > 10000:
        # Remove oldest (in production, use timestamp-based eviction)
        state.pop()

    return [value]


def main():
    """
    Deduplication job:
    1. Read events from Kafka
    2. Parse events
    3. Partition by user_id
    4. Deduplicate based on event_id using keyed state
    5. Write unique events to Kafka
    """

    env = StreamExecutionEnvironment("StatefulDeduplication")
    env.set_parallelism(4).enable_checkpointing(10000)

    # Source
    kafka_source = KafkaSourceOperator(
        topic="user-events",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        group_id="dedup-group",
        watermark_strategy=WatermarkStrategies.bounded_out_of_orderness(5000)
    )

    # Parse events
    def parse_event(line):
        import json
        return json.loads(line)

    # Deduplication operator
    dedup_operator = KeyedProcessOperator(deduplication_process_function)

    # Pipeline
    result = env.add_source(kafka_source) \
        .map(parse_event) \
        .key_by(lambda event: event['user_id'])

    # Manually add the stateful operator (in full implementation, would have .process() method)
    from jobmanager.job_graph import JobVertex, JobEdge, EdgeType

    vertex_id = env._generate_vertex_id()
    vertex = JobVertex(
        vertex_id=vertex_id,
        operator=dedup_operator,
        parallelism=env.parallelism
    )
    env.job_graph.add_vertex(vertex)

    edge = JobEdge(
        source_vertex_id=result.vertex_id,
        target_vertex_id=vertex_id,
        edge_type=EdgeType.FORWARD
    )
    env.job_graph.add_edge(edge)

    # Sink
    kafka_sink = KafkaSinkOperator(
        topic="unique-events",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
    )

    from jobmanager.job_graph import DataStream
    final_stream = DataStream(env, vertex_id)
    final_stream.add_sink(kafka_sink)

    # Serialize job
    job_graph = env.get_job_graph()

    import pickle
    with open('stateful_deduplication_job.pkl', 'wb') as f:
        pickle.dump(job_graph, f)

    print("Job serialized to stateful_deduplication_job.pkl")
    return job_graph


if __name__ == '__main__':
    main()
