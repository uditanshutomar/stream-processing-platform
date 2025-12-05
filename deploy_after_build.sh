#!/bin/bash
# Deploy to Kubernetes after images are built

set -e

export GCP_PROJECT_ID="dcsc-project-479911"
NAMESPACE="stream-processing"

echo "=========================================="
echo "Deploying to Kubernetes"
echo "=========================================="
echo ""

cd deployment/kubernetes

# Deploy dependencies
echo "Deploying dependencies..."
kubectl apply -f postgres-deployment.yaml
kubectl apply -f kafka-deployment.yaml

echo "Waiting for PostgreSQL and Kafka to be ready..."
kubectl wait --for=condition=ready pod -l app=postgres -n $NAMESPACE --timeout=300s || true
kubectl wait --for=condition=ready pod -l app=kafka -n $NAMESPACE --timeout=300s || true

# Deploy main services
echo ""
echo "Deploying main services..."
kubectl apply -f jobmanager-deployment.yaml
kubectl apply -f taskmanager-daemonset.yaml
kubectl apply -f gui-deployment.yaml

# Deploy monitoring
echo ""
echo "Deploying monitoring..."
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml

# Deploy HA resources
echo ""
echo "Deploying HA resources..."
kubectl apply -f pdb.yaml
kubectl apply -f hpa.yaml

echo ""
echo "Waiting for services to be ready..."
sleep 30

echo ""
echo "Checking deployment status..."
kubectl get pods -n $NAMESPACE
kubectl get svc -n $NAMESPACE

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Get external IPs:"
echo "  kubectl get svc -n $NAMESPACE"
echo ""
echo "Access services:"
echo "  JobManager: kubectl port-forward svc/jobmanager 8081:8081 -n $NAMESPACE"
echo "  GUI: kubectl port-forward svc/gui 5000:80 -n $NAMESPACE"
echo "  Grafana: kubectl port-forward svc/grafana 3000:3000 -n $NAMESPACE"

