FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for RocksDB
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    librocksdb-dev \
    libsnappy-dev \
    libbz2-dev \
    libz-dev \
    liblz4-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY taskmanager/requirements.txt /app/taskmanager/
RUN pip install --no-cache-dir -r taskmanager/requirements.txt

# Copy common modules
COPY common/ /app/common/

# Copy taskmanager code
COPY taskmanager/ /app/taskmanager/

# Expose ports
EXPOSE 6124 9090

# Create volume for RocksDB state
VOLUME ["/data/rocksdb"]

# Run TaskManager - using shell form to expand environment variables
CMD python -m taskmanager.task_executor --task-manager-id $TASK_MANAGER_ID
