#!/usr/bin/env python3
"""
Complete example: Testing stream processing with real IoT sensor data

This example demonstrates:
1. Reading from a real data generator
2. Stateful processing (detecting anomalies)
3. Checkpointing with fault tolerance
4. Resource management and scheduling
"""
import sys
import os
import time
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.checkpoint_coordinator import CheckpointCoordinator
from jobmanager.resource_manager import ResourceManager
from jobmanager.scheduler import TaskScheduler
from examples.data_generator_iot import generate_sensor_data

# Statistics tracking
stats = {
    "total_readings": 0,
    "anomalies_detected": 0,
    "checkpoints_completed": 0,
    "start_time": time.time()
}

def process_sensor_reading(reading):
    """
    Process a sensor reading and detect anomalies

    In a real implementation, this would be an operator in the pipeline
    """
    stats["total_readings"] += 1

    # Simple anomaly detection logic
    is_anomaly = (
        reading["temperature"] < 10 or reading["temperature"] > 35 or
        reading["humidity"] < 20 or reading["humidity"] > 80 or
        reading["temperature"] == -999.9  # Sensor failure
    )

    if is_anomaly:
        stats["anomalies_detected"] += 1
        print(f"🚨 ANOMALY DETECTED: Sensor {reading['sensor_id']} in {reading['location']}")
        print(f"   Temperature: {reading['temperature']}°C, Humidity: {reading['humidity']}%")

    return {
        **reading,
        "anomaly_detected": is_anomaly
    }

def print_statistics():
    """Print current statistics"""
    elapsed = time.time() - stats["start_time"]
    throughput = stats["total_readings"] / elapsed if elapsed > 0 else 0

    print("\n" + "="*80)
    print("📊 STREAM PROCESSING STATISTICS")
    print("="*80)
    print(f"Runtime:              {elapsed:.1f} seconds")
    print(f"Total Readings:       {stats['total_readings']:,}")
    print(f"Anomalies Detected:   {stats['anomalies_detected']:,}")
    print(f"Anomaly Rate:         {stats['anomalies_detected']/max(stats['total_readings'],1)*100:.2f}%")
    print(f"Throughput:           {throughput:.1f} readings/second")
    print(f"Checkpoints:          {stats['checkpoints_completed']}")
    print("="*80 + "\n")

def main():
    print("="*80)
    print("🚀 STREAM PROCESSING PLATFORM - REAL DATA TEST")
    print("="*80)
    print()
    print("Testing with IoT Sensor Data:")
    print("  - 10 sensors generating data")
    print("  - Real-time anomaly detection")
    print("  - Checkpointing every 10 seconds")
    print("  - Fault-tolerant processing")
    print()
    print("Press Ctrl+C to stop and see statistics...")
    print()

    # Setup infrastructure
    print("🔧 Setting up infrastructure...")

    # 1. Resource Manager
    resource_manager = ResourceManager(heartbeat_timeout_ms=30000)
    resource_manager.start()

    # Register TaskManagers
    for i in range(3):
        resource_manager.register_task_manager(
            task_manager_id=f"tm_{i}",
            host="localhost",
            port=6124 + i,
            task_slots=4
        )

    print(f"   ✓ Registered {len(resource_manager.get_all_task_managers())} TaskManagers")

    # 2. Checkpoint Coordinator
    coordinator = CheckpointCoordinator(
        job_id="iot_monitoring",
        checkpoint_interval_ms=10000,  # Checkpoint every 10 seconds
        checkpoint_timeout_ms=30000     # 30 second timeout
    )
    coordinator.start()
    print("   ✓ Started Checkpoint Coordinator")

    # 3. Task Scheduler
    scheduler = TaskScheduler(resource_manager)
    print("   ✓ Initialized Task Scheduler")

    print("\n🌊 Starting data stream processing...\n")

    # Simulate task IDs for checkpointing
    task_ids = ["task_sensor_reader", "task_anomaly_detector", "task_aggregator"]

    # Setup signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print("\n\n⏸️  Shutting down gracefully...")
        coordinator.stop()
        resource_manager.stop()
        print_statistics()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Generate and process data
    data_generator = generate_sensor_data(
        num_sensors=10,
        anomaly_rate=0.05,  # 5% anomaly rate
        readings_per_second=2
    )

    checkpoint_trigger_count = 0
    last_checkpoint_time = time.time()

    try:
        for reading in data_generator:
            # Process the reading
            result = process_sensor_reading(reading)

            # Simulate checkpointing every 10 seconds
            if time.time() - last_checkpoint_time >= 10:
                checkpoint_id = coordinator.trigger_checkpoint(task_ids)
                checkpoint_trigger_count += 1

                # Simulate task acknowledgments
                import pickle
                state = {"readings_processed": stats["total_readings"]}
                state_bytes = pickle.dumps(state)

                for task_id in task_ids:
                    coordinator.acknowledge_checkpoint(
                        checkpoint_id=checkpoint_id,
                        task_id=task_id,
                        state_data=state_bytes,
                        task_manager_id="tm_0"
                    )

                # Check if completed
                latest = coordinator.get_latest_checkpoint()
                if latest and latest.checkpoint_id == checkpoint_id:
                    stats["checkpoints_completed"] += 1
                    print(f"✅ Checkpoint {checkpoint_id} completed "
                          f"({stats['total_readings']} readings processed)")

                last_checkpoint_time = time.time()

            # Print progress every 100 readings
            if stats["total_readings"] % 100 == 0:
                elapsed = time.time() - stats["start_time"]
                throughput = stats["total_readings"] / elapsed
                print(f"📈 Processed {stats['total_readings']:,} readings "
                      f"({throughput:.1f} readings/sec, "
                      f"{stats['anomalies_detected']} anomalies)")

    except KeyboardInterrupt:
        pass
    finally:
        print("\n\n⏹️  Stopping services...")
        coordinator.stop()
        resource_manager.stop()
        print_statistics()

if __name__ == "__main__":
    main()
