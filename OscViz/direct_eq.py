#!/usr/bin/env python3
import time
import numpy as np
import pulsectl
import threading
import logging
import traceback
import board
import busio
import digitalio
import os
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

# EQ bands center frequencies (Hz)
EQ_FREQS = [63, 250, 500, 1000, 2000, 4000, 8000]

class DirectEQ:
    def __init__(self):
        # Initialize Adafruit MCP3008
        try:
            self.spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            self.cs = digitalio.DigitalInOut(board.CE0)
            self.mcp = MCP3008(self.spi, self.cs)
            
            self.adc_channels = []
            for i in range(8):  # 7 EQ bands + volume
                self.adc_channels.append(AnalogIn(self.mcp, i))
            
            logger.info("MCP3008 initialized using Adafruit CircuitPython library")
        except Exception as e:
            logger.error(f"Failed to initialize MCP3008: {e}")
            logger.error(traceback.format_exc())
            raise
        
        self.lock = threading.Lock()
        self.running = True
        
        # Connect to PulseAudio
        self.pulse = pulsectl.Pulse('eq-controller')
        logger.info("Connected to PulseAudio")
        
        # Current settings
        self.eq_gains = [0.0] * 7
        self.volume = 1.0

        # Set up system EQ if possible
        self.setup_system_eq()
    
    def setup_system_eq(self):
        """Try to load PulseAudio equalizer module if not already loaded"""
        try:
            # Check if equalizer module is already loaded
            result = os.popen('pactl list modules | grep equalizer').read()
            if not result:
                # Try to load the module-equalizer-sink
                os.system('pactl load-module module-equalizer-sink')
                os.system('pactl set-default-sink equalizer')
                logger.info("Loaded PulseAudio equalizer module")
            else:
                logger.info("PulseAudio equalizer already loaded")
            return True
        except Exception as e:
            logger.error(f"Couldn't set up system EQ: {e}")
            return False
    
    def read_adc(self, channel):
        """Read from MCP3008 ADC channel (0-7) using Adafruit library"""
        if 0 <= channel < len(self.adc_channels):
            try:
                raw_value = self.adc_channels[channel].value
                scaled_value = int(raw_value * 1023 / 65535)
                logger.debug(f"Channel {channel} raw: {raw_value}, scaled: {scaled_value}, voltage: {self.adc_channels[channel].voltage:.2f}V")
                return scaled_value
            except Exception as e:
                logger.error(f"ADC read error on channel {channel}: {e}")
                return 0
        return 0
    
    def update_controls(self):
        """Read potentiometer values and update settings"""
        try:
            # Read all raw values
            raw_values = [self.read_adc(i) for i in range(8)]
            logger.debug(f"Raw ADC values: {raw_values}")
            
            # Update EQ settings (channels 0-6)
            eq_changed = False
            for i in range(7):
                raw_value = raw_values[i]
                # Convert from 0-1023 to -12dB to +12dB
                gain_db = (raw_value / 1023.0) * 24.0 - 12.0
                
                # Update if changed significantly
                if abs(gain_db - self.eq_gains[i]) > 0.5:
                    self.eq_gains[i] = gain_db
                    eq_changed = True
                    logger.debug(f"Updated EQ band {i} (center: {EQ_FREQS[i]}Hz) gain to {gain_db}dB")
            
            # Update volume (channel 7)
            raw_volume = raw_values[7]
            new_volume = raw_volume / 1023.0
            
            # Update volume if changed significantly
            if abs(new_volume - self.volume) > 0.02:
                self.volume = new_volume
                self.apply_volume_setting()
                logger.debug(f"Volume updated to {self.volume*100:.1f}%")
                
            # Update system EQ if needed
            if eq_changed:
                self.apply_eq_settings()
                
        except Exception as e:
            logger.error(f"Error reading controls: {e}")
            logger.error(traceback.format_exc())
    
    def apply_eq_settings(self):
        """Apply EQ settings to the system"""
        try:
            # Method 1: If equalizer-sink is available
            try:
                # Each band needs specific command
                for i, gain_db in enumerate(self.eq_gains):
                    # Convert to filter parameter (0.0 to 1.0 where 0.5 is neutral)
                    gain_norm = (gain_db + 12) / 24.0
                    # Apply to appropriate band
                    os.system(f'pactl set-sink-equalizer-sink-input 0 {i} {gain_norm}')
            except Exception as eq_error:
                logger.debug(f"Couldn't use equalizer-sink: {eq_error}")
                # Fall back to alternate methods if available
            
            logger.info(f"Applied EQ settings: {self.eq_gains}")
            
        except Exception as e:
            logger.error(f"Error applying EQ settings: {e}")
    
    def apply_volume_setting(self):
        """Apply volume setting to default sink"""
        try:
            with self.pulse as p:
                # Get default sink
                sink_name = p.server_info().default_sink_name
                sink = p.get_sink_by_name(sink_name)
                
                # Set volume (PulseAudio uses 0-65536 range)
                volume = int(self.volume * 65536)
                p.volume_set(sink, pulsectl.PulseVolumeInfo([volume, volume]))
                
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
    
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
                time.sleep(0.1)  # 10Hz update rate
        except Exception as e:
            logger.error(f"Control loop error: {e}")
            self.running = False
    
    def stop(self):
        """Stop control system"""
        self.running = False
        
        if hasattr(self, 'control_thread'):
            self.control_thread.join(timeout=1.0)
        
        if hasattr(self, 'pulse'):
            self.pulse.close()
        
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