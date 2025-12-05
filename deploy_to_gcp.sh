#!/bin/bash
# Quick deployment script for dcsc-project-479911

set -e

export GCP_PROJECT_ID="dcsc-project-479911"
export GCP_REGION="us-central1"
export GCP_ZONE="us-central1-a"
export GKE_CLUSTER_NAME="stream-processing-cluster"

# Load existing environment config if available
if [ -f .gcp_env ]; then
    source .gcp_env
fi

echo "=========================================="
echo "Deploying to GCP Project: $GCP_PROJECT_ID"
echo "=========================================="
echo ""

# Set gcloud project
gcloud config set project $GCP_PROJECT_ID

# Fix quota project warning
gcloud auth application-default set-quota-project $GCP_PROJECT_ID 2>/dev/null || true

echo "Step 1: Running GCP setup..."
./scripts/setup_gcp.sh

echo ""
echo "Step 2: Building and deploying..."
./scripts/gcp_quick_test.sh

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "To access services:"
echo "  kubectl get svc -n stream-processing"
echo ""
echo "To view logs:"
echo "  kubectl logs -l app=jobmanager -n stream-processing -f"
echo "  kubectl logs -l app=gui -n stream-processing -f"

