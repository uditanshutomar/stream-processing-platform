# GCP Deployment Improvements

This document outlines the improvements made to the GCP deployment configuration for better production readiness, reliability, and security.

## Summary of Improvements

### 1. Health Check Endpoint ✅
**Issue**: Kubernetes manifests referenced `/health` endpoint that didn't exist.

**Fix**: Added proper health check endpoint to JobManager API:
- Returns 200 OK when healthy
- Returns 503 Service Unavailable when unhealthy
- Checks resource manager status
- Includes timestamp for monitoring

**File**: `jobmanager/api.py`

### 2. Improved GCS Error Handling ✅
**Issue**: GCS client initialization and uploads lacked proper error handling and validation.

**Fixes**:
- Added bucket existence check with warning if missing
- Improved error messages for debugging
- Added fallback to local storage if GCS fails
- Better logging for troubleshooting

**Files**: 
- `jobmanager/checkpoint_coordinator.py`
- `taskmanager/task_executor.py`

### 3. Pod Disruption Budgets (PDB) ✅
**Issue**: No protection against voluntary disruptions during cluster maintenance.

**Fix**: Added PDBs to ensure:
- At least 1 JobManager always available
- At least 2 TaskManagers always available
- Prevents accidental downtime during node drains

**File**: `deployment/kubernetes/pdb.yaml`

### 4. Persistent Volumes for TaskManager ✅
**Issue**: TaskManager used `emptyDir` which loses state on pod restart.

**Fix**: Created StatefulSet alternative with:
- PersistentVolumeClaims (100GB per TaskManager)
- State preserved across restarts
- Better for production workloads

**File**: `deployment/kubernetes/taskmanager-statefulset.yaml`

**Note**: Choose between DaemonSet (one per node) or StatefulSet (fixed replicas) based on your needs.

### 5. Horizontal Pod Autoscaler (HPA) ✅
**Issue**: No automatic scaling based on load.

**Fix**: Added HPA for JobManager:
- Scales based on CPU (70% threshold) and Memory (80% threshold)
- Min 2 replicas, Max 5 replicas
- Smart scaling policies (scale up faster, scale down slower)
- Stabilization windows to prevent thrashing

**File**: `deployment/kubernetes/hpa.yaml`

### 6. Network Policies ✅
**Issue**: No network isolation between pods.

**Fix**: Added network policies for:
- Ingress: Only allow traffic from authorized sources
- Egress: Control outbound connections
- Service-specific port restrictions
- Prometheus metrics scraping allowed

**File**: `deployment/kubernetes/network-policy.yaml`

### 7. Enhanced Health Probes ✅
**Issue**: Basic health checks without startup probes.

**Fixes**:
- Added startup probes (allows slow-starting containers)
- Improved timeout and failure threshold settings
- Better configuration for production workloads

**Files**:
- `deployment/kubernetes/jobmanager-deployment.yaml`
- `deployment/kubernetes/taskmanager-daemonset.yaml`

### 8. Pod Affinity/Anti-Affinity ✅
**Issue**: Pods could be scheduled on same node, risking single point of failure.

**Fix**: Added anti-affinity rules:
- JobManagers prefer different nodes
- TaskManagers prefer different nodes
- Improves high availability

**Files**:
- `deployment/kubernetes/jobmanager-deployment.yaml`
- `deployment/kubernetes/taskmanager-statefulset.yaml`

### 9. Resource Quotas and Limits ✅
**Issue**: No resource limits to prevent resource exhaustion.

**Fixes**:
- ResourceQuota: Namespace-level limits
- LimitRange: Default requests/limits for containers
- Prevents resource starvation
- Better resource planning

**Files**:
- `deployment/kubernetes/resource-quota.yaml`
- `deployment/kubernetes/limit-range.yaml`

## Deployment Order

When deploying, apply resources in this order:

```bash
# 1. Namespace and RBAC
kubectl apply -f namespace.yaml
kubectl apply -f rbac.yaml

# 2. Resource limits
kubectl apply -f resource-quota.yaml
kubectl apply -f limit-range.yaml

# 3. Config and secrets
kubectl apply -f configmap.yaml
kubectl apply -f postgres-secret.yaml

# 4. Dependencies
kubectl apply -f postgres-deployment.yaml
kubectl apply -f kafka-deployment.yaml

# 5. Main services
kubectl apply -f jobmanager-deployment.yaml
kubectl apply -f taskmanager-daemonset.yaml  # or taskmanager-statefulset.yaml

# 6. High availability
kubectl apply -f pdb.yaml
kubectl apply -f hpa.yaml

# 7. Security (optional, may need adjustment)
kubectl apply -f network-policy.yaml

# 8. Monitoring
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml
```

## Additional Recommendations

### 1. Use Workload Identity (Instead of Service Account Keys)

For better security, migrate from service account keys to Workload Identity:

```bash
# Enable Workload Identity on cluster
gcloud container clusters update CLUSTER_NAME \
    --workload-pool=PROJECT_ID.svc.id.goog

# Bind Kubernetes SA to GCP SA
gcloud iam service-accounts add-iam-policy-binding \
    GCP_SA@PROJECT_ID.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:PROJECT_ID.svc.id.goog[stream-processing/stream-processing-sa]"

# Add annotation to Kubernetes SA
kubectl annotate serviceaccount stream-processing-sa \
    iam.gke.io/gcp-service-account=GCP_SA@PROJECT_ID.iam.gserviceaccount.com \
    -n stream-processing
```

### 2. Use Cloud SQL Proxy (Instead of In-Cluster PostgreSQL)

For production, use Cloud SQL:

```bash
# Create Cloud SQL instance
gcloud sql instances create stream-processing-db \
    --database-version=POSTGRES_14 \
    --tier=db-n1-standard-2 \
    --region=us-central1

# Deploy Cloud SQL Proxy as sidecar
# See: https://cloud.google.com/sql/docs/postgres/connect-kubernetes-engine
```

### 3. Enable Pod Security Standards

```bash
# Add Pod Security Standards
kubectl label namespace stream-processing \
    pod-security.kubernetes.io/enforce=restricted \
    pod-security.kubernetes.io/audit=restricted \
    pod-security.kubernetes.io/warn=restricted
```

### 4. Add Monitoring Alerts

Create alerting policies in Cloud Monitoring for:
- High CPU/Memory usage
- Pod restart frequency
- Checkpoint failures
- Job failures
- Network errors

### 5. Enable Audit Logging

```bash
# Enable audit logging for the cluster
gcloud container clusters update CLUSTER_NAME \
    --enable-audit-logging \
    --audit-log-config-file=audit-config.yaml
```

## Testing the Improvements

### Test Health Endpoint
```bash
kubectl port-forward svc/jobmanager 8081:8081 -n stream-processing
curl http://localhost:8081/health
```

### Test Pod Disruption Budget
```bash
# Try to drain a node - should be blocked if it would violate PDB
kubectl drain NODE_NAME --ignore-daemonsets
```

### Test HPA
```bash
# Generate load and watch HPA scale
kubectl get hpa jobmanager-hpa -n stream-processing -w
```

### Test Network Policy
```bash
# Try to connect from unauthorized pod - should be blocked
kubectl run test-pod --image=busybox -n stream-processing --rm -it -- sh
# Try to connect to jobmanager:8081 - should fail
```

## Performance Impact

These improvements have minimal performance impact:
- Health checks: <1ms overhead
- Network policies: ~0.1ms latency per connection
- PDB: No runtime impact
- HPA: Scales based on metrics, no constant overhead
- Affinity rules: Only affect scheduling, not runtime

## Security Benefits

1. **Network Policies**: Isolate services, prevent lateral movement
2. **Resource Limits**: Prevent DoS via resource exhaustion
3. **Health Checks**: Faster failure detection and recovery
4. **PDB**: Prevent accidental downtime
5. **Affinity Rules**: Reduce blast radius of node failures

## Cost Considerations

- **HPA**: May increase costs during peak load (scales up)
- **Persistent Volumes**: Additional storage costs (~$0.17/GB/month)
- **Resource Quotas**: Help prevent runaway costs
- **Network Policies**: No additional cost

## Next Steps

1. Review and adjust resource limits based on your workload
2. Set up monitoring and alerting
3. Test disaster recovery scenarios
4. Document runbooks for common issues
5. Consider implementing Workload Identity
6. Set up CI/CD for automated deployments

## Troubleshooting

### PDB blocking pod deletion
```bash
# Temporarily delete PDB for maintenance
kubectl delete pdb jobmanager-pdb -n stream-processing
# Do maintenance
# Recreate PDB
kubectl apply -f pdb.yaml
```

### HPA not scaling
```bash
# Check HPA status
kubectl describe hpa jobmanager-hpa -n stream-processing

# Check metrics
kubectl top pods -n stream-processing
```

### Network policy too restrictive
```bash
# Temporarily disable
kubectl delete networkpolicy stream-processing-network-policy -n stream-processing
# Adjust policy
# Reapply
kubectl apply -f network-policy.yaml
```

