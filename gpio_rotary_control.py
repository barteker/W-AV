import RPi.GPIO as GPIO
import time
import requests
import logging
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# GPIO Setup
ENCODER_A = 23    # Rotary encoder pin A
ENCODER_B = 24    # Rotary encoder pin B
SELECT_BTN = 27   # Select button

# Navigation state
current_tab = 0
current_item = 0
tabs = ['playlists', 'albums', 'liked-songs']
items = []
last_encoder_value = None

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
    items = fetch_tab_data(tabs[current_tab])
    logging.info(f"Loaded {len(items)} items for tab {tabs[current_tab]}")

def setup_gpio():
    """Initialize GPIO pins"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup encoder pins with pull-up resistors
        GPIO.setup(ENCODER_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(ENCODER_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(SELECT_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        logging.info("GPIO setup completed")
        return True
    except Exception as e:
        logging.error(f"GPIO setup failed: {e}")
        return False

def get_encoder_value():
    """Read rotary encoder value"""
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

def update_interface(tab=None, item=None, returnToTabs=False, focus_change=None):
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
            
        requests.post('http://localhost:8888/ui-update', json=data)
    except Exception as e:
        logging.error(f"Failed to update interface: {e}")

def handle_selection():
    """Handle selection button press"""
    global current_tab, current_item, items
    
    try:
        if current_item == 0:  # Back button
            update_interface(returnToTabs=True)
            logging.info("Returning to tabs")
        else:
            if 0 <= current_item-1 < len(items):  # Subtract 1 to account for back button
                item = items[current_item-1]
                if item.get('uri'):
                    requests.post('http://localhost:8888/play-context', 
                                json={'uri': item['uri']})
                    logging.info(f"Playing: {item['name']} ({item['uri']})")
    except Exception as e:
        logging.error(f"Selection error: {e}")

def main():
    if not setup_gpio():
        return
    
    global last_encoder_value, current_tab, current_item, items
    last_encoder_value = GPIO.input(ENCODER_A)
    
    # Initial data load
    update_current_items()
    
    try:
        while True:
            # Read encoder
            rotation = get_encoder_value()
            
            if rotation != 0:
                # Determine focus change direction based on rotation
                focus_direction = 'next' if rotation > 0 else 'previous'
                update_interface(focus_change=focus_direction)
                logging.info(f"Focus change: {focus_direction}")
                # Update selection based on rotation
                # Add 1 to max items to account for back button
                current_item = max(0, min(current_item + rotation, len(items) + 1))
                update_interface(item=current_item)
                logging.info(f"Current item: {current_item}")
                logging.info(f"Total items: {len(items)}")
            
            # Check select button
            if GPIO.input(SELECT_BTN) == GPIO.LOW:
                time.sleep(0.2)  # Debounce
                if GPIO.input(SELECT_BTN) == GPIO.LOW:
                    handle_selection()
                    
                    while GPIO.input(SELECT_BTN) == GPIO.LOW:
                        time.sleep(0.05)
            
            time.sleep(0.001)  # Small delay
            
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()