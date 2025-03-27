import RPi.GPIO as GPIO
import time
import os
import logging
import signal
import sys
import subprocess
from logging.handlers import RotatingFileHandler

# Modified logging setup with rotation
log_handler = RotatingFileHandler(
    '/home/pi/power_switch.log',
    maxBytes=1024*1024,  # 1MB per file
    backupCount=3        # Keep 3 backup files
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)

# Avoid pins already in use (7, 8, 12, 16, 23, 24, 27, 5, 9, 10, 11)
POWER_SWITCH_PIN = 17  # GPIO17 (Pin 11)

# Initialize variables
shutdown_in_progress = False

def setup():
    """Initialize GPIO pins"""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Setup power switch pin with pull-up resistor
    # Switch should connect the pin to ground when in OFF position
    GPIO.setup(POWER_SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    logging.info("Power switch initialized on GPIO %d", POWER_SWITCH_PIN)

def clean_exit(signum, frame):
    """Handle clean exit when receiving termination signals"""
    logging.info("Termination signal received. Cleaning up...")
    GPIO.cleanup()
    sys.exit(0)

def gracefully_terminate_processes():
    """Stop important processes before shutdown"""
    processes_to_stop = [
        "node server.js",     # W-AV server
        "python3 gpio_control.py",
        "python3 gpio_rotary_control.py"
    ]
    
    logging.info("Gracefully terminating processes...")
    
    for process in processes_to_stop:
        try:
            # Find process ID by name
            cmd = f"pgrep -f '{process}'"
            result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
            
            if result.stdout.strip():
                pid = result.stdout.strip()
                logging.info(f"Stopping process: {process} (PID: {pid})")
                
                # Send SIGTERM to allow graceful shutdown
                subprocess.run(f"kill -15 {pid}", shell=True)
                
                # Wait a moment for process to terminate
                time.sleep(1)
                
                # Check if process is still running and force kill if needed
                check = subprocess.run(f"kill -0 {pid} 2>/dev/null || echo terminated", 
                                      shell=True, text=True, capture_output=True)
                
                if "terminated" not in check.stdout:
                    logging.info(f"Forcing termination of {process}")
                    subprocess.run(f"kill -9 {pid}", shell=True)
        except Exception as e:
            logging.error(f"Error stopping {process}: {e}")
    
    # Give processes a moment to fully terminate
    time.sleep(2)
    logging.info("Process termination complete")

def initiate_shutdown():
    """Perform system halt with graceful shutdown"""
    global shutdown_in_progress
    
    if shutdown_in_progress:
        return
        
    shutdown_in_progress = True
    logging.info("Initiating shutdown sequence")
    
    # First stop our custom processes
    gracefully_terminate_processes()
    
    # Then sync filesystems to prevent data loss
    subprocess.run("sync", shell=True)
    
    # Now halt the system
    logging.info("Executing system halt")
    os.system("sudo halt")  # Changed to halt for wake-on-GPIO capability

def monitor_switch():
    """Monitor the power switch state"""
    previous_state = GPIO.input(POWER_SWITCH_PIN)
    debounce_time = 0.1
    
    logging.info("Starting power switch monitoring")
    
    while True:
        current_state = GPIO.input(POWER_SWITCH_PIN)
        
        # State change detected (accounting for pull-up: LOW = switch ON, HIGH = switch OFF)
        if current_state != previous_state:
            # Wait for debounce
            time.sleep(debounce_time)
            current_state = GPIO.input(POWER_SWITCH_PIN)
            
            # If still different after debounce, process the change
            if current_state != previous_state:
                if current_state == GPIO.HIGH:  # Switch turned OFF
                    logging.info("Power switch turned OFF")
                    initiate_shutdown()
                
                previous_state = current_state
        
        time.sleep(0.1)  # Small delay to prevent CPU overuse

def main():
    """Main function"""
    try:
        # Register signal handlers
        signal.signal(signal.SIGTERM, clean_exit)
        signal.signal(signal.SIGINT, clean_exit)
        
        # Setup GPIO
        setup()
        
        # Check initial switch state
        if GPIO.input(POWER_SWITCH_PIN) == GPIO.HIGH:
            logging.info("Starting with power switch in OFF position")
        else:
            logging.info("Starting with power switch in ON position")
        
        # Start monitoring
        monitor_switch()
        
    except Exception as e:
        logging.error(f"Error in power switch script: {e}")
    finally:
        GPIO.cleanup()
        logging.info("GPIO cleaned up")

if __name__ == "__main__":
    main()