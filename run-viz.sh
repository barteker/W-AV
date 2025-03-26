#!/bin/bash
export DISPLAY=:0
export XAUTHORITY=/home/wave/.Xauthority
export QT_QPA_PLATFORM=xcb
export XDG_RUNTIME_DIR=/run/user/1000

# Check for second display using xrandr
SECOND_DISPLAY=$(xrandr --query | grep " connected" | awk '{print $1}' | tail -1)

# If found, position window on second display
if [ -n "$SECOND_DISPLAY" ]; then
    echo "Second display found: $SECOND_DISPLAY"
    # Get resolution of second display
    RESOLUTION=$(xrandr --query | grep "$SECOND_DISPLAY" | grep -oP '\d+x\d+\+\d+\+\d+' | head -1)
    echo "Resolution: $RESOLUTION"
    
    # Extract position
    POSITION_X=$(echo $RESOLUTION | grep -oP '\+\d+\+' | grep -oP '\d+')
    POSITION_Y=$(echo $RESOLUTION | grep -oP '\+\d+$' | grep -oP '\d+')
    
    # Export position for Python script
    export SECOND_DISPLAY_X=$POSITION_X
    export SECOND_DISPLAY_Y=$POSITION_Y
    
    echo "Positioning on second display at: $POSITION_X,$POSITION_Y"
else
    echo "No second display found, using primary display"
fi

# Run the oscilloscope app
cd /home/wave/W-AV
python3 oscilloscopeViz.py