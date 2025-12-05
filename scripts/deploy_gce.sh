#!/bin/bash
# Deploy Stream Processing Platform to GCE VM
# This script creates a VM, installs Docker, copies project files, and runs docker-compose.

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
VM_NAME="stream-processing-vm"
ZONE="us-central1-a"
MACHINE_TYPE="e2-standard-8"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"
PROJECT_ID=$(gcloud config get-value project)

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
    if [ -z "$PROJECT_ID" ]; then
        print_error "GCP Project ID not set. Please run 'gcloud config set project <PROJECT_ID>'."
        exit 1
    fi
}

create_firewall_rules() {
    print_info "Creating firewall rules..."
    if ! gcloud compute firewall-rules describe allow-stream-processing --project="$PROJECT_ID" &>/dev/null; then
        gcloud compute firewall-rules create allow-stream-processing \
            --project="$PROJECT_ID" \
            --allow tcp:5000,tcp:8081 \
            --target-tags=stream-processing-server \
            --description="Allow GUI and JobManager access"
    else
        print_info "Firewall rule 'allow-stream-processing' already exists."
    fi
}

create_vm() {
    print_info "Creating VM '$VM_NAME'..."
    if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" &>/dev/null; then
        print_warn "VM '$VM_NAME' already exists. Skipping creation."
    else
        gcloud compute instances create "$VM_NAME" \
            --project="$PROJECT_ID" \
            --zone="$ZONE" \
            --machine-type="$MACHINE_TYPE" \
            --image-family="$IMAGE_FAMILY" \
            --image-project="$IMAGE_PROJECT" \
            --tags=stream-processing-server,http-server,https-server \
            --boot-disk-size=50GB \
            --scopes=cloud-platform
    fi

    print_info "Waiting for VM to be ready..."
    sleep 30
}

install_dependencies() {
    print_info "Installing Docker and Docker Compose on VM..."
    gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="
        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gnupg
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo \
          \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
          \$(. /etc/os-release && echo \"\$VERSION_CODENAME\") stable\" | \
          sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        sudo usermod -aG docker \$USER
    "
}

deploy_app() {
    print_info "Copying project files to VM..."
    # Create directory on VM
    gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="mkdir -p ~/stream-processing-platform"
    
    # Copy files (excluding heavy/unnecessary dirs via rsync exclude if possible, but scp is simpler for now)
    # We'll use a temporary tarball to speed up transfer of many small files
    print_info "Creating tarball of project..."
    tar -czf stream-processing.tar.gz \
        --exclude='.git' \
        --exclude='venv' \
        --exclude='__pycache__' \
        --exclude='*.tar.gz' \
        .

    print_info "Uploading tarball..."
    gcloud compute scp stream-processing.tar.gz "$VM_NAME":~/ --zone="$ZONE" --project="$PROJECT_ID"

    print_info "Extracting and deploying..."
    gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="
        tar -xzf stream-processing.tar.gz -C ~/stream-processing-platform
        cd ~/stream-processing-platform/deployment
        # Ensure docker-compose uses the correct context
        # We might need to adjust paths if they are relative in docker-compose.yml
        # The docker-compose.yml uses '../' context, which is correct relative to 'deployment' dir
        
        echo 'Starting services...'
        docker compose up -d --build
    "
    
    rm stream-processing.tar.gz
}

get_vm_ip() {
    IP=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
    print_info "Deployment complete!"
    print_info "GUI: http://$IP:5000"
    print_info "JobManager: http://$IP:8081"
}

main() {
    check_prerequisites
    create_firewall_rules
    create_vm
    install_dependencies
    deploy_app
    get_vm_ip
}

main
