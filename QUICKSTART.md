# Quick Start Guide

Get the Stream Processing Platform running in under 5 minutes!

## Prerequisites

- Docker Desktop installed and running
- 8GB RAM available
- Internet connection for pulling images

## Step 1: Start the Platform (2 minutes)

```bash
cd stream-processing-platform/deployment
docker-compose up -d
```

Wait for all services to be healthy:
```bash
docker-compose ps
```

Expected output:
```
NAME                      STATUS
stream-jobmanager         Up (healthy)
stream-taskmanager-1      Up
stream-taskmanager-2      Up
stream-taskmanager-3      Up
stream-kafka              Up (healthy)
stream-postgres           Up (healthy)
stream-prometheus         Up
stream-grafana            Up
```

## Step 2: Verify the Cluster (30 seconds)

Check cluster health:
```bash
curl http://localhost:8081/cluster/metrics
```

Expected response:
```json
{
  "total_task_managers": 3,
  "active_task_managers": 3,
  "total_slots": 12,
  "available_slots": 12,
  "utilization": 0.0
}
```

## Step 3: Run Your First Job (2 minutes)

### Create a Simple Word Count Job

```bash
cd ..  # Back to project root
python3 examples/word_count.py
```

This generates `word_count_job.pkl`.

### Submit the Job

```bash
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@word_count_job.pkl"
```

Response:
```json
{
  "job_id": "job_a3f2e9b1",
  "status": "RUNNING"
}
```

### Check Job Status

```bash
export JOB_ID=job_a3f2e9b1  # Use your actual job ID
curl http://localhost:8081/jobs/${JOB_ID}/status
```

## Step 4: Send Test Data

### Create Kafka Topic

```bash
docker exec stream-kafka kafka-topics \
  --create --topic input-text \
  --bootstrap-server localhost:9092 \
  --partitions 4 --replication-factor 1
```

### Send Sample Data

```bash
# Send lines of text
docker exec -i stream-kafka kafka-console-producer \
  --broker-list localhost:9092 --topic input-text << EOF
hello world
stream processing is awesome
hello kafka
distributed systems are cool
stream processing with python
hello world again
EOF
```

### Consume Results

```bash
docker exec stream-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic word-count-output \
  --from-beginning
```

Expected output (after 10 second window):
```
("hello", 3)
("world", 2)
("stream", 2)
("processing", 2)
...
```

## Step 5: Monitor (1 minute)

### View Prometheus Metrics

Open: http://localhost:9090

Try queries:
- `records_processed_total` - Total records processed
- `rate(records_processed_total[1m])` - Throughput (records/sec)
- `backpressure_ratio` - Backpressure indicator

### View Grafana Dashboards

Open: http://localhost:3000
- Username: `admin`
- Password: `admin`

## Step 6: Test Fault Tolerance (Optional)

### Kill a TaskManager

```bash
docker kill stream-taskmanager-2
```

### Verify Job Continues

```bash
curl http://localhost:8081/jobs/${JOB_ID}/status
```

Status should remain `RUNNING` - the job automatically recovers!

### Restart TaskManager

```bash
docker start stream-taskmanager-2
```

### Check Recovery

```bash
curl http://localhost:8081/cluster/metrics
```

The failed TaskManager should rejoin and become available.

## Next Steps

### Run Other Examples

```bash
# Windowed aggregation
python3 examples/windowed_aggregation.py
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@windowed_aggregation_job.pkl"

# Stateful deduplication
python3 examples/stateful_deduplication.py
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@stateful_deduplication_job.pkl"

# Stream join
python3 examples/stream_join.py
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@stream_join_job.pkl"
```

### Build Your Own Job

Create `my_job.py`:

```python
from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import KafkaSourceOperator
from taskmanager.operators.sinks import KafkaSinkOperator

env = StreamExecutionEnvironment("MyJob")
env.set_parallelism(4).enable_checkpointing(10000)

source = KafkaSourceOperator(
    topic="my-input",
    bootstrap_servers="kafka:9092",
    group_id="my-group"
)

# Your transformations here
stream = env.add_source(source) \
    .map(lambda x: x.upper()) \
    .filter(lambda x: len(x) > 5)

sink = KafkaSinkOperator(
    topic="my-output",
    bootstrap_servers="kafka:9092"
)

stream.add_sink(sink)

# Serialize and submit
import pickle
with open('my_job.pkl', 'wb') as f:
    pickle.dump(env.get_job_graph(), f)
```

Submit:
```bash
python3 my_job.py
curl -X POST http://localhost:8081/jobs/submit -F "job_file=@my_job.pkl"
```

### Run Tests

```bash
# Unit tests
python3 -m pytest tests/unit/ -v

# Integration tests
python3 -m pytest tests/integration/ -v

# Benchmarks
python3 scripts/benchmark.py
```

### Chaos Testing

```bash
./scripts/chaos_test.sh
```

This randomly kills and restarts TaskManagers while monitoring job health.

## Common Commands

### View Logs

```bash
# JobManager
docker-compose logs -f jobmanager

# TaskManager
docker-compose logs -f taskmanager1

# All services
docker-compose logs -f
```

### Restart Services

```bash
# Restart specific service
docker-compose restart jobmanager

# Restart all
docker-compose restart
```

### Stop Platform

```bash
# Stop (data preserved)
docker-compose stop

# Stop and remove (data lost)
docker-compose down -v
```

### Scale TaskManagers

```bash
docker-compose up -d --scale taskmanager1=5
```

## Troubleshooting

### Issue: Containers not starting

**Check Docker resources**:
```bash
docker stats
```

Ensure at least 8GB RAM allocated to Docker Desktop.

### Issue: JobManager API not responding

**Check if JobManager is running**:
```bash
docker-compose ps jobmanager
docker-compose logs jobmanager
```

**Restart JobManager**:
```bash
docker-compose restart jobmanager
```

### Issue: TaskManagers not registering

**Check network connectivity**:
```bash
docker exec stream-taskmanager-1 nc -zv jobmanager 6123
```

**Check heartbeat logs**:
```bash
docker-compose logs taskmanager1 | grep -i heartbeat
```

### Issue: Job submission fails

**Verify job file is valid**:
```python
import pickle
with open('word_count_job.pkl', 'rb') as f:
    job_graph = pickle.load(f)
    print(job_graph)
```

**Check available slots**:
```bash
curl http://localhost:8081/cluster/metrics
```

### Issue: No output from job

**Verify Kafka topics exist**:
```bash
docker exec stream-kafka kafka-topics \
  --list --bootstrap-server localhost:9092
```

**Check job status**:
```bash
curl http://localhost:8081/jobs/${JOB_ID}/status
```

**View TaskManager logs**:
```bash
docker-compose logs taskmanager1 | tail -100
```

## Architecture at a Glance

```
┌──────────────────────────────────────────────────────┐
│                   REST API (8081)                     │
│                     JobManager                        │
│  ┌────────────────────────────────────────────────┐  │
│  │ Scheduler │ ResourceMgr │ CheckpointCoordinator│  │
│  └────────────────────────────────────────────────┘  │
└───────────────────────┬──────────────────────────────┘
                        │ gRPC (6123)
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼───────┐ ┌────▼──────┐ ┌──────▼──────┐
│ TaskManager 1 │ │TaskMgr 2  │ │ TaskMgr 3   │
│  (4 slots)    │ │ (4 slots) │ │ (4 slots)   │
│ ┌───────────┐ │ │┌─────────┐│ │┌──────────┐ │
│ │ Operators │ │ ││Operators││ ││Operators │ │
│ │  + State  │ │ ││ + State ││ ││ + State  │ │
│ └───────────┘ │ │└─────────┘│ │└──────────┘ │
└───────────────┘ └───────────┘ └─────────────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
                ┌───────▼────────┐
                │  Kafka Cluster │
                └────────────────┘
```

## Performance Expectations

With default configuration (3 TaskManagers, 4 slots each):

- **Throughput**: 50,000+ records/second
- **Latency**: <100ms p99 for windowed operations
- **Checkpoint Duration**: <1 second for 1GB state
- **Recovery Time**: <30 seconds from TaskManager failure
- **Uptime**: 99.9% during chaos testing

## Learn More

- **Architecture**: [docs/architecture.md](docs/architecture.md)
- **API Reference**: [docs/api_reference.md](docs/api_reference.md)
- **Deployment Guide**: [docs/deployment_guide.md](docs/deployment_guide.md)
- **Full README**: [README.md](README.md)

## Support

For issues or questions:
1. Check logs: `docker-compose logs`
2. Review documentation in `docs/`
3. Run tests: `pytest tests/`
4. Check metrics: http://localhost:9090

---

**Congratulations!** You now have a production-grade distributed stream processing platform running locally. Start building real-time data pipelines! 🚀
