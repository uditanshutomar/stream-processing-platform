"""
Stream Join Example
Demonstrates: Joining two streams with time bounds
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import StreamExecutionEnvironment, JobVertex, JobEdge, EdgeType
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from taskmanager.operators.stateful import JoinOperator
from common.watermarks import WatermarkStrategies
from common.config import Config


def join_function(left_value, right_value):
    """
    Join function to combine user clicks and impressions.

    Args:
        left_value: Click event
        right_value: Impression event

    Returns:
        Joined event
    """
    return {
        'user_id': left_value['user_id'],
        'ad_id': left_value['ad_id'],
        'click_timestamp': left_value['timestamp'],
        'impression_timestamp': right_value['timestamp'],
        'time_to_click_ms': left_value['timestamp'] - right_value['timestamp']
    }


def main():
    """
    Stream join job:
    1. Read clicks from Kafka
    2. Read impressions from Kafka
    3. Join clicks and impressions on ad_id within 5-minute window
    4. Calculate time-to-click
    5. Write results to Kafka
    """

    env = StreamExecutionEnvironment("StreamJoin")
    env.set_parallelism(4).enable_checkpointing(10000)

    # Click stream
    clicks_source = KafkaSourceOperator(
        topic="ad-clicks",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        group_id="join-clicks-group",
        watermark_strategy=WatermarkStrategies.bounded_out_of_orderness(5000)
    )

    # Impression stream
    impressions_source = KafkaSourceOperator(
        topic="ad-impressions",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        group_id="join-impressions-group",
        watermark_strategy=WatermarkStrategies.bounded_out_of_orderness(5000)
    )

    # Parse events
    def parse_event(line):
        import json
        return json.loads(line)

    # Build click stream
    clicks = env.add_source(clicks_source) \
        .map(parse_event) \
        .key_by(lambda event: event['ad_id'])

    # Build impression stream (need separate env for second source)
    # In full implementation, would support multiple sources properly
    # For now, demonstrate the concept

    # Join operator (5 minute time bound)
    join_operator = JoinOperator(
        time_bound_ms=300000,  # 5 minutes
        join_func=join_function
    )
    join_operator.set_stream_side(True)  # This is left stream

    # Add join vertex
    vertex_id = env._generate_vertex_id()
    vertex = JobVertex(
        vertex_id=vertex_id,
        operator=join_operator,
        parallelism=env.parallelism
    )
    env.job_graph.add_vertex(vertex)

    # Connect click stream to join
    edge = JobEdge(
        source_vertex_id=clicks.vertex_id,
        target_vertex_id=vertex_id,
        edge_type=EdgeType.FORWARD
    )
    env.job_graph.add_edge(edge)

    # Sink
    kafka_sink = KafkaSinkOperator(
        topic="click-attribution",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
    )

    from jobmanager.job_graph import DataStream
    result = DataStream(env, vertex_id)
    result.add_sink(kafka_sink)

    # Serialize job
    job_graph = env.get_job_graph()

    import pickle
    with open('stream_join_job.pkl', 'wb') as f:
        pickle.dump(job_graph, f)

    print("Job serialized to stream_join_job.pkl")
    print("\nNote: This example demonstrates join concept.")
    print("Full implementation would support multiple sources and proper join semantics.")

    return job_graph


if __name__ == '__main__':
    main()
