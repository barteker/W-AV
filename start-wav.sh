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

# Disable the user service for oscviz to prevent duplicate starts
systemctl --user stop oscviz.service
systemctl --user disable oscviz.service

# Set Firefox window position to ensure it's on the main display
export MOZ_X_POSITION=0
export MOZ_Y_POSITION=0

# Start Firefox in kiosk mode on the primary display
WM_CLASS="Firefox.firefox" firefox --kiosk http://localhost:8888/ --window-position=0,0 &

# Allow Firefox to initialize 
sleep 5

# Start the oscilloscope visualization
cd /home/wave/W-AV/OscViz
./env/bin/python3 oscVizQt5.py &

# Wait for all processes
wait