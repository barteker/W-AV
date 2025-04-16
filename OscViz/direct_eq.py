#!/usr/bin/env python3
import time
import numpy as np
import threading
import logging
import traceback
import board
import busio
import digitalio
import os
import subprocess
from logging.handlers import RotatingFileHandler
from adafruit_mcp3xxx.analog_in import AnalogIn
from adafruit_mcp3xxx.mcp3008 import MCP3008

# Configure logging
log_handler = RotatingFileHandler(
    '/home/wave/eq_control.log',
    maxBytes=1024*1024,
    backupCount=3
)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)
logger = logging.getLogger(__name__)

# EQ bands center frequencies (Hz) - matched to Calf EQ8
EQ_FREQS = [63, 250, 500, 1000, 2000, 4000, 8000]

class DirectEQ:
    def __init__(self):
        # Initialize Adafruit MCP3008
        try:
            self.spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            self.cs = digitalio.DigitalInOut(board.CE0)
            self.mcp = MCP3008(self.spi, self.cs)
            
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
        
        self.lock = threading.Lock()
        self.running = True
        
        # Current settings
        self.eq_gains = [0.0] * 7
        
        # Simple smoothing with larger window
        self.gain_history = [[0.0] * 5 for _ in range(7)]  # 5-sample history for each band
        
        # Start calfjackhost if not running
        self._setup_calf()
        
    def _setup_calf(self):
        """Set up Calf EQ8 plugin"""
        try:
            # Check if calfjackhost is already running
            result = subprocess.run(["pgrep", "calfjackhost"], capture_output=True, text=True)
            if result.returncode != 0:
                # Start calfjackhost with EQ8
                subprocess.Popen(["calfjackhost", "eq8:eq"])
                time.sleep(2)  # Wait for startup
            
            # Set up initial connections if needed
            self._setup_connections()
            
            logger.info("Calf EQ8 initialized")
            
        except Exception as e:
            logger.error(f"Failed to set up Calf EQ8: {e}")
            raise
            
    def _setup_connections(self):
        """Set up JACK connections"""
        try:
            # Connect system capture to EQ input
            subprocess.run(["jack_connect", "system:capture_1", "eq8:In L"])
            subprocess.run(["jack_connect", "system:capture_2", "eq8:In R"])
            
            # Connect EQ output to system playback
            subprocess.run(["jack_connect", "eq8:Out L", "system:playback_1"])
            subprocess.run(["jack_connect", "eq8:Out R", "system:playback_2"])
            
        except Exception as e:
            logger.error(f"Failed to set up JACK connections: {e}")
    
    def read_adc(self, channel):
        """Read from MCP3008 ADC channel (0-7) using Adafruit library"""
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
        """Read potentiometer values and update settings"""
        try:
            # Read all channels at once
            raw_values = [self.read_adc(i) for i in range(7)]
            
            # Convert to dB values (-12 to +12 range)
            new_gains = []
            eq_changed = False
            
            for i, raw_value in enumerate(raw_values):
                # Convert to dB (-12 to +12 range)
                gain_db = (raw_value / 1023.0) * 24.0 - 12.0
                
                # Update history and calculate moving average
                self.gain_history[i].pop(0)
                self.gain_history[i].append(gain_db)
                avg_gain = sum(self.gain_history[i]) / len(self.gain_history[i])
                
                # Round to nearest 0.5 dB
                rounded_gain = round(avg_gain * 2) / 2
                
                # Check if changed significantly (0.5 dB threshold)
                if abs(rounded_gain - self.eq_gains[i]) >= 0.5:
                    eq_changed = True
                    self.eq_gains[i] = rounded_gain
                    logger.debug(f"Band {i} ({EQ_FREQS[i]}Hz): {rounded_gain:+.1f}dB")
            
            if eq_changed:
                self.apply_eq_settings()
            
        except Exception as e:
            logger.error(f"Error updating controls: {e}")
            logger.error(traceback.format_exc())
    
    def apply_eq_settings(self):
        """Apply EQ settings using Calf EQ8"""
        try:
            for i, gain in enumerate(self.eq_gains):
                # Set EQ band gain using Calf's control interface
                cmd = [
                    "calf-ctl",
                    "set",
                    "eq8",
                    f"band{i+1}_gain",
                    f"{gain:.1f}"
                ]
                subprocess.run(cmd, capture_output=True)
            
            logger.info(f"Applied EQ settings: {[f'{g:+.1f}dB' for g in self.eq_gains]}")
            
        except Exception as e:
            logger.error(f"Error applying EQ settings: {e}")
            logger.error(traceback.format_exc())
    
    def start(self):
        """Start control thread"""
        self.running = True
        self.control_thread = threading.Thread(target=self._control_loop)
        self.control_thread.daemon = True
        self.control_thread.start()
        logger.info("EQ control system started")
    
    def _control_loop(self):
        """Background thread for reading potentiometers"""
        try:
            while self.running:
                with self.lock:
                    self.update_controls()
                time.sleep(0.05)  # 20Hz update rate
        except Exception as e:
            logger.error(f"Control loop error: {e}")
            logger.error(traceback.format_exc())
            self.running = False
    
    def stop(self):
        """Stop control system"""
        self.running = False
        
        if hasattr(self, 'control_thread'):
            self.control_thread.join(timeout=1.0)
        
        logger.info("EQ control system stopped")

if __name__ == "__main__":
    try:
        logger.info("Starting DirectEQ application")
        
        # Create and start EQ controller
        eq = DirectEQ()
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