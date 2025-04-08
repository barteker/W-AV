#!/bin/bash

# Set display environment variables first
export DISPLAY=:0
export XAUTHORITY=/home/wave/.Xauthority

# Function to start Openbox
start_openbox() {
    openbox &
    OPENBOX_PID=$!
    
    # Wait for X server to initialize
    sleep 5
    
    # Check if openbox started successfully
    if ps -p $OPENBOX_PID > /dev/null; then
        return 0
    else
        echo "Failed to start Openbox" >&2
        return 1
    fi
}

# Try to start Openbox with retries
MAX_RETRIES=5
RETRY_COUNT=0
OPENBOX_STARTED=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$OPENBOX_STARTED" = false ]; do
    if start_openbox; then
        OPENBOX_STARTED=true
    else
        RETRY_COUNT=$((RETRY_COUNT+1))
        sleep 2
    fi
done

# Start a background process to monitor and restart Openbox if needed
(
    while true; do
        if ! pgrep -x openbox > /dev/null; then
            start_openbox >/dev/null 2>&1
        fi
        sleep 10
    done
) &
MONITOR_PID=$!

# Launch our main script
/home/wave/W-AV/minimal-wav-start.sh