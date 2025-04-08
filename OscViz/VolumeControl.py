#!/usr/bin/env python3
import time
import logging
import traceback
import threading
import subprocess
from logging.handlers import RotatingFileHandler

# Add Adafruit CircuitPython imports
import board
import busio
import digitalio
from adafruit_mcp3xxx.analog_in import AnalogIn
from adafruit_mcp3xxx.mcp3008 import MCP3008

# ===== LOGGING CONFIGURATION =====
# Set this to False to disable most logging for better performance
ENABLE_VERBOSE_LOGGING = False

# Configure logging
log_handler = RotatingFileHandler(
    '/home/wave/volume_control.log',
    maxBytes=1024*1024,
    backupCount=3
)
logging.basicConfig(
    # Use ERROR level when verbose logging is disabled to minimize overhead
    level=logging.INFO if ENABLE_VERBOSE_LOGGING else logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)
logger = logging.getLogger(__name__)

# MCP3008 configuration
ADC_CHANNELS = 8

class VolumeControl:
    def __init__(self):
        # Initialize Adafruit MCP3008
        try:
            # Create the SPI bus
            self.spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            
            # Create the CS (chip select)
            self.cs = digitalio.DigitalInOut(board.CE0)
            
            # Create the MCP object
            self.mcp = MCP3008(self.spi, self.cs)
            
            # Create analog input channels on the MCP3008
            self.adc_channels = []
            for i in range(ADC_CHANNELS):
                self.adc_channels.append(AnalogIn(self.mcp, i))
            
            logger.info("MCP3008 initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP3008: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Thread synchronization
        self.running = True
        
        # Current volume level (0.0 to 1.0)
        self.volume = 1.0
        
        # Apply initial volume
        self.set_alsa_volume(100)
        logger.info("Volume control initialized")
    
    def read_adc(self, channel):
        """Read from MCP3008 ADC channel using Adafruit library"""
        if 0 <= channel < len(self.adc_channels):
            try:
                raw_value = self.adc_channels[channel].value
                scaled_value = int(raw_value * 1023 / 65535)
                
                # Skip string formatting entirely if not at debug level
                # This saves CPU cycles even when logging is disabled
                if ENABLE_VERBOSE_LOGGING and logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Channel {channel} raw: {raw_value}, scaled: {scaled_value}")
                    
                return scaled_value
            except Exception as e:
                logger.error(f"ADC read error on channel {channel}: {e}")
                return 0
        return 0
    
    def set_alsa_volume(self, volume_percent):
        """Set the ALSA volume using amixer"""
        try:
            # Use the Digital Playback Volume control (numid=1)
            cmd = ["amixer", "-c", "Pro", "cset", "numid=1", f"{volume_percent}%"]
            
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Set Digital Playback Volume to {volume_percent}%")
                return True
            else:
                logger.error(f"Failed to set volume: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    def update_volume(self):
        """Read volume potentiometer and update if needed"""
        try:
            # Read volume from channel 7
            raw_volume = self.read_adc(7)
            new_volume = raw_volume / 1023.0
            
            # Update if changed significantly
            if abs(new_volume - self.volume) > 0.02:
                self.volume = new_volume
                vol_percent = int(self.volume * 100)
                logger.info(f"Volume changed to {vol_percent}%")
                
                # Set the ALSA volume
                self.set_alsa_volume(vol_percent)
        except Exception as e:
            logger.error(f"Error updating volume: {e}")
    
    def _control_loop(self):
        """Background thread for reading volume potentiometer"""
        try:
            while self.running:
                self.update_volume()
                time.sleep(0.1)  # 10Hz update rate
        except Exception as e:
            logger.error(f"Control loop error: {e}")
    
    def start(self):
        """Start the volume control thread"""
        try:
            self.control_thread = threading.Thread(target=self._control_loop)
            self.control_thread.daemon = True
            self.control_thread.start()
            logger.info("Volume control started")
        except Exception as e:
            logger.error(f"Failed to start control thread: {e}")
    
    def stop(self):
        """Stop the volume control thread"""
        self.running = False
        
        if hasattr(self, 'control_thread') and self.control_thread.is_alive():
            self.control_thread.join(timeout=1.0)
        
        logger.info("Volume control stopped")

# Run as standalone
if __name__ == "__main__":
    try:
        logger.info("Starting Volume Control application")
        
        # Initialize and start volume control
        vc = VolumeControl()
        vc.start()
        
        # Keep running until interrupted
        logger.info("Volume Control running. Press Ctrl+C to stop.")
        while vc.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        logger.error(traceback.format_exc())
    finally:
        if 'vc' in locals():
            vc.stop()
        logger.info("Application exited")