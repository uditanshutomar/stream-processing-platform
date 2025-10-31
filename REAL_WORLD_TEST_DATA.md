# Real-World Test Data Suggestions

## 1. 🌐 Network Traffic Data (Click Stream Analytics)

### Dataset: Web Server Logs
**Source**: Apache/Nginx access logs or public datasets

**Format**:
```json
{
  "timestamp": "2025-10-31T10:15:30Z",
  "user_id": "user_12345",
  "url": "/products/item-456",
  "method": "GET",
  "status_code": 200,
  "response_time_ms": 45,
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "session_id": "sess_abc123"
}
```

**Test Scenarios**:
- **Real-time Analytics**: Count page views per minute
- **Session Tracking**: Track user sessions with stateful operators
- **Anomaly Detection**: Detect unusual traffic patterns (DDoS)
- **Conversion Funnel**: Track user journey through checkout

**Public Dataset**:
- NASA Access Logs: http://ita.ee.lbl.gov/html/contrib/NASA-HTTP.html
- Kaggle Web Server Logs

---

## 2. 📊 Financial Market Data (High-Frequency Trading)

### Dataset: Stock Market Tick Data
**Source**: Yahoo Finance API, Alpha Vantage, or Polygon.io

**Format**:
```json
{
  "timestamp": 1730369730000,
  "symbol": "AAPL",
  "price": 178.45,
  "volume": 1000,
  "bid": 178.44,
  "ask": 178.46,
  "exchange": "NASDAQ"
}
```

**Test Scenarios**:
- **Moving Average**: Calculate 5-minute moving average
- **Price Alerts**: Trigger alerts on price thresholds
- **Volume Analysis**: Aggregate trading volume in windows
- **Arbitrage Detection**: Compare prices across exchanges
- **VWAP Calculation**: Volume-weighted average price

**Getting Data**:
```python
import yfinance as yf
import time

def stream_stock_data():
    ticker = yf.Ticker("AAPL")
    while True:
        data = ticker.history(period="1m", interval="1m")
        yield {
            "timestamp": int(time.time() * 1000),
            "symbol": "AAPL",
            "price": float(data['Close'].iloc[-1]),
            "volume": int(data['Volume'].iloc[-1])
        }
        time.sleep(1)
```

---

## 3. 🌡️ IoT Sensor Data (Industrial Monitoring)

### Dataset: Environmental Sensor Readings
**Source**: Smart home devices, weather stations, industrial sensors

**Format**:
```json
{
  "sensor_id": "temp_sensor_001",
  "timestamp": 1730369730000,
  "temperature": 22.5,
  "humidity": 45.2,
  "pressure": 1013.25,
  "location": "warehouse_a",
  "device_type": "DHT22"
}
```

**Test Scenarios**:
- **Anomaly Detection**: Detect temperature spikes
- **Predictive Maintenance**: Identify failing sensors
- **Aggregation**: Average temperature per room per hour
- **Alert System**: Notify when thresholds exceeded
- **Trend Analysis**: Track temperature changes over time

**Public Dataset**:
- Intel Berkeley Research Lab: http://db.csail.mit.edu/labdata/labdata.html
- NOAA Weather Data: https://www.ncdc.noaa.gov/data-access

**Sample Generator**:
```python
import random
import time

def generate_sensor_data():
    sensors = [f"sensor_{i:03d}" for i in range(10)]
    while True:
        for sensor_id in sensors:
            yield {
                "sensor_id": sensor_id,
                "timestamp": int(time.time() * 1000),
                "temperature": round(20 + random.gauss(0, 5), 2),
                "humidity": round(50 + random.gauss(0, 10), 2),
                "pressure": round(1013 + random.gauss(0, 5), 2)
            }
        time.sleep(0.1)
```

---

## 4. 🚗 Vehicle Telemetry Data (Fleet Management)

### Dataset: GPS and Vehicle Metrics
**Source**: Taxi trip data, fleet management systems

**Format**:
```json
{
  "vehicle_id": "vehicle_42",
  "timestamp": 1730369730000,
  "latitude": 40.7580,
  "longitude": -73.9855,
  "speed": 45.5,
  "fuel_level": 65.2,
  "engine_rpm": 2500,
  "odometer": 45230.5
}
```

**Test Scenarios**:
- **Geofencing**: Detect vehicles entering/leaving zones
- **Speed Monitoring**: Track speed violations
- **Route Optimization**: Analyze common routes
- **Fuel Efficiency**: Calculate MPG in real-time
- **Predictive Maintenance**: Monitor engine health

**Public Dataset**:
- NYC Taxi Trip Data: https://www1.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- Uber Movement Data: https://movement.uber.com/

---

## 5. 🛒 E-commerce Events (Retail Analytics)

### Dataset: User Shopping Behavior
**Source**: Online store transaction logs

**Format**:
```json
{
  "event_id": "evt_12345",
  "timestamp": 1730369730000,
  "user_id": "user_789",
  "event_type": "add_to_cart",
  "product_id": "prod_456",
  "product_name": "Wireless Mouse",
  "price": 29.99,
  "category": "Electronics",
  "quantity": 1,
  "session_id": "sess_abc123"
}
```

**Event Types**: `page_view`, `add_to_cart`, `remove_from_cart`, `purchase`, `search`

**Test Scenarios**:
- **Shopping Cart Abandonment**: Track incomplete purchases
- **Real-time Recommendations**: Suggest products based on behavior
- **Conversion Rate**: Calculate funnel metrics
- **Inventory Management**: Track stock in real-time
- **Fraud Detection**: Identify suspicious patterns

**Public Dataset**:
- Kaggle Retail Data: https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset
- UCI Online Retail: https://archive.ics.uci.edu/ml/datasets/online+retail

---

## 6. 📱 Social Media Stream (Sentiment Analysis)

### Dataset: Social Media Posts
**Source**: Twitter/X API, Reddit API, Mastodon

**Format**:
```json
{
  "post_id": "tweet_12345",
  "timestamp": 1730369730000,
  "user_id": "user_456",
  "text": "This product is amazing! #awesome",
  "hashtags": ["awesome"],
  "mentions": ["@brand"],
  "retweets": 5,
  "likes": 23,
  "language": "en"
}
```

**Test Scenarios**:
- **Trending Topics**: Track hashtag popularity
- **Sentiment Analysis**: Classify positive/negative posts
- **Influencer Detection**: Identify high-engagement users
- **Brand Monitoring**: Track brand mentions
- **Event Detection**: Detect viral content

**Getting Data**:
```python
# Using tweepy for Twitter
import tweepy

# Or use Reddit API
import praw
```

---

## 7. 🏥 Healthcare Data (Patient Monitoring)

### Dataset: Patient Vital Signs
**Source**: Hospital monitoring systems, wearables

**Format**:
```json
{
  "patient_id": "patient_1001",
  "timestamp": 1730369730000,
  "heart_rate": 72,
  "blood_pressure_systolic": 120,
  "blood_pressure_diastolic": 80,
  "oxygen_saturation": 98,
  "temperature": 37.0,
  "alert_level": "normal"
}
```

**Test Scenarios**:
- **Critical Alert System**: Detect dangerous vital signs
- **Trend Analysis**: Track patient recovery
- **Anomaly Detection**: Identify irregular patterns
- **Bed Occupancy**: Track hospital capacity
- **Emergency Response**: Prioritize critical patients

**Note**: Use synthetic data for privacy compliance

---

## 8. 🎮 Gaming Analytics (Player Behavior)

### Dataset: Game Events
**Source**: Game servers, player actions

**Format**:
```json
{
  "player_id": "player_789",
  "timestamp": 1730369730000,
  "event_type": "level_complete",
  "level": 15,
  "score": 8500,
  "time_spent_seconds": 180,
  "items_collected": 12,
  "deaths": 2
}
```

**Test Scenarios**:
- **Player Retention**: Track engagement over time
- **Difficulty Balancing**: Analyze level completion rates
- **Cheat Detection**: Identify suspicious behavior
- **Real-time Leaderboards**: Rank players
- **A/B Testing**: Compare feature effectiveness

---

## 9. 🌐 Network Performance (DevOps Monitoring)

### Dataset: Server Metrics
**Source**: Application logs, system metrics

**Format**:
```json
{
  "server_id": "web_server_01",
  "timestamp": 1730369730000,
  "cpu_usage": 45.2,
  "memory_usage": 68.5,
  "disk_io": 1024,
  "network_in": 50000,
  "network_out": 30000,
  "request_count": 150,
  "error_count": 2,
  "avg_response_time": 45
}
```

**Test Scenarios**:
- **Auto-scaling**: Trigger scaling based on load
- **Alert System**: Notify on resource exhaustion
- **Performance Analysis**: Track response times
- **Error Rate Monitoring**: Detect service degradation
- **Capacity Planning**: Predict resource needs

---

## 10. ⚡ Smart Grid Data (Energy Monitoring)

### Dataset: Power Consumption
**Source**: Smart meters, grid sensors

**Format**:
```json
{
  "meter_id": "meter_12345",
  "timestamp": 1730369730000,
  "power_consumption_kwh": 2.5,
  "voltage": 220.5,
  "current": 11.4,
  "power_factor": 0.95,
  "grid_frequency": 50.02,
  "location": "residential_area_a"
}
```

**Test Scenarios**:
- **Load Balancing**: Distribute power efficiently
- **Peak Detection**: Identify high demand periods
- **Anomaly Detection**: Detect power theft
- **Demand Forecasting**: Predict consumption
- **Fault Detection**: Identify grid issues

---

## 📦 Ready-to-Use Test Data Generators

### Generator 1: E-commerce Events
```python
# Create: examples/data_generator_ecommerce.py

import random
import time
import json
from datetime import datetime

products = [
    {"id": "prod_1", "name": "Laptop", "price": 999.99, "category": "Electronics"},
    {"id": "prod_2", "name": "Mouse", "price": 29.99, "category": "Electronics"},
    {"id": "prod_3", "name": "Keyboard", "price": 79.99, "category": "Electronics"},
    {"id": "prod_4", "name": "Monitor", "price": 299.99, "category": "Electronics"},
    {"id": "prod_5", "name": "Headphones", "price": 149.99, "category": "Audio"},
]

event_types = ["page_view", "add_to_cart", "remove_from_cart", "purchase", "search"]
users = [f"user_{i}" for i in range(1, 101)]

def generate_ecommerce_events():
    """Generate realistic e-commerce events"""
    while True:
        user = random.choice(users)
        product = random.choice(products)
        event_type = random.choices(
            event_types,
            weights=[50, 20, 5, 10, 15]  # Realistic distribution
        )[0]

        event = {
            "event_id": f"evt_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "user_id": user,
            "event_type": event_type,
            "product_id": product["id"],
            "product_name": product["name"],
            "price": product["price"],
            "category": product["category"],
            "session_id": f"sess_{hash(user) % 10000}"
        }

        yield event
        time.sleep(random.uniform(0.1, 0.5))  # 2-10 events per second

if __name__ == "__main__":
    for event in generate_ecommerce_events():
        print(json.dumps(event))
```

### Generator 2: IoT Sensor Data
```python
# Create: examples/data_generator_iot.py

import random
import time
import json
import math

def generate_sensor_data(num_sensors=20, anomaly_rate=0.01):
    """Generate IoT sensor data with occasional anomalies"""
    sensors = [f"sensor_{i:03d}" for i in range(num_sensors)]
    baseline_temp = 22.0
    time_offset = 0

    while True:
        time_offset += 1
        # Simulate daily temperature cycle
        daily_cycle = 3 * math.sin(time_offset / 100)

        for sensor_id in sensors:
            # Introduce anomalies
            is_anomaly = random.random() < anomaly_rate

            if is_anomaly:
                temperature = random.uniform(40, 60)  # Anomalous reading
            else:
                temperature = baseline_temp + daily_cycle + random.gauss(0, 1)

            reading = {
                "sensor_id": sensor_id,
                "timestamp": int(time.time() * 1000),
                "temperature": round(temperature, 2),
                "humidity": round(50 + random.gauss(0, 5), 2),
                "pressure": round(1013 + random.gauss(0, 2), 2),
                "is_anomaly": is_anomaly
            }

            yield reading

        time.sleep(0.5)  # Update every 0.5 seconds

if __name__ == "__main__":
    for reading in generate_sensor_data():
        print(json.dumps(reading))
```

### Generator 3: Financial Tick Data
```python
# Create: examples/data_generator_financial.py

import random
import time
import json

class StockSimulator:
    def __init__(self, symbol, initial_price=100.0):
        self.symbol = symbol
        self.price = initial_price
        self.volatility = 0.02

    def next_price(self):
        """Generate next price using random walk"""
        change = self.price * self.volatility * random.gauss(0, 1)
        self.price += change
        return self.price

def generate_market_data(symbols=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]):
    """Generate realistic stock market tick data"""
    simulators = {symbol: StockSimulator(symbol, random.uniform(50, 500))
                  for symbol in symbols}

    while True:
        for symbol, sim in simulators.items():
            price = sim.next_price()
            spread = price * 0.001  # 0.1% spread

            tick = {
                "timestamp": int(time.time() * 1000),
                "symbol": symbol,
                "price": round(price, 2),
                "bid": round(price - spread/2, 2),
                "ask": round(price + spread/2, 2),
                "volume": random.randint(100, 10000),
                "exchange": "NASDAQ"
            }

            yield tick

        time.sleep(0.1)  # 10 ticks per second per symbol

if __name__ == "__main__":
    for tick in generate_market_data():
        print(json.dumps(tick))
```

---

## 🧪 Complete Test Example

### Example: Real-Time E-commerce Analytics
```python
# Create: examples/ecommerce_analytics_test.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.job_graph import StreamExecutionEnvironment
from taskmanager.operators.sources import IteratorSourceOperator
from taskmanager.operators.sinks import PrintSinkOperator
from taskmanager.operators.stateless import FilterOperator, MapOperator
from taskmanager.operators.stateful import ReduceOperator
from examples.data_generator_ecommerce import generate_ecommerce_events

def main():
    # Create environment
    env = StreamExecutionEnvironment("EcommerceAnalytics")
    env.set_parallelism(4).enable_checkpointing(5000)

    # Create source from generator
    event_generator = generate_ecommerce_events()
    source = IteratorSourceOperator(event_generator)

    # Build pipeline
    stream = env.add_source(source)

    # Filter only purchase events
    purchases = stream.filter(lambda e: e["event_type"] == "purchase")

    # Extract revenue
    revenue = purchases.map(lambda e: {
        "timestamp": e["timestamp"],
        "revenue": e["price"] * e.get("quantity", 1)
    })

    # Aggregate revenue per minute (simplified)
    # In real implementation, use window operators

    # Sink results
    revenue.add_sink(PrintSinkOperator("Revenue Stream"))

    # Execute
    job_graph = env.get_job_graph()
    print(f"Job Graph: {len(job_graph.vertices)} vertices")
    print("Starting stream processing...")

    # Let it run for 30 seconds
    import time
    time.sleep(30)

    print("Test completed!")

if __name__ == "__main__":
    main()
```

---

## 📊 Recommended Starting Point

**Best for beginners**: Start with **IoT Sensor Data** (Option 3)
- Simple data structure
- Easy to generate synthetic data
- Clear anomaly patterns
- Good for testing checkpointing (stateful operations)
- No external dependencies needed

**Command to get started**:
```bash
# 1. Create the data generator
python3 examples/data_generator_iot.py > /tmp/sensor_data.jsonl

# 2. Run your stream processing job
python3 examples/iot_monitoring_test.py
```

---

## 🎯 Testing Checklist

Use real data to test:
- ✅ **Throughput**: Process 10,000+ events/second
- ✅ **Latency**: End-to-end latency < 100ms
- ✅ **Checkpointing**: Verify state persistence
- ✅ **Failure Recovery**: Kill a TaskManager mid-stream
- ✅ **Exactly-once**: Verify no duplicates after recovery
- ✅ **Scalability**: Add more TaskManagers dynamically
- ✅ **Memory**: Monitor for leaks over 1+ hour run
- ✅ **Backpressure**: Handle slow downstream operators

Would you like me to create a complete working example for any specific use case?
