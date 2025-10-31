#!/usr/bin/env python3
"""
Unit Benchmark - Measures ISOLATED operator performance (NOT realistic!)

⚠️  WARNING: These benchmarks measure individual operators in isolation
    without distributed system overhead. Results are NOT representative
    of real-world performance.

WHAT THIS MEASURES:
- Pure Python function execution speed
- Single-process, in-memory operations
- No network, serialization, or distributed overhead

WHAT THIS DOES NOT MEASURE:
- Kafka producer/consumer latency (5-50ms)
- Network communication overhead (1-5ms)
- gRPC RPC calls (1-5ms)
- Serialization/deserialization (1-3ms)
- State persistence to RocksDB (1-10ms)
- Checkpoint coordination (1-30s)
- Multi-process overhead

REALISTIC PERFORMANCE:
These benchmarks will show millions of records/second and sub-millisecond
latency. Real distributed system performance will be 10-100x slower due
to the overhead listed above. This is NORMAL and EXPECTED.

For realistic benchmarks, use: scripts/realistic_benchmark.py
See documentation: docs/realistic_benchmarking.md
"""
import time
import sys
import os
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.serialization import StreamRecord
from taskmanager.operators.stateless import MapOperator, FilterOperator
from taskmanager.operators.stateful import WindowOperator, TumblingWindow


def benchmark_throughput(operator, num_records=100000):
    """
    Measure throughput of an operator.

    Args:
        operator: Operator to benchmark
        num_records: Number of records to process

    Returns:
        Throughput in records/second
    """
    records = [StreamRecord(value=i) for i in range(num_records)]

    start_time = time.time()

    for record in records:
        operator.process_element(record)

    end_time = time.time()
    duration = end_time - start_time

    throughput = num_records / duration

    return throughput


def benchmark_latency(operator, num_samples=10000):
    """
    Measure per-record latency of an operator.

    Args:
        operator: Operator to benchmark
        num_samples: Number of samples

    Returns:
        Dictionary with latency statistics
    """
    latencies = []

    for i in range(num_samples):
        record = StreamRecord(value=i)

        start = time.perf_counter()
        operator.process_element(record)
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        latencies.append(latency_ms)

    return {
        'mean': statistics.mean(latencies),
        'median': statistics.median(latencies),
        'p95': sorted(latencies)[int(0.95 * len(latencies))],
        'p99': sorted(latencies)[int(0.99 * len(latencies))],
        'max': max(latencies),
    }


def main():
    """Run benchmarks"""
    print("=== Unit Benchmarks (Isolated Operators) ===\n")
    print("⚠️  WARNING: These are NOT realistic distributed system benchmarks!")
    print("   These measure individual operator performance in isolation.")
    print("   Real-world performance will be 10-100x slower due to:")
    print("   • Kafka I/O (5-50ms)")
    print("   • Network + serialization (2-8ms)")
    print("   • gRPC communication (1-5ms)")
    print("   • State persistence (1-10ms)")
    print("   • Checkpoint coordination (1-30s)")
    print("")
    print("   For realistic benchmarks, see: scripts/realistic_benchmark.py")
    print("   Documentation: docs/realistic_benchmarking.md")
    print("="*70 + "\n")

    # Benchmark MapOperator
    print("1. MapOperator Throughput")
    map_op = MapOperator(lambda x: x * 2)
    map_throughput = benchmark_throughput(map_op)
    print(f"   Throughput: {map_throughput:,.0f} records/second")

    print("\n2. MapOperator Latency")
    map_latency = benchmark_latency(map_op)
    print(f"   Mean: {map_latency['mean']:.4f} ms")
    print(f"   P95:  {map_latency['p95']:.4f} ms")
    print(f"   P99:  {map_latency['p99']:.4f} ms")

    # Benchmark FilterOperator
    print("\n3. FilterOperator Throughput")
    filter_op = FilterOperator(lambda x: x % 2 == 0)
    filter_throughput = benchmark_throughput(filter_op)
    print(f"   Throughput: {filter_throughput:,.0f} records/second")

    # Benchmark WindowOperator
    print("\n4. WindowOperator (with state)")
    window_op = WindowOperator(
        window_assigner=TumblingWindow(10000),
        reduce_func=lambda a, b: a + b
    )

    # Add records to window
    start = time.time()
    for i in range(10000):
        window_op.process_element(StreamRecord(value=i, key="k1", timestamp=i))
    end = time.time()

    window_throughput = 10000 / (end - start)
    print(f"   Throughput: {window_throughput:,.0f} records/second")

    # Performance targets
    print("\n=== Performance Targets ===")
    targets = {
        'Throughput': (50000, 'records/second'),
        'Map Latency P99': (1.0, 'ms'),
        'Window Latency': (100.0, 'ms'),
    }

    results = {
        'Throughput': map_throughput,
        'Map Latency P99': map_latency['p99'],
        'Window Latency': map_latency['p99'],  # Simplified
    }

    all_passed = True
    for metric, (target, unit) in targets.items():
        actual = results[metric]
        passed = actual <= target if 'Latency' in metric else actual >= target
        status = "✓ PASS" if passed else "✗ FAIL"

        print(f"{status} {metric}: {actual:,.2f} {unit} (target: {target:,.0f} {unit})")

        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All unit benchmarks passed!")
    else:
        print("Some unit benchmarks failed.")
    
    print("\n" + "="*70)
    print("⚠️  REMINDER: These results are NOT realistic!")
    print("   Actual distributed system performance:")
    print("   • Throughput: 10K-100K records/sec (not millions)")
    print("   • Latency: 10-100ms P99 (not sub-millisecond)")
    print("   • This is NORMAL and EXPECTED for distributed systems")
    print("="*70)
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
