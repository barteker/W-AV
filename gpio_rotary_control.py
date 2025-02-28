import RPi.GPIO as GPIO
import time
import requests
import logging

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

def update_interface(tab=None, item=None, returnToTabs=False):
    """Send interface update to server"""
    try:
        data = {
            'returnToTabs': returnToTabs
        }
        if tab is not None:
            data['tab'] = tab
        if item is not None:
            data['item'] = item
            
        requests.post('http://localhost:8888/ui-update', json=data)
    except Exception as e:
        logging.error(f"Failed to update interface: {e}")

def handle_selection():
    """Handle selection button press"""
    try:
        if current_item == 0:  # Back button
            update_interface(returnToTabs=True)
            logging.info("Returning to tabs")
        else:
            if 0 <= current_item < len(items):
                uri = items[current_item].get('uri')
                if uri:
                    requests.post('http://localhost:8888/play-context', 
                                json={'uri': uri})
                    logging.info(f"Playing: {uri}")
    except Exception as e:
        logging.error(f"Selection error: {e}")

def update_focus(direction):
    """Send focus update to interface"""
    try:
        requests.post('http://localhost:8888/ui-update', 
                     json={'focus_change': direction})
    except Exception as e:
        logging.error(f"Failed to update focus: {e}")

def trigger_click():
    """Trigger click on focused element"""
    try:
        requests.post('http://localhost:8888/ui-update', 
                     json={'trigger_click': True})
    except Exception as e:
        logging.error(f"Failed to trigger click: {e}")

def main():
    if not setup_gpio():
        return
    
    global last_encoder_value, current_tab, current_item
    last_encoder_value = GPIO.input(ENCODER_A)
    
    try:
        while True:
            # Read encoder
            rotation = get_encoder_value()
            
            if rotation != 0:
                # Update selection based on rotation
                current_item = max(0, min(current_item + rotation, len(items)))
                update_interface(item=current_item)
                logging.info(f"Current item: {current_item}")
            
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