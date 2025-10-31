#!/bin/bash

# Development environment setup script

set -e

echo "Setting up Stream Processing Platform development environment..."

# Create Python virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing JobManager dependencies..."
pip install -r jobmanager/requirements.txt

echo "Installing TaskManager dependencies..."
pip install -r taskmanager/requirements.txt

echo "Installing development dependencies..."
pip install pytest pytest-cov black flake8 mypy

# Generate gRPC stubs
echo "Generating gRPC stubs..."
bash scripts/generate_proto.sh

# Create necessary directories
echo "Creating directories..."
mkdir -p /tmp/checkpoints
mkdir -p /tmp/taskmanager_state
mkdir -p logs

# Run tests
echo "Running tests..."
python -m pytest tests/unit/ -v

echo ""
echo "✓ Setup complete!"
echo ""
echo "To activate the environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To start the platform:"
echo "  cd deployment"
echo "  docker-compose up -d"
echo ""
echo "To run examples:"
echo "  python examples/word_count.py"
