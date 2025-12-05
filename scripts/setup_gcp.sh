#!/bin/bash
# GCP Setup Script for Stream Processing Platform
# This script automates the initial GCP setup for deploying the platform

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-central1}"
ZONE="${GCP_ZONE:-us-central1-a}"
CLUSTER_NAME="${GKE_CLUSTER_NAME:-stream-processing-cluster}"
BUCKET_NAME="${GCS_BUCKET_NAME:-}"

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    print_info "Checking prerequisites..."
    
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed. Please install it first."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install it first."
        exit 1
    fi
    
    print_info "All prerequisites are installed."
}

get_project_id() {
    if [ -z "$PROJECT_ID" ]; then
        print_info "Getting current GCP project..."
        PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
        
        if [ -z "$PROJECT_ID" ]; then
            print_error "No GCP project set. Please set GCP_PROJECT_ID or run 'gcloud config set project PROJECT_ID'"
            exit 1
        fi
    fi
    
    print_info "Using project: $PROJECT_ID"
}

create_gcs_bucket() {
    if [ -z "$BUCKET_NAME" ]; then
        BUCKET_NAME="stream-processing-checkpoints-$(date +%s)"
    fi
    
    print_info "Creating GCS bucket: $BUCKET_NAME"
    
    if gsutil ls -b gs://$BUCKET_NAME &> /dev/null; then
        print_warn "Bucket $BUCKET_NAME already exists. Skipping creation."
    else
        gsutil mb -p $PROJECT_ID -l $REGION gs://$BUCKET_NAME
        gsutil versioning set on gs://$BUCKET_NAME
        print_info "Bucket created and versioning enabled."
    fi
    
    echo "export GCS_BUCKET_NAME=$BUCKET_NAME" >> .gcp_env
}

create_service_account() {
    print_info "Creating service account..."
    
    SA_NAME="stream-processing-sa"
    SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
    
    if gcloud iam service-accounts describe $SA_EMAIL &> /dev/null; then
        print_warn "Service account $SA_EMAIL already exists. Skipping creation."
    else
        gcloud iam service-accounts create $SA_NAME \
            --display-name="Stream Processing Service Account"
        print_info "Service account created. Waiting for propagation..."
        sleep 10
    fi
    
    # Grant Storage Admin role
    print_info "Granting Storage Admin role..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="roles/storage.admin" \
        --condition=None &> /dev/null || true
    
    # Create and download key
    print_info "Creating service account key..."
    KEY_FILE="key.json"
    if [ -f "$KEY_FILE" ]; then
        print_warn "Key file $KEY_FILE already exists. Skipping key creation."
    else
        gcloud iam service-accounts keys create $KEY_FILE \
            --iam-account=$SA_EMAIL
        print_info "Service account key saved to $KEY_FILE"
        print_warn "Keep this file secure! It will be used to create Kubernetes secret."
    fi
    
    echo "export SA_EMAIL=$SA_EMAIL" >> .gcp_env
    echo "export KEY_FILE=$KEY_FILE" >> .gcp_env
}

enable_apis() {
    print_info "Enabling required GCP APIs..."
    
    gcloud services enable \
        container.googleapis.com \
        containerregistry.googleapis.com \
        storage-component.googleapis.com \
        cloudbuild.googleapis.com \
        --project=$PROJECT_ID
    
    print_info "APIs enabled."
}

create_gke_cluster() {
    print_info "Checking if GKE cluster exists..."
    
    # Check cluster status
    CLUSTER_STATUS=$(gcloud container clusters list --project=$PROJECT_ID --filter="name=$CLUSTER_NAME" --format="value(status)" 2>/dev/null)
    
    if [ -n "$CLUSTER_STATUS" ]; then
        if [ "$CLUSTER_STATUS" == "STOPPING" ]; then
            print_error "Cluster $CLUSTER_NAME is currently being deleted (status: STOPPING)."
            print_error "Please wait for deletion to complete before running this script again."
            exit 1
        fi
        
        print_warn "Cluster $CLUSTER_NAME already exists (status: $CLUSTER_STATUS). Skipping creation."
        print_info "Getting cluster credentials..."
        gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
    else
        print_info "Creating GKE cluster: $CLUSTER_NAME"
        
        gcloud container clusters create $CLUSTER_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --num-nodes=2 \
            --machine-type=n1-standard-4 \
            --disk-size=50GB \
            --enable-autoscaling \
            --min-nodes=2 \
            --max-nodes=10 \
            --enable-autorepair \
            --enable-autoupgrade \
            --addons=HorizontalPodAutoscaling,HttpLoadBalancing
        
        print_info "Cluster created successfully."
    fi
}

create_k8s_secret() {
    if [ ! -f "key.json" ]; then
        print_error "Service account key file (key.json) not found. Please run service account creation first."
        return
    fi
    
    print_info "Creating Kubernetes namespace..."
    kubectl create namespace stream-processing --dry-run=client -o yaml | kubectl apply -f -
    
    print_info "Creating Kubernetes secret for GCS access..."
    kubectl create secret generic gcp-service-account-key \
        --from-file=key.json=key.json \
        --namespace=stream-processing \
        --dry-run=client -o yaml | kubectl apply -f -
    
    print_info "Kubernetes secret created."
}

update_manifests() {
    print_info "Updating Kubernetes manifests with project-specific values..."
    
    # Update jobmanager-deployment.yaml
    if [ -f "deployment/kubernetes/jobmanager-deployment.yaml" ]; then
        sed -i.bak "s/PROJECT_ID/$PROJECT_ID/g" deployment/kubernetes/jobmanager-deployment.yaml
        sed -i.bak "s/YOUR_BUCKET_NAME/$BUCKET_NAME/g" deployment/kubernetes/jobmanager-deployment.yaml
        rm deployment/kubernetes/jobmanager-deployment.yaml.bak 2>/dev/null || true
    fi
    
    # Update taskmanager-daemonset.yaml
    if [ -f "deployment/kubernetes/taskmanager-daemonset.yaml" ]; then
        sed -i.bak "s/PROJECT_ID/$PROJECT_ID/g" deployment/kubernetes/taskmanager-daemonset.yaml
        sed -i.bak "s/YOUR_BUCKET_NAME/$BUCKET_NAME/g" deployment/kubernetes/taskmanager-daemonset.yaml
        rm deployment/kubernetes/taskmanager-daemonset.yaml.bak 2>/dev/null || true
    fi
    
    # Update gui-deployment.yaml
    if [ -f "deployment/kubernetes/gui-deployment.yaml" ]; then
        sed -i.bak "s/PROJECT_ID/$PROJECT_ID/g" deployment/kubernetes/gui-deployment.yaml
        rm deployment/kubernetes/gui-deployment.yaml.bak 2>/dev/null || true
    fi
    
    print_info "Manifests updated."
}

print_summary() {
    print_info "=========================================="
    print_info "GCP Setup Complete!"
    print_info "=========================================="
    echo ""
    print_info "Project ID: $PROJECT_ID"
    print_info "Region: $REGION"
    print_info "Zone: $ZONE"
    print_info "Cluster: $CLUSTER_NAME"
    print_info "GCS Bucket: $BUCKET_NAME"
    echo ""
    print_info "Next steps:"
    echo "  1. Build and push Docker images:"
    echo "     gcloud builds submit --config cloudbuild.yaml"
    echo ""
    echo "  2. Deploy to GKE:"
    echo "     cd deployment/kubernetes"
    echo "     kubectl apply -f namespace.yaml"
    echo "     kubectl apply -f rbac.yaml"
    echo "     kubectl apply -f configmap.yaml"
    echo "     kubectl apply -f postgres-secret.yaml"
    echo "     kubectl apply -f postgres-deployment.yaml"
    echo "     kubectl apply -f kafka-deployment.yaml"
    echo "     kubectl apply -f jobmanager-deployment.yaml"
    echo "     kubectl apply -f taskmanager-daemonset.yaml"
    echo "     kubectl apply -f gui-deployment.yaml"
    echo "     kubectl apply -f prometheus-deployment.yaml"
    echo "     kubectl apply -f grafana-deployment.yaml"
    echo ""
    echo "  3. Check deployment status:"
    echo "     kubectl get pods -n stream-processing"
    echo ""
    echo "  4. Access services:"
    echo "     kubectl get svc -n stream-processing"
    echo "     # Or use port-forward:"
    echo "     kubectl port-forward svc/jobmanager 8081:8081 -n stream-processing"
    echo "     kubectl port-forward svc/gui 5000:80 -n stream-processing"
    echo ""
    print_warn "Keep key.json secure! Consider using Workload Identity for production."
    print_info "Environment variables saved to .gcp_env"
}

# Main execution
main() {
    print_info "Starting GCP setup for Stream Processing Platform..."
    echo ""
    
    check_prerequisites
    get_project_id
    enable_apis
    create_gcs_bucket
    create_service_account
    create_gke_cluster
    create_k8s_secret
    update_manifests
    print_summary
}

# Run main function
main

