# Distributed Stream Processing Platform

A distributed systems course project inspired by Apache Flink. Built in Python, it explores job scheduling, worker coordination, checkpoint metadata, RocksDB-backed state, and recovery in a master-worker architecture.

## Start here

- [Scheduler](jobmanager/scheduler.py): task placement and execution planning
- [Checkpoint coordinator](jobmanager/checkpoint_coordinator.py): checkpoint lifecycle, acknowledgments, and storage
- [Task execution](taskmanager/task_executor.py) and [state backends](taskmanager/state/)
- [Docker Compose deployment](deployment/docker-compose.yml): services, dependencies, and actual host ports

**Project scope:** this is an educational implementation, not a production-hardened Flink replacement. Checkpoint barrier dispatch includes a placeholder in the coordinator, so end-to-end exactly-once processing is not established by the current code. Component benchmarks are not evidence of distributed throughput.

---
## Team

[Uditanshu Tomar](https://github.com/uditanshutomar) and Ishneet Chadha

## How to Run

### Prerequisites
*   **Docker** & **Docker Compose**
*   **Python 3.9+**
*   **Google Cloud SDK** (only for GCP deployment)
*   **kubectl** (only for GCP deployment)

### Option 1: Run Locally (Docker Compose)
The checked-in Compose configuration uses Google Cloud Storage for checkpoints. Before starting it, replace `GCS_CHECKPOINT_PATH` for the JobManager and all three TaskManagers with a bucket you control, and set `GCP_KEY_PATH` to an existing credentials file with access to that bucket. The file's existing bucket is project-specific. Cloud storage access can incur charges.

Clone the repository and run the following commands from its root. Docker Compose runs the services locally; checkpoint storage still uses GCS.

1.  **Navigate to deployment directory:**
    ```bash
    cd deployment
    ```

2.  **Start the cluster:**
    ```bash
    docker compose up -d --build
    ```

3.  **Access the Dashboard:**
    Open [http://localhost:5000](http://localhost:5000) in your browser.

4.  **Verify Cluster Health:**
    ```bash
    curl http://localhost:8081/cluster/metrics
    ```

5.  **Stop the cluster:**
    ```bash
    docker compose down
    ```

### Option 2: Run on Google Cloud Platform (GKE)
Deploy the platform to a Google Kubernetes Engine cluster.

1.  **Configure GCP Project:**
    ```bash
    export GCP_PROJECT_ID="your-project-id"
    gcloud config set project $GCP_PROJECT_ID
    ```

2.  **Run Deployment Script:**
    This script will setup GKE, build images, and deploy all services.
    ```bash
    ./deploy_to_gcp.sh
    ```

3.  **Access Services:**
    ```bash
    # Get External IP of the GUI
    kubectl get svc -n stream-processing gui
    ```

---

## Running Jobs

### 1. Run the Demo (GUI)
1.  Go to the **Dashboard** ([http://localhost:5000](http://localhost:5000)).
2.  Click **"Start Demo"** in the "Control Panel".
3.  Watch real-time metrics update as the `DemoWeatherProcessing` job runs.
4.  See data flowing in the "Live Data Stream" panel.

### 2. Submit a Job (CLI)
You can submit custom jobs written in Python.

**Example: Word Count**
```bash
# 1. Generate the job file
python examples/word_count.py

# 2. Submit to the cluster
curl -X POST http://localhost:8081/jobs/submit \
  -F "job_file=@word_count_job.pkl"
```

**Monitor the Job:**
```bash
# Check Status
curl http://localhost:8081/jobs/{job_id}/status
```

---

## Architecture

*   **JobManager (Master)**: Coordinates execution, manages resources, and handles checkpoints.
*   **TaskManager (Worker)**: Executes tasks in parallel slots.
*   **Kafka**: Handles data ingestion and inter-operator communication.
*   **gRPC**: Used for internal control plane communication.
*   **RocksDB**: Embedded state backend for stateful operations.
*   **GCS/S3**: Distributed storage for fault-tolerance checkpoints.

## Features

*   **Checkpoint Coordination**: Snapshot metadata and acknowledgments, with incomplete barrier dispatch.
*   **Failure Recovery**: Worker health monitoring and recovery paths.
*   **Execution Design**: Operator chaining and flow control.
*   **Stateful Operations**: Windowing, Aggregations, Joins.
*   **Observability**: Prometheus metrics & Grafana dashboards.

## Project Structure

```
stream-processing-platform/
├── jobmanager/              # Control Plane (Scheduler, API)
├── taskmanager/             # Data Plane (Execution, State)
├── common/                  # Shared Utils (Proto, Config)
├── gui/                     # Web Dashboard
├── examples/                # Example Jobs
├── deployment/              # Docker & K8s Configs
└── scripts/                 # Deployment Scripts
```

## Configuration

Key environment variables in `deployment/docker-compose.yml`:

*   `TASK_SLOTS`: Number of concurrent tasks per TaskManager (Default: 4).
*   `CHECKPOINT_INTERVAL`: Frequency of checkpoints in ms (Default: 10000).
*   `STATE_BACKEND`: `rocksdb` or `memory`.
*   `GCS_CHECKPOINT_PATH`: GCS bucket for checkpoints.

## Monitoring

*   **Grafana**: [http://localhost:3001](http://localhost:3001) (admin/admin)
*   **Prometheus**: [http://localhost:9095](http://localhost:9095)

---

**Built with**: Python, FastAPI, gRPC, Kafka, RocksDB, Docker, Kubernetes.
