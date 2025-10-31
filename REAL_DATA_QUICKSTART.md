# Real Data Testing - Quick Start Guide

## 🚀 Quick Demo

Run this to see all three data generators in action:

```bash
python3 -c "
import sys
sys.path.insert(0, 'examples')
import itertools

# IoT Sensor Data
from data_generator_iot import generate_sensor_data
print('IoT Sensors:')
for reading in itertools.islice(generate_sensor_data(num_sensors=2), 3):
    print(f'  {reading[\"sensor_id\"]}: {reading[\"temperature\"]}°C')

# E-commerce Events
from data_generator_ecommerce import generate_ecommerce_events
print('\nE-commerce Events:')
for event in itertools.islice(generate_ecommerce_events(), 3):
    print(f'  {event[\"event_type\"]}: {event[\"product_name\"]}')

# Financial Data
from data_generator_financial import generate_market_data
print('\nStock Prices:')
for tick in itertools.islice(generate_market_data(symbols=['AAPL']), 3):
    print(f'  {tick[\"symbol\"]}: \${tick[\"price\"]}')
"
```

## 📊 Available Data Generators

### 1. IoT Sensor Data Generator
Simulates temperature, humidity, and pressure sensors with realistic anomalies.

**Run it:**
```bash
python3 examples/data_generator_iot.py
```

**Output:**
```json
{
  "sensor_id": "sensor_001",
  "location": "zone_0",
  "device_type": "DHT22",
  "timestamp": 1730369730000,
  "temperature": 22.5,
  "humidity": 45.2,
  "pressure": 1013.25,
  "battery_level": 100.0,
  "is_anomaly": false
}
```

**Use Cases:**
- Real-time temperature monitoring
- Anomaly detection (temperature spikes)
- Predictive maintenance
- Alert systems

---

### 2. E-commerce Event Generator
Simulates online shopping behavior with realistic user journeys.

**Run it:**
```bash
python3 examples/data_generator_ecommerce.py
```

**Output:**
```json
{
  "event_id": "evt_123456789",
  "timestamp": 1730369730000,
  "user_id": "user_0042",
  "event_type": "add_to_cart",
  "product_id": "prod_2",
  "product_name": "Wireless Mouse",
  "price": 29.99,
  "category": "Electronics",
  "quantity": 1,
  "session_id": "sess_9876",
  "cart_size": 1
}
```

**Event Types:**
- `page_view` - User views product
- `search` - User searches for products
- `add_to_cart` - User adds item to cart
- `remove_from_cart` - User removes item from cart
- `purchase` - User completes purchase

**Use Cases:**
- Shopping cart abandonment analysis
- Conversion funnel tracking
- Real-time recommendations
- Revenue analytics

---

### 3. Financial Market Data Generator
Simulates stock market tick data using geometric Brownian motion.

**Run it:**
```bash
python3 examples/data_generator_financial.py
```

**Output:**
```json
{
  "timestamp": 1730369730000,
  "symbol": "AAPL",
  "price": 178.45,
  "bid": 178.44,
  "ask": 178.46,
  "volume": 1250,
  "daily_high": 179.20,
  "daily_low": 176.80,
  "daily_volume": 125000,
  "exchange": "NASDAQ"
}
```

**Use Cases:**
- Moving average calculations
- Price alerts and thresholds
- Volume-weighted average price (VWAP)
- Trading signal generation

---

## 🧪 Test with Your Code

### Example 1: Basic Processing

```python
import sys
sys.path.insert(0, 'examples')
from data_generator_iot import generate_sensor_data

# Process IoT data
for reading in generate_sensor_data(num_sensors=5):
    # Your processing logic here
    if reading['temperature'] > 30:
        print(f"Alert: High temperature from {reading['sensor_id']}")

    # Add your checkpoint logic
    # Add your state management
    # etc.
```

### Example 2: With Checkpointing

```python
import sys
sys.path.insert(0, 'examples')
from jobmanager.checkpoint_coordinator import CheckpointCoordinator
from examples.data_generator_ecommerce import generate_ecommerce_events
import pickle
import time

# Setup checkpoint coordinator
coordinator = CheckpointCoordinator(
    job_id="ecommerce_test",
    checkpoint_interval_ms=10000,  # 10 seconds
    checkpoint_timeout_ms=30000
)
coordinator.start()

# Process events
task_ids = ["task_1"]
count = 0
last_checkpoint = time.time()

try:
    for event in generate_ecommerce_events():
        count += 1

        # Your business logic here
        if event['event_type'] == 'purchase':
            print(f"Purchase: ${event['price']}")

        # Checkpoint every 10 seconds
        if time.time() - last_checkpoint >= 10:
            checkpoint_id = coordinator.trigger_checkpoint(task_ids)

            # Simulate acknowledgment
            state = {"events_processed": count}
            state_bytes = pickle.dumps(state)

            for task_id in task_ids:
                coordinator.acknowledge_checkpoint(
                    checkpoint_id, task_id, state_bytes, "tm_1"
                )

            print(f"Checkpoint {checkpoint_id} created")
            last_checkpoint = time.time()

except KeyboardInterrupt:
    coordinator.stop()
```

### Example 3: Complete Test

Run the comprehensive test example:

```bash
python3 examples/test_with_real_data.py
```

This demonstrates:
- ✅ Real data ingestion
- ✅ Stream processing
- ✅ Anomaly detection
- ✅ Checkpointing
- ✅ Resource management
- ✅ Statistics tracking

---

## 🎯 Recommended Testing Scenarios

### Scenario 1: Throughput Test
**Goal:** Test how many events/second your system can handle

```bash
# Generate high-frequency IoT data (20 readings/sec)
python3 -c "
from examples.data_generator_iot import generate_sensor_data
for reading in generate_sensor_data(num_sensors=50, readings_per_second=20):
    pass  # Your processing here
"
```

### Scenario 2: Fault Tolerance Test
**Goal:** Test checkpoint and recovery mechanisms

```python
# 1. Start processing
# 2. Trigger checkpoint
# 3. Simulate crash (kill process)
# 4. Restart and verify recovery from checkpoint
```

### Scenario 3: State Management Test
**Goal:** Test stateful operators with real data

```python
# Track running averages of sensor temperatures
# Maintain user shopping cart state
# Calculate cumulative stock returns
```

### Scenario 4: Latency Test
**Goal:** Measure end-to-end processing latency

```python
# Add timestamp at ingestion
# Measure time until output
# Target: <100ms latency
```

---

## 📈 Performance Benchmarks

Test your code against these targets:

| Metric | Target | Test Command |
|--------|--------|--------------|
| **Throughput** | 10,000+ events/sec | High-frequency generator |
| **Latency** | <100ms end-to-end | Timestamp injection |
| **Checkpoint Time** | <5 seconds | Large state snapshot |
| **Recovery Time** | <10 seconds | Kill and restart |
| **Memory** | Stable over 1 hour | Long-running test |

---

## 🐛 Debugging Tips

### View Raw Data
```bash
# See what the generator produces
python3 examples/data_generator_iot.py | head -20

# Save to file for analysis
python3 examples/data_generator_iot.py > /tmp/sensor_data.jsonl
```

### Slow Down Generation
```python
# Modify generator parameters
generate_sensor_data(
    num_sensors=5,
    readings_per_second=0.5  # One reading every 2 seconds
)
```

### Add Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

for event in generate_ecommerce_events():
    logging.debug(f"Processing: {event}")
    # Your logic
```

---

## 💡 Next Steps

1. **Start Simple**: Begin with IoT sensor data (easiest to understand)
2. **Add Checkpointing**: Integrate CheckpointCoordinator
3. **Test Failure Recovery**: Simulate crashes and verify recovery
4. **Scale Up**: Add more sensors/events and measure performance
5. **Add State**: Implement stateful operators (aggregations, joins)

---

## 📚 Additional Resources

- **Full Documentation**: See `REAL_WORLD_TEST_DATA.md` for all 10 data types
- **Code Fixes**: See `FIXES_SUMMARY.md` for all improvements made
- **Test Results**: See `tests/test_comprehensive_validation.py` for complete tests

---

## ✅ Validation Checklist

Before production, test:

- [ ] Process 100,000+ events successfully
- [ ] Checkpoint completes successfully
- [ ] Recovery from checkpoint works
- [ ] No memory leaks over 1+ hour
- [ ] Latency stays under 100ms
- [ ] No data loss on failure
- [ ] No duplicate processing (exactly-once)
- [ ] Multiple TaskManagers work correctly
- [ ] Database reconnection handles disconnects

---

**Happy Testing!** 🎉

Your stream processing platform is now ready to handle real-world data!
