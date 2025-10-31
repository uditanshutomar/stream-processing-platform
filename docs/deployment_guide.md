# Deployment Guide

## Docker Compose Deployment

The simplest way to deploy the platform is using Docker Compose.

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum
- 20GB disk space

### Quick Start

```bash
cd deployment
docker-compose up -d
```

This will start all services:
- JobManager (1 instance)
- TaskManager (3 instances)
- PostgreSQL
- Kafka + Zookeeper
- Prometheus
- Grafana

### Verify Deployment

```bash
# Check all containers are running
docker-compose ps

# Check JobManager logs
docker-compose logs -f jobmanager

# Check TaskManager logs
docker-compose logs -f taskmanager1

# Test API endpoint
curl http://localhost:8081/cluster/metrics
```

### Scaling TaskManagers

To add more TaskManagers:

```bash
docker-compose up -d --scale taskmanager1=5
```

Or modify `docker-compose.yml` to add more services.

### Stopping the Platform

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (data will be lost)
docker-compose down -v
```

## Kubernetes Deployment

For production deployments, Kubernetes is recommended.

### Prerequisites

- Kubernetes 1.20+
- kubectl configured
- 3+ worker nodes with 4GB RAM each

### Architecture

```
┌─────────────────────────────────────┐
│         LoadBalancer/Ingress        │
│    (JobManager API: port 8081)      │
└─────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
   ┌────▼────┐         ┌────▼────┐
   │ JobMgr  │         │ JobMgr  │  (HA)
   │ Pod 1   │         │ Pod 2   │
   └────┬────┘         └────┬────┘
        │                   │
   ┌────▼───────────────────▼────┐
   │     TaskManager DaemonSet    │
   │  (One pod per worker node)   │
   └─────────────────────────────┘
```

### Deployment Steps

1. **Create Namespace**:
```bash
kubectl create namespace stream-processing
```

2. **Deploy PostgreSQL** (using Helm):
```bash
helm install postgres bitnami/postgresql \
  --namespace stream-processing \
  --set auth.database=stream_processing \
  --set auth.username=postgres \
  --set auth.password=postgres
```

3. **Deploy Kafka** (using Strimzi):
```bash
kubectl apply -f https://strimzi.io/install/latest?namespace=stream-processing
kubectl apply -f deployment/kubernetes/kafka-cluster.yaml
```

4. **Deploy JobManager**:
```bash
kubectl apply -f deployment/kubernetes/jobmanager-deployment.yaml
kubectl apply -f deployment/kubernetes/jobmanager-service.yaml
```

5. **Deploy TaskManagers**:
```bash
kubectl apply -f deployment/kubernetes/taskmanager-daemonset.yaml
```

6. **Verify Deployment**:
```bash
kubectl get pods -n stream-processing
kubectl logs -n stream-processing deployment/jobmanager
```

### Kubernetes Manifests

#### JobManager Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jobmanager
  namespace: stream-processing
spec:
  replicas: 2  # For HA
  selector:
    matchLabels:
      app: jobmanager
  template:
    metadata:
      labels:
        app: jobmanager
    spec:
      containers:
      - name: jobmanager
        image: stream-processing/jobmanager:latest
        ports:
        - containerPort: 8081  # REST API
        - containerPort: 6123  # gRPC
        env:
        - name: POSTGRES_HOST
          value: postgres-postgresql.stream-processing.svc.cluster.local
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: kafka-kafka-bootstrap.stream-processing.svc.cluster.local:9092
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
```

#### TaskManager DaemonSet

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: taskmanager
  namespace: stream-processing
spec:
  selector:
    matchLabels:
      app: taskmanager
  template:
    metadata:
      labels:
        app: taskmanager
    spec:
      containers:
      - name: taskmanager
        image: stream-processing/taskmanager:latest
        ports:
        - containerPort: 6124  # gRPC
        - containerPort: 9090  # Metrics
        env:
        - name: TASK_MANAGER_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: JOBMANAGER_HOST
          value: jobmanager.stream-processing.svc.cluster.local
        - name: TASK_SLOTS
          value: "4"
        volumeMounts:
        - name: rocksdb-state
          mountPath: /data/rocksdb
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
      volumes:
      - name: rocksdb-state
        emptyDir: {}
```

## AWS Deployment

### Using EKS

1. **Create EKS Cluster**:
```bash
eksctl create cluster \
  --name stream-processing \
  --region us-east-1 \
  --nodes 3 \
  --node-type t3.xlarge
```

2. **Configure S3 for Checkpoints**:
```bash
aws s3 mb s3://stream-processing-checkpoints
```

3. **Create IAM Role for TaskManagers**:
```bash
# Allow TaskManagers to write to S3
aws iam create-role --role-name StreamProcessingTaskManager \
  --assume-role-policy-document file://trust-policy.json

aws iam attach-role-policy \
  --role-name StreamProcessingTaskManager \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
```

4. **Deploy with S3 Backend**:
```yaml
env:
- name: S3_CHECKPOINT_PATH
  value: s3://stream-processing-checkpoints
- name: AWS_REGION
  value: us-east-1
```

### Using ECS

For serverless deployment with AWS ECS Fargate:

1. **Create Task Definitions** for JobManager and TaskManager
2. **Configure VPC** with proper networking
3. **Set up Application Load Balancer** for JobManager API
4. **Configure RDS PostgreSQL** for metadata
5. **Configure MSK** (Managed Kafka) for messaging

## Production Considerations

### High Availability

**JobManager HA**:
- Run 2+ JobManager replicas
- Use shared PostgreSQL for coordination
- Configure load balancer for API

**TaskManager Fault Tolerance**:
- Enable auto-restart on failure
- Configure health checks
- Set resource limits

### Security

**Network Security**:
```yaml
# Use NetworkPolicies in Kubernetes
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: taskmanager-policy
spec:
  podSelector:
    matchLabels:
      app: taskmanager
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: jobmanager
    ports:
    - protocol: TCP
      port: 6124
```

**Encryption**:
- Enable TLS for gRPC communication
- Encrypt PostgreSQL connections
- Use encrypted S3 buckets

**Authentication**:
- Add API authentication (JWT, OAuth2)
- Configure Kafka SASL/SSL
- Use IAM roles for AWS services

### Monitoring

**Prometheus**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9090"
```

**Grafana Dashboards**:
- Import pre-built dashboards
- Configure alerts for high backpressure
- Set up alerting via PagerDuty/Slack

### Backup and Recovery

**Automated Backups**:
```bash
# PostgreSQL backup
kubectl exec -n stream-processing postgres-0 -- \
  pg_dump -U postgres stream_processing > backup.sql

# S3 checkpoint backup (use S3 versioning)
aws s3api put-bucket-versioning \
  --bucket stream-processing-checkpoints \
  --versioning-configuration Status=Enabled
```

### Resource Planning

**JobManager**:
- CPU: 2+ cores
- Memory: 4GB minimum
- Disk: 50GB for logs

**TaskManager** (per node):
- CPU: 4+ cores (1 per slot recommended)
- Memory: 8GB minimum (2GB per slot recommended)
- Disk: 100GB for RocksDB state

**Kafka**:
- 3+ brokers for fault tolerance
- Replication factor: 3
- Min ISR: 2

### Performance Tuning

**Checkpointing**:
```python
# Adjust checkpoint interval based on state size
env.enable_checkpointing(60000)  # Increase to 60s for large state
```

**Parallelism**:
```python
# Set based on available task slots
env.set_parallelism(12)  # 3 TaskManagers × 4 slots
```

**RocksDB**:
```yaml
env:
- name: ROCKSDB_WRITE_BUFFER_SIZE
  value: "134217728"  # 128MB for high throughput
- name: ROCKSDB_BLOCK_CACHE_SIZE
  value: "536870912"  # 512MB for large state
```

### Maintenance

**Rolling Updates**:
```bash
# Update TaskManagers without downtime
kubectl set image daemonset/taskmanager \
  taskmanager=stream-processing/taskmanager:v2.0

kubectl rollout status daemonset/taskmanager
```

**Savepoint for Job Migration**:
```bash
# Create savepoint
curl -X POST http://localhost:8081/jobs/${JOB_ID}/savepoint

# Cancel old job
curl -X POST http://localhost:8081/jobs/${JOB_ID}/cancel

# Submit new job with savepoint
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@new_job.pkl" \
  -F "savepoint_path=s3://checkpoints/job-${JOB_ID}/chk-42"
```

## Troubleshooting

### Common Issues

**JobManager not starting**:
```bash
# Check PostgreSQL connectivity
kubectl exec -it deployment/jobmanager -- \
  nc -zv postgres-postgresql 5432

# Check logs
kubectl logs deployment/jobmanager
```

**TaskManager not registering**:
```bash
# Verify network connectivity to JobManager
kubectl exec -it daemonset/taskmanager -- \
  nc -zv jobmanager 6123

# Check heartbeat logs
kubectl logs daemonset/taskmanager | grep heartbeat
```

**High checkpoint duration**:
- Reduce state size
- Increase checkpoint interval
- Use incremental checkpoints (future)
- Optimize RocksDB settings

**High backpressure**:
- Scale out TaskManagers
- Optimize slow operators
- Increase operator parallelism
- Check sink throughput
