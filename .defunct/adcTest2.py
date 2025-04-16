#!/usr/bin/python3

import time
import board
import busio
import digitalio
from adafruit_mcp3xxx.analog_in import AnalogIn
from adafruit_mcp3xxx.mcp3008 import MCP3008

# Create the SPI bus
spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

# Create the CS (chip select)
cs = digitalio.DigitalInOut(board.CE0)

# Create the MCP object
mcp = MCP3008(spi, cs)

# Create analog input channels on the MCP3008
channels = []
for i in range(8):
    channels.append(AnalogIn(mcp, i))

print('Reading MCP3008 values using Adafruit library, press Ctrl-C to quit...')
print('-' * 57)

try:
    while True:
        # Display header
        print('| Chan | Raw  | Voltage | Bar Graph')
        print('-' * 57)
        
        # Read all channels
        for i, chan in enumerate(channels):
            # Get raw ADC value
            raw = chan.value
            
            # Calculate voltage (assumes 3.3V reference)
            volts = chan.voltage
            
            # Create a simple bar graph
            bar_length = int(volts * 20)  # Scale to 20 characters
            bar = '#' * bar_length
            
            # Print the results
            print(f'| {i:4} | {raw:4} | {volts:.2f}V | {bar}')
        
        print('-' * 57)
        time.sleep(0.5)
        
except KeyboardInterrupt:
    print("\nTest terminated by user")