from gpiozero import MCP3008
from time import sleep

# Create an object called pot that refers to MCP3008 channel 0
pot = MCP3008(0)

# Counter for tracking readings
reading_count = 0

print("ADC Reading Test - Press CTRL+C to exit")
print("=====================================")

try:
    while True:
        reading_count += 1
        value = pot.value
        
        # Format the value with better visual representation
        bar_length = int(value * 50)  # Scale to 50 characters for visualization
        bar = '█' * bar_length
        
        # Print current reading with a progress bar
        print(f"Reading #{reading_count}: {value:.6f} [{bar:<50}]")
        
        sleep(0.1)
except KeyboardInterrupt:
    print("\nTest terminated by user")