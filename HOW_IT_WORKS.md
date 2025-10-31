# How the Stream Processing Platform Works

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Explained](#architecture-explained)
3. [How Data Flows](#how-data-flows)
4. [Fault Tolerance Mechanism](#fault-tolerance-mechanism)
5. [How to Use the Platform](#how-to-use-the-platform)
6. [Building Your First Job](#building-your-first-job)
7. [Advanced Features](#advanced-features)
8. [Troubleshooting](#troubleshooting)

---

## System Overview

This is a **distributed stream processing platform** similar to Apache Flink. Think of it as a system that can:
- Process millions of events per second
- Never lose data, even when servers crash (exactly-once semantics)
- Handle real-time analytics, monitoring, and event processing
- Automatically recover from failures

### Real-World Use Cases

**Example 1: Real-Time Analytics**
```
User clicks on website → Kafka → Stream Processing → Dashboard
                                   ↓
                    Count clicks per page per minute
                    Detect trending pages
                    Alert on anomalies
```

**Example 2: Fraud Detection**
```
Credit card transactions → Kafka → Stream Processing → Alert system
                                    ↓
                    Detect unusual patterns
                    Flag suspicious activity
                    Block fraudulent charges
```

**Example 3: IoT Monitoring**
```
Sensor readings → Kafka → Stream Processing → Database/Alerts
                           ↓
           Aggregate temperature per zone
           Detect equipment failures
           Trigger maintenance alerts
```

---

## Architecture Explained

### The Big Picture

```
┌─────────────────────────────────────────────────────┐
│                   YOUR APPLICATION                   │
│  (Python code defining the processing logic)        │
└──────────────────┬──────────────────────────────────┘
                   │ Submit Job
                   ↓
┌─────────────────────────────────────────────────────┐
│                   JOBMANAGER                         │
│  (The "Boss" - coordinates everything)              │
│  • Schedules tasks                                   │
│  • Monitors health                                   │
│  • Manages checkpoints                               │
└──────────────────┬──────────────────────────────────┘
                   │ Commands
                   ↓
┌─────────────────────────────────────────────────────┐
│               TASKMANAGERS (Workers)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Worker 1 │  │ Worker 2 │  │ Worker 3 │          │
│  │ 4 slots  │  │ 4 slots  │  │ 4 slots  │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│  (Actually process the data)                         │
└──────────────────┬──────────────────────────────────┘
                   │ Read/Write
                   ↓
┌─────────────────────────────────────────────────────┐
│                  DATA SOURCES                        │
│  • Kafka (message queue)                             │
│  • PostgreSQL (metadata)                             │
│  • S3 (checkpoints)                                  │
└─────────────────────────────────────────────────────┘
```

### Components Explained Simply

#### 1. **JobManager** (The Control Tower)
Think of it as an airport control tower:
- **What it does**: Coordinates everything, makes decisions
- **Responsibilities**:
  - Accepts your job (the processing logic you write)
  - Breaks it into tasks
  - Assigns tasks to workers
  - Monitors worker health
  - Triggers checkpoints for fault tolerance

**REST API** (Port 8081):
```bash
# Submit a job
POST /jobs/submit

# Check job status
GET /jobs/{job_id}/status

# Cancel a job
POST /jobs/{job_id}/cancel

# View cluster health
GET /cluster/metrics
```

#### 2. **TaskManager** (The Workers)
Think of them as assembly line workers:
- **What they do**: Execute the actual data processing
- **Each has**:
  - 4 "slots" (can run 4 tasks in parallel)
  - Memory for processing
  - Storage for state (using RocksDB)

**How they work**:
1. Receive tasks from JobManager
2. Process streaming data
3. Maintain state (e.g., counts, sums)
4. Send results downstream
5. Report health back to JobManager

#### 3. **Kafka** (The Data Highway)
Think of it as a highway with lanes:
- **What it does**: Reliably transports messages
- **Why we need it**:
  - Decouples data producers from consumers
  - Provides durability (messages stored on disk)
  - Enables replay (can go back in time)
  - Scales horizontally

#### 4. **PostgreSQL** (The Memory Bank)
Stores metadata:
- Job definitions
- Checkpoint information
- Job status and history

#### 5. **RocksDB** (The Fast Cache)
Local storage on each TaskManager:
- Stores operator state (counts, aggregations, etc.)
- Very fast (embedded database)
- Supports snapshots for checkpoints

#### 6. **S3** (The Backup Vault)
Cloud storage for fault tolerance:
- Checkpoint snapshots stored here
- Used for recovery after failures
- Durable and replicated

---

## How Data Flows

### Step-by-Step: Processing a Word Count

Let's trace how "hello world" gets counted:

```
Input: "hello world hello"

Step 1: SOURCE (Kafka)
┌────────────────────┐
│ "hello world hello"│ ← Read from Kafka topic
└─────────┬──────────┘
          │
          ↓
Step 2: FLAT_MAP (Split into words)
┌───────┐ ┌───────┐ ┌───────┐
│"hello"│ │"world"│ │"hello"│
└───┬───┘ └───┬───┘ └───┬───┘
    │         │         │
    └─────────┼─────────┘
              ↓
Step 3: MAP (Create tuples)
┌──────────┐ ┌──────────┐ ┌──────────┐
│("hello",1)│ │("world",1)│ │("hello",1)│
└─────┬────┘ └─────┬────┘ └─────┬────┘
      │            │            │
      └────────────┼────────────┘
                   ↓
Step 4: KEY_BY (Partition by word)
        ┌──────────────────┐
        │  Partitioning    │
        └──────────────────┘
              ↓         ↓
    TaskManager 1   TaskManager 2
    "hello" → TM1   "world" → TM2
              ↓         ↓
Step 5: WINDOW (10-second tumbling)
    [Accumulate for 10s]
              ↓         ↓
Step 6: REDUCE (Sum counts)
    ┌──────────┐   ┌──────────┐
    │("hello",2)│   │("world",1)│
    └─────┬────┘   └─────┬────┘
          │              │
          └──────┬───────┘
                 ↓
Step 7: FILTER (Count > 5)
    [Applied per record]
                 ↓
Step 8: SINK (Kafka)
    Write to output topic
```

### Parallelism in Action

With parallelism=4, the work is distributed:

```
                    JobManager
                        │
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
   TaskManager 1   TaskManager 2   TaskManager 3
   ┌─────────┐     ┌─────────┐     ┌─────────┐
   │ Slot 1  │     │ Slot 1  │     │ Slot 1  │
   │ Source  │     │ Map     │     │ Reduce  │
   ├─────────┤     ├─────────┤     ├─────────┤
   │ Slot 2  │     │ Slot 2  │     │ Slot 2  │
   │ FlatMap │     │ KeyBy   │     │ Filter  │
   ├─────────┤     ├─────────┤     ├─────────┤
   │ Slot 3  │     │ Slot 3  │     │ Slot 3  │
   │ Window  │     │ Reduce  │     │ Sink    │
   ├─────────┤     ├─────────┤     ├─────────┤
   │ Slot 4  │     │ Slot 4  │     │ Slot 4  │
   │ (idle)  │     │ (idle)  │     │ (idle)  │
   └─────────┘     └─────────┘     └─────────┘
```

---

## Fault Tolerance Mechanism

### The Problem
What happens if a TaskManager crashes while processing data?
- We could lose data
- We could process the same data twice
- We could get incorrect results

### The Solution: Checkpointing

Our platform uses **Chandy-Lamport snapshots** for exactly-once semantics.

#### How Checkpoints Work

**Every 10 seconds** (configurable):

```
Step 1: JobManager triggers checkpoint
┌────────────┐
│ JobManager │ → "Start Checkpoint #42!"
└────────────┘
      ↓ (inject barriers)

Step 2: Barriers flow through the pipeline
[Source] → barrier → [Map] → barrier → [Window] → barrier → [Sink]
   │                    │                   │
   ↓                    ↓                   ↓
Save Kafka          (stateless,         Save window
  offsets          no state to save)      contents

Step 3: Each operator saves its state
• Kafka Source: "I read up to offset 1234"
• Window Operator: "I have 50 records in current window"
• All state → Upload to S3

Step 4: Everyone reports back
TaskManager 1 → "Checkpoint #42 done! State at s3://..."
TaskManager 2 → "Checkpoint #42 done! State at s3://..."
TaskManager 3 → "Checkpoint #42 done! State at s3://..."

Step 5: JobManager commits
"Checkpoint #42 is complete!" → Write to PostgreSQL
```

#### Recovery After Failure

```
Time: 10:00:00 - Checkpoint #42 completes
Time: 10:00:05 - TaskManager 2 CRASHES! 💥
Time: 10:00:06 - JobManager detects failure (missed heartbeat)

Recovery Process:
1. Cancel all tasks
2. Query PostgreSQL: "What's the latest checkpoint?"
   → Checkpoint #42 (5 seconds ago)
3. Download state from S3
4. Reschedule tasks on available TaskManagers
5. Restore state:
   • Kafka: Seek to offset 1234
   • Windows: Restore 50 buffered records
6. Resume processing

Result: Zero data loss, no duplicates!
```

### Exactly-Once Guarantees

**How we achieve it**:

1. **Kafka Integration**:
   ```python
   # Source: Store offsets in checkpoint
   checkpoint = {
       'partition_0': 1234,
       'partition_1': 5678
   }

   # After checkpoint completes, commit to Kafka
   consumer.commit(offsets)
   ```

2. **State Snapshots**:
   ```python
   # Before checkpoint
   window_state = {
       'hello': [1, 1, 1],  # 3 occurrences
       'world': [1]         # 1 occurrence
   }

   # Snapshot to S3
   s3.upload('state.bin', pickle.dumps(window_state))
   ```

3. **Barrier Alignment**:
   ```
   Input 1: [record, record, BARRIER, record]
   Input 2: [record, BARRIER, record, record]
                        ↓
   Operator waits for BOTH barriers before snapshotting
   Buffers late records until alignment
   ```

---

## How to Use the Platform

### Prerequisites

```bash
# Check you have:
docker --version        # Docker 20.10+
docker-compose --version # Docker Compose 2.0+
python3 --version       # Python 3.9+
```

### Step 1: Start the Platform

```bash
cd /Users/uditanshutomar/stream-processing-platform/deployment
docker-compose up -d
```

**What this starts**:
- 1 JobManager (the boss)
- 3 TaskManagers (the workers)
- 1 Kafka broker (message queue)
- 1 Zookeeper (Kafka coordinator)
- 1 PostgreSQL (metadata storage)
- 1 Prometheus (metrics collection)
- 1 Grafana (visualization)

**Wait for services to be ready** (30-60 seconds):
```bash
docker-compose ps
# All should show "Up" or "Up (healthy)"
```

### Step 2: Verify the Cluster

```bash
# Check cluster health
curl http://localhost:8081/cluster/metrics
```

**Expected response**:
```json
{
  "total_task_managers": 3,
  "active_task_managers": 3,
  "total_slots": 12,
  "available_slots": 12,
  "utilization": 0.0,
  "total_jobs": 0,
  "running_jobs": 0
}
```

✅ **You have 12 available slots** (3 TaskManagers × 4 slots each)

### Step 3: Prepare Kafka Topics

```bash
# Create input topic
docker exec stream-kafka kafka-topics \
  --create --topic input-text \
  --bootstrap-server localhost:9092 \
  --partitions 4 --replication-factor 1

# Create output topic
docker exec stream-kafka kafka-topics \
  --create --topic word-count-output \
  --bootstrap-server localhost:9092 \
  --partitions 4 --replication-factor 1

# Verify topics created
docker exec stream-kafka kafka-topics \
  --list --bootstrap-server localhost:9092
```

---

## Building Your First Job

### Understanding the Job Structure

A streaming job has:
1. **Source**: Where data comes from (Kafka, files, databases)
2. **Transformations**: What you do with the data (map, filter, aggregate)
3. **Sink**: Where results go (Kafka, databases, files)

### Example 1: Simple Filter Job

**Goal**: Filter messages containing the word "error"

```python
# error_filter.py
from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from common.config import Config

# Define the filter function
def contains_error(message):
    return 'error' in message.lower()

# Create execution environment
env = StreamExecutionEnvironment("ErrorFilter")
env.set_parallelism(2).enable_checkpointing(10000)

# Define source
source = KafkaSourceOperator(
    topic="input-text",
    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
    group_id="error-filter-group"
)

# Build pipeline
result = env.add_source(source) \
    .filter(contains_error)

# Define sink
sink = KafkaSinkOperator(
    topic="errors-output",
    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
)

result.add_sink(sink)

# Serialize job
import pickle
with open('error_filter_job.pkl', 'wb') as f:
    pickle.dump(env.get_job_graph(), f)

print("Job created: error_filter_job.pkl")
```

**Run it**:
```bash
python3 error_filter.py

# Submit to cluster
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@error_filter_job.pkl"
```

### Example 2: Real-Time Counter

**Goal**: Count events per category every 30 seconds

```python
# category_counter.py
from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from taskmanager.operators.stateful import TumblingWindow
from common.config import Config
import json

# Parse JSON messages
def parse_json(message):
    return json.loads(message)

# Extract category
def get_category(event):
    return event['category']

# Create count tuple
def create_count(event):
    return (event['category'], 1)

# Sum counts
def sum_counts(a, b):
    return (a[0], a[1] + b[1])

# Create environment
env = StreamExecutionEnvironment("CategoryCounter")
env.set_parallelism(4).enable_checkpointing(10000)

# Source
source = KafkaSourceOperator(
    topic="events",
    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
    group_id="category-counter-group"
)

# Pipeline
result = env.add_source(source) \
    .map(parse_json) \
    .map(create_count) \
    .key_by(get_category) \
    .window(TumblingWindow(30000)) \
    .reduce(sum_counts)

# Sink
sink = KafkaSinkOperator(
    topic="category-counts",
    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
)

result.add_sink(sink)

# Serialize
import pickle
with open('category_counter_job.pkl', 'wb') as f:
    pickle.dump(env.get_job_graph(), f)
```

### Example 3: Anomaly Detection

**Goal**: Detect when values exceed a threshold

```python
# anomaly_detector.py
from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator
from common.config import Config
import json

# Parse sensor reading
def parse_reading(message):
    data = json.loads(message)
    return {
        'sensor_id': data['sensor_id'],
        'value': float(data['value']),
        'timestamp': data['timestamp']
    }

# Detect anomaly
def is_anomaly(reading):
    return reading['value'] > 100.0  # Threshold

# Format alert
def create_alert(reading):
    return {
        'alert': 'HIGH_VALUE',
        'sensor_id': reading['sensor_id'],
        'value': reading['value'],
        'threshold': 100.0,
        'timestamp': reading['timestamp']
    }

# Environment
env = StreamExecutionEnvironment("AnomalyDetector")
env.set_parallelism(2).enable_checkpointing(5000)

# Source
source = KafkaSourceOperator(
    topic="sensor-readings",
    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
    group_id="anomaly-detector-group"
)

# Pipeline
alerts = env.add_source(source) \
    .map(parse_reading) \
    .filter(is_anomaly) \
    .map(create_alert)

# Sink
sink = KafkaSinkOperator(
    topic="alerts",
    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
)

alerts.add_sink(sink)

# Serialize
import pickle
with open('anomaly_detector_job.pkl', 'wb') as f:
    pickle.dump(env.get_job_graph(), f)
```

---

## Advanced Features

### 1. Windowing

Windows group events by time for aggregation:

**Tumbling Windows** (non-overlapping):
```python
# Every 10 seconds, emit results
TumblingWindow(10000)

Timeline:
[0-10s] [10-20s] [20-30s] [30-40s]
  10 events → emit
           10 events → emit
                    15 events → emit
```

**Sliding Windows** (overlapping):
```python
# 30-second window, slides every 10 seconds
SlidingWindow(size_ms=30000, slide_ms=10000)

Timeline:
[0-30s] = Window 1
   [10-40s] = Window 2
      [20-50s] = Window 3
```

**Session Windows** (gap-based):
```python
# Group events with <5 second gaps
SessionWindow(gap_ms=5000)

Events at: 0s, 2s, 3s, 10s, 12s
Windows:   [0-8s]     [10-17s]
           (3 events) (2 events)
```

### 2. State Management

Keep data across events:

```python
from taskmanager.operators.stateful import KeyedProcessOperator

def process_with_state(key, value, state):
    # state is a dictionary you can modify
    if state is None:
        state = {'count': 0, 'sum': 0}

    state['count'] += 1
    state['sum'] += value

    avg = state['sum'] / state['count']

    return [(key, avg)]

operator = KeyedProcessOperator(process_with_state)
```

### 3. Watermarks (Event Time Processing)

Handle out-of-order events:

```python
from common.watermarks import WatermarkStrategies

# Allow 5 seconds of out-of-orderness
strategy = WatermarkStrategies.bounded_out_of_orderness(5000)

source = KafkaSourceOperator(
    topic="events",
    bootstrap_servers="kafka:9092",
    group_id="my-group",
    watermark_strategy=strategy  # Add watermarks
)
```

**How it works**:
```
Events arrive: ts=100, ts=102, ts=98, ts=105
Watermark = max(105) - 5 = 100

When watermark reaches 110:
→ Trigger window [100-110]
→ Late events with ts<100 are dropped
```

### 4. Monitoring Your Jobs

**Prometheus Metrics** (http://localhost:9090):
```promql
# Throughput
rate(records_processed_total[1m])

# Latency (95th percentile)
histogram_quantile(0.95, processing_latency_seconds)

# Backpressure
backpressure_ratio
```

**Grafana Dashboards** (http://localhost:3000):
- Login: admin/admin
- View throughput, latency, errors
- Set up alerts

**JobManager API**:
```bash
# Job status
curl http://localhost:8081/jobs/{job_id}/status

# Job metrics
curl http://localhost:8081/jobs/{job_id}/metrics

# Cluster metrics
curl http://localhost:8081/cluster/metrics
```

---

## Troubleshooting

### Problem: Job submission fails

**Symptoms**:
```json
{
  "detail": "No available TaskManagers for scheduling"
}
```

**Solution**:
```bash
# Check TaskManagers are running
curl http://localhost:8081/taskmanagers

# Restart if needed
docker-compose restart taskmanager1 taskmanager2 taskmanager3
```

### Problem: No output from job

**Check list**:

1. **Kafka topics exist**:
   ```bash
   docker exec stream-kafka kafka-topics --list \
     --bootstrap-server localhost:9092
   ```

2. **Data is being sent to input topic**:
   ```bash
   docker exec stream-kafka kafka-console-consumer \
     --bootstrap-server localhost:9092 \
     --topic input-text --from-beginning
   ```

3. **Job is running**:
   ```bash
   curl http://localhost:8081/jobs/{job_id}/status
   # Should show "RUNNING"
   ```

4. **Check TaskManager logs**:
   ```bash
   docker-compose logs -f taskmanager1
   ```

### Problem: High latency

**Causes & Solutions**:

1. **Insufficient parallelism**:
   ```python
   env.set_parallelism(8)  # Increase from 4
   ```

2. **Too frequent checkpoints**:
   ```python
   env.enable_checkpointing(30000)  # Increase from 10000
   ```

3. **Large state**:
   - Increase TaskManager memory
   - Optimize state usage
   - Use state TTL

### Problem: TaskManager crashes

**Check**:
```bash
# Memory usage
docker stats

# Logs for errors
docker logs stream-taskmanager-1
```

**Solutions**:
- Increase memory: Edit `docker-compose.yml`
- Reduce parallelism
- Optimize operators

---

## Quick Reference

### Common Commands

```bash
# Start platform
cd deployment && docker-compose up -d

# Stop platform
docker-compose down

# View logs
docker-compose logs -f jobmanager
docker-compose logs -f taskmanager1

# Restart service
docker-compose restart jobmanager

# Scale TaskManagers
docker-compose up -d --scale taskmanager1=5

# Create Kafka topic
docker exec stream-kafka kafka-topics \
  --create --topic my-topic \
  --bootstrap-server localhost:9092 \
  --partitions 4 --replication-factor 1

# Send test data
echo "hello world" | docker exec -i stream-kafka \
  kafka-console-producer --broker-list localhost:9092 \
  --topic input-text

# Read output
docker exec stream-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic word-count-output --from-beginning

# Submit job
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@my_job.pkl"

# Check job status
curl http://localhost:8081/jobs/{job_id}/status

# Cancel job
curl -X POST http://localhost:8081/jobs/{job_id}/cancel
```

### API Endpoints

```
GET  /                           - Health check
GET  /jobs                       - List all jobs
POST /jobs/submit                - Submit new job
GET  /jobs/{id}/status           - Get job status
POST /jobs/{id}/cancel           - Cancel job
GET  /jobs/{id}/metrics          - Get job metrics
POST /jobs/{id}/savepoint        - Create savepoint
GET  /taskmanagers               - List TaskManagers
GET  /cluster/metrics            - Cluster metrics
```

---

## Summary

**What you learned**:
1. ✅ How the architecture works (JobManager + TaskManagers)
2. ✅ How data flows through the system
3. ✅ How fault tolerance works (checkpoints)
4. ✅ How to start the platform
5. ✅ How to build and submit jobs
6. ✅ How to monitor and troubleshoot

**Next steps**:
- Try the examples in `examples/`
- Build your own streaming job
- Explore the API with `docs/api_reference.md`
- Deploy to production with `docs/deployment_guide.md`

**Need help?**
- Documentation: `docs/`
- Examples: `examples/`
- Tests: Run `pytest tests/` to see how components work
- Benchmarks: Run `python scripts/benchmark.py`

---

**The platform is ready to process your real-time data streams!** 🚀
