# GCP Deployment Guide

This guide walks you through deploying the Stream Processing Platform on Google Cloud Platform (GCP) using Google Kubernetes Engine (GKE).

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [GCP Setup](#gcp-setup)
3. [Build and Push Docker Images](#build-and-push-docker-images)
4. [Deploy to GKE](#deploy-to-gke)
5. [Configure Storage](#configure-storage)
6. [Access the Platform](#access-the-platform)
7. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
8. [Production Considerations](#production-considerations)

## Prerequisites

- GCP account with billing enabled
- `gcloud` CLI installed and configured
- `kubectl` installed
- Docker installed locally
- Basic knowledge of Kubernetes

### Install Required Tools

```bash
# Install gcloud CLI (if not already installed)
# macOS
brew install google-cloud-sdk

# Linux
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Initialize gcloud
gcloud init
gcloud auth login
```

## GCP Setup

### 1. Create a GCP Project

```bash
# Set your project ID
export PROJECT_ID="your-project-id"
export REGION="us-central1"  # Choose your preferred region
export ZONE="us-central1-a"

# Create a new project (optional)
gcloud projects create $PROJECT_ID --name="Stream Processing Platform"

# Set the project as default
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable \
    container.googleapis.com \
    containerregistry.googleapis.com \
    storage-component.googleapis.com \
    sqladmin.googleapis.com \
    cloudbuild.googleapis.com
```

### 2. Create GKE Cluster

```bash
# Create a GKE cluster
gcloud container clusters create stream-processing-cluster \
    --zone=$ZONE \
    --num-nodes=3 \
    --machine-type=n1-standard-4 \
    --disk-size=100GB \
    --enable-autoscaling \
    --min-nodes=3 \
    --max-nodes=10 \
    --enable-autorepair \
    --enable-autoupgrade \
    --addons=HorizontalPodAutoscaling,HttpLoadBalancing

# Get cluster credentials
gcloud container clusters get-credentials stream-processing-cluster --zone=$ZONE
```

### 3. Create GCS Bucket for Checkpoints

```bash
# Create a GCS bucket for checkpoint storage
export BUCKET_NAME="stream-processing-checkpoints-$(date +%s)"

gsutil mb -p $PROJECT_ID -l $REGION gs://$BUCKET_NAME

# Enable versioning for backup
gsutil versioning set on gs://$BUCKET_NAME

# Set lifecycle policy (optional - delete old checkpoints after 30 days)
cat > lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 30}
      }
    ]
  }
}
EOF
gsutil lifecycle set lifecycle.json gs://$BUCKET_NAME
rm lifecycle.json
```

### 4. Create Service Account for GCS Access

```bash
# Create service account
gcloud iam service-accounts create stream-processing-sa \
    --display-name="Stream Processing Service Account"

# Grant Storage Admin role
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:stream-processing-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

# Create and download key
gcloud iam service-accounts keys create key.json \
    --iam-account=stream-processing-sa@$PROJECT_ID.iam.gserviceaccount.com

# Create Kubernetes secret from the key
kubectl create secret generic gcp-service-account-key \
    --from-file=key.json=key.json \
    --namespace=stream-processing

# Clean up local key file (optional, keep it secure if needed)
# rm key.json
```

## Build and Push Docker Images

### Option 1: Using Cloud Build (Recommended)

Create `cloudbuild.yaml` in the project root:

```yaml
steps:
  # Build JobManager image
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'gcr.io/$PROJECT_ID/stream-processing-jobmanager:latest'
      - '-f'
      - 'jobmanager/Dockerfile'
      - '.'
  
  # Build TaskManager image
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'gcr.io/$PROJECT_ID/stream-processing-taskmanager:latest'
      - '-f'
      - 'taskmanager/Dockerfile'
      - '.'
  
  # Push JobManager image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/stream-processing-jobmanager:latest']
  
  # Push TaskManager image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/stream-processing-taskmanager:latest']

images:
  - 'gcr.io/$PROJECT_ID/stream-processing-jobmanager:latest'
  - 'gcr.io/$PROJECT_ID/stream-processing-taskmanager:latest'
```

Build and push:

```bash
gcloud builds submit --config cloudbuild.yaml
```

### Option 2: Using Local Docker

```bash
# Configure Docker to use gcloud as credential helper
gcloud auth configure-docker

# Build JobManager image
docker build -t gcr.io/$PROJECT_ID/stream-processing-jobmanager:latest \
    -f jobmanager/Dockerfile .

# Build TaskManager image
docker build -t gcr.io/$PROJECT_ID/stream-processing-taskmanager:latest \
    -f taskmanager/Dockerfile .

# Push images
docker push gcr.io/$PROJECT_ID/stream-processing-jobmanager:latest
docker push gcr.io/$PROJECT_ID/stream-processing-taskmanager:latest
```

## Deploy to GKE

### 1. Update Kubernetes Manifests

Before deploying, update the following files with your project-specific values:

**`deployment/kubernetes/jobmanager-deployment.yaml`**:
- Replace `PROJECT_ID` with your GCP project ID
- Replace `YOUR_BUCKET_NAME` with your GCS bucket name

**`deployment/kubernetes/taskmanager-daemonset.yaml`**:
- Replace `PROJECT_ID` with your GCP project ID
- Replace `YOUR_BUCKET_NAME` with your GCS bucket name

### 2. Deploy All Components

```bash
cd deployment/kubernetes

# Create namespace
kubectl apply -f namespace.yaml

# Deploy PostgreSQL
kubectl apply -f postgres-secret.yaml
kubectl apply -f postgres-deployment.yaml

# Deploy Kafka and Zookeeper
kubectl apply -f kafka-deployment.yaml

# Wait for dependencies to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n stream-processing --timeout=300s
kubectl wait --for=condition=ready pod -l app=kafka -n stream-processing --timeout=300s

# Deploy RBAC
kubectl apply -f rbac.yaml

# Deploy ConfigMap
kubectl apply -f configmap.yaml

# Deploy JobManager
kubectl apply -f jobmanager-deployment.yaml

# Deploy TaskManagers
kubectl apply -f taskmanager-daemonset.yaml

# Deploy Monitoring
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml
```

### 3. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n stream-processing

# Check services
kubectl get services -n stream-processing

# Check JobManager logs
kubectl logs -f deployment/jobmanager -n stream-processing

# Check TaskManager logs
kubectl logs -f daemonset/taskmanager -n stream-processing
```

## Configure Storage

The platform uses Google Cloud Storage (GCS) for checkpoint storage. The configuration is set via environment variables in the Kubernetes deployments.

### Verify GCS Access

```bash
# Test GCS access from a pod
kubectl run -it --rm gcs-test --image=google/cloud-sdk:slim \
    --restart=Never -n stream-processing -- \
    gsutil ls gs://$BUCKET_NAME
```

## Access the Platform

### Get External IPs

```bash
# Get JobManager LoadBalancer IP
JOBMANAGER_IP=$(kubectl get svc jobmanager -n stream-processing \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Get Grafana LoadBalancer IP
GRAFANA_IP=$(kubectl get svc grafana -n stream-processing \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo "JobManager API: http://$JOBMANAGER_IP:8081"
echo "Grafana: http://$GRAFANA_IP:3000"
```

### Test the API

```bash
# Check cluster health
curl http://$JOBMANAGER_IP:8081/cluster/metrics

# Expected response:
# {
#   "total_task_managers": 3,
#   "active_task_managers": 3,
#   "total_slots": 12,
#   "available_slots": 12,
#   "utilization": 0.0
# }
```

### Submit a Job

```bash
# Generate a job file
python examples/word_count.py

# Submit job
curl -X POST http://$JOBMANAGER_IP:8081/jobs/submit \
    -F "job_file=@word_count_job.pkl"
```

## Monitoring and Troubleshooting

### View Logs

```bash
# JobManager logs
kubectl logs -f deployment/jobmanager -n stream-processing

# TaskManager logs (all instances)
kubectl logs -f daemonset/taskmanager -n stream-processing

# PostgreSQL logs
kubectl logs -f statefulset/postgres -n stream-processing

# Kafka logs
kubectl logs -f statefulset/kafka -n stream-processing
```

### Check Resource Usage

```bash
# View resource usage
kubectl top pods -n stream-processing

# View node resources
kubectl top nodes
```

### Common Issues

#### Issue: Pods not starting

```bash
# Check pod status
kubectl describe pod <pod-name> -n stream-processing

# Check events
kubectl get events -n stream-processing --sort-by='.lastTimestamp'
```

#### Issue: Cannot connect to GCS

```bash
# Verify service account secret exists
kubectl get secret gcp-service-account-key -n stream-processing

# Check if service account has correct permissions
gcloud projects get-iam-policy $PROJECT_ID \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:stream-processing-sa@$PROJECT_ID.iam.gserviceaccount.com"
```

#### Issue: High memory usage

```bash
# Scale TaskManagers (if using Deployment instead of DaemonSet)
kubectl scale deployment taskmanager --replicas=5 -n stream-processing

# Or add more nodes to cluster
gcloud container clusters resize stream-processing-cluster \
    --num-nodes=5 --zone=$ZONE
```

## Production Considerations

### 1. Use Cloud SQL for PostgreSQL

Instead of running PostgreSQL in Kubernetes, use Cloud SQL for better reliability:

```bash
# Create Cloud SQL instance
gcloud sql instances create stream-processing-db \
    --database-version=POSTGRES_14 \
    --tier=db-f1-micro \
    --region=$REGION

# Create database
gcloud sql databases create stream_processing \
    --instance=stream-processing-db

# Create user
gcloud sql users create postgres \
    --instance=stream-processing-db \
    --password=YOUR_SECURE_PASSWORD

# Get connection name
gcloud sql instances describe stream-processing-db \
    --format="value(connectionName)"
```

Update `jobmanager-deployment.yaml` to use Cloud SQL Proxy or Private IP.

### 2. Use Managed Kafka (Confluent Cloud)

For production, consider using Confluent Cloud instead of self-managed Kafka:

1. Create a Confluent Cloud account
2. Create a Kafka cluster
3. Get bootstrap servers and API keys
4. Update `KAFKA_BOOTSTRAP_SERVERS` in ConfigMap

### 3. Enable Autoscaling

```bash
# Enable cluster autoscaling (already done in cluster creation)
# Configure HPA for JobManager
kubectl autoscale deployment jobmanager \
    --cpu-percent=70 \
    --min=2 \
    --max=5 \
    -n stream-processing
```

### 4. Set Up Monitoring and Alerting

```bash
# Enable GKE monitoring
gcloud container clusters update stream-processing-cluster \
    --enable-monitoring \
    --zone=$ZONE

# Create alerting policies in Cloud Monitoring
# - High CPU usage
# - Pod restarts
# - Checkpoint failures
```

### 5. Backup Strategy

```bash
# Enable GCS versioning (already done)
# Set up automated PostgreSQL backups
gcloud sql backups create \
    --instance=stream-processing-db

# Schedule regular backups
gcloud scheduler jobs create http backup-job \
    --schedule="0 2 * * *" \
    --uri="https://sqladmin.googleapis.com/v1/projects/$PROJECT_ID/instances/stream-processing-db/backupRuns" \
    --http-method=POST
```

### 6. Security Best Practices

- Use Workload Identity instead of service account keys
- Enable network policies
- Use TLS for all inter-service communication
- Regularly rotate secrets
- Enable audit logging

```bash
# Enable Workload Identity
gcloud container clusters update stream-processing-cluster \
    --workload-pool=$PROJECT_ID.svc.id.goog \
    --zone=$ZONE

# Create service account with Workload Identity
gcloud iam service-accounts create stream-processing-sa \
    --display-name="Stream Processing Service Account"

# Bind Kubernetes service account to GCP service account
gcloud iam service-accounts add-iam-policy-binding \
    stream-processing-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:$PROJECT_ID.svc.id.goog[stream-processing/stream-processing-sa]"
```

### 7. Cost Optimization

- Use preemptible nodes for TaskManagers
- Right-size node machine types
- Enable cluster autoscaling
- Use committed use discounts
- Set up budget alerts

```bash
# Add preemptible node pool
gcloud container node-pools create preemptible-pool \
    --cluster=stream-processing-cluster \
    --zone=$ZONE \
    --num-nodes=0 \
    --enable-autoscaling \
    --min-nodes=0 \
    --max-nodes=10 \
    --preemptible \
    --machine-type=n1-standard-4
```

## Cleanup

To remove all resources:

```bash
# Delete Kubernetes resources
kubectl delete namespace stream-processing

# Delete GKE cluster
gcloud container clusters delete stream-processing-cluster --zone=$ZONE

# Delete GCS bucket (careful - this deletes all checkpoints!)
gsutil rm -r gs://$BUCKET_NAME

# Delete Cloud SQL instance (if created)
gcloud sql instances delete stream-processing-db

# Delete service account
gcloud iam service-accounts delete \
    stream-processing-sa@$PROJECT_ID.iam.gserviceaccount.com
```

## Next Steps

- Review the [Architecture Documentation](architecture.md) for system design details
- Check the [API Reference](api_reference.md) for available endpoints
- Explore [Examples](../examples/) for sample jobs
- Set up CI/CD pipelines for automated deployments
- **See [GCP Improvements](gcp_improvements.md) for production-ready enhancements**

## Support

For issues or questions:
- Check logs: `kubectl logs -n stream-processing`
- Review [Troubleshooting](#monitoring-and-troubleshooting) section
- Check GCP Console for resource status

