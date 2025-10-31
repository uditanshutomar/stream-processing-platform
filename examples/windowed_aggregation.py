"""
Windowed Aggregation Example
Demonstrates: Sliding windows, various aggregation functions
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from taskmanager.operators.stateful import SlidingWindow, AggregateOperator
from common.watermarks import WatermarkStrategies
from common.config import Config


def main():
    """
    Windowed aggregation job:
    1. Read sensor data from Kafka (sensor_id, temperature, timestamp)
    2. Parse and extract fields
    3. Partition by sensor_id
    4. Apply sliding window (30 seconds, slide 10 seconds)
    5. Compute average temperature per window
    6. Write results to Kafka
    """

    env = StreamExecutionEnvironment("WindowedAggregation")
    env.set_parallelism(4).enable_checkpointing(10000)

    # Source
    kafka_source = KafkaSourceOperator(
        topic="sensor-data",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        group_id="windowed-agg-group",
        watermark_strategy=WatermarkStrategies.bounded_out_of_orderness(5000)
    )

    # Parse JSON sensor data
    def parse_sensor_data(line):
        import json
        data = json.loads(line)
        return {
            'sensor_id': data['sensor_id'],
            'temperature': float(data['temperature']),
            'timestamp': int(data['timestamp'])
        }

    # Processing pipeline
    result = env.add_source(kafka_source) \
        .map(parse_sensor_data) \
        .key_by(lambda data: data['sensor_id']) \
        .window(SlidingWindow(size_ms=30000, slide_ms=10000)) \
        .reduce(lambda a, b: {
            'sensor_id': a['sensor_id'],
            'temperature': (a['temperature'] + b['temperature']) / 2,
            'count': a.get('count', 1) + b.get('count', 1)
        })

    # Sink
    kafka_sink = KafkaSinkOperator(
        topic="sensor-aggregates",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
    )

    result.add_sink(kafka_sink)

    # Serialize job
    job_graph = env.get_job_graph()

    import pickle
    with open('windowed_aggregation_job.pkl', 'wb') as f:
        pickle.dump(job_graph, f)

    print("Job serialized to windowed_aggregation_job.pkl")
    return job_graph


if __name__ == '__main__':
    main()
