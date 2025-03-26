#!/bin/bash
# Master script to start all W/AV components

# Configure display
export DISPLAY=:0
export XAUTHORITY=/home/wave/.Xauthority

# Wait for X server
sleep 5

# Start Node.js server if not already running
if ! pgrep -f "node.*server.js" > /dev/null; then
    cd /home/wave/W-AV
    npm start &
    sleep 5
fi

# Start Firefox in kiosk mode
firefox --kiosk http://localhost:8888/ &

# Start the oscilloscope visualization
# cd /home/wave/W-AV
# ./run-viz.sh &

# Wait for all processes
wait
