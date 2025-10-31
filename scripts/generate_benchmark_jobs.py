#!/usr/bin/env python3
"""
Generate benchmark job files for realistic performance testing

Creates optimized job graphs for different benchmark scenarios:
1. Simple stateless pipeline (Map -> Filter)
2. Stateful pipeline with windowing (KeyBy -> Window -> Aggregate)
3. High throughput pipeline
"""

import sys
import os
import pickle

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from taskmanager.operators.stateful import TumblingWindow
from common.watermarks import WatermarkStrategies


# Picklable functions for benchmarks
def multiply_by_two(x):
    """Map function: multiply by 2"""
    return x * 2

def filter_greater_than_100(x):
    """Filter function: keep values > 100"""
    return x > 100

def extract_key_value(x):
    """Extract key-value tuple from record"""
    return (x.get('key', 'default'), x.get('value', 0))

def sum_tuples(a, b):
    """Reduce function: sum tuple values"""
    return (a[0], a[1] + b[1])

def increment(x):
    """Map function: increment by 1"""
    return x + 1

def get_first_element(tuple):
    """Key extractor: get first element of tuple"""
    return tuple[0]


def generate_simple_pipeline_job():
    """
    Generate a simple stateless pipeline for latency benchmarking
    
    Pipeline: Kafka Source -> Map (x*2) -> Filter (x>100) -> Kafka Sink
    """
    print("Generating simple pipeline job...")
    
    env = StreamExecutionEnvironment("SimpleBenchmark")
    env.set_parallelism(4)
    
    # Source
    source = KafkaSourceOperator(
        topic="bench-simple-input",
        bootstrap_servers="kafka:9092",
        group_id="bench-simple-group",
        watermark_strategy=WatermarkStrategies.no_watermarks()
    )
    
    # Pipeline
    result = env.add_source(source) \
        .map(multiply_by_two) \
        .filter(filter_greater_than_100)
    
    # Sink
    sink = KafkaSinkOperator(
        topic="bench-simple-output",
        bootstrap_servers="kafka:9092"
    )
    
    result.add_sink(sink)
    
    # Save job
    job_file = 'benchmark_simple_pipeline.pkl'
    with open(job_file, 'wb') as f:
        pickle.dump(env.get_job_graph(), f)
    
    print(f"✓ Created: {job_file}")
    return job_file


def generate_stateful_pipeline_job():
    """
    Generate a stateful pipeline with windowing
    
    Pipeline: Kafka Source -> Map (extract key) -> KeyBy -> Window (10s) -> Sum -> Kafka Sink
    """
    print("Generating stateful pipeline job...")
    
    env = StreamExecutionEnvironment("StatefulBenchmark")
    env.set_parallelism(4)
    env.enable_checkpointing(10000)  # 10s checkpoints
    
    # Source with watermarks
    source = KafkaSourceOperator(
        topic="bench-stateful-input",
        bootstrap_servers="kafka:9092",
        group_id="bench-stateful-group",
        watermark_strategy=WatermarkStrategies.bounded_out_of_orderness(5000)
    )
    
    # Pipeline with state
    result = env.add_source(source) \
        .map(extract_key_value) \
        .key_by(get_first_element) \
        .window(TumblingWindow(10000)) \
        .reduce(sum_tuples)
    
    # Sink
    sink = KafkaSinkOperator(
        topic="bench-stateful-output",
        bootstrap_servers="kafka:9092"
    )
    
    result.add_sink(sink)
    
    # Save job
    job_file = 'benchmark_stateful_pipeline.pkl'
    with open(job_file, 'wb') as f:
        pickle.dump(env.get_job_graph(), f)
    
    print(f"✓ Created: {job_file}")
    return job_file


def generate_high_throughput_job():
    """
    Generate an optimized high-throughput pipeline
    
    Pipeline: Kafka Source -> Map -> Kafka Sink (with chaining enabled)
    """
    print("Generating high-throughput job...")
    
    env = StreamExecutionEnvironment("ThroughputBenchmark")
    env.set_parallelism(8)  # Higher parallelism for throughput
    # Note: Operator chaining is enabled by default in scheduler
    
    # Source
    source = KafkaSourceOperator(
        topic="bench-throughput-input",
        bootstrap_servers="kafka:9092",
        group_id="bench-throughput-group",
        watermark_strategy=WatermarkStrategies.no_watermarks()
    )
    
    # Simple pipeline (will be chained)
    result = env.add_source(source) \
        .map(increment)
    
    # Sink
    sink = KafkaSinkOperator(
        topic="bench-throughput-output",
        bootstrap_servers="kafka:9092"
    )
    
    result.add_sink(sink)
    
    # Save job
    job_file = 'benchmark_high_throughput.pkl'
    with open(job_file, 'wb') as f:
        pickle.dump(env.get_job_graph(), f)
    
    print(f"✓ Created: {job_file}")
    return job_file


def main():
    """Generate all benchmark jobs"""
    print("\n📦 Generating Benchmark Job Files")
    print("="*70)
    
    try:
        jobs = []
        
        # Generate jobs
        jobs.append(generate_simple_pipeline_job())
        jobs.append(generate_stateful_pipeline_job())
        jobs.append(generate_high_throughput_job())
        
        print("\n✓ All benchmark jobs generated successfully!")
        print("\nGenerated files:")
        for job in jobs:
            print(f"  • {job}")
        
        print("\n📝 To submit jobs:")
        print("  curl -X POST http://localhost:8081/jobs/submit \\")
        print("    -F 'job_file=@benchmark_simple_pipeline.pkl'")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Failed to generate jobs: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
