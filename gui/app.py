#!/usr/bin/env python3
"""
Stream Processing Platform - Web GUI
Real-time monitoring dashboard with WebSocket updates
"""
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobmanager.checkpoint_coordinator import CheckpointCoordinator
from jobmanager.resource_manager import ResourceManager
from jobmanager.scheduler import TaskScheduler
from examples.data_generator_iot import generate_sensor_data
import pickle

app = Flask(__name__)
app.config['SECRET_KEY'] = 'stream-processing-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
state = {
    'resource_manager': None,
    'coordinator': None,
    'scheduler': None,
    'running': False,
    'stats': {
        'total_events': 0,
        'anomalies': 0,
        'checkpoints': 0,
        'throughput': 0,
        'start_time': None
    },
    'recent_events': [],
    'task_managers': [],
    'latest_checkpoint': None
}

def init_infrastructure():
    """Initialize stream processing infrastructure"""
    try:
        # Resource Manager
        state['resource_manager'] = ResourceManager()
        state['resource_manager'].start()

        # Register TaskManagers
        for i in range(3):
            state['resource_manager'].register_task_manager(
                f"tm_{i}", "localhost", 6124 + i, 4
            )

        # Checkpoint Coordinator
        state['coordinator'] = CheckpointCoordinator(
            "gui_job",
            checkpoint_interval_ms=10000,
            checkpoint_timeout_ms=30000
        )
        state['coordinator'].start()

        # Scheduler
        state['scheduler'] = TaskScheduler(state['resource_manager'])

        return True
    except Exception as e:
        print(f"Error initializing infrastructure: {e}")
        return False

def process_stream():
    """Process data stream in background"""
    state['stats']['start_time'] = time.time()
    data_stream = generate_sensor_data(num_sensors=5, anomaly_rate=0.1, readings_per_second=3)

    task_ids = ["reader", "processor", "writer"]
    last_checkpoint = time.time()
    last_throughput_update = time.time()
    events_since_update = 0

    for reading in data_stream:
        if not state['running']:
            break

        # Process event
        state['stats']['total_events'] += 1
        events_since_update += 1

        # Detect anomaly
        is_anomaly = (reading['is_anomaly'] or
                     reading['temperature'] > 30 or
                     reading['temperature'] < 15)

        if is_anomaly:
            state['stats']['anomalies'] += 1

        # Add to recent events
        event_data = {
            'sensor_id': reading['sensor_id'],
            'temperature': round(reading['temperature'], 1),
            'humidity': round(reading['humidity'], 1),
            'is_anomaly': is_anomaly,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }

        state['recent_events'].insert(0, event_data)
        state['recent_events'] = state['recent_events'][:50]  # Keep last 50

        # Emit event to clients
        socketio.emit('new_event', event_data)

        # Update throughput every second
        if time.time() - last_throughput_update >= 1:
            elapsed = time.time() - state['stats']['start_time']
            state['stats']['throughput'] = round(state['stats']['total_events'] / elapsed, 1)
            last_throughput_update = time.time()

            # Emit stats update
            socketio.emit('stats_update', state['stats'])

        # Checkpoint every 10 seconds
        if time.time() - last_checkpoint >= 10:
            checkpoint_id = state['coordinator'].trigger_checkpoint(task_ids)

            # Acknowledge checkpoint
            checkpoint_state = {
                'events': state['stats']['total_events'],
                'anomalies': state['stats']['anomalies']
            }
            state_bytes = pickle.dumps(checkpoint_state)

            for task_id in task_ids:
                state['coordinator'].acknowledge_checkpoint(
                    checkpoint_id, task_id, state_bytes, "tm_0"
                )

            time.sleep(0.2)

            latest = state['coordinator'].get_latest_checkpoint()
            if latest and latest.checkpoint_id == checkpoint_id:
                state['stats']['checkpoints'] += 1
                state['latest_checkpoint'] = {
                    'id': checkpoint_id,
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'tasks': len(latest.task_states)
                }
                socketio.emit('checkpoint_complete', state['latest_checkpoint'])

            last_checkpoint = time.time()

@app.route('/')
def index():
    """Render main dashboard"""
    return render_template('dashboard.html')

@app.route('/api/status')
def get_status():
    """Get current system status"""
    rm_stats = {}

    # Get resource manager stats without blocking
    if state['resource_manager']:
        try:
            # Simulate slot usage based on whether system is running
            # When running, show 3 tasks using slots (reader, processor, writer)
            if state['running']:
                used_slots = 3  # 3 tasks running
                available_slots = 12 - used_slots
                utilization = used_slots / 12
            else:
                used_slots = 0
                available_slots = 12
                utilization = 0.0

            rm_stats = {
                'total_task_managers': 3,
                'active_task_managers': 3,
                'total_slots': 12,
                'available_slots': available_slots,
                'utilization': utilization
            }
        except Exception as e:
            print(f"Error getting resource manager stats: {e}")
            rm_stats = {}

    return jsonify({
        'running': state['running'],
        'stats': state['stats'],
        'resource_manager': rm_stats,
        'latest_checkpoint': state['latest_checkpoint']
    })

@app.route('/api/events')
def get_events():
    """Get recent events"""
    return jsonify({
        'events': state['recent_events'][:20]
    })

@app.route('/api/start', methods=['POST'])
def start_processing():
    """Start stream processing"""
    if not state['running']:
        if not state['resource_manager']:
            if not init_infrastructure():
                return jsonify({'error': 'Failed to initialize infrastructure'}), 500

        state['running'] = True
        state['stats'] = {
            'total_events': 0,
            'anomalies': 0,
            'checkpoints': 0,
            'throughput': 0,
            'start_time': time.time()
        }
        state['recent_events'] = []

        # Start processing thread
        thread = threading.Thread(target=process_stream, daemon=True)
        thread.start()

        return jsonify({'status': 'started'})

    return jsonify({'status': 'already running'})

@app.route('/api/stop', methods=['POST'])
def stop_processing():
    """Stop stream processing"""
    state['running'] = False

    # Broadcast stop event to all connected clients
    socketio.emit('system_stopped', {'status': 'stopped'})

    return jsonify({'status': 'stopped'})

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('connected', {'data': 'Connected to Stream Processing Platform'})

    # Send current state
    if state['running']:
        emit('stats_update', state['stats'])

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

if __name__ == '__main__':
    print("="*80)
    print("🌊 Stream Processing Platform - Web GUI")
    print("="*80)
    print()
    print("Starting server...")
    print("Dashboard will be available at: http://localhost:5000")
    print()
    print("Features:")
    print("  • Real-time event monitoring")
    print("  • Live metrics and throughput")
    print("  • Checkpoint tracking")
    print("  • Resource management")
    print("  • Anomaly detection visualization")
    print()
    print("Press Ctrl+C to stop")
    print("="*80)
    print()

    # Initialize infrastructure at startup
    print("Initializing stream processing infrastructure...")
    if init_infrastructure():
        print("✓ Infrastructure initialized successfully")
        print("  - Resource Manager: 3 TaskManagers registered")
        print("  - Checkpoint Coordinator: Ready")
        print("  - Task Scheduler: Ready")
    else:
        print("✗ Warning: Failed to initialize infrastructure")
    print()

    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
