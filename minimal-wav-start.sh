#!/bin/bash

# Set up error logging (only errors)
exec 2> >(tee /home/wave/wav-startup.log >&2)

# Load X resources
xrdb -merge ~/.Xresources

# Set display environment variables
export DISPLAY=:0
export XAUTHORITY=/home/wave/.Xauthority

# Wait for X to be fully ready
sleep 3

# Rotate the second display into correct orientation
sudo xrandr --output HDMI-2 --rotate right >/dev/null 2>&1

# Start Node.js server
cd /home/wave/W-AV
npm start >/dev/null 2>&1 &
sleep 5

# Wait for the server to be ready (longer timeout)
for i in {1..15}; do
    if curl -s http://localhost:8888 > /dev/null; then
        break
    fi
    sleep 1
done

# Start Firefox in kiosk mode
firefox --kiosk http://localhost:8888/ --window-position=0,0 &
FIREFOX_PID=$!
sleep 5

# Check if Firefox started successfully
if ! ps -p $FIREFOX_PID > /dev/null; then
    echo "Failed to start Firefox" >&2
fi

# Start oscilloscope visualization
cd /home/wave/W-AV/OscViz
./env/bin/python3 VolumeControl.py >/dev/null 2>&1 &

# Keep the X session running
wait