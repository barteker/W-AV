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
    '/home/wave/power_switch.log',
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
sleep_mode_active = False
processes_to_manage = [
    "node server.js",              # W-AV server
    "python3 gpio_control.py",     # GPIO control
    "python3 gpio_rotary_control.py", # Rotary encoder control
    "python3 oscVizQt5.py",        # Oscilloscope visualizer
    "python3 VolEQSliders.py",     # Volume/EQ control
    "firefox --kiosk"              # Web interface
]

def setup():
    """Initialize GPIO pins"""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Setup power switch pin with pull-up resistor
    # Switch should connect the pin to ground when in ON position
    GPIO.setup(POWER_SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    logging.info("Power switch initialized on GPIO %d", POWER_SWITCH_PIN)

def clean_exit(signum, frame):
    """Handle clean exit when receiving termination signals"""
    logging.info("Termination signal received. Cleaning up...")
    # If in sleep mode, wake up before exiting
    if sleep_mode_active:
        exit_sleep_mode()
    GPIO.cleanup()
    sys.exit(0)

def find_process_ids(process_pattern):
    """Find all PIDs matching a pattern, returning a list"""
    try:
        cmd = f"pgrep -f '{process_pattern}'"
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        if result.stdout.strip():
            # Return list of PIDs (might be multiple)
            return result.stdout.strip().split('\n')
        return []
    except Exception as e:
        logging.error(f"Error finding PIDs for {process_pattern}: {e}")
        return []

def suspend_processes():
    """Suspend power-intensive processes"""
    logging.info("Suspending processes...")
    
    # Save PIDs to a file for reliable resumption
    pid_file = "/tmp/wave_suspended_pids.txt"
    with open(pid_file, "w") as f:
        for process in processes_to_manage:
            try:
                pids = find_process_ids(process)
                if pids:
                    for pid in pids:
                        logging.info(f"Suspending process: {process} (PID: {pid})")
                        f.write(f"{pid},{process}\n")
                        
                        # Send SIGSTOP to suspend the process
                        try:
                            os.kill(int(pid), signal.SIGSTOP)
                            logging.info(f"Successfully sent SIGSTOP to PID {pid}")
                        except Exception as e:
                            logging.error(f"Failed to send SIGSTOP to PID {pid}: {e}")
                else:
                    logging.info(f"No PIDs found for process: {process}")
            except Exception as e:
                logging.error(f"Error in suspend_processes for {process}: {e}")
    
    logging.info("Process suspension complete")

def resume_processes():
    """Resume previously suspended processes"""
    logging.info("Resuming processes...")
    
    # Read PIDs from the file
    pid_file = "/tmp/wave_suspended_pids.txt"
    if not os.path.exists(pid_file):
        logging.warning("No suspended PID file found")
        return
    
    with open(pid_file, "r") as f:
        lines = f.readlines()
        
    for line in lines:
        try:
            if "," in line:
                pid, process = line.strip().split(",", 1)
                logging.info(f"Resuming process: {process} (PID: {pid})")
                
                # Check if process still exists
                try:
                    os.kill(int(pid), 0)  # This just checks if the process exists
                    
                    # Send SIGCONT to resume the process
                    os.kill(int(pid), signal.SIGCONT)
                    logging.info(f"Successfully sent SIGCONT to PID {pid}")
                except ProcessLookupError:
                    logging.warning(f"PID {pid} no longer exists, may need to restart {process}")
                    # Here you could add code to restart the process
        except Exception as e:
            logging.error(f"Error resuming process from line '{line}': {e}")
    
    # Clean up the PID file
    try:
        os.remove(pid_file)
    except:
        pass
    
    logging.info("Process resume complete")

def turn_off_display():
    """Turn off HDMI display to save power"""
    logging.info("Turning off HDMI display")
    
    try:
        # Use vcgencmd as primary method (confirmed available)
        subprocess.run("/usr/bin/vcgencmd display_power 0", shell=True)
        
        # Target the correct card1 DRM controls for your system
        try:
            subprocess.run("sudo sh -c 'echo off > /sys/class/drm/card1-HDMI-A-1/status'", shell=True)
            subprocess.run("sudo sh -c 'echo off > /sys/class/drm/card1-HDMI-A-2/status'", shell=True)
        except Exception as e:
            logging.error(f"DRM control error: {e}")
            
        # Framebuffer blanking
        subprocess.run("sudo sh -c 'echo 1 > /sys/class/graphics/fb0/blank'", shell=True)
        
        # Switch to a text console but don't kill X
        subprocess.run("sudo chvt 1", shell=True)
        
        # Use DPMS with proper user context from the service file
        try:
            # Find the actual user running X
            user_cmd = "who | grep '(:0)' | awk '{print $1}'"
            x_user = subprocess.check_output(user_cmd, shell=True, text=True).strip()
            if not x_user:
                x_user = "wave"  # Default to 'wave' if detection fails
                
            # Use that user's authority to set DPMS
            subprocess.run(f"sudo -u {x_user} DISPLAY=:0 XAUTHORITY=/home/{x_user}/.Xauthority xset dpms force off", shell=True)
        except Exception as e:
            logging.error(f"DPMS control error: {e}")
    except Exception as e:
        logging.error(f"Error turning off display: {e}")

def turn_on_display():
    """Turn on HDMI display"""
    logging.info("Turning on HDMI display")
    
    try:
        # Re-enable DRM outputs
        try:
            subprocess.run("sudo sh -c 'echo on > /sys/class/drm/card1-HDMI-A-1/status'", shell=True)
            subprocess.run("sudo sh -c 'echo on > /sys/class/drm/card1-HDMI-A-2/status'", shell=True)
        except:
            pass
            
        # Unblank framebuffer
        subprocess.run("sudo sh -c 'echo 0 > /sys/class/graphics/fb0/blank'", shell=True)
        
        # Use vcgencmd to power on HDMI
        subprocess.run("/usr/bin/vcgencmd display_power 1", shell=True)
        
        # Switch back to GUI console
        subprocess.run("sudo chvt 7", shell=True)
        
        # Reset DPMS
        try:
            # Use the same user detection approach
            user_cmd = "who | grep '(:0)' | awk '{print $1}'"
            x_user = subprocess.check_output(user_cmd, shell=True, text=True).strip()
            if not x_user:
                x_user = "wave"  # Default to 'wave' if detection fails
                
            # Turn DPMS back on
            subprocess.run(f"sudo -u {x_user} DISPLAY=:0 XAUTHORITY=/home/{x_user}/.Xauthority xset dpms force on", shell=True)
        except Exception as e:
            logging.error(f"DPMS reset error: {e}")
    except Exception as e:
        logging.error(f"Error turning on display: {e}")

def enter_sleep_mode():
    """Put system into low-power sleep mode"""
    global sleep_mode_active
    
    if sleep_mode_active:
        return
        
    sleep_mode_active = True
    logging.info("Entering sleep mode")
    
    # First suspend processes
    suspend_processes()
    
    # Then turn off display
    turn_off_display()
    
    # Reduce CPU frequency to save power
    subprocess.run("echo powersave | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor", shell=True)
    
    # Create a flag file that your processes can check
    subprocess.run("touch /tmp/wav_sleep_mode", shell=True)
    
    logging.info("Sleep mode activated")

def exit_sleep_mode():
    """Exit sleep mode and restore normal operation"""
    global sleep_mode_active
    
    if not sleep_mode_active:
        return
        
    sleep_mode_active = False
    logging.info("Exiting sleep mode")
    
    # Restore CPU frequency governor
    subprocess.run("echo ondemand | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor", shell=True)
    
    # Restore maximum CPU frequency
    subprocess.run("echo 1500000 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq", shell=True)
    
    # Remove the tvservice calls and LED brightness controls that don't work
    
    # Remove sleep mode flag file
    subprocess.run("rm -f /tmp/wav_sleep_mode", shell=True)
    
    # Turn display back on first 
    turn_on_display()
    
    # Resume processes after display is on
    resume_processes()
    
    logging.info("Normal operation restored")

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
                    enter_sleep_mode()
                else:  # Switch turned ON
                    logging.info("Power switch turned ON")
                    exit_sleep_mode()
                
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
        
        # Check initial switch state and set mode accordingly
        if GPIO.input(POWER_SWITCH_PIN) == GPIO.HIGH:
            logging.info("Starting with power switch in OFF position")
            enter_sleep_mode()
        else:
            logging.info("Starting with power switch in ON position")
            # Make sure we're not in sleep mode
            exit_sleep_mode()
        
        # Start monitoring
        monitor_switch()
        
    except Exception as e:
        logging.error(f"Error in power switch script: {e}")
    finally:
        # Ensure we exit sleep mode if the script is terminating
        if sleep_mode_active:
            exit_sleep_mode()
        GPIO.cleanup()
        logging.info("GPIO cleaned up")

if __name__ == "__main__":
    main()