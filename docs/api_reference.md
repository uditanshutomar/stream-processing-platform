# API Reference

## REST API Endpoints

### Job Management

#### Submit Job

```http
POST /jobs/submit
Content-Type: multipart/form-data

Parameters:
  job_file: Binary file containing pickled JobGraph

Response: 200 OK
{
  "job_id": "job_a3f2e9b1",
  "status": "RUNNING"
}
```

**Example**:
```bash
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@word_count_job.pkl"
```

#### Get Job Status

```http
GET /jobs/{job_id}/status

Response: 200 OK
{
  "job_id": "job_a3f2e9b1",
  "status": "RUNNING",
  "start_time": 1698765432000,
  "end_time": null,
  "metrics": {}
}
```

Status values:
- `CREATED`: Job submitted but not yet started
- `RUNNING`: Job actively processing
- `FAILING`: Experiencing failures
- `FAILED`: Job permanently failed
- `CANCELLING`: Cancellation in progress
- `CANCELED`: Job successfully canceled
- `FINISHED`: Job completed successfully

#### Cancel Job

```http
POST /jobs/{job_id}/cancel?with_savepoint=false

Response: 200 OK
{
  "job_id": "job_a3f2e9b1",
  "status": "CANCELED",
  "savepoint_path": null
}
```

Parameters:
- `with_savepoint` (optional): Create savepoint before canceling

#### Get Job Metrics

```http
GET /jobs/{job_id}/metrics

Response: 200 OK
{
  "job_id": "job_a3f2e9b1",
  "throughput": 52341.5,
  "latency_ms": 23.7,
  "backpressure_ratio": 0.12,
  "checkpoint_duration_ms": 847.3
}
```

#### Trigger Savepoint

```http
POST /jobs/{job_id}/savepoint

Response: 200 OK
{
  "checkpoint_id": 42,
  "s3_location": "s3://bucket/checkpoints/job-a3f2e9b1/chk-42"
}
```

#### List Jobs

```http
GET /jobs

Response: 200 OK
{
  "jobs": [
    {
      "job_id": "job_a3f2e9b1",
      "job_name": "WordCount",
      "status": "RUNNING",
      "start_time": 1698765432000
    }
  ]
}
```

### Cluster Management

#### List TaskManagers

```http
GET /taskmanagers

Response: 200 OK
{
  "task_managers": [
    {
      "task_manager_id": "taskmanager-1",
      "host": "172.18.0.5",
      "port": 6124,
      "task_slots": 4,
      "available_slots": 2,
      "status": "active"
    }
  ]
}
```

#### Get Cluster Metrics

```http
GET /cluster/metrics

Response: 200 OK
{
  "total_task_managers": 3,
  "active_task_managers": 3,
  "total_slots": 12,
  "available_slots": 8,
  "utilization": 0.33,
  "total_jobs": 2,
  "running_jobs": 1
}
```

## Python API

### StreamExecutionEnvironment

Entry point for defining streaming jobs.

```python
from jobmanager.job_graph import StreamExecutionEnvironment

env = StreamExecutionEnvironment("JobName")
```

#### Methods

**`set_parallelism(parallelism: int)`**
```python
env.set_parallelism(4)  # Set default parallelism
```

**`enable_checkpointing(interval_ms: int)`**
```python
env.enable_checkpointing(10000)  # 10 second checkpoints
```

**`add_source(source_operator)`**
```python
stream = env.add_source(KafkaSourceOperator(...))
```

**`execute()`**
```python
job_id = env.execute()  # Submit job
```

### DataStream

Represents a stream of data with transformations.

```python
from jobmanager.job_graph import DataStream
```

#### Transformations

**`map(func)`** - One-to-one transformation
```python
stream.map(lambda x: x * 2)
```

**`filter(func)`** - Conditional filtering
```python
stream.filter(lambda x: x > 100)
```

**`flat_map(func)`** - One-to-many transformation
```python
stream.flat_map(lambda line: line.split())
```

**`key_by(key_selector)`** - Partition by key
```python
stream.key_by(lambda record: record['user_id'])
```

### KeyedStream

Keyed stream with stateful operations.

```python
keyed = stream.key_by(lambda x: x[0])
```

#### Operations

**`window(window_assigner)`** - Apply windowing
```python
keyed.window(TumblingWindow(10000))
```

**`reduce(reduce_func)`** - Reduce aggregation
```python
keyed.reduce(lambda a, b: a + b)
```

### WindowedStream

Stream with windowing applied.

#### Window Types

**TumblingWindow** - Non-overlapping fixed windows
```python
from taskmanager.operators.stateful import TumblingWindow

window = TumblingWindow(size_ms=10000)  # 10 second windows
```

**SlidingWindow** - Overlapping fixed windows
```python
from taskmanager.operators.stateful import SlidingWindow

window = SlidingWindow(size_ms=30000, slide_ms=10000)
```

**SessionWindow** - Gap-based dynamic windows
```python
from taskmanager.operators.stateful import SessionWindow

window = SessionWindow(gap_ms=5000)  # 5 second gap
```

### Operators

#### Source Operators

**KafkaSourceOperator** - Read from Kafka
```python
from taskmanager.operators.sources import KafkaSourceOperator

source = KafkaSourceOperator(
    topic="input-topic",
    bootstrap_servers="kafka:9092",
    group_id="my-group",
    watermark_strategy=WatermarkStrategies.bounded_out_of_orderness(5000)
)
```

#### Sink Operators

**KafkaSinkOperator** - Write to Kafka
```python
from taskmanager.operators.sinks import KafkaSinkOperator

sink = KafkaSinkOperator(
    topic="output-topic",
    bootstrap_servers="kafka:9092"
)
```

### State API

#### ValueState

```python
from taskmanager.state import ValueState

state = ValueState(state_backend, key)
state.update(value)
value = state.get()
state.clear()
```

#### ListState

```python
from taskmanager.state import ListState

state = ListState(state_backend, key)
state.add(value)
state.add_all([v1, v2, v3])
values = state.get()
state.clear()
```

#### MapState

```python
from taskmanager.state import MapState

state = MapState(state_backend, key)
state.put(map_key, map_value)
value = state.get(map_key)
state.remove(map_key)
state.contains(map_key)

for k, v in state.items():
    # Process items
    pass
```

### Watermarks

```python
from common.watermarks import WatermarkStrategies

# Bounded out-of-orderness
strategy = WatermarkStrategies.bounded_out_of_orderness(5000)

# No watermarks
strategy = WatermarkStrategies.no_watermarks()
```

## Metrics

### Prometheus Metrics

Access at `http://localhost:9090`

**Counter Metrics**:
- `records_processed_total{task, operator}` - Total records processed

**Histogram Metrics**:
- `processing_latency_seconds{operator}` - Processing latency distribution
- `checkpoint_duration_seconds{job}` - Checkpoint duration distribution

**Gauge Metrics**:
- `backpressure_ratio{task}` - Backpressure ratio (0.0 to 1.0)
- `watermark_lag_ms{task}` - Watermark lag in milliseconds
- `state_size_bytes{task, operator}` - State size in bytes

### Example Queries

**Average throughput per operator**:
```promql
rate(records_processed_total[5m])
```

**P95 latency**:
```promql
histogram_quantile(0.95, processing_latency_seconds)
```

**Jobs with high backpressure**:
```promql
backpressure_ratio > 0.5
```

## Configuration

### Environment Variables

**JobManager**:
```
JOBMANAGER_HOST=localhost
JOBMANAGER_REST_PORT=8081
JOBMANAGER_RPC_PORT=6123
CHECKPOINT_INTERVAL=10000
STATE_BACKEND=rocksdb
S3_CHECKPOINT_PATH=s3://bucket/checkpoints
```

**TaskManager**:
```
TASK_MANAGER_ID=taskmanager-1
JOBMANAGER_HOST=localhost
TASKMANAGER_RPC_PORT=6124
TASK_SLOTS=4
MEMORY_SIZE=2048
```

**Database**:
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=stream_processing
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

**Kafka**:
```
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```
