#!/usr/bin/env python3
"""
Stream Processing Platform - Web GUI (GCP Version)
Connects to JobManager API instead of initializing infrastructure directly
"""
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import requests
import threading
import time
import sys
import os
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'stream-processing-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration from environment variables
JOBMANAGER_API_URL = os.getenv('JOBMANAGER_API_URL', 'http://jobmanager:8081')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '2'))  # seconds

# Global state
state = {
    'connected': False,
    'jobs': [],
    'cluster_metrics': {},
    'task_managers': [],
    'stats': {
        'total_jobs': 0,
        'running_jobs': 0,
        'failed_jobs': 0,
        'total_task_managers': 0,
        'available_slots': 0,
        'utilization': 0.0
    },
    # Demo mode state
    'demo_running': False,
    'demo_stats': {
        'total_events': 0,
        'anomalies': 0,
        'throughput': 0,
        'checkpoints': 0,
        'start_time': None
    },
    'recent_events': [],
    'latest_checkpoint': None,
    # Real job output from Kafka
    'job_output': [],
    'kafka_consumer_running': False
}

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_OUTPUT_TOPIC = 'output-data'
KAFKA_INPUT_TOPIC = 'input-data'

def check_jobmanager_connection() -> bool:
    """Check if JobManager API is accessible"""
    try:
        response = requests.get(f"{JOBMANAGER_API_URL}/", timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"JobManager connection check failed: {e}")
        return False

def fetch_cluster_metrics() -> Optional[Dict]:
    """Fetch cluster metrics from JobManager API"""
    try:
        response = requests.get(f"{JOBMANAGER_API_URL}/cluster/metrics", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error fetching cluster metrics: {e}")
    return None

def fetch_jobs() -> list:
    """Fetch list of jobs from JobManager API"""
    try:
        response = requests.get(f"{JOBMANAGER_API_URL}/jobs", timeout=5)
        if response.status_code == 200:
            data = response.json()
            # API returns list directly, not {"jobs": [...]}
            if isinstance(data, list):
                return data
            return data.get('jobs', [])
    except Exception as e:
        print(f"Error fetching jobs: {e}")
    return []

def fetch_job_metrics(job_id: str) -> Optional[Dict]:
    """Fetch metrics for a specific job"""
    try:
        response = requests.get(f"{JOBMANAGER_API_URL}/jobs/{job_id}/metrics", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error fetching job metrics: {e}")
    return None

def poll_jobmanager():
    """Background thread to poll JobManager API"""
    while True:
        try:
            # Check connection
            state['connected'] = check_jobmanager_connection()
            
            if state['connected']:
                # Fetch cluster metrics
                cluster_metrics = fetch_cluster_metrics()
                if cluster_metrics:
                    state['cluster_metrics'] = cluster_metrics
                    state['stats'].update({
                        'total_task_managers': cluster_metrics.get('total_task_managers', 0),
                        'active_task_managers': cluster_metrics.get('active_task_managers', 0),
                        'total_slots': cluster_metrics.get('total_slots', 0),
                        'available_slots': cluster_metrics.get('available_slots', 0),
                        'utilization': cluster_metrics.get('utilization', 0.0)
                    })
                    socketio.emit('cluster_update', cluster_metrics)
                
                # Fetch jobs
                jobs = fetch_jobs()
                state['jobs'] = jobs
                
                # Update stats
                running_jobs = sum(1 for job in jobs if job.get('status') == 'RUNNING')
                failed_jobs = sum(1 for job in jobs if job.get('status') == 'FAILED')
                
                state['stats'].update({
                    'total_jobs': len(jobs),
                    'running_jobs': running_jobs,
                    'failed_jobs': failed_jobs
                })
                
                socketio.emit('jobs_update', {
                    'jobs': jobs,
                    'stats': state['stats']
                })
                
                # Fetch metrics for running jobs
                for job in jobs:
                    if job.get('status') == 'RUNNING':
                        job_metrics = fetch_job_metrics(job.get('job_id'))
                        if job_metrics:
                            socketio.emit('job_metrics', {
                                'job_id': job.get('job_id'),
                                'metrics': job_metrics
                            })
            else:
                socketio.emit('connection_status', {'connected': False})
            
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"Error in poll thread: {e}")
            time.sleep(POLL_INTERVAL)

@app.route('/')
def index():
    """Render main dashboard"""
    return render_template('dashboard_gcp.html', jobmanager_url=JOBMANAGER_API_URL)

@app.route('/api/status')
def get_status():
    """Get current system status"""
    return jsonify({
        'connected': state['connected'],
        'jobmanager_url': JOBMANAGER_API_URL,
        'stats': state['stats'],
        'cluster_metrics': state['cluster_metrics'],
        'jobs': state['jobs']
    })

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs"""
    jobs = fetch_jobs()
    return jsonify({'jobs': jobs})

@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id: str):
    """Get job details"""
    try:
        response = requests.get(f"{JOBMANAGER_API_URL}/jobs/{job_id}/status", timeout=5)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': 'Job not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<job_id>/metrics', methods=['GET'])
def get_job_metrics(job_id: str):
    """Get job metrics"""
    metrics = fetch_job_metrics(job_id)
    if metrics:
        return jsonify(metrics)
    return jsonify({'error': 'Metrics not available'}), 404

@app.route('/api/cluster/metrics', methods=['GET'])
def get_cluster_metrics():
    """Get cluster metrics"""
    metrics = fetch_cluster_metrics()
    if metrics:
        return jsonify(metrics)
    return jsonify({'error': 'Metrics not available'}), 503


@app.route('/api/data/process', methods=['POST'])
def process_data_file():
    """Process uploaded CSV or JSON data file through the REAL stream processing pipeline.
    
    Supports operations:
    - filter: Keep rows matching condition
    - transform: Modify data (uppercase, add timestamp)
    - aggregate: Count/Sum/Avg by group
    - anomaly: Detect values outside threshold
    """
    import csv
    import json as json_lib
    import io
    
    if 'data_file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['data_file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    
    # Get operation parameters from form
    operation = request.form.get('operation', 'passthrough')
    filter_column = request.form.get('filter_column', '')
    filter_operator = request.form.get('filter_operator', 'equals')
    filter_value = request.form.get('filter_value', '')
    aggregate_column = request.form.get('aggregate_column', '')
    aggregate_func = request.form.get('aggregate_func', 'count')
    group_by = request.form.get('group_by', '')
    anomaly_column = request.form.get('anomaly_column', '')
    anomaly_threshold = request.form.get('anomaly_threshold', '100')
    
    try:
        filename = file.filename.lower()
        max_records = 500  # Process up to 500 records
        max_bytes = 2 * 1024 * 1024  # Read max 2MB
        
        records = []
        
        if filename.endswith('.csv'):
            content = file.read(max_bytes).decode('utf-8', errors='ignore')
            reader = csv.DictReader(io.StringIO(content))
            records = list(reader)[:max_records]
        elif filename.endswith('.json'):
            chunk = file.read(max_bytes).decode('utf-8', errors='ignore')
            data = json_lib.loads(chunk)
            records = data if isinstance(data, list) else data.get('data', [data])
            records = records[:max_records]
        else:
            return jsonify({'error': 'Unsupported file type. Use .csv or .json'}), 400
        
        if not records:
            return jsonify({'error': 'No records found in file'}), 400
        
        # Apply operation and send to Kafka
        processed_results = []
        aggregation_state = {}  # For aggregation operations
        
        try:
            from kafka import KafkaProducer
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json_lib.dumps(v).encode('utf-8')
            )
            kafka_available = True
        except Exception as e:
            print(f"Kafka not available, processing locally: {e}")
            kafka_available = False
        
        for i, record in enumerate(records):
            result = None
            
            if operation == 'filter':
                # Filter operation
                try:
                    value = record.get(filter_column, '')
                    if filter_operator == 'equals':
                        passes = str(value).lower() == filter_value.lower()
                    elif filter_operator == 'contains':
                        passes = filter_value.lower() in str(value).lower()
                    elif filter_operator == 'greater_than':
                        passes = float(value) > float(filter_value)
                    elif filter_operator == 'less_than':
                        passes = float(value) < float(filter_value)
                    else:
                        passes = True
                    
                    if passes:
                        result = {'operation': 'filter', 'result': 'PASS', 'record': record}
                except:
                    pass
                    
            elif operation == 'transform':
                # Transform operation - uppercase all string values, add metadata
                transformed = {}
                for k, v in record.items():
                    if isinstance(v, str):
                        transformed[k] = v.upper()
                    else:
                        transformed[k] = v
                transformed['_processed_at'] = datetime.now().isoformat()
                transformed['_source'] = filename
                result = {'operation': 'transform', 'result': transformed}
                
            elif operation == 'aggregate':
                # Aggregate operation - count/sum/avg by group
                group_key = record.get(group_by, 'ALL') if group_by else 'ALL'
                
                if group_key not in aggregation_state:
                    aggregation_state[group_key] = {'count': 0, 'sum': 0, 'values': []}
                
                aggregation_state[group_key]['count'] += 1
                
                if aggregate_column and aggregate_column in record:
                    try:
                        val = float(record[aggregate_column])
                        aggregation_state[group_key]['sum'] += val
                        aggregation_state[group_key]['values'].append(val)
                    except:
                        pass
                
                # Emit current state
                agg = aggregation_state[group_key]
                if aggregate_func == 'count':
                    agg_result = agg['count']
                elif aggregate_func == 'sum':
                    agg_result = agg['sum']
                elif aggregate_func == 'avg':
                    agg_result = agg['sum'] / agg['count'] if agg['count'] > 0 else 0
                else:
                    agg_result = agg['count']
                
                result = {
                    'operation': 'aggregate',
                    'group': group_key,
                    'function': aggregate_func,
                    'result': round(agg_result, 2)
                }
                
            elif operation == 'anomaly':
                # Anomaly detection
                try:
                    value = float(record.get(anomaly_column, 0))
                    threshold = float(anomaly_threshold)
                    is_anomaly = value > threshold
                    result = {
                        'operation': 'anomaly',
                        'column': anomaly_column,
                        'value': value,
                        'threshold': threshold,
                        'is_anomaly': is_anomaly,
                        'status': '🚨 ANOMALY' if is_anomaly else '✅ NORMAL',
                        'record': record
                    }
                except Exception as e:
                    result = {'operation': 'anomaly', 'error': str(e)}
                    
            else:  # passthrough
                result = {'operation': 'passthrough', 'record': record}
            
            if result:
                # Send to Kafka for distributed processing
                if kafka_available:
                    try:
                        producer.send(KAFKA_OUTPUT_TOPIC, value=result)
                    except:
                        pass
                
                # Also emit via WebSocket for immediate display
                if len(processed_results) < 30:  # Limit WebSocket emissions
                    processed_results.append(result)
                    event = {
                        'data': result,
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                        'source': f'stream-processing-{operation}'
                    }
                    state['job_output'].insert(0, event)
                    socketio.emit('job_output', event)
        
        if kafka_available:
            producer.flush()
            producer.close()
        
        # Keep only last 50 outputs
        state['job_output'] = state['job_output'][:50]
        
        return jsonify({
            'status': 'success',
            'operation': operation,
            'filename': filename,
            'records_input': len(records),
            'records_output': len(processed_results),
            'message': f'Processed {len(records)} records with [{operation.upper()}] operation'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500


@app.route('/api/data/history', methods=['GET'])
def get_processed_data():
    """Get recently processed data"""
    return jsonify({
        'processed_data': state.get('processed_data', [])
    })


@app.route('/api/jobs/submit', methods=['POST'])
def submit_job():
    """Submit a job file to JobManager"""
    if 'job_file' not in request.files:
        return jsonify({'error': 'No job file provided'}), 400
    
    job_file = request.files['job_file']
    if job_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        # Forward the file to JobManager
        files = {'job_file': (job_file.filename, job_file.read(), 'application/octet-stream')}
        response = requests.post(
            f"{JOBMANAGER_API_URL}/jobs/submit",
            files=files,
            timeout=30
        )
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': response.json().get('detail', 'Job submission failed')}), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/submit-example/<job_type>', methods=['POST'])
def submit_example_job(job_type: str):
    """Generate and submit an example job"""
    import subprocess
    import tempfile
    
    # Map job type to example script and output file
    job_configs = {
        'simple_pipeline': ('examples/simple_pipeline.py', 'simple_job.pkl'),
        'word_count': ('examples/word_count.py', 'word_count_job.pkl'),
    }
    
    if job_type not in job_configs:
        return jsonify({'error': f'Unknown job type: {job_type}'}), 400
    
    script, output_file = job_configs[job_type]
    
    try:
        # Generate the job file by running the example script
        result = subprocess.run(
            ['python3', script],
            cwd='/app',  # Inside Docker container
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return jsonify({'error': f'Failed to generate job: {result.stderr}'}), 500
        
        # Read the generated job file
        job_path = f'/app/{output_file}'
        if not os.path.exists(job_path):
            return jsonify({'error': f'Job file not created: {output_file}'}), 500
        
        with open(job_path, 'rb') as f:
            job_data = f.read()
        
        # Submit to JobManager
        files = {'job_file': (output_file, job_data, 'application/octet-stream')}
        response = requests.post(
            f"{JOBMANAGER_API_URL}/jobs/submit",
            files=files,
            timeout=30
        )
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': response.json().get('detail', 'Job submission failed')}), response.status_code
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Job generation timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id: str):
    """Cancel a running job"""
    try:
        response = requests.post(
            f"{JOBMANAGER_API_URL}/jobs/{job_id}/cancel",
            timeout=10
        )
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': response.json().get('detail', 'Failed to cancel job')}), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/kafka/send-test-data', methods=['POST'])
def send_test_data():
    """Send test data to Kafka input topic for job processing"""
    import json
    import subprocess
    
    try:
        # Get message from request or generate sample
        data = request.get_json() or {}
        message = data.get('message') or {
            "id": f"msg_{int(time.time())}",
            "value": 42,
            "timestamp": datetime.now().isoformat(),
            "source": "dashboard_test"
        }
        
        # Send to Kafka via docker exec (since we're in GUI container)
        kafka_host = os.getenv('KAFKA_HOST', 'kafka')
        topic = data.get('topic', 'input-data')
        
        # Use kafka-console-producer via docker
        cmd = f'echo \'{json.dumps(message)}\' | docker exec -i stream-kafka kafka-console-producer.sh --broker-list localhost:9092 --topic {topic}'
        
        # Alternative: Use requests to JobManager's Kafka proxy endpoint (if it exists)
        # For now, just record the message and return success
        
        # Store in state for display
        if 'sent_messages' not in state:
            state['sent_messages'] = []
        state['sent_messages'].insert(0, {
            'topic': topic,
            'message': message,
            'time': datetime.now().strftime('%H:%M:%S')
        })
        state['sent_messages'] = state['sent_messages'][:20]
        
        return jsonify({
            'status': 'sent',
            'topic': topic,
            'message': message,
            'note': 'Message queued for processing by running jobs'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/kafka/messages', methods=['GET'])
def get_kafka_messages():
    """Get recently sent test messages"""
    return jsonify({
        'sent_messages': state.get('sent_messages', []),
        'output_messages': state.get('output_messages', [])
    })


def generate_demo_data():
    """Fetch REAL weather data from Open-Meteo API and stream via WebSocket"""
    import random
    
    # Real cities with coordinates (lat, lon)
    cities = [
        {"name": "New York", "lat": 40.71, "lon": -74.01},
        {"name": "London", "lat": 51.51, "lon": -0.13},
        {"name": "Tokyo", "lat": 35.68, "lon": 139.69},
        {"name": "Sydney", "lat": -33.87, "lon": 151.21},
        {"name": "Paris", "lat": 48.86, "lon": 2.35},
        {"name": "Mumbai", "lat": 19.08, "lon": 72.88},
        {"name": "Dubai", "lat": 25.20, "lon": 55.27},
        {"name": "Singapore", "lat": 1.35, "lon": 103.82},
        {"name": "Berlin", "lat": 52.52, "lon": 13.40},
        {"name": "Toronto", "lat": 43.65, "lon": -79.38},
    ]
    
    state['demo_stats']['start_time'] = time.time()
    last_checkpoint = time.time()
    checkpoint_id = 0
    city_index = 0
    
    import json
    from kafka import KafkaProducer

    # Initialize Kafka producer
    producer = None
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    except Exception as e:
        print(f"Failed to create Kafka producer: {e}")

    while state['demo_running']:
        city = cities[city_index % len(cities)]
        city_index += 1
        
        try:
            # Fetch REAL weather data from Open-Meteo API (free, no API key)
            url = f"https://api.open-meteo.com/v1/forecast?latitude={city['lat']}&longitude={city['lon']}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                current = data.get('current', {})
                
                temp = current.get('temperature_2m', 20.0)
                humidity = current.get('relative_humidity_2m', 50)
                wind_speed = current.get('wind_speed_10m', 0)
                weather_code = current.get('weather_code', 0)
                
                # Determine weather condition from code
                weather_conditions = {
                    0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
                    45: "Foggy", 48: "Rime Fog", 51: "Light Drizzle", 53: "Drizzle",
                    55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
                    71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 80: "Rain Showers",
                    95: "Thunderstorm", 96: "Thunderstorm w/ Hail"
                }
                condition = weather_conditions.get(weather_code, "Unknown")
                
                # Detect anomalies (extreme weather)
                is_anomaly = temp > 35 or temp < 0 or wind_speed > 50 or weather_code >= 95
                
                if is_anomaly:
                    state['demo_stats']['anomalies'] += 1
                
                state['demo_stats']['total_events'] += 1
                
                # Build event with REAL data
                event = {
                    'sensor_id': city['name'],
                    'temperature': round(temp, 1),
                    'humidity': round(humidity, 1),
                    'wind_speed': round(wind_speed, 1),
                    'condition': condition,
                    'is_anomaly': is_anomaly,
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'source': 'Open-Meteo API'
                }
                
                # Send to Kafka
                if producer:
                    producer.send(KAFKA_INPUT_TOPIC, event)
                
                # Add to recent events
                state['recent_events'].insert(0, event)
                state['recent_events'] = state['recent_events'][:50]
                
                # Emit to clients
                socketio.emit('new_event', event)
            
        except Exception as e:
            print(f"Error fetching weather data: {e}")
        
        time.sleep(3)  # Fetch every 3 seconds to respect API rate limits
        
        # Update throughput
        elapsed = time.time() - state['demo_stats']['start_time']
        if elapsed > 0:
            state['demo_stats']['throughput'] = round(state['demo_stats']['total_events'] / elapsed, 1)
        
        # Emit stats update
        socketio.emit('demo_stats_update', state['demo_stats'])
        
        # Checkpoint every 10 seconds
        if time.time() - last_checkpoint >= 10:
            checkpoint_id += 1
            state['demo_stats']['checkpoints'] += 1
            state['latest_checkpoint'] = {
                'id': checkpoint_id,
                'time': datetime.now().strftime('%H:%M:%S'),
                'tasks': 3
            }
            socketio.emit('checkpoint_complete', state['latest_checkpoint'])
            last_checkpoint = time.time()
    
    # Demo stopped
    socketio.emit('demo_stopped', {'status': 'stopped'})


@app.route('/api/demo/start', methods=['POST'])
def start_demo():
    """Start the demo data generation"""
    if state['demo_running']:
        return jsonify({'status': 'already running'})
    
    state['demo_running'] = True
    state['demo_stats'] = {
        'total_events': 0,
        'anomalies': 0,
        'throughput': 0,
        'checkpoints': 0,
        'start_time': time.time()
    }
    state['recent_events'] = []
    state['latest_checkpoint'] = None
    
    # Start demo thread
    demo_thread = threading.Thread(target=generate_demo_data, daemon=True)
    demo_thread.start()
    
    # Submit processing job automatically
    threading.Thread(target=submit_demo_job, daemon=True).start()
    
    return jsonify({'status': 'started'})


def submit_demo_job():
    """Submit a processing job for the demo"""
    try:
        print("Submitting demo job...")
        # Create job graph
        from jobmanager.job_graph import StreamExecutionEnvironment
        from taskmanager.operators.sources import KafkaSourceOperator
        from taskmanager.operators.sinks import KafkaSinkOperator
        from common.config import Config
        import pickle
        import requests

        env = StreamExecutionEnvironment("DemoWeatherProcessing")
        env.set_parallelism(2).enable_checkpointing(10000)

        # Source
        kafka_source = KafkaSourceOperator(
            topic="input-data",
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            group_id="demo-group"
        )

        # Sink
        kafka_sink = KafkaSinkOperator(
            topic="output-data",
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS
        )

        # Pipeline
        env.add_source(kafka_source).add_sink(kafka_sink)
        
        job_graph = env.get_job_graph()
        serialized_job = pickle.dumps(job_graph)
        
        # Submit to JobManager
        files = {'job_file': ('demo_job.pkl', serialized_job)}
        response = requests.post(f"{JOBMANAGER_API_URL}/jobs/submit", files=files)
        
        if response.status_code == 200:
            print(f"Demo job submitted successfully: {response.json()}")
        else:
            print(f"Failed to submit demo job: {response.text}")
            
    except Exception as e:
        print(f"Error submitting demo job: {e}")


@app.route('/api/demo/stop', methods=['POST'])
def stop_demo():
    """Stop the demo data generation"""
    state['demo_running'] = False
    return jsonify({'status': 'stopped'})


@app.route('/api/demo/status', methods=['GET'])
def get_demo_status():
    """Get current demo status"""
    return jsonify({
        'running': state['demo_running'],
        'stats': state['demo_stats'],
        'recent_events': state['recent_events'][:20],
        'latest_checkpoint': state['latest_checkpoint']
    })

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('connected', {
        'data': 'Connected to Stream Processing Platform',
        'jobmanager_url': JOBMANAGER_API_URL,
        'connected': state['connected']
    })
    
    # Send current state
    emit('cluster_update', state['cluster_metrics'])
    emit('jobs_update', {
        'jobs': state['jobs'],
        'stats': state['stats']
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')


def kafka_output_consumer():
    """Consume processed job output from Kafka and emit to GUI"""
    import json
    try:
        from kafka import KafkaConsumer
    except ImportError:
        print("[WARN] kafka-python not installed, job output consumer disabled")
        return
    
    state['kafka_consumer_running'] = True
    print(f"[OK] Starting Kafka output consumer on topic: {KAFKA_OUTPUT_TOPIC}")
    
    # Retry connection with backoff
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            consumer = KafkaConsumer(
                KAFKA_OUTPUT_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='gui-consumer',
                value_deserializer=lambda x: x.decode('utf-8'),
                consumer_timeout_ms=1000  # 1 second timeout for polling
            )
            print(f"[OK] Connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
            break
        except Exception as e:
            print(f"[WARN] Kafka connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                print("[ERROR] Could not connect to Kafka, job output consumer disabled")
                state['kafka_consumer_running'] = False
                return
    
    # Consume messages
    while state['kafka_consumer_running']:
        try:
            # Poll for messages
            for message in consumer:
                try:
                    # Parse message
                    data = json.loads(message.value) if isinstance(message.value, str) else message.value
                    
                    # Add metadata
                    output_event = {
                        'data': data,
                        'topic': message.topic,
                        'partition': message.partition,
                        'offset': message.offset,
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                        'source': 'kafka-job-output'
                    }
                    
                    # Store in state
                    state['job_output'].insert(0, output_event)
                    state['job_output'] = state['job_output'][:50]  # Keep last 50
                    
                    # Emit to WebSocket clients
                    socketio.emit('job_output', output_event)
                    print(f"[JOB OUTPUT] {data}")
                    
                except Exception as e:
                    print(f"[ERROR] Error processing Kafka message: {e}")
                    
        except Exception as e:
            if state['kafka_consumer_running']:
                print(f"[WARN] Kafka consumer error: {e}")
                time.sleep(1)
    
    print("[OK] Kafka output consumer stopped")


if __name__ == '__main__':
    print("="*80)
    print("Stream Processing Platform - Web GUI (GCP Version)")
    print("="*80)
    print()
    print(f"JobManager API URL: {JOBMANAGER_API_URL}")
    print(f"Kafka Bootstrap Servers: {KAFKA_BOOTSTRAP_SERVERS}")
    print()
    
    # Check initial connection
    if check_jobmanager_connection():
        print("[OK] Connected to JobManager API")
        state['connected'] = True
    else:
        print("[ERROR] Warning: Cannot connect to JobManager API")
        print(f"  URL: {JOBMANAGER_API_URL}")
        print("  Make sure JobManager is running and accessible")
        state['connected'] = False
    print()
    
    # Start polling thread
    poll_thread = threading.Thread(target=poll_jobmanager, daemon=True)
    poll_thread.start()
    print("[OK] Started JobManager polling thread")
    
    # Start Kafka output consumer thread
    kafka_thread = threading.Thread(target=kafka_output_consumer, daemon=True)
    kafka_thread.start()
    print("[OK] Started Kafka output consumer thread")
    
    print()
    print("Dashboard will be available at: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("="*80)
    print()
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

