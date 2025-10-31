#!/bin/bash

# Script to generate Python gRPC stubs from protobuf definitions

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
PROTO_DIR="$PROJECT_ROOT/common/protobuf"
OUTPUT_DIR="$PROJECT_ROOT/common/protobuf"

echo "Generating Python gRPC stubs..."
echo "Proto directory: $PROTO_DIR"
echo "Output directory: $OUTPUT_DIR"

# Install grpcio-tools if not available
python3 -m pip install grpcio-tools --quiet

# Generate Python code from proto files
python3 -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_DIR/stream_processing.proto"

echo "Generated files:"
ls -lh "$OUTPUT_DIR"/*.py

# Create __init__.py if it doesn't exist
if [ ! -f "$OUTPUT_DIR/__init__.py" ]; then
    touch "$OUTPUT_DIR/__init__.py"
    echo "Created __init__.py"
fi

echo "gRPC stub generation completed successfully!"
