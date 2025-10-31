#!/usr/bin/env python3
"""
IoT sensor data generator
Simulates temperature, humidity, and pressure sensors with anomalies
"""
import random
import time
import json
import math

def generate_sensor_data(num_sensors=20, anomaly_rate=0.02, readings_per_second=2):
    """
    Generate IoT sensor data with occasional anomalies

    Args:
        num_sensors: Number of sensors to simulate
        anomaly_rate: Probability of generating an anomalous reading (0.0-1.0)
        readings_per_second: Rate of data generation per sensor
    """
    sensors = [
        {
            "id": f"sensor_{i:03d}",
            "location": f"zone_{i // 5}",  # Group sensors into zones
            "type": random.choice(["DHT22", "BME280", "SHT31"])
        }
        for i in range(num_sensors)
    ]

    baseline_temp = 22.0  # Comfortable room temperature
    time_offset = 0

    while True:
        time_offset += 1

        # Simulate daily temperature cycle (sine wave)
        # Full cycle every ~600 iterations (about 5 minutes at 2Hz)
        daily_cycle = 3 * math.sin(2 * math.pi * time_offset / 600)

        for sensor in sensors:
            # Introduce anomalies
            is_anomaly = random.random() < anomaly_rate

            if is_anomaly:
                # Anomalous readings
                anomaly_type = random.choice(["high_temp", "low_temp", "sensor_failure"])

                if anomaly_type == "high_temp":
                    temperature = random.uniform(40, 60)
                    humidity = random.uniform(10, 30)
                elif anomaly_type == "low_temp":
                    temperature = random.uniform(-10, 5)
                    humidity = random.uniform(80, 95)
                else:  # sensor_failure
                    temperature = -999.9
                    humidity = -999.9
            else:
                # Normal readings with small random variations
                temperature = baseline_temp + daily_cycle + random.gauss(0, 0.5)
                humidity = 50 + random.gauss(0, 5)

            pressure = 1013 + random.gauss(0, 2)  # Normal atmospheric pressure

            reading = {
                "sensor_id": sensor["id"],
                "location": sensor["location"],
                "device_type": sensor["type"],
                "timestamp": int(time.time() * 1000),
                "temperature": round(temperature, 2),
                "humidity": round(humidity, 2),
                "pressure": round(pressure, 2),
                "battery_level": round(100 - (time_offset / 10000) * 100, 1),  # Slowly draining
                "is_anomaly": is_anomaly
            }

            yield reading

        time.sleep(1.0 / readings_per_second)

if __name__ == "__main__":
    print("# IoT Sensor Data Generator")
    print("# Generating sensor readings... (Ctrl+C to stop)")
    print("# Watch for anomalies (marked with is_anomaly: true)")
    print()

    try:
        for reading in generate_sensor_data(num_sensors=10, anomaly_rate=0.05):
            # Color code anomalies for visibility
            if reading["is_anomaly"]:
                print(f"⚠️  ANOMALY: {json.dumps(reading)}")
            else:
                print(json.dumps(reading))
    except KeyboardInterrupt:
        print("\nStopped.")
