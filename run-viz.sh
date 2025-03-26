# Replace the run-viz.sh with:
#!/bin/bash
export DISPLAY=:0
export XAUTHORITY=/home/wave/.Xauthority
export QT_QPA_PLATFORM=xcb

# Move the window to the second display
python3 -c "
import os
os.environ['DISPLAY'] = ':0'
from PyQt5.QtWidgets import QApplication
app = QApplication([])
screens = app.screens()
if len(screens) > 1:
    second_screen = screens[1].geometry()
    with open('/tmp/second_screen_info', 'w') as f:
        f.write(f'{second_screen.x()} {second_screen.y()} {second_screen.width()} {second_screen.height()}')
"

# Get second screen info if available
if [ -f "/tmp/second_screen_info" ]; then
    read -r x y width height < /tmp/second_screen_info
    export SECOND_DISPLAY_X=$x
    export SECOND_DISPLAY_Y=$y
    export SECOND_DISPLAY_WIDTH=$width
    export SECOND_DISPLAY_HEIGHT=$height
fi

# Run the oscilloscope
python3 /home/wave/W-AV/oscilloscopeViz.py
