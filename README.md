# Distributed Stream Processing Platform

A production-grade stream processing system inspired by Apache Flink, implementing exactly-once semantics, fault tolerance, and high-throughput data processing with Python.

---

## 🚀 How to Run

### Prerequisites
*   **Docker** & **Docker Compose**
*   **Python 3.9+**
*   **Google Cloud SDK** (only for GCP deployment)
*   **kubectl** (only for GCP deployment)

### Option 1: Run Locally (Docker Compose)
The easiest way to run the platform is using Docker Compose.

1.  **Navigate to deployment directory:**
    ```bash
    cd deployment
    ```

2.  **Start the cluster:**
    ```bash
    docker-compose up -d
    ```

3.  **Access the Dashboard:**
    Open [http://localhost:5000](http://localhost:5000) in your browser.

4.  **Verify Cluster Health:**
    ```bash
    curl http://localhost:8081/cluster/metrics
    ```

5.  **Stop the cluster:**
    ```bash
    docker-compose down
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

## 🏃 Running Jobs

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

## 🏗 Architecture

*   **JobManager (Master)**: Coordinates execution, manages resources, and handles checkpoints.
*   **TaskManager (Worker)**: Executes tasks in parallel slots.
*   **Kafka**: Handles data ingestion and inter-operator communication.
*   **gRPC**: Used for internal control plane communication.
*   **RocksDB**: Embedded state backend for stateful operations.
*   **GCS/S3**: Distributed storage for fault-tolerance checkpoints.

## ✨ Features

*   ✅ **Exactly-Once Processing**: Distributed snapshots (Chandy-Lamport).
*   ✅ **Fault Tolerance**: Automatic failure recovery.
*   ✅ **High Throughput**: Operator chaining & flow control.
*   ✅ **Stateful Operations**: Windowing, Aggregations, Joins.
*   ✅ **Observability**: Prometheus metrics & Grafana dashboards.

## 📂 Project Structure

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

## 🛠 Configuration

Key environment variables in `deployment/docker-compose.yml`:

*   `TASK_SLOTS`: Number of concurrent tasks per TaskManager (Default: 4).
*   `CHECKPOINT_INTERVAL`: Frequency of checkpoints in ms (Default: 10000).
*   `STATE_BACKEND`: `rocksdb` or `memory`.
*   `GCS_CHECKPOINT_PATH`: GCS bucket for checkpoints.

## 📊 Monitoring

*   **Grafana**: [http://localhost:3000](http://localhost:3000) (admin/admin)
*   **Prometheus**: [http://localhost:9090](http://localhost:9090)

---

**Built with**: Python, FastAPI, gRPC, Kafka, RocksDB, Docker, Kubernetes.
