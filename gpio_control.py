import RPi.GPIO as GPIO
import time
import requests
import sys
import logging
import os
from logging.handlers import RotatingFileHandler

# Setup logging with rotation and error level only
log_handler = RotatingFileHandler(
    '/home/wave/gpio_control.log',
    maxBytes=1024*1024,  # 1MB per file
    backupCount=2        # Keep only 2 backup files
)

logging.basicConfig(
    level=logging.ERROR,  # Only log errors
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)

# GPIO Setup
PLAY_BTN = 7
STOP_BTN = 6
NEXT_BTN = 16    # Add next track button
PREV_BTN = 12    # Add previous track button

def force_cleanup():
    """Force cleanup of GPIO resources"""
    try:
        GPIO.cleanup()
    except:
        pass
    time.sleep(1)

def setup_gpio():
    """Initialize GPIO pins"""
    try:
        # Set GPIO mode first
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup all buttons with pull-up resistors
        GPIO.setup(PLAY_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(STOP_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(NEXT_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PREV_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        return True
    except Exception as e:
        logging.error(f"GPIO setup failed: {e}")
        return False

def handle_button(channel):
    """Handle button press events"""
    try:
        if channel == PLAY_BTN:
            response = requests.get('http://127.0.0.1:8888/player-state')
            if response.status_code == 200:
                state = response.json()
                if not state or not state.get('is_playing'):
                    requests.post('http://127.0.0.1:8888/play')
            
        elif channel == STOP_BTN:
            response = requests.get('http://127.0.0.1:8888/player-state')
            if response.status_code == 200:
                state = response.json()
                if state and state.get('is_playing'):
                    requests.post('http://127.0.0.1:8888/pause')
                    
        elif channel == NEXT_BTN:
            # Get current state before skipping
            response = requests.get('http://127.0.0.1:8888/player-state')
            was_playing = False
            if response.status_code == 200:
                state = response.json()
                was_playing = state and state.get('is_playing')
            
            # Skip to next track without automatically playing
            requests.post('http://127.0.0.1:8888/next')
            
        elif channel == PREV_BTN:
            # Get current state before skipping
            response = requests.get('http://127.0.0.1:8888/player-state')
            was_playing = False
            if response.status_code == 200:
                state = response.json()
                was_playing = state and state.get('is_playing')
            
            # Skip to previous track without automatically playing
            requests.post('http://127.0.0.1:8888/previous')
            
    except Exception as e:
        logging.error(f"Button press error: {e}")

def main():
    if not setup_gpio():
        logging.error("Failed to setup GPIO. Exiting...")
        sys.exit(1)
    
    try:
        # Initialize button states
        prev_play = GPIO.input(PLAY_BTN)
        prev_stop = GPIO.input(STOP_BTN)
        prev_next = GPIO.input(NEXT_BTN)
        prev_prev = GPIO.input(PREV_BTN)
        
        logging.info("GPIO Controller Started - Polling for button presses...")
        
        while True:
            # Read current button states
            play_current = GPIO.input(PLAY_BTN)
            stop_current = GPIO.input(STOP_BTN)
            next_current = GPIO.input(NEXT_BTN)
            prev_current = GPIO.input(PREV_BTN)
            
            # Check for button presses (transition from HIGH to LOW)
            if play_current == GPIO.LOW and prev_play == GPIO.HIGH:
                handle_button(PLAY_BTN)
                time.sleep(0.2)  # Debounce delay
                
            if stop_current == GPIO.LOW and prev_stop == GPIO.HIGH:
                handle_button(STOP_BTN)
                time.sleep(0.2)  # Debounce delay
                
            if next_current == GPIO.LOW and prev_next == GPIO.HIGH:
                handle_button(NEXT_BTN)
                time.sleep(0.2)  # Debounce delay
                
            if prev_current == GPIO.LOW and prev_prev == GPIO.HIGH:
                handle_button(PREV_BTN)
                time.sleep(0.2)  # Debounce delay
            
            # Update previous states
            prev_play = play_current
            prev_stop = stop_current
            prev_next = next_current
            prev_prev = prev_current
            
            time.sleep(0.05)  # Small delay to prevent CPU overuse
            
    except KeyboardInterrupt:
        logging.info("Shutting down gracefully...")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        GPIO.cleanup()
        logging.info("GPIO cleaned up")

if __name__ == "__main__":
    main()