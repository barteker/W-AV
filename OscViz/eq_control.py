#!/usr/bin/env python3
import time
import logging
import traceback
import threading
import subprocess
import mido
from logging.handlers import RotatingFileHandler

# Add Adafruit CircuitPython imports
import board
import busio
import digitalio
from adafruit_mcp3xxx.analog_in import AnalogIn
from adafruit_mcp3xxx.mcp3008 import MCP3008

# ===== LOGGING CONFIGURATION =====
# Set this to False to disable most logging for better performance
ENABLE_VERBOSE_LOGGING = True

# Configure logging
log_handler = RotatingFileHandler(
    '/home/wave/eq_control.log',
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

# EQ band frequencies (Hz)
EQ_FREQS = [63, 170, 310, 600, 1000, 3000, 6000]

class EQControl:
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
        
        # Current EQ gains (in dB)
        self.eq_gains = [0.0] * 7
        
        # Setup JACK and Calf EQ
        self._setup_jack_eq()
        logger.info("EQ control initialized")
    
    def read_adc(self, channel):
        """Read from MCP3008 ADC channel using Adafruit library"""
        if 0 <= channel < len(self.adc_channels):
            try:
                raw_value = self.adc_channels[channel].value
                scaled_value = int(raw_value * 1023 / 65535)
                
                # Skip string formatting entirely if not at debug level
                # This saves CPU cycles when logging is disabled
                if ENABLE_VERBOSE_LOGGING and logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Channel {channel} raw: {raw_value}, scaled: {scaled_value}")
                    
                return scaled_value
            except Exception as e:
                logger.error(f"ADC read error on channel {channel}: {e}")
                return 0
        return 0
    
    def _setup_jack_eq(self):
        """Set up JACK with Calf EQ8"""
        try:
            # Check if calfjackhost is already running
            result = subprocess.run(["pgrep", "calfjackhost"], capture_output=True, text=True)
            if result.returncode == 0:
                # Stop existing calfjackhost
                subprocess.run(["killall", "calfjackhost"])
                time.sleep(1)  # Wait for it to stop
            
            # Start calfjackhost with EQ8
            subprocess.Popen(["pw-jack", "calfjackhost", "--no-gui", "eq8"])
            time.sleep(2)  # Wait for startup
            
            # Initialize MIDI output
            try:
                self.midi_out = mido.open_output('Calf Studio Gear:Calf EQ8 MIDI in 1')
                logger.info("MIDI output initialized")
            except Exception as e:
                logger.error(f"Failed to initialize MIDI: {e}")
                raise
            
            # Set up JACK connections
            subprocess.run(["pw-jack", "jack_connect", "Chromium:output_FL", "Calf EQ8:In L"])
            subprocess.run(["pw-jack", "jack_connect", "Chromium:output_FR", "Calf EQ8:In R"])
            subprocess.run(["pw-jack", "jack_connect", "Calf EQ8:Out L", "system:playback_1"])
            subprocess.run(["pw-jack", "jack_connect", "Calf EQ8:Out R", "system:playback_2"])
            
            logger.info("JACK and Calf EQ8 initialized successfully")
        except Exception as e:
            logger.error(f"Error setting up JACK EQ: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def apply_eq_settings(self):
        """Apply EQ settings using MIDI CC messages"""
        try:
            for i, gain in enumerate(self.eq_gains):
                # Convert gain from -12..+12 dB to 0..127 MIDI range
                midi_value = int((gain + 12) / 24 * 127)
                midi_value = max(0, min(127, midi_value))
                
                # Send MIDI CC message (CC numbers 20-26 for the 7 bands)
                msg = mido.Message('control_change', 
                                 control=20+i,
                                 value=midi_value)
                self.midi_out.send(msg)
            
            if ENABLE_VERBOSE_LOGGING:
                logger.debug(f"Applied EQ settings: {[f'{g:+.1f}dB' for g in self.eq_gains]}")
                
        except Exception as e:
            logger.error(f"Error applying EQ settings: {e}")
    
    def update_eq(self):
        """Read potentiometers and update EQ if needed"""
        try:
            eq_changed = False
            
            # Read the first 7 channels for EQ bands
            for i in range(7):
                raw_value = self.read_adc(i)
                
                # Convert to dB (-12 to +12 range)
                gain_db = (raw_value / 1023.0) * 24.0 - 12.0
                
                # Round to nearest 0.5 dB
                rounded_gain = round(gain_db * 2) / 2
                
                # Update if changed significantly (0.5 dB threshold)
                if abs(rounded_gain - self.eq_gains[i]) >= 0.5:
                    eq_changed = True
                    self.eq_gains[i] = rounded_gain
                    logger.info(f"Band {i+1} ({EQ_FREQS[i]}Hz): {rounded_gain:+.1f}dB")
            
            if eq_changed:
                self.apply_eq_settings()
                
        except Exception as e:
            logger.error(f"Error updating EQ: {e}")
    
    def _control_loop(self):
        """Background thread for reading potentiometers"""
        try:
            while self.running:
                self.update_eq()
                time.sleep(0.1)  # 10Hz update rate
        except Exception as e:
            logger.error(f"Control loop error: {e}")
    
    def start(self):
        """Start the EQ control thread"""
        try:
            self.control_thread = threading.Thread(target=self._control_loop)
            self.control_thread.daemon = True
            self.control_thread.start()
            logger.info("EQ control started")
        except Exception as e:
            logger.error(f"Failed to start control thread: {e}")
    
    def stop(self):
        """Stop the EQ control thread"""
        self.running = False
        
        if hasattr(self, 'control_thread') and self.control_thread.is_alive():
            self.control_thread.join(timeout=1.0)
        
        # Close MIDI output
        if hasattr(self, 'midi_out'):
            self.midi_out.close()
        
        # Stop calfjackhost
        try:
            subprocess.run(["killall", "calfjackhost"])
        except Exception as e:
            logger.error(f"Error stopping calfjackhost: {e}")
        
        logger.info("EQ control stopped")

# Run as standalone
if __name__ == "__main__":
    try:
        logger.info("Starting EQ Control application")
        
        # Initialize and start EQ control
        eq = EQControl()
        eq.start()
        
        # Keep running until interrupted
        logger.info("EQ Control running. Press Ctrl+C to stop.")
        while eq.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        logger.error(traceback.format_exc())
    finally:
        if 'eq' in locals():
            eq.stop()
        logger.info("Application exited") 