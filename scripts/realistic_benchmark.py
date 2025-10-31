#!/usr/bin/env python3
"""
Realistic End-to-End Benchmark for Distributed Stream Processing Platform

This benchmark measures actual distributed system performance including:
- Kafka producer/consumer overhead
- Network serialization/deserialization
- gRPC communication between components
- State persistence to RocksDB
- Checkpoint coordination
- Multi-process overhead

Prerequisites:
1. Docker Compose cluster must be running: cd deployment && docker-compose up -d
2. Kafka topics must be created
3. JobManager must be available at localhost:8081
"""

import time
import json
import statistics
import sys
import os
import requests
import threading
from datetime import datetime
from typing import List, Dict, Any
import pickle

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.admin import KafkaAdminClient, NewTopic
except ImportError:
    print("ERROR: kafka-python-ng not installed. Install with: pip install kafka-python-ng")
    sys.exit(1)


class RealisticBenchmark:
    """End-to-end benchmark runner"""
    
    def __init__(self, 
                 kafka_bootstrap='localhost:9092',
                 jobmanager_url='http://localhost:8081'):
        self.kafka_bootstrap = kafka_bootstrap
        self.jobmanager_url = jobmanager_url
        self.results = {}
        
    def setup_kafka_topics(self, topics: List[str]):
        """Create Kafka topics for benchmarking"""
        print("Setting up Kafka topics...")
        try:
            admin_client = KafkaAdminClient(
                bootstrap_servers=self.kafka_bootstrap,
                client_id='benchmark-admin'
            )
            
            topic_list = [
                NewTopic(name=topic, num_partitions=4, replication_factor=1)
                for topic in topics
            ]
            
            try:
                admin_client.create_topics(new_topics=topic_list, validate_only=False)
                print(f"✓ Created topics: {', '.join(topics)}")
            except Exception as e:
                if 'TopicExistsError' in str(e):
                    print(f"✓ Topics already exist: {', '.join(topics)}")
                else:
                    raise
            
            admin_client.close()
            time.sleep(2)  # Wait for topics to be ready
            
        except Exception as e:
            print(f"✗ Failed to setup Kafka topics: {e}")
            raise
    
    def benchmark_simple_pipeline(self, num_records=10000):
        """
        Benchmark 1: Simple stateless pipeline (Map -> Filter)
        Measures: End-to-end latency including Kafka
        """
        print("\n" + "="*70)
        print("BENCHMARK 1: Simple Stateless Pipeline (Map -> Filter)")
        print("="*70)
        
        input_topic = 'bench-simple-input'
        output_topic = 'bench-simple-output'
        
        self.setup_kafka_topics([input_topic, output_topic])
        
        # Create and submit job
        job_id = self._submit_simple_job(input_topic, output_topic)
        if not job_id:
            print("✗ Failed to submit job")
            return
        
        print(f"✓ Job submitted: {job_id}")
        time.sleep(5)  # Wait for job to start
        
        # Produce records with timestamps
        print(f"Producing {num_records} records to Kafka...")
        latencies = self._produce_and_measure(input_topic, output_topic, num_records)
        
        # Calculate statistics
        if latencies:
            stats = {
                'mean': statistics.mean(latencies),
                'median': statistics.median(latencies),
                'p50': sorted(latencies)[int(0.50 * len(latencies))],
                'p95': sorted(latencies)[int(0.95 * len(latencies))],
                'p99': sorted(latencies)[int(0.99 * len(latencies))],
                'min': min(latencies),
                'max': max(latencies),
            }
            
            throughput = num_records / (max(latencies) / 1000.0) if latencies else 0
            
            print(f"\n📊 Results:")
            print(f"   Records processed: {len(latencies)}/{num_records}")
            print(f"   End-to-end latency:")
            print(f"     Mean:   {stats['mean']:.2f} ms")
            print(f"     Median: {stats['median']:.2f} ms")
            print(f"     P95:    {stats['p95']:.2f} ms")
            print(f"     P99:    {stats['p99']:.2f} ms")
            print(f"     Min:    {stats['min']:.2f} ms")
            print(f"     Max:    {stats['max']:.2f} ms")
            print(f"   Throughput: {throughput:,.0f} records/second")
            
            self.results['simple_pipeline'] = {
                'latency': stats,
                'throughput': throughput,
                'records_processed': len(latencies)
            }
        else:
            print("✗ No latency measurements collected")
        
        # Cancel job
        self._cancel_job(job_id)
    
    def benchmark_stateful_pipeline(self, num_records=5000):
        """
        Benchmark 2: Stateful pipeline with windowing
        Measures: Latency with state operations and checkpoints
        """
        print("\n" + "="*70)
        print("BENCHMARK 2: Stateful Pipeline (KeyBy -> Window -> Aggregate)")
        print("="*70)
        
        input_topic = 'bench-stateful-input'
        output_topic = 'bench-stateful-output'
        
        self.setup_kafka_topics([input_topic, output_topic])
        
        # Create and submit stateful job
        job_id = self._submit_stateful_job(input_topic, output_topic)
        if not job_id:
            print("✗ Failed to submit job")
            return
        
        print(f"✓ Job submitted: {job_id}")
        time.sleep(5)
        
        # Produce keyed records
        print(f"Producing {num_records} keyed records...")
        start_time = time.time()
        self._produce_keyed_records(input_topic, num_records)
        
        # Wait for processing and measure checkpoint time
        time.sleep(10)
        
        # Trigger checkpoint
        checkpoint_duration = self._measure_checkpoint(job_id)
        
        end_time = time.time()
        duration = end_time - start_time
        throughput = num_records / duration
        
        print(f"\n📊 Results:")
        print(f"   Records produced: {num_records}")
        print(f"   Processing time: {duration:.2f} seconds")
        print(f"   Throughput: {throughput:,.0f} records/second")
        print(f"   Checkpoint duration: {checkpoint_duration:.2f} seconds")
        
        self.results['stateful_pipeline'] = {
            'throughput': throughput,
            'checkpoint_duration': checkpoint_duration,
            'records_processed': num_records
        }
        
        # Cancel job
        self._cancel_job(job_id)
    
    def benchmark_high_throughput(self, duration_seconds=30):
        """
        Benchmark 3: Maximum sustained throughput
        Measures: Peak throughput with backpressure
        """
        print("\n" + "="*70)
        print(f"BENCHMARK 3: Maximum Sustained Throughput ({duration_seconds}s)")
        print("="*70)
        
        input_topic = 'bench-throughput-input'
        output_topic = 'bench-throughput-output'
        
        self.setup_kafka_topics([input_topic, output_topic])
        
        job_id = self._submit_simple_job(input_topic, output_topic)
        if not job_id:
            print("✗ Failed to submit job")
            return
        
        print(f"✓ Job submitted: {job_id}")
        time.sleep(5)
        
        # Produce as fast as possible
        print(f"Producing records for {duration_seconds} seconds...")
        records_sent = self._produce_continuous(input_topic, duration_seconds)
        
        # Wait for processing to complete
        time.sleep(5)
        
        # Get job metrics
        metrics = self._get_job_metrics(job_id)
        
        throughput = records_sent / duration_seconds
        
        print(f"\n📊 Results:")
        print(f"   Records sent: {records_sent:,}")
        print(f"   Duration: {duration_seconds} seconds")
        print(f"   Average throughput: {throughput:,.0f} records/second")
        
        if metrics:
            print(f"   Job metrics:")
            for key, value in metrics.items():
                print(f"     {key}: {value}")
        
        self.results['high_throughput'] = {
            'throughput': throughput,
            'records_sent': records_sent,
            'duration': duration_seconds
        }
        
        self._cancel_job(job_id)
    
    def _produce_and_measure(self, input_topic: str, output_topic: str, 
                            num_records: int) -> List[float]:
        """Produce records and measure end-to-end latency"""
        producer = KafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        consumer = KafkaConsumer(
            output_topic,
            bootstrap_servers=self.kafka_bootstrap,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='latest',
            consumer_timeout_ms=10000,
            group_id='benchmark-consumer'
        )
        
        # Start consumer in background
        latencies = []
        sent_times = {}
        consumer_done = threading.Event()
        
        def consume():
            try:
                for message in consumer:
                    record = message.value
                    if 'id' in record and 'timestamp' in record:
                        record_id = record['id']
                        if record_id in sent_times:
                            latency = (time.time() * 1000) - sent_times[record_id]
                            latencies.append(latency)
                    
                    if len(latencies) >= num_records * 0.9:  # 90% received
                        break
            except Exception as e:
                print(f"Consumer error: {e}")
            finally:
                consumer_done.set()
        
        consumer_thread = threading.Thread(target=consume)
        consumer_thread.start()
        
        time.sleep(2)  # Let consumer connect
        
        # Produce records
        for i in range(num_records):
            record = {
                'id': i,
                'timestamp': time.time() * 1000,
                'value': i
            }
            sent_times[i] = record['timestamp']
            producer.send(input_topic, value=record)
            
            if i % 1000 == 0:
                producer.flush()
        
        producer.flush()
        
        # Wait for consumer
        consumer_done.wait(timeout=30)
        
        producer.close()
        consumer.close()
        
        return latencies
    
    def _produce_keyed_records(self, topic: str, num_records: int):
        """Produce records with keys for stateful operations"""
        producer = KafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        keys = ['key_a', 'key_b', 'key_c', 'key_d', 'key_e']
        
        for i in range(num_records):
            record = {
                'key': keys[i % len(keys)],
                'value': i,
                'timestamp': int(time.time() * 1000)
            }
            producer.send(topic, value=record)
            
            if i % 500 == 0:
                producer.flush()
        
        producer.flush()
        producer.close()
    
    def _produce_continuous(self, topic: str, duration_seconds: int) -> int:
        """Produce records continuously for specified duration"""
        producer = KafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            linger_ms=10,  # Batch for throughput
            batch_size=32768
        )
        
        start_time = time.time()
        count = 0
        
        while time.time() - start_time < duration_seconds:
            record = {
                'id': count,
                'value': count,
                'timestamp': int(time.time() * 1000)
            }
            producer.send(topic, value=record)
            count += 1
            
            if count % 1000 == 0:
                producer.flush()
        
        producer.flush()
        producer.close()
        
        return count
    
    def _submit_simple_job(self, input_topic: str, output_topic: str) -> str:
        """Submit a simple stateless job"""
        # Note: This is a placeholder - actual job submission would require
        # generating a proper JobGraph pickle file
        print("⚠️  Note: Job submission requires pre-generated job file")
        print("    For now, manually submit a job or implement job generation")
        return None
    
    def _submit_stateful_job(self, input_topic: str, output_topic: str) -> str:
        """Submit a stateful job with windowing"""
        print("⚠️  Note: Job submission requires pre-generated job file")
        return None
    
    def _measure_checkpoint(self, job_id: str) -> float:
        """Trigger checkpoint and measure duration"""
        try:
            start = time.time()
            response = requests.post(
                f"{self.jobmanager_url}/jobs/{job_id}/savepoint",
                timeout=60
            )
            if response.status_code == 200:
                duration = time.time() - start
                return duration
        except Exception as e:
            print(f"Checkpoint measurement failed: {e}")
        return 0.0
    
    def _get_job_metrics(self, job_id: str) -> Dict[str, Any]:
        """Get job metrics from JobManager"""
        try:
            response = requests.get(
                f"{self.jobmanager_url}/jobs/{job_id}/metrics",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Failed to get metrics: {e}")
        return {}
    
    def _cancel_job(self, job_id: str):
        """Cancel a running job"""
        if not job_id:
            return
        try:
            requests.post(f"{self.jobmanager_url}/jobs/{job_id}/cancel", timeout=10)
            print(f"✓ Job {job_id} cancelled")
        except Exception as e:
            print(f"Failed to cancel job: {e}")
    
    def check_cluster_status(self) -> bool:
        """Verify cluster is running and healthy"""
        print("Checking cluster status...")
        try:
            response = requests.get(
                f"{self.jobmanager_url}/cluster/metrics",
                timeout=5
            )
            if response.status_code == 200:
                metrics = response.json()
                print(f"✓ JobManager reachable")
                print(f"  TaskManagers: {metrics.get('active_task_managers', 0)}")
                print(f"  Available slots: {metrics.get('available_slots', 0)}")
                return metrics.get('active_task_managers', 0) > 0
            else:
                print(f"✗ JobManager returned status {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Cannot reach JobManager: {e}")
            return False
    
    def print_summary(self):
        """Print benchmark summary"""
        print("\n" + "="*70)
        print("BENCHMARK SUMMARY")
        print("="*70)
        
        if not self.results:
            print("No benchmarks completed successfully")
            return
        
        print("\n📈 Performance Results:")
        
        if 'simple_pipeline' in self.results:
            r = self.results['simple_pipeline']
            print(f"\n  Simple Pipeline (Stateless):")
            print(f"    Latency P99: {r['latency']['p99']:.2f} ms")
            print(f"    Throughput:  {r['throughput']:,.0f} rec/s")
        
        if 'stateful_pipeline' in self.results:
            r = self.results['stateful_pipeline']
            print(f"\n  Stateful Pipeline (Windows):")
            print(f"    Throughput:       {r['throughput']:,.0f} rec/s")
            print(f"    Checkpoint time:  {r['checkpoint_duration']:.2f} s")
        
        if 'high_throughput' in self.results:
            r = self.results['high_throughput']
            print(f"\n  Maximum Sustained Throughput:")
            print(f"    Peak throughput:  {r['throughput']:,.0f} rec/s")
        
        print("\n" + "="*70)
        print("\n💡 Realistic Expectations for Distributed Systems:")
        print("   • Stateless latency (P99):  10-50 ms")
        print("   • Stateful latency (P99):   50-200 ms")
        print("   • Throughput per core:      10,000-100,000 rec/s")
        print("   • Checkpoint duration:      1-30 seconds")
        print("="*70)


def main():
    """Run realistic benchmarks"""
    print("\n🚀 Realistic End-to-End Benchmark")
    print("="*70)
    
    benchmark = RealisticBenchmark()
    
    # Check cluster is running
    if not benchmark.check_cluster_status():
        print("\n❌ ERROR: Cluster is not running!")
        print("\nTo start the cluster:")
        print("  cd deployment")
        print("  docker-compose up -d")
        print("\nWait 30 seconds for services to start, then retry.")
        return 1
    
    print("\n⚠️  IMPORTANT: This benchmark measures REAL distributed system performance")
    print("   It includes:")
    print("   • Kafka producer/consumer overhead")
    print("   • Network serialization")
    print("   • gRPC communication")
    print("   • State persistence")
    print("   • Checkpoint coordination")
    
    try:
        # Run benchmarks
        # benchmark.benchmark_simple_pipeline(num_records=5000)
        # benchmark.benchmark_stateful_pipeline(num_records=3000)
        # benchmark.benchmark_high_throughput(duration_seconds=20)
        
        print("\n⚠️  Note: Job submission not yet implemented in this script")
        print("   To run full benchmarks:")
        print("   1. Submit your job manually using examples/word_count.py")
        print("   2. Modify this script to use your actual job file")
        print("   3. Or implement job generation in _submit_*_job() methods")
        
        # Print summary
        benchmark.print_summary()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
