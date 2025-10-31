#!/bin/bash

# Chaos testing script - randomly kills and restarts TaskManagers
# while monitoring job health

set -e

JOBMANAGER_URL="http://localhost:8081"
CHAOS_DURATION=300  # 5 minutes
CHECK_INTERVAL=10   # 10 seconds

echo "Starting chaos testing for ${CHAOS_DURATION} seconds..."

# Function to get job status
get_job_status() {
    local job_id=$1
    curl -s "${JOBMANAGER_URL}/jobs/${job_id}/status" | grep -o '"status":"[^"]*"' | cut -d'"' -f4
}

# Function to kill random TaskManager
kill_random_taskmanager() {
    local containers=("stream-taskmanager-1" "stream-taskmanager-2" "stream-taskmanager-3")
    local random_idx=$((RANDOM % 3))
    local container=${containers[$random_idx]}

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Killing ${container}..."
    docker kill ${container} 2>/dev/null || true
}

# Function to restart TaskManager
restart_taskmanager() {
    local containers=("stream-taskmanager-1" "stream-taskmanager-2" "stream-taskmanager-3")
    local random_idx=$((RANDOM % 3))
    local container=${containers[$random_idx]}

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting ${container}..."
    docker start ${container} 2>/dev/null || true
}

# Submit a test job
echo "Submitting test job..."
JOB_ID=$(curl -s -X POST -F "job_file=@examples/word_count_job.pkl" \
    "${JOBMANAGER_URL}/jobs/submit" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$JOB_ID" ]; then
    echo "Failed to submit job"
    exit 1
fi

echo "Job submitted: ${JOB_ID}"

# Start chaos loop
start_time=$(date +%s)
failures=0
successes=0

while true; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))

    if [ $elapsed -gt $CHAOS_DURATION ]; then
        echo "Chaos testing completed after ${CHAOS_DURATION} seconds"
        break
    fi

    # Randomly decide action
    action=$((RANDOM % 10))

    if [ $action -lt 3 ]; then
        # 30% chance to kill
        kill_random_taskmanager
        ((failures++))
    elif [ $action -lt 6 ]; then
        # 30% chance to restart
        restart_taskmanager
    fi

    # Check job status
    sleep $CHECK_INTERVAL
    status=$(get_job_status "$JOB_ID")

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Job status: ${status}"

    if [ "$status" == "RUNNING" ]; then
        ((successes++))
    elif [ "$status" == "FAILED" ]; then
        echo "Job failed during chaos testing!"
        exit 1
    fi
done

# Calculate uptime
uptime_percent=$(awk "BEGIN {printf \"%.2f\", ($successes / ($successes + $failures)) * 100}")

echo ""
echo "=== Chaos Testing Results ==="
echo "Duration: ${CHAOS_DURATION}s"
echo "Failures injected: ${failures}"
echo "Health checks passed: ${successes}"
echo "Uptime: ${uptime_percent}%"
echo ""

if (( $(echo "$uptime_percent >= 99.9" | bc -l) )); then
    echo "✓ Chaos testing PASSED (uptime >= 99.9%)"
    exit 0
else
    echo "✗ Chaos testing FAILED (uptime < 99.9%)"
    exit 1
fi
