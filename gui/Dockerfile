FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY gui/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install requests for API calls
RUN pip install --no-cache-dir requests==2.31.0

# Copy GUI code
COPY gui/ /app/gui/

# Copy examples and dependencies needed to generate jobs
COPY examples/ /app/examples/
COPY common/ /app/common/
COPY taskmanager/ /app/taskmanager/
COPY jobmanager/ /app/jobmanager/

# Expose port
EXPOSE 5000

# Run GUI (GCP version)
CMD ["python", "gui/app_gcp.py"]

