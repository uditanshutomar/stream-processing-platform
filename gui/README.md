# Stream Processing Platform - Web GUI

Modern, real-time monitoring dashboard for the stream processing platform.

## Features

- **Real-time Event Monitoring** - See events as they're processed
- **Live Metrics** - Throughput, anomaly detection, and more
- **Checkpoint Tracking** - Monitor state snapshots
- **Resource Management** - TaskManager status and utilization
- **Anomaly Visualization** - Highlighted anomalous events
- **WebSocket Updates** - No page refresh needed

## Quick Start

### 1. Install Dependencies

```bash
pip3 install -r gui/requirements.txt
```

### 2. Start the GUI

```bash
python3 gui/app.py
```

### 3. Open Browser

Navigate to: http://localhost:5000

### 4. Start Processing

Click the "Start Processing" button to begin streaming data!

## What You'll See

### Dashboard Components:

1. **Total Events** - Count of all processed events
2. **Anomalies Detected** - Number of unusual readings
3. **Throughput** - Events processed per second
4. **Checkpoints** - Number of state snapshots taken
5. **Resource Manager** - TaskManager status and slots
6. **Recent Events** - Live stream of sensor readings

### Real-time Updates:

- Events appear instantly as they're processed
- Anomalies are highlighted in red
- Metrics update every second
- Checkpoints show when state is saved

## Architecture

```
┌─────────────────┐
│   Web Browser   │
│  (Dashboard)    │
└────────┬────────┘
         │ WebSocket
         │
┌────────▼────────┐
│   Flask App     │
│  + SocketIO     │
└────────┬────────┘
         │
         ├──► CheckpointCoordinator
         ├──► ResourceManager
         ├──► TaskScheduler
         └──► Data Generator
```

## Technologies

- **Backend**: Flask + SocketIO
- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript
- **Real-time**: WebSockets
- **Data**: Live IoT sensor stream

---

**Your stream processing platform now has a beautiful, working GUI!**
