"""
Word Count Example - Classic stream processing application
Demonstrates: Source, FlatMap, KeyBy, Window, Reduce, Sink
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from taskmanager.operators.stateful import TumblingWindow
from common.watermarks import WatermarkStrategies
from common.config import Config


# Define functions for pickling (lambdas can't be pickled)
def split_line(line):
    """Split line into words"""
    return line.split()

def create_tuple(word):
    """Create (word, 1) tuple"""
    return (word.lower(), 1)

def extract_key(tuple_val):
    """Extract key from tuple"""
    return tuple_val[0]

def sum_counts(a, b):
    """Sum counts in tuples"""
    return (a[0], a[1] + b[1])

def filter_threshold(tuple_val):
    """Filter tuples with count > 5"""
    return tuple_val[1] > 5


def main():
    """
    Word count streaming job:
    1. Read lines from Kafka
    2. Split lines into words
    3. Create (word, 1) tuples
    4. Partition by word
    5. Window into 10-second tumbling windows
    6. Sum counts per window
    7. Filter words with count > 5
    8. Write results to Kafka
    """

    # Create execution environment
    env = StreamExecutionEnvironment("WordCount")

    # Set parallelism and enable checkpointing
    env.set_parallelism(4) \
       .enable_checkpointing(10000)  # 10 second checkpoints

    # Create Kafka source
    kafka_source = KafkaSourceOperator(
        topic="input-text",
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        group_id="word-count-group",
        watermark_strategy=WatermarkStrategies.bounded_out_of_orderness(5000)
    )

    # Build processing pipeline
    result = env.add_source(kafka_source) \
        .flat_map(split_line) \
        .map(create_tuple) \
        .key_by(extract_key) \
        .window(TumblingWindow(10000)) \
        .reduce(sum_counts) \
        .filter(filter_threshold)

    # Create Kafka sink
    kafka_sink = KafkaSinkOperator(
        topic="word-count-output",
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
    with open('word_count_job.pkl', 'wb') as f:
        pickle.dump(job_graph, f)

    print("\nJob serialized to word_count_job.pkl")
    print("Submit with: curl -X POST http://localhost:8081/jobs/submit -F 'job_file=@word_count_job.pkl'")

    return job_graph


if __name__ == '__main__':
    main()
