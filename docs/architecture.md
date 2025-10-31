# Architecture Overview

## System Design

This is a production-grade distributed stream processing platform inspired by Apache Flink, built in Python. The system implements a master-worker architecture with strong fault tolerance guarantees.

### Components

#### 1. JobManager (Control Plane)

The JobManager is the central coordinator responsible for:

- **Job Submission**: Accepts job definitions via REST API
- **Job Scheduling**: Converts logical JobGraphs into physical execution plans
- **Resource Management**: Tracks TaskManager health and available slots
- **Checkpoint Coordination**: Triggers and coordinates distributed snapshots
- **Failure Recovery**: Detects failures and reschedules tasks

**Key Classes**:
- `api.py`: FastAPI REST endpoints
- `job_graph.py`: JobGraph representation and fluent API
- `scheduler.py`: Task scheduling with operator chaining and bin-packing
- `resource_manager.py`: TaskManager registry and health monitoring
- `checkpoint_coordinator.py`: Distributed snapshot coordination

#### 2. TaskManager (Data Plane)

TaskManagers execute the actual data processing:

- **Task Execution**: Runs operators on streaming data
- **State Management**: Maintains operator state with RocksDB backend
- **Checkpoint Participation**: Snapshots and restores state
- **Flow Control**: Implements credit-based backpressure
- **Metrics Collection**: Exposes Prometheus metrics

**Key Classes**:
- `task_executor.py`: Core execution engine
- `operators/`: Stateless and stateful operator implementations
- `state/`: RocksDB backend and state abstractions
- `network/`: Buffer pool and flow control
- `metrics.py`: Prometheus metrics

### Communication

- **JobManager REST API**: HTTP/FastAPI (port 8081)
- **gRPC**: Inter-component communication (ports 6123, 6124+)
- **Protocol Buffers**: Message serialization

### Data Flow

```
Source Operators
    ↓
Map/Filter/FlatMap (Stateless)
    ↓
KeyBy (Partitioning)
    ↓
Window/Aggregate (Stateful)
    ↓
Sink Operators
```

## Fault Tolerance

### Exactly-Once Semantics

The system achieves exactly-once processing through:

1. **Checkpointing**: Periodic distributed snapshots using Chandy-Lamport algorithm
2. **Barrier Alignment**: Operators buffer records until barriers align from all inputs
3. **State Persistence**: RocksDB snapshots uploaded to S3
4. **Kafka Integration**: Consumer offsets included in checkpoint state
5. **Atomic Commit**: Checkpoint metadata atomically written to PostgreSQL

### Recovery Process

On TaskManager failure:

1. ResourceManager detects missed heartbeats
2. JobManager cancels all tasks
3. Latest checkpoint retrieved from PostgreSQL
4. Tasks rescheduled on available TaskManagers
5. State restored from S3 snapshots
6. Kafka sources resume from checkpointed offsets

## Performance Optimizations

### Operator Chaining

Sequences of one-to-one stateless operators (e.g., map-filter-map) are fused into single tasks, avoiding:
- Serialization overhead
- Network transfer
- Thread context switches

### Credit-Based Flow Control

- Downstream tasks grant credits to upstream senders
- Senders can only transmit when holding credits
- Prevents fast producers from overwhelming slow consumers
- Maintains system stability under load

### Buffer Pool

- Fixed-size memory buffers reused for data transfer
- Prevents frequent allocation/deallocation
- Controls memory footprint
- Reduces GC pressure

### Bin-Packing Scheduling

- Tasks allocated to TaskManagers to maximize utilization
- Considers available slots across cluster
- Minimizes resource fragmentation

## State Management

### RocksDB Backend

- Embedded key-value store for operator state
- Efficient snapshots via RocksDB checkpoints
- Configurable memory and cache sizes
- Persistent storage on disk/volumes

### State Abstractions

- **ValueState**: Single value per key
- **ListState**: List of values per key
- **MapState**: Nested key-value pairs per key
- **ReducingState**: Incremental aggregation
- **AggregatingState**: Custom accumulators

## Watermarks

### Event Time Processing

- Watermarks represent progress in event time
- Generated at sources with bounded out-of-orderness
- Propagated through operators
- Trigger window computations when watermark passes window end

### Generation Strategy

```python
watermark = max_event_timestamp - max_out_of_orderness
```

Configurable parameters:
- Emission interval (default: 200ms)
- Out-of-orderness bound (default: 5 seconds)

## Monitoring

### Metrics

Prometheus metrics exposed on port 9090:

- `records_processed_total`: Counter per operator/task
- `processing_latency_seconds`: Histogram per operator
- `checkpoint_duration_seconds`: Histogram per job
- `backpressure_ratio`: Gauge per task (0.0 to 1.0)
- `watermark_lag_ms`: Gauge per task
- `state_size_bytes`: Gauge per operator

### Dashboards

Grafana dashboards (port 3000) visualize:
- Throughput and latency trends
- Checkpoint durations
- Backpressure indicators
- Resource utilization
- Task distribution

## Scalability

### Horizontal Scaling

- Add TaskManagers to increase capacity
- Set operator parallelism for data parallelism
- Jobs automatically utilize available slots

### Resource Isolation

- Task slots limit concurrent tasks per TaskManager
- Memory limits prevent resource exhaustion
- CPU affinity (future enhancement)

## Configuration

Key configuration parameters in `common/config.py`:

- `CHECKPOINT_INTERVAL`: Checkpoint frequency (default: 10000ms)
- `TASK_SLOTS`: Concurrent tasks per TaskManager (default: 4)
- `STATE_BACKEND`: State storage backend (default: "rocksdb")
- `S3_CHECKPOINT_PATH`: S3 path for checkpoints
- `HEARTBEAT_INTERVAL`: Heartbeat frequency (default: 5000ms)
- `HEARTBEAT_TIMEOUT`: Failure detection timeout (default: 15000ms)

## Future Enhancements

1. **Savepoints**: Manual checkpoints for job migration
2. **Dynamic Scaling**: Auto-scale based on load
3. **Incremental Checkpoints**: Only checkpoint changed state
4. **Local Recovery**: Recover from local disk without full rescheduling
5. **Async I/O**: Non-blocking external lookups
6. **Broadcast State**: Shared read-only state across tasks
7. **Side Outputs**: Multiple output streams from single operator
