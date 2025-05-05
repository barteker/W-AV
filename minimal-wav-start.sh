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
    if curl -s http://127.0.0.1:8888 > /dev/null; then
        break
    fi
    sleep 1
done

# # Start EQ Audio Routing to DAC
# cd /home/wave/W-AV/OscViz
# python3 browser_eq_route.py >/dev/null 2>&1 &
# sleep 3

# Start Chromium in kiosk mode with HTTP
chromium-browser --kiosk \
                --window-position=0,0 \
                http://127.0.0.1:8888/ &
BROWSER_PID=$!
sleep 5

# Check if Chromium started successfully
if ! ps -p $BROWSER_PID > /dev/null; then
    echo "Failed to start Chromium" >&2
fi

# Start volume control
# Start JamesDSP
cd
./JDSP4Linux/build/src/jamesdsp >/dev/null 2>&1 &

# Return to main directory and start audio control scripts
cd /home/wave/W-AV
./env/bin/python3 OscViz/VolumeControl.py >/dev/null 2>&1 &

# Start EQ control scripts
./env/bin/python3 OscViz/jdsp_eq_control.py >/dev/null 2>&1 &
PYTHONPATH=/usr/lib/python3/dist-packages ./env/bin/python3 OscViz/oscVizQt5.py >/dev/null 2>&1 &

# Keep the X session running
wait
