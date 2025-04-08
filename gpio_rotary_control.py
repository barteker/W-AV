import RPi.GPIO as GPIO
import time
import requests
import logging
import json
from logging.handlers import RotatingFileHandler

# Setup logging with rotation and error level only
log_handler = RotatingFileHandler(
    '/home/wave/rotary_control.log',
    maxBytes=1024*1024,  # 1MB per file
    backupCount=2        # Keep only 2 backup files
)

logging.basicConfig(
    level=logging.ERROR,  # Only log errors
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)

# GPIO Pin Configuration
ENCODER_A = 23    # Rotary encoder pin A
ENCODER_B = 24    # Rotary encoder pin B
SELECT_BTN = 27   # Select button

# State tracking variables
last_encoder_value = None
current_tab = 0
current_item = 0
tabs = ['playlists', 'albums', 'liked-songs'] 
items = []

def fetch_tab_data(tab_name):
    """Fetch data for the specified tab"""
    try:
        response = requests.get(f'http://localhost:8888/{tab_name}')
        if response.status_code == 200:
            data = response.json()
            # Transform the data into a consistent format
            formatted_items = []
            for item in data:
                if tab_name == 'albums':
                    formatted_items.append({
                        'name': item['album']['name'],
                        'uri': item['album']['uri'],
                        'type': 'album'
                    })
                elif tab_name == 'playlists':
                    formatted_items.append({
                        'name': item['name'],
                        'uri': item['uri'],
                        'type': 'playlist'
                    })
                elif tab_name == 'liked-songs':
                    formatted_items.append({
                        'name': item['track']['name'],
                        'uri': item['track']['uri'],
                        'type': 'track'
                    })
            return formatted_items
        else:
            logging.error(f"Failed to fetch {tab_name}. Status code: {response.status_code}")
            return []
    except Exception as e:
        logging.error(f"Error fetching {tab_name}: {e}")
        return []

def update_current_items():
    """Update items list based on current tab"""
    global items
    try:
        items = fetch_tab_data(tabs[current_tab])
    except Exception as e:
        logging.error(f"Error updating items: {e}")
        items = []

def setup_gpio():
    """Initialize GPIO pins with proper pull-up resistors"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        GPIO.setup(ENCODER_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(ENCODER_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(SELECT_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        return True
    except Exception as e:
        logging.error(f"GPIO setup failed: {e}")
        return False

def get_encoder_value():
    """Read rotary encoder value and determine direction of rotation"""
    global last_encoder_value
    
    clk_state = GPIO.input(ENCODER_A)
    dt_state = GPIO.input(ENCODER_B)
    
    if last_encoder_value is None:
        last_encoder_value = clk_state
        return 0
    
    if clk_state != last_encoder_value:
        if dt_state != clk_state:
            last_encoder_value = clk_state
            return 1  # Clockwise
        else:
            last_encoder_value = clk_state
            return -1  # Counter-clockwise
    
    return 0

def update_interface(tab=None, item=None, returnToTabs=False, focus_change=None, trigger_click=False):
    """Send interface update to server"""
    try:
        data = {
            'returnToTabs': returnToTabs
        }
        if tab is not None:
            data['tab'] = tab
        if item is not None:
            data['item'] = item
        if focus_change is not None:
            data['focus_change'] = focus_change
        if trigger_click:
            data['trigger_click'] = True
            
        requests.post('http://localhost:8888/ui-update', json=data)
    except Exception as e:
        logging.error(f"Failed to update interface: {e}")

def handle_selection():
    """Handle selection button press"""
    try:
        update_interface(trigger_click=True)
    except Exception as e:
        logging.error(f"Selection error: {e}")

def main():
    """Main program loop handling encoder input and button presses"""
    if not setup_gpio():
        return
    
    global last_encoder_value
    last_encoder_value = GPIO.input(ENCODER_A)
    
    # Initial data load
    try:
        update_current_items()
    except Exception as e:
        logging.error(f"Failed initial data load: {e}")
    
    try:
        while True:
            # Handle rotary encoder rotation
            rotation = get_encoder_value()
            if rotation != 0:
                focus_direction = 'next' if rotation > 0 else 'previous'
                update_interface(focus_change=focus_direction)
                
            # Handle button press
            if GPIO.input(SELECT_BTN) == GPIO.LOW:
                time.sleep(0.02)  # Debounce
                if GPIO.input(SELECT_BTN) == GPIO.LOW:
                    update_interface(trigger_click=True)
                    
                    # Implement cooldown period after button press
                    cooldown_time = 0.2  # 200ms cooldown
                    time.sleep(cooldown_time)
            
            time.sleep(0.001)  # Small delay for CPU efficiency
            
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()