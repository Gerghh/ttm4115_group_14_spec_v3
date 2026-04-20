#!/bin/bash
# Script to run the Unified Drone Delivery System GUI

# Check if stmpy is installed
python3 -c "import stmpy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "stmpy not found. Installing dependencies..."
    pip install stmpy paho-mqtt
fi

echo "Starting Unified Drone Delivery System GUI..."
python3 unified_gui.py
