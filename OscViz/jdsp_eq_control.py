#!/usr/bin/env python3
import time
import numpy as np
import threading
import logging
import traceback
import os
import subprocess
import signal
from logging.handlers import RotatingFileHandler

# Add Adafruit CircuitPython imports for hardware
import board
import busio
import digitalio
from adafruit_mcp3xxx.analog_in import AnalogIn
from adafruit_mcp3xxx.mcp3008 import MCP3008

# ===== LOGGING CONFIGURATION =====
log_handler = RotatingFileHandler(
    '/home/wave/jdsp_eq_control.log',
    maxBytes=1024*1024,
    backupCount=3
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)
logger = logging.getLogger(__name__)

# Path to jamesdsp binary
JAMESDSP_BIN = "/home/wave/JDSP4Linux/build/src/jamesdsp"

# EQ bands center frequencies (Hz)
INPUT_FREQS = [60, 150, 400, 1000, 2400, 6000, 15000]  # 7 Bands from sliders
JDSP_FREQS = [25, 40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000, 6300, 10000, 16000]  # 15 Bands in JamesDSP

# Configuration parameters
UPDATE_INTERVAL = 0.3  # Reduce update frequency to 5Hz (was 0.05 = 20Hz)
HISTORY_SIZE = 10      # Increase history size for better smoothing (was 5)
CHANGE_THRESHOLD = 1.0 # Increase threshold to reduce updates (was 0.5dB)
UPDATE_BATCH_TIME = 1.0 # Only update JamesDSP at most once per second

class JDSPEQControl:
    def __init__(self):
        """Initialize the JamesDSP EQ control system"""
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
            for i in range(7):  # 7 EQ bands
                self.adc_channels.append(AnalogIn(self.mcp, i))
            
            logger.info("MCP3008 initialized successfully")
            
            # Test ADC readings
            test_readings = [self.read_adc(i) for i in range(7)]
            logger.info(f"Initial ADC readings: {test_readings}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP3008: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Thread synchronization
        self.lock = threading.Lock()
        self.running = True
        
        # Current EQ settings
        self.eq_gains = [0.0] * 7  # 7 bands, initial values at 0dB
        
        # Simple smoothing with larger window
        self.gain_history = [[0.0] * HISTORY_SIZE for _ in range(7)]  # Larger history for each band
        
        # Track the last time we updated JamesDSP
        self.last_update_time = 0
        
        # Flag to track if EQ has changed since last update
        self.eq_needs_update = False
        
        # Initialize JamesDSP
        self._init_jamesdsp()
        
    def _init_jamesdsp(self):
        """Initialize JamesDSP settings"""
        try:
            # Enable graphic equalizer
            subprocess.run([JAMESDSP_BIN, "--set", "graphiceq_enable=true"], check=True)
            # Set initial flat EQ
            self._apply_eq_to_jdsp([0.0] * 7)
            logger.info("JamesDSP initialized with flat EQ")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to initialize JamesDSP: {e}")
        except Exception as e:
            logger.error(f"Error initializing JamesDSP: {e}")
            logger.error(traceback.format_exc())
    
    def read_adc(self, channel):
        """Read from MCP3008 ADC channel (0-6) using Adafruit library"""
        if 0 <= channel < len(self.adc_channels):
            try:
                raw_value = self.adc_channels[channel].value
                scaled_value = int(raw_value * 1023 / 65535)
                return scaled_value
            except Exception as e:
                logger.error(f"ADC read error on channel {channel}: {e}")
                return 0
        return 0
    
    def update_controls(self):
        """Read potentiometer values and update EQ settings"""
        try:
            # Read all channels at once
            raw_values = [self.read_adc(i) for i in range(7)]
            
            # Convert to dB values (-12 to +12 range)
            eq_changed = False
            
            for i, raw_value in enumerate(raw_values):
                # Convert to dB (-12 to +12 range)
                gain_db = (raw_value / 1023.0) * 24.0 - 12.0
                
                # Update history and calculate moving average
                self.gain_history[i].pop(0)
                self.gain_history[i].append(gain_db)
                
                # Use weighted average to emphasize recent values but smooth out noise
                weights = np.linspace(0.5, 1.0, HISTORY_SIZE)
                weighted_values = np.array(self.gain_history[i]) * weights
                avg_gain = np.sum(weighted_values) / np.sum(weights)
                
                # Round to nearest 0.5 dB
                rounded_gain = round(avg_gain * 2) / 2
                
                # Check if changed significantly
                if abs(rounded_gain - self.eq_gains[i]) >= CHANGE_THRESHOLD:
                    eq_changed = True
                    self.eq_gains[i] = rounded_gain
                    logger.debug(f"Band {i} ({INPUT_FREQS[i]}Hz): {rounded_gain:+.1f}dB")
            
            # Set flag if EQ changed
            if eq_changed:
                self.eq_needs_update = True
            
            # Check if it's time to update JamesDSP
            current_time = time.time()
            if self.eq_needs_update and (current_time - self.last_update_time) >= UPDATE_BATCH_TIME:
                self._apply_eq_to_jdsp(self.eq_gains)
                self.last_update_time = current_time
                self.eq_needs_update = False
            
        except Exception as e:
            logger.error(f"Error updating controls: {e}")
            logger.error(traceback.format_exc())
    
    def _apply_eq_to_jdsp(self, gains):
        """Apply 7-band EQ settings to JamesDSP's 15-band EQ"""
        try:
            # Map the 7 bands to 15 bands
            mapped_gains = self._map_7_to_15_bands(gains)
            
            # Format the EQ string for JamesDSP
            eq_string = "GraphicEQ: "
            
            # Add each frequency and gain
            for i, freq in enumerate(JDSP_FREQS):
                eq_string += f"{freq} {mapped_gains[i]:.1f}"
                if i < len(JDSP_FREQS) - 1:
                    eq_string += "; "
            
            # Apply the EQ settings using a separate thread to avoid blocking
            update_thread = threading.Thread(
                target=self._send_command_to_jamesdsp,
                args=(eq_string,)
            )
            update_thread.daemon = True
            update_thread.start()
            
            logger.info(f"Applied EQ: {[f'{g:+.1f}dB' for g in gains]} -> JamesDSP")
            
        except Exception as e:
            logger.error(f"Error applying EQ settings: {e}")
            logger.error(traceback.format_exc())
    
    def _send_command_to_jamesdsp(self, eq_string):
        """Send command to JamesDSP in a separate thread"""
        try:
            subprocess.run(
                [JAMESDSP_BIN, "--set", f"graphiceq_param={eq_string}"], 
                check=True,
                timeout=5  # Add timeout to prevent hanging
            )
        except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Failed to send command to JamesDSP: {e}")
    
    def _map_7_to_15_bands(self, gains_7band):
        """Map 7 bands to 15 bands used by JamesDSP"""
        # Initialize 15 bands with zeros
        gains_15band = [0.0] * 15
        
        # Map bands based on frequencies:
        # Input: 60, 150, 400, 1000, 2400, 6000, 15000
        # JDSP:  25, 40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000, 6300, 10000, 16000
        
        # 60Hz (first band) affects 25, 40, 63, 100
        gains_15band[0] = gains_7band[0] * 0.5  # 25Hz (partial effect)
        gains_15band[1] = gains_7band[0] * 0.7  # 40Hz (partial effect)
        gains_15band[2] = gains_7band[0]        # 63Hz (direct match)
        gains_15band[3] = gains_7band[0] * 0.7  # 100Hz (partial effect)
        
        # 150Hz (second band) affects 100, 160, 250
        gains_15band[3] += gains_7band[1] * 0.3  # 100Hz (partial effect)
        gains_15band[4] = gains_7band[1]         # 160Hz (direct match)
        gains_15band[5] = gains_7band[1] * 0.7   # 250Hz (partial effect)
        
        # 400Hz (third band) affects 250, 400, 630
        gains_15band[5] += gains_7band[2] * 0.3  # 250Hz (partial effect)
        gains_15band[6] = gains_7band[2]         # 400Hz (direct match)
        gains_15band[7] = gains_7band[2] * 0.7   # 630Hz (partial effect)
        
        # 1000Hz (fourth band) affects 630, 1000, 1600
        gains_15band[7] += gains_7band[3] * 0.3  # 630Hz (partial effect)
        gains_15band[8] = gains_7band[3]         # 1000Hz (direct match)
        gains_15band[9] = gains_7band[3] * 0.7   # 1600Hz (partial effect)
        
        # 2400Hz (fifth band) affects 1600, 2500, 4000
        gains_15band[9] += gains_7band[4] * 0.3  # 1600Hz (partial effect)
        gains_15band[10] = gains_7band[4]        # 2500Hz (direct match)
        gains_15band[11] = gains_7band[4] * 0.7  # 4000Hz (partial effect)
        
        # 6000Hz (sixth band) affects 4000, 6300, 10000
        gains_15band[11] += gains_7band[5] * 0.3  # 4000Hz (partial effect)
        gains_15band[12] = gains_7band[5]         # 6300Hz (direct match)
        gains_15band[13] = gains_7band[5] * 0.7   # 10000Hz (partial effect)
        
        # 15000Hz (seventh band) affects 10000, 16000
        gains_15band[13] += gains_7band[6] * 0.3  # 10000Hz (partial effect)
        gains_15band[14] = gains_7band[6]         # 16000Hz (direct match)
        
        # Simplify the overlapping bands - just average the contributions
        for i in range(len(gains_15band)):
            if i in [3, 5, 7, 9, 11, 13]:  # These bands have multiple contributions
                gains_15band[i] /= 2.0  # Average the two contributions
        
        return gains_15band
    
    def start(self):
        """Start control thread"""
        self.running = True
        self.control_thread = threading.Thread(target=self._control_loop)
        self.control_thread.daemon = True
        self.control_thread.start()
        logger.info("JamesDSP EQ control system started")
    
    def _control_loop(self):
        """Background thread for reading potentiometers"""
        try:
            while self.running:
                with self.lock:
                    self.update_controls()
                time.sleep(UPDATE_INTERVAL)  # Reduced update rate
        except Exception as e:
            logger.error(f"Control loop error: {e}")
            logger.error(traceback.format_exc())
            self.running = False
    
    def stop(self):
        """Stop control system and clean up"""
        self.running = False
        
        if hasattr(self, 'control_thread'):
            self.control_thread.join(timeout=1.0)
        
        # Set EQ back to flat
        try:
            flat_eq = [0.0] * 7
            self._apply_eq_to_jdsp(flat_eq)
            logger.info("EQ reset to flat")
        except:
            pass
        
        logger.info("JamesDSP EQ control system stopped")

# Run as standalone
if __name__ == "__main__":
    try:
        logger.info("Starting JamesDSP EQ Control application")

        # Start JamesDSP service - commented out, assuming JamesDSP is already running
        # subprocess.run([JAMESDSP_BIN], shell=False)
        
        # Check if JamesDSP binary exists
        if not os.path.exists(JAMESDSP_BIN):
            logger.error(f"JamesDSP binary not found at: {JAMESDSP_BIN}")
            logger.error("Please modify the JAMESDSP_BIN variable to point to your installation")
            exit(1)
        
        # Check if JamesDSP is running
        try:
            subprocess.run([JAMESDSP_BIN, "--get", "master_enable"], check=True, capture_output=True)
            logger.info("JamesDSP is running")
        except subprocess.CalledProcessError:
            logger.warning("JamesDSP may not be running. Starting it now...")
            try:
                # Start JamesDSP in background
                subprocess.Popen([JAMESDSP_BIN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2)  # Give it time to start
            except Exception as e:
                logger.error(f"Failed to start JamesDSP: {e}")
        
        # Create and start EQ controller
        eq = JDSPEQControl()
        eq.start()
        
        # Set up signal handler for clean shutdown
        def handle_signal(sig, frame):
            logger.info(f"Received signal {sig}, shutting down")
            eq.stop()
            exit(0)
        
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        
        # Keep running until interrupted
        logger.info(f"JamesDSP EQ Control running using {JAMESDSP_BIN}")
        logger.info("Bands: 60Hz, 150Hz, 400Hz, 1kHz, 2.4kHz, 6kHz, 15kHz")
        logger.info(f"Update interval: {UPDATE_INTERVAL:.2f}s, EQ update rate: {UPDATE_BATCH_TIME:.1f}s")
        logger.info("Press Ctrl+C to stop.")
        
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