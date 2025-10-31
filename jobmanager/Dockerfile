FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY jobmanager/requirements.txt /app/jobmanager/
RUN pip install --no-cache-dir -r jobmanager/requirements.txt

# Copy common modules
COPY common/ /app/common/

# Copy taskmanager module (needed by scheduler)
COPY taskmanager/ /app/taskmanager/

# Copy jobmanager code
COPY jobmanager/ /app/jobmanager/

# Expose ports
EXPOSE 8081 6123

# Run JobManager API
CMD ["python", "-m", "jobmanager.api"]
