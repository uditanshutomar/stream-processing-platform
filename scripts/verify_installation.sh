#!/bin/bash

# Verification script to check if all components are properly installed

echo "=========================================="
echo "Stream Processing Platform Verification"
echo "=========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_component() {
    local name=$1
    local path=$2

    if [ -f "$path" ] || [ -d "$path" ]; then
        echo -e "${GREEN}✓${NC} $name"
        return 0
    else
        echo -e "${RED}✗${NC} $name (missing: $path)"
        return 1
    fi
}

passed=0
failed=0

echo "Checking Core Components..."
echo ""

# JobManager
check_component "JobManager API" "jobmanager/api.py" && ((passed++)) || ((failed++))
check_component "JobGraph" "jobmanager/job_graph.py" && ((passed++)) || ((failed++))
check_component "Scheduler" "jobmanager/scheduler.py" && ((passed++)) || ((failed++))
check_component "ResourceManager" "jobmanager/resource_manager.py" && ((passed++)) || ((failed++))
check_component "CheckpointCoordinator" "jobmanager/checkpoint_coordinator.py" && ((passed++)) || ((failed++))

echo ""
echo "Checking TaskManager..."
echo ""

check_component "TaskExecutor" "taskmanager/task_executor.py" && ((passed++)) || ((failed++))
check_component "Operators Base" "taskmanager/operators/base.py" && ((passed++)) || ((failed++))
check_component "Stateless Operators" "taskmanager/operators/stateless.py" && ((passed++)) || ((failed++))
check_component "Stateful Operators" "taskmanager/operators/stateful.py" && ((passed++)) || ((failed++))
check_component "Source Operators" "taskmanager/operators/sources.py" && ((passed++)) || ((failed++))
check_component "Sink Operators" "taskmanager/operators/sinks.py" && ((passed++)) || ((failed++))

echo ""
echo "Checking State Management..."
echo ""

check_component "RocksDB Backend" "taskmanager/state/rocksdb_backend.py" && ((passed++)) || ((failed++))
check_component "State Types" "taskmanager/state/state_types.py" && ((passed++)) || ((failed++))

echo ""
echo "Checking Network Layer..."
echo ""

check_component "Buffer Pool" "taskmanager/network/buffer_pool.py" && ((passed++)) || ((failed++))
check_component "Flow Control" "taskmanager/network/flow_control.py" && ((passed++)) || ((failed++))

echo ""
echo "Checking Common Modules..."
echo ""

check_component "Config" "common/config.py" && ((passed++)) || ((failed++))
check_component "Serialization" "common/serialization.py" && ((passed++)) || ((failed++))
check_component "Watermarks" "common/watermarks.py" && ((passed++)) || ((failed++))
check_component "Proto Definition" "common/protobuf/stream_processing.proto" && ((passed++)) || ((failed++))
check_component "Proto Generated (pb2)" "common/protobuf/stream_processing_pb2.py" && ((passed++)) || ((failed++))
check_component "Proto Generated (grpc)" "common/protobuf/stream_processing_pb2_grpc.py" && ((passed++)) || ((failed++))

echo ""
echo "Checking Examples..."
echo ""

check_component "Word Count Example" "examples/word_count.py" && ((passed++)) || ((failed++))
check_component "Windowed Aggregation" "examples/windowed_aggregation.py" && ((passed++)) || ((failed++))
check_component "Stateful Deduplication" "examples/stateful_deduplication.py" && ((passed++)) || ((failed++))
check_component "Stream Join" "examples/stream_join.py" && ((passed++)) || ((failed++))

echo ""
echo "Checking Tests..."
echo ""

check_component "Unit Tests" "tests/unit/test_operators.py" && ((passed++)) || ((failed++))
check_component "Integration Tests" "tests/integration/test_failure_recovery.py" && ((passed++)) || ((failed++))

echo ""
echo "Checking Deployment..."
echo ""

check_component "Docker Compose" "deployment/docker-compose.yml" && ((passed++)) || ((failed++))
check_component "JobManager Dockerfile" "jobmanager/Dockerfile" && ((passed++)) || ((failed++))
check_component "TaskManager Dockerfile" "taskmanager/Dockerfile" && ((passed++)) || ((failed++))

echo ""
echo "Checking Scripts..."
echo ""

check_component "Proto Generator" "scripts/generate_proto.sh" && ((passed++)) || ((failed++))
check_component "Benchmark" "scripts/benchmark.py" && ((passed++)) || ((failed++))
check_component "Chaos Test" "scripts/chaos_test.sh" && ((passed++)) || ((failed++))

echo ""
echo "Checking Documentation..."
echo ""

check_component "README" "README.md" && ((passed++)) || ((failed++))
check_component "QUICKSTART" "QUICKSTART.md" && ((passed++)) || ((failed++))
check_component "Architecture Doc" "docs/architecture.md" && ((passed++)) || ((failed++))
check_component "API Reference" "docs/api_reference.md" && ((passed++)) || ((failed++))
check_component "Deployment Guide" "docs/deployment_guide.md" && ((passed++)) || ((failed++))

echo ""
echo "=========================================="
echo "Verification Results"
echo "=========================================="
echo -e "${GREEN}Passed:${NC} $passed"
echo -e "${RED}Failed:${NC} $failed"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✓ All components verified successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Generate gRPC stubs: ./scripts/generate_proto.sh"
    echo "2. Start the platform: cd deployment && docker-compose up -d"
    echo "3. Run examples: python examples/word_count.py"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some components are missing. Please check the installation.${NC}"
    exit 1
fi
