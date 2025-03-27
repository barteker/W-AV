#!/bin/bash
cd /home/wave/W-AV
export DISPLAY=:0
export XAUTHORITY=/home/wave/.Xauthority
export XDG_RUNTIME_DIR=/run/user/1000
export QT_QPA_PLATFORM=xcb

# Check for second display
SECOND_DISPLAY=$(xrandr --query | grep " connected" | tail -n 1 | awk '{print $1}')
if [ "$SECOND_DISPLAY" != "HDMI-1" ]; then
    export SECOND_DISPLAY_X=1024
    export SECOND_DISPLAY_Y=0
fi

python3 oscilloscopeViz.py