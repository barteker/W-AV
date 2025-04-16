#!/usr/bin/env python3
import time
import logging
import traceback
import threading
import board
import busio
import digitalio
from adafruit_mcp3xxx.analog_in import AnalogIn
from adafruit_mcp3xxx.mcp3008 import MCP3008

class ADCController:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
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
            for i in range(8):  # MCP3008 has 8 channels
                self.adc_channels.append(AnalogIn(self.mcp, i))
            
            self.logger.info("MCP3008 initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize MCP3008: {e}")
            self.logger.error(traceback.format_exc())
            raise
        
        # Thread synchronization
        self.running = True
        self.values = [0] * 8  # Store latest values for all channels
        
        # Start the reading thread
        self.start_thread()
    
    def read_adc(self, channel):
        """Read from MCP3008 ADC channel using Adafruit library"""
        if 0 <= channel < len(self.adc_channels):
            try:
                raw_value = self.adc_channels[channel].value
                scaled_value = int(raw_value * 1023 / 65535)  # Scale to 0-1023 range
                return scaled_value
            except Exception as e:
                self.logger.error(f"ADC read error on channel {channel}: {e}")
                return 0
        return 0
    
    def _read_loop(self):
        """Background thread for continuously reading all ADC channels"""
        try:
            while self.running:
                for i in range(8):
                    self.values[i] = self.read_adc(i)
                time.sleep(0.01)  # 100Hz update rate
        except Exception as e:
            self.logger.error(f"Read loop error: {e}")
    
    def start_thread(self):
        """Start the ADC reading thread"""
        try:
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.daemon = True
            self.read_thread.start()
            self.logger.info("ADC controller started")
        except Exception as e:
            self.logger.error(f"Failed to start read thread: {e}")
    
    def get_raw_values(self):
        """Get the latest values from all channels"""
        return self.values.copy()
    
    def start(self):
        """Start the ADC controller if not already running"""
        if not self.running:
            self.running = True
            self.start_thread()
    
    def stop(self):
        """Stop the ADC controller"""
        self.running = False
        if hasattr(self, 'read_thread') and self.read_thread.is_alive():
            self.read_thread.join(timeout=1.0)
        self.logger.info("ADC controller stopped")

# Test the ADC controller if run directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    adc = ADCController()
    
    try:
        while True:
            values = adc.get_raw_values()
            print(f"ADC Values: {values}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        adc.stop() 