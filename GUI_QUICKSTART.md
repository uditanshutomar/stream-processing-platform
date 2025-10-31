# Web GUI Quick Start Guide

## 🚀 Get Started in 3 Steps

### Step 1: Start the Platform with GUI

```bash
cd deployment
docker-compose up -d
```

This starts:
- **JobManager** (REST API + WebSocket)
- **3 TaskManagers** (processing workers)
- **PostgreSQL** (metadata storage)
- **Kafka** (message broker)
- **Prometheus + Grafana** (monitoring)
- **Web GUI** ← NEW! 🎉

### Step 2: Access the GUI

Open your browser and visit:

**http://localhost:3001**

You'll see the dashboard with cluster metrics and running jobs.

### Step 3: Submit Your First Job

#### Option A: Via GUI (Easy!)

1. Click **"Submit Job"** in the sidebar
2. Drag and drop your `.pkl` job file
3. Click **"Submit Job"** button
4. View real-time metrics!

#### Option B: Create a Job First

```bash
# Generate example job
cd ..
python3 examples/word_count.py
```

Then upload `word_count_job.pkl` via the GUI!

## 📸 What You'll See

### Dashboard Page

```
┌─────────────────────────────────────────────────────┐
│  Distributed Stream Processing Platform             │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Cluster Overview                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │TaskManagers  │  │ Total Slots  │  │   Jobs   │  │
│  │      3       │  │     12       │  │    0     │  │
│  └──────────────┘  └──────────────┘  └──────────┘  │
│                                                      │
│  Utilization: ████░░░░░░ 0%                         │
│                                                      │
│  Running Jobs                                        │
│  (Submit your first job to see it here!)            │
│                                                      │
│  [📤 Submit New Job]                                │
└─────────────────────────────────────────────────────┘
```

### Job Detail Page (Real-Time!)

```
┌─────────────────────────────────────────────────────┐
│  Job: WordCount                     [Cancel] [⚙]   │
├─────────────────────────────────────────────────────┤
│  Status: 🟢 RUNNING          Started: 2m ago        │
│                                                      │
│  Current Metrics (Live via WebSocket)               │
│  ┌────────────────┐  ┌────────────────┐            │
│  │  Throughput    │  │  Latency P99   │            │
│  │  45,000 rec/s  │  │    45.2 ms     │            │
│  └────────────────┘  └────────────────┘            │
│                                                      │
│  📊 Real-Time Throughput Chart                      │
│  (Updates every second!)                            │
│                                                      │
│  Execution Graph:                                    │
│  ① [Kafka Source] → ② [FlatMap] → ③ [Map]          │
│  → ④ [KeyBy] → ⑤ [Window] → ⑥ [Reduce]             │
│  → ⑦ [Filter] → ⑧ [Kafka Sink]                     │
└─────────────────────────────────────────────────────┘
```

## 🎯 Common Tasks

### Monitor Cluster Health

1. Go to **Dashboard** (home page)
2. See:
   - Active TaskManagers
   - Available slots
   - Cluster utilization
   - Running jobs

### View All Jobs

1. Click **"Jobs"** in sidebar
2. Filter by status (Running, Finished, Failed, etc.)
3. Click any job to see details

### Check TaskManager Health

1. Click **"TaskManagers"** in sidebar
2. View:
   - Status (Active/Lost)
   - CPU & Memory usage
   - Running tasks
   - Slot allocation

### Cancel a Job

1. Go to job detail page
2. Click **"Cancel Job"** button
3. Confirm cancellation

### Trigger Savepoint

1. Go to running job detail page
2. Click **"Trigger Savepoint"** button
3. Wait for confirmation

## ⚙️ Configuration

### Change API Endpoint

If JobManager is on a different host:

```bash
cd gui/frontend

# Create local config
cat > .env.local << EOF
REACT_APP_API_URL=http://your-jobmanager:8081
REACT_APP_WS_URL=ws://your-jobmanager:8081
EOF

# Rebuild
docker-compose build gui
docker-compose up -d gui
```

### Run GUI in Development Mode

For faster iteration during development:

```bash
cd gui/frontend
npm install
npm start
```

Opens at **http://localhost:3000** with hot reload!

## 🔍 Troubleshooting

### GUI Shows "Failed to load"

**Check JobManager is running:**
```bash
curl http://localhost:8081/cluster/metrics
```

If it fails, start JobManager:
```bash
cd deployment
docker-compose up -d jobmanager
```

### No Real-Time Updates

**WebSocket might not be connected.**

Check browser console (F12) for errors:
- `WebSocket connection failed` - JobManager not reachable
- Falls back to auto-refresh (every 5 seconds)

### Docker Build Fails

```bash
# Clean rebuild
cd deployment
docker-compose down
docker-compose build --no-cache gui
docker-compose up -d
```

### Port 3001 Already in Use

Change the port in `docker-compose.yml`:

```yaml
gui:
  ports:
    - "8080:80"  # Use 8080 instead
```

Then access at **http://localhost:8080**

## 🎨 Features

### ✅ What's Included

- ✅ **Dashboard** - Cluster overview
- ✅ **Job List** - All jobs with filtering
- ✅ **Job Details** - Execution graph + metrics
- ✅ **Real-Time Metrics** - WebSocket updates
- ✅ **Job Submission** - Drag-and-drop upload
- ✅ **TaskManager View** - Worker monitoring
- ✅ **Responsive Design** - Works on mobile
- ✅ **Dark/Light Theme** - Material-UI theming

### 🚧 Coming Soon (Future)

- 🚧 **Visual Job Builder** - Drag-and-drop pipeline creation
- 🚧 **SQL Query Interface** - Submit jobs via SQL
- 🚧 **User Authentication** - Multi-user support
- 🚧 **Job Templates** - Pre-built job library
- 🚧 **Advanced Metrics** - More detailed analytics

## 📱 Mobile Support

The GUI is fully responsive! Access from:
- 📱 Mobile phone
- 💻 Tablet  
- 🖥️ Desktop

All features work on mobile devices.

## 🆘 Need Help?

### Check Logs

```bash
# GUI container logs
docker logs stream-gui

# JobManager logs
docker logs stream-jobmanager

# All logs
docker-compose logs
```

### Verify Setup

```bash
# Check all services are running
docker-compose ps

# Should show 8 services UP:
#   postgres, zookeeper, kafka
#   jobmanager, taskmanager1-3
#   prometheus, grafana, gui
```

### Test API Manually

```bash
# Cluster metrics
curl http://localhost:8081/cluster/metrics

# List jobs
curl http://localhost:8081/jobs

# JobManager health
curl http://localhost:8081/
```

## 🎓 Next Steps

1. **Submit a job** via the GUI
2. **Monitor it** in real-time
3. **Explore TaskManagers** to see resource usage
4. **Try the benchmarks** from `scripts/realistic_benchmark.py`
5. **Build your own jobs** using the Python API

## 📚 More Documentation

- **GUI Details**: `gui/README.md`
- **API Reference**: `docs/api_reference.md`
- **Job Examples**: `examples/`
- **Realistic Benchmarks**: `REALISTIC_PERFORMANCE.md`

---

**Enjoy your new GUI! 🎉**

Access it at: **http://localhost:3001**

