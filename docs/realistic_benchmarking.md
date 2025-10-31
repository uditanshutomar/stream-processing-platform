# Realistic Performance Benchmarking Guide

## Overview

This guide explains how to perform realistic end-to-end performance benchmarks on your distributed stream processing platform. Unlike unit benchmarks that test individual operators in isolation, these benchmarks measure actual distributed system performance including all real-world overheads.

## What Makes a Benchmark "Realistic"?

### ❌ Unrealistic Benchmarks (Unit Tests)
The existing `scripts/benchmark.py` measures:
- Pure Python function execution in a single process
- No network communication
- No serialization/deserialization
- No distributed system overhead
- **Result**: Inflated metrics (millions of records/second, sub-microsecond latency)

### ✅ Realistic Benchmarks (End-to-End)
The new `scripts/realistic_benchmark.py` measures:
- **Kafka I/O**: Producer and consumer overhead (5-50ms typical)
- **Network serialization**: Protobuf encoding/decoding
- **gRPC communication**: Inter-process RPC calls (1-5ms)
- **State persistence**: RocksDB disk writes (1-10ms)
- **Checkpoint coordination**: Distributed snapshot overhead (1-30s)
- **Multi-process overhead**: Actual distributed execution

## Realistic Performance Expectations

For a production Flink-like system running on typical hardware:

| Metric | Realistic Range | Notes |
|--------|----------------|-------|
| **Stateless Pipeline Latency (P99)** | 10-50 ms | Including Kafka + network |
| **Stateful Pipeline Latency (P99)** | 50-200 ms | With state operations |
| **Throughput per CPU core** | 10K-100K rec/s | Depends on operation complexity |
| **Checkpoint Duration** | 1-30 seconds | For GB-scale state |
| **Recovery Time** | 10-60 seconds | From TaskManager failure |

### Real-World Examples

**Apache Flink** (production deployments):
- Typical throughput: 50K-200K events/sec per core (stateless)
- With windowing: 20K-80K events/sec per core
- Latency (P99): 20-100ms for simple pipelines
- Checkpoint time: 2-15 seconds for multi-GB state

**Your Platform** (realistic expectations):
- Python overhead: ~2-5x slower than Java (Flink)
- Expected throughput: 10K-50K events/sec per core
- Expected latency: 20-150ms (stateless), 100-500ms (stateful)

## Running Realistic Benchmarks

### Prerequisites

1. **Start the full Docker Compose cluster**:
   ```bash
   cd deployment
   docker-compose up -d
   ```

2. **Wait for services to be ready** (~30 seconds):
   ```bash
   # Check cluster health
   curl http://localhost:8081/cluster/metrics
   ```

3. **Install Kafka Python client**:
   ```bash
   pip install kafka-python-ng
   ```

### Step 1: Generate Benchmark Jobs

```bash
cd scripts
python3 generate_benchmark_jobs.py
```

This creates three job files:
- `benchmark_simple_pipeline.pkl` - Stateless (Map → Filter)
- `benchmark_stateful_pipeline.pkl` - Stateful (KeyBy → Window → Aggregate)
- `benchmark_high_throughput.pkl` - Optimized throughput test

### Step 2: Submit a Benchmark Job

```bash
# Submit simple pipeline
curl -X POST http://localhost:8081/jobs/submit \
  -F 'job_file=@benchmark_simple_pipeline.pkl'

# Note the job_id from response
```

### Step 3: Run End-to-End Benchmark

**Option A: Manual Testing**

1. **Produce test data** to Kafka:
   ```python
   from kafka import KafkaProducer
   import json
   import time
   
   producer = KafkaProducer(
       bootstrap_servers='localhost:9092',
       value_serializer=lambda v: json.dumps(v).encode('utf-8')
   )
   
   # Send 10,000 records
   start = time.time()
   for i in range(10000):
       record = {
           'id': i,
           'value': i,
           'timestamp': int(time.time() * 1000)
       }
       producer.send('bench-simple-input', value=record)
       
       if i % 1000 == 0:
           producer.flush()
   
   producer.flush()
   duration = time.time() - start
   
   print(f"Sent 10,000 records in {duration:.2f} seconds")
   print(f"Throughput: {10000/duration:.0f} records/second")
   ```

2. **Consume and measure latency**:
   ```python
   from kafka import KafkaConsumer
   import json
   
   consumer = KafkaConsumer(
       'bench-simple-output',
       bootstrap_servers='localhost:9092',
       value_deserializer=lambda v: json.loads(v.decode('utf-8')),
       auto_offset_reset='earliest',
       group_id='benchmark-consumer'
   )
   
   count = 0
   for message in consumer:
       count += 1
       if count >= 10000:
           break
   
   print(f"Received {count} records")
   ```

**Option B: Automated Benchmark (Future)**

```bash
# Note: Full automation requires job submission integration
python3 realistic_benchmark.py
```

### Step 4: Monitor Performance

**Check job metrics**:
```bash
curl http://localhost:8081/jobs/{job_id}/metrics
```

**View in Grafana**:
- Open http://localhost:3000 (admin/admin)
- View pre-configured dashboards

**Check Prometheus metrics**:
- Open http://localhost:9090
- Query: `records_processed_total`, `processing_latency_seconds`

## Benchmark Scenarios

### 1. Latency Benchmark (Simple Pipeline)

**Goal**: Measure end-to-end latency for stateless operations

**Job**: Kafka → Map → Filter → Kafka

**Metrics**:
- P50, P95, P99 latency
- Expected: 10-50ms P99

**How to measure**:
- Embed timestamp in each record
- Calculate latency at output: `receive_time - send_time`

### 2. Stateful Pipeline Benchmark

**Goal**: Measure performance with state operations and checkpoints

**Job**: Kafka → KeyBy → Window (10s) → Aggregate → Kafka

**Metrics**:
- Throughput with state
- Checkpoint duration
- Expected: 5K-30K records/sec, 2-15s checkpoints

### 3. Maximum Throughput Benchmark

**Goal**: Measure peak sustained throughput

**Job**: Optimized pipeline with operator chaining

**Metrics**:
- Maximum records/second
- Backpressure indicators
- Expected: 20K-100K records/sec (all cores combined)

### 4. Chaos/Recovery Benchmark

**Goal**: Measure fault tolerance and recovery time

**Test**:
1. Submit job with checkpointing enabled
2. Kill a TaskManager: `docker kill taskmanager-1`
3. Measure recovery time
4. Verify no data loss (exactly-once)

**Metrics**:
- Recovery time
- Data loss (should be zero)
- Expected: 10-60 second recovery

## Understanding Your Results

### Comparing to Unit Benchmarks

Your unit benchmarks (`scripts/benchmark.py`) show:
- MapOperator: 3.96M records/second
- Latency: 0.0004ms

**These are NOT realistic** because they:
1. Don't include network overhead
2. Don't include Kafka I/O
3. Don't include serialization
4. Run in a single Python process

**Realistic benchmarks will show**:
- 10-100x slower throughput (still good!)
- 100-1000x higher latency (milliseconds, not microseconds)
- This is NORMAL for distributed systems

### Performance Breakdown

For a typical record flowing through your system:

```
Total End-to-End Latency: ~30-100ms
├── Kafka produce:        5-20ms
├── Network transfer:     1-5ms
├── gRPC receive:         1-3ms
├── Deserialization:      0.5-2ms
├── Operator processing:  0.1-1ms  ← Your unit benchmark measures this
├── Serialization:        0.5-2ms
├── gRPC send:            1-3ms
├── Network transfer:     1-5ms
└── Kafka consume:        5-20ms
```

**Your unit benchmark only measures the "Operator processing" line (0.1-1ms)!**

The other 95%+ of latency comes from distributed system overhead.

## Optimization Tips

If your realistic benchmarks show poor performance:

### For Low Throughput
1. **Increase parallelism**: More TaskManager slots
2. **Enable operator chaining**: Reduces serialization
3. **Tune Kafka**: Increase batch size, adjust linger.ms
4. **Buffer tuning**: Increase buffer pool size

### For High Latency
1. **Reduce checkpoint frequency**: Less coordination overhead
2. **Optimize network**: Lower latency links, same datacenter
3. **Tune buffer settings**: Balance memory vs latency
4. **Profile operators**: Find slow operations

### For Checkpoint Duration
1. **Use RocksDB incremental**: Only snapshot changes
2. **Increase state backend buffer**: Faster snapshots
3. **Optimize S3 writes**: Multi-part upload, parallel writes
4. **Reduce state size**: TTL, compaction

## Troubleshooting

### "Throughput much lower than expected"

**Check**:
1. Is Kafka the bottleneck? Test with direct Kafka producer
2. Are TaskManagers underutilized? Check CPU/memory metrics
3. Is there backpressure? Check flow control metrics
4. Network bandwidth saturated? Monitor network I/O

### "High latency spikes"

**Common causes**:
1. Garbage collection pauses (Python GC)
2. RocksDB compaction
3. Network congestion
4. Checkpoint coordination

**Solutions**:
- Monitor GC with metrics
- Tune RocksDB compaction
- Increase buffer sizes
- Reduce checkpoint frequency

### "Job keeps failing"

**Check**:
1. TaskManager logs: `docker logs taskmanager-1`
2. JobManager logs: `docker logs jobmanager`
3. Kafka connectivity: Can TaskManagers reach Kafka?
4. Resource limits: Sufficient memory/CPU?

## Reporting Performance

When sharing benchmark results, always include:

1. **Hardware specs**: CPU cores, RAM, disk type
2. **Cluster configuration**: TaskManagers, slots per TM
3. **Job configuration**: Parallelism, checkpointing settings
4. **Workload details**: Record size, operation complexity
5. **All overhead included**: Kafka, network, serialization
6. **Percentiles**: P50, P95, P99 (not just average)

**Example**:
```
Hardware: 4-core CPU, 16GB RAM, SSD
Cluster: 3 TaskManagers × 4 slots = 12 total slots
Job: Simple pipeline (Map→Filter), parallelism=8
Records: 100KB total, 100 bytes per record
Checkpoints: Every 10 seconds

Results:
- Throughput: 45,000 records/second
- Latency P50: 12ms, P95: 28ms, P99: 45ms
- Checkpoint duration: 3.2 seconds
- Includes: Kafka + network + all distributed overhead
```

## Conclusion

**Remember**: Distributed systems are inherently slower than in-process operations, but they provide:
- Fault tolerance
- Horizontal scalability
- Exactly-once processing
- State management

Your "slow" 30ms latency is actually **excellent** for a distributed system that guarantees exactly-once semantics!

The unit benchmarks measuring microseconds are useful for comparing operator implementations, but **only end-to-end benchmarks reflect real production performance**.
