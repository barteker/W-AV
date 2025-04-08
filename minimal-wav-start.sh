#!/bin/bash

# Set up error logging
exec > >(tee /home/wave/wav-startup.log) 2>&1
echo "Starting W/AV system at $(date)"

# Load X resources
xrdb -merge ~/.Xresources

# Set display environment variables
export DISPLAY=:0
export XAUTHORITY=/home/wave/.Xauthority

# Wait for X to be fully ready
sleep 3
echo "X environment initialized"

# Rotate the second display into correct orientation
sudo xrandr --output HDMI-2 --rotate right

# Start Node.js server
cd /home/wave/W-AV
npm start &
sleep 5

# Wait for the server to be ready (longer timeout)
echo "Waiting for server to initialize..."
for i in {1..15}; do
    if curl -s http://localhost:8888 > /dev/null; then
        echo "Server is running"
        break
    fi
    echo "Waiting for server ($i/15)..."
    sleep 1
done

# Start Firefox in kiosk mode
echo "Starting Firefox..."
firefox --kiosk http://localhost:8888/ --window-position=0,0 &
FIREFOX_PID=$!
sleep 5

# Check if Firefox started successfully
if ! ps -p $FIREFOX_PID > /dev/null; then
    echo "Failed to start Firefox" >&2
fi

# Start GPIO control scripts
echo "Starting GPIO control scripts..."
cd /home/wave/W-AV
# Removed these becuase they were started by service scripts
# python3 gpio_control.py &
# python3 gpio_rotary_control.py &

# Start oscilloscope visualization
echo "Starting oscilloscope visualization..."
cd /home/wave/W-AV/OscViz
# ./env/bin/python3 oscVizQt5.py & # Also seems to be started by service script
./env/bin/python3 VolumeControl.py &

echo "All components started"

# Keep the X session running
wait