import spidev
import time
from subprocess import call

# Initialize SPI with more explicit error handling
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1000000
    spi.mode = 0
except Exception as e:
    print(f"Error initializing SPI: {e}")
    print("Please check if SPI is enabled and you have the correct permissions")
    exit(1)

# EQ frequency bands (in Hz)
BANDS = [60, 170, 350, 1000, 3500, 10000, 15000]

def read_adc(channel):
    """Read value from MCP3008 ADC channel"""
    if channel > 7 or channel < 0:
        return -1
    
    # Start bit, single-ended, channel number
    r = spi.xfer2([1, (8 + channel) << 4, 0])
    adc_val = ((r[1] & 3) << 8) + r[2]
    return adc_val

def map_value(value, in_min, in_max, out_min, out_max):
    """Map ADC value to dB range"""
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def set_eq_band(band_idx, gain):
    """Set PulseAudio equalizer band gain"""
    try:
        cmd = f"pacmd load-module module-equalizer-sink"
        call(cmd.split())
        cmd = f"pactl set-sink-equalizer-sink 0 {band_idx} {gain}"
        call(cmd.split())
    except Exception as e:
        print(f"Error setting EQ: {e}")

def main():
    print("Hardware EQ Controller Starting...")
    
    # Initialize equalizer
    try:
        cmd = "pulseaudio --start"
        call(cmd.split())
        cmd = "pactl load-module module-equalizer-sink"
        call(cmd.split())
        cmd = "pactl load-module module-dbus-protocol"
        call(cmd.split())
    except Exception as e:
        print(f"Error initializing equalizer: {e}")
    
    try:
        while True:
            # Read each potentiometer and update EQ
            for i in range(len(BANDS)):
                adc_value = read_adc(i)
                gain = map_value(adc_value, 0, 1023, -12, 12)
                set_eq_band(i, gain)
                print(f"Band {BANDS[i]}Hz: {gain:.1f}dB")
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        spi.close()

if __name__ == "__main__":
    main()