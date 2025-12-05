"""
Simple Data Pipeline Example - Works with job submission
Uses built-in functions that can be serialized properly
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from common.config import Config


def main():
    """
    Simple data pipeline job:
    1. Read from Kafka
    2. Write to Kafka (passthrough)
    """

    # Create execution environment
    env = StreamExecutionEnvironment("SimplePassthrough")

    # Set parallelism and enable checkpointing
    env.set_parallelism(2).enable_checkpointing(10000)

    # Create Kafka source
    kafka_source = KafkaSourceOperator(
        topic="input-data",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        group_id="simple-pipeline-group"
    )

    # Build simple passthrough pipeline
    result = env.add_source(kafka_source)

    # Create Kafka sink
    kafka_sink = KafkaSinkOperator(
        topic="output-data",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
    )

    # Add sink
    result.add_sink(kafka_sink)

    # Get the job graph
    job_graph = env.get_job_graph()

    # Print statistics
    print(f"Job Graph Statistics:")
    stats = job_graph.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Serialize for submission
    import pickle
    with open('simple_job.pkl', 'wb') as f:
        pickle.dump(job_graph, f)

    print("\nJob serialized to simple_job.pkl")
    print("Submit with: curl -X POST http://localhost:8081/jobs/submit -F 'job_file=@simple_job.pkl'")

    return job_graph


if __name__ == '__main__':
    main()
