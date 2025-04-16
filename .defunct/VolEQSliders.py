#!/usr/bin/env python3
import time
import numpy as np
import pulsectl
import threading
import scipy.signal as signal
import os
import logging
import traceback
from logging.handlers import RotatingFileHandler

# Add Adafruit CircuitPython imports to replace spidev
import board
import busio
import digitalio
from adafruit_mcp3xxx.analog_in import AnalogIn
from adafruit_mcp3xxx.mcp3008 import MCP3008

# Configure logging
log_handler = RotatingFileHandler(
    '/home/wave/eq_control.log',
    maxBytes=1024*1024,
    backupCount=3
)
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG for more details
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)
logger = logging.getLogger(__name__)

# Audio configuration - smaller periods for lower latency
SAMPLE_RATE = 44100
PERIOD_SIZE = 256  # Much smaller for low latency (vs 1024)
BUFFER_SIZE = 512  # Smaller buffer (vs 4096)
CHANNELS = 2
FORMAT = 'float32'  # Changed to match PulseAudio

# MCP3008 configuration
ADC_CHANNELS = 8  # 7 for EQ bands + 1 for volume

# EQ bands center frequencies (Hz)
EQ_FREQS = [63, 250, 500, 1000, 2000, 4000, 8000]
Q_FACTOR = 1.414  # Standard Q factor for audio EQ

def setup_pulseaudio_eq():
    """Set up PulseAudio EQ system"""
    try:
        # Create virtual sinks with return code checking
        pre_eq_result = os.system('pactl load-module module-null-sink sink_name=pre_eq sink_properties=device.description="Pre-EQ Input"')
        if pre_eq_result != 0:
            logger.error(f"Failed to create pre_eq sink, return code: {pre_eq_result}")
            return False
            
        post_eq_result = os.system('pactl load-module module-null-sink sink_name=post_eq sink_properties=device.description="Post-EQ Output"')
        if post_eq_result != 0:
            logger.error(f"Failed to create post_eq sink, return code: {post_eq_result}")
            return False
        
        # Give PulseAudio time to create the sinks
        time.sleep(1)
        
        # Create EQ sink
        eq_result = os.system('pactl load-module module-ladspa-sink sink_name=eq_sink master=post_eq plugin=mbeq_1197 label=mbeq control="0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0"')
        if eq_result != 0:
            logger.error(f"Failed to create EQ sink, return code: {eq_result}")
            # Check if LADSPA plugin is installed
            os.system('ls -la /usr/lib/ladspa/')
            return False
            
        # Give PulseAudio time to create the sink
        time.sleep(1)
        
        # Connect them with loopback
        loopback_result = os.system('pactl load-module module-loopback source=pre_eq.monitor sink=eq_sink latency_msec=10')
        if loopback_result != 0:
            logger.error(f"Failed to create loopback, return code: {loopback_result}")
            return False
        
        # Verify sinks exist before returning success
        with pulsectl.Pulse('eq-setup-verification') as pulse:
            sources = [s.name for s in pulse.source_list()]
            sinks = [s.name for s in pulse.sink_list()]
            
            if 'pre_eq.monitor' not in sources:
                logger.error("pre_eq.monitor source was not created")
                return False
                
            if 'post_eq' not in sinks:
                logger.error("post_eq sink was not created")
                return False
                
            logger.info(f"Verified PulseAudio sinks and sources: {sinks}, {sources}")
        
        # Set default sink
        os.system('pactl set-default-sink pre_eq')
        
        logger.info("PulseAudio EQ system configured")
        return True
    except Exception as e:
        logger.error(f"Failed to set up PulseAudio EQ: {e}")
        return False

class AudioEQ:
    def __init__(self):
        # Initialize Adafruit MCP3008 - replaces SPI setup
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
            
            logger.info("MCP3008 initialized using Adafruit CircuitPython library")
        except Exception as e:
            logger.error(f"Failed to initialize MCP3008: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Thread synchronization
        self.lock = threading.Lock()
        self.running = True
        
        # EQ state
        self.eq_gains = [0.0] * 7  # Initial EQ gains in dB
        self.volume = 1.0  # 0.0 to 1.0
        self.filters = self._create_filters()
        self.filter_states_left = [np.zeros(4) for _ in range(7)]
        self.filter_states_right = [np.zeros(4) for _ in range(7)]
        
        # Setup PulseAudio devices
        if not self.setup_pulse_devices():
            raise Exception("Failed to initialize PulseAudio devices")
        
        logger.info("Initializing Audio EQ system with PulseAudio")
    
    def setup_pulse_devices(self):
        try:
            self.pulse = pulsectl.Pulse('eq-processor')
            
            # Set up monitor source from pre_eq sink
            self.source_name = 'pre_eq.monitor'
            self.sink_name = 'post_eq'
            
            logger.info(f"Using PulseAudio: source={self.source_name}, sink={self.sink_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to setup PulseAudio: {e}")
            return False
    
    def _create_filters(self):
        """Create bandpass filters for each EQ band"""
        filters = []
        for freq in EQ_FREQS:
            nyquist = SAMPLE_RATE / 2
            normalized_freq = freq / nyquist
            # Start with no gain (0 dB) - fix parameter order
            b, a = signal.iirpeak(normalized_freq, Q_FACTOR, SAMPLE_RATE)  # Remove fs= keyword
            filters.append((b, a))
        return filters
    
    def _update_filter(self, index, gain_db):
        """Update filter coefficients for the given band and gain"""
        freq = EQ_FREQS[index]
        nyquist = SAMPLE_RATE / 2
        normalized_freq = freq / nyquist
        
        # Update filter coefficients - fix parameter order
        b, a = signal.iirpeak(normalized_freq, Q_FACTOR, SAMPLE_RATE)  # Remove fs= keyword
        self.filters[index] = (b, a)
        
        logger.debug(f"Updated EQ band {index} (center: {freq}Hz) gain to {gain_db}dB")
    
    def read_adc(self, channel):
        """Read from MCP3008 ADC channel (0-7) using Adafruit library"""
        if 0 <= channel < len(self.adc_channels):
            try:
                # Get raw value from the Adafruit library
                raw_value = self.adc_channels[channel].value
                
                # Scale from 16-bit value (0-65535) to 10-bit value (0-1023)
                scaled_value = int(raw_value * 1023 / 65535)
                
                # Debug logging
                logger.debug(f"Channel {channel} raw: {raw_value}, scaled: {scaled_value}, voltage: {self.adc_channels[channel].voltage:.2f}V")
                
                return scaled_value
            except Exception as e:
                logger.error(f"ADC read error on channel {channel}: {e}")
                return 0
        return 0
    
    def update_controls(self):
        """Read potentiometer values and update EQ settings"""
        try:
            # Read all raw values first for debugging
            raw_values = [self.read_adc(i) for i in range(ADC_CHANNELS)]
            logger.debug(f"Raw ADC values: {raw_values}")
            
            # Read EQ bands (channels 0-6)
            for i in range(7):
                raw_value = raw_values[i]
                # Convert from 0-1023 to -12dB to +12dB
                gain_db = (raw_value / 1023.0) * 24.0 - 12.0
                
                # Update if changed significantly
                if abs(gain_db - self.eq_gains[i]) > 0.5:
                    self.eq_gains[i] = gain_db
                    self._update_filter(i, gain_db)
            
            # Read volume (channel 7)
            raw_volume = raw_values[7]
            new_volume = raw_volume / 1023.0
            
            # Update volume if changed significantly
            if abs(new_volume - self.volume) > 0.02:
                self.volume = new_volume
                logger.debug(f"Volume updated to {self.volume*100:.1f}%")
                
        except Exception as e:
            logger.error(f"Error reading controls: {e}")
            logger.error(traceback.format_exc())
    
    def update_eq_filters(self):
        # Convert slider values to string format for LADSPA
        eq_params = ",".join([f"{g:.1f}" for g in self.eq_gains])
        
        # Run pactl command to update filter
        os.system(f'pactl set-sink-input-volume eq_sink "{eq_params}"')
    
    def update_eq_settings(self):
        """Apply EQ settings to PulseAudio LADSPA EQ"""
        try:
            # Format EQ values into a string for LADSPA (15 bands)
            # Map 7 bands to 15 by duplicating some values
            bands_15 = []
            
            # Convert from dB to linear gain (0.0-2.0 range approximately)
            for i, gain_db in enumerate(self.eq_gains):
                # Example mapping - adjust based on your preference:
                if i == 0:  # 63Hz (first band)
                    bands_15.extend([gain_db, gain_db])  # Map to bands 1-2
                elif i == 1:  # 250Hz (second band)
                    bands_15.extend([gain_db, gain_db, gain_db])  # Map to bands 3-5
                elif i == 2:  # 500Hz
                    bands_15.extend([gain_db, gain_db])  # Map to bands 6-7
                elif i == 3:  # 1kHz
                    bands_15.extend([gain_db, gain_db])  # Map to bands 8-9
                elif i == 4:  # 2kHz
                    bands_15.extend([gain_db, gain_db])  # Map to bands 10-11
                elif i == 5:  # 4kHz
                    bands_15.extend([gain_db, gain_db])  # Map to bands 12-13
                elif i == 6:  # 8kHz
                    bands_15.extend([gain_db, gain_db])  # Map to bands 14-15
            
            # Format for LADSPA
            eq_values = ",".join([f"{g:.1f}" for g in bands_15])
            
            # Apply to LADSPA EQ
            cmd = f'pactl set-sink-input-volume eq_sink "{eq_values}"'
            logger.debug(f"EQ command: {cmd}")
            os.system(cmd)
            
        except Exception as e:
            logger.error(f"Error updating EQ settings: {e}")
    
    def process_audio(self, in_data):
        """Apply EQ and volume to audio data"""
        # Convert bytes to numpy array
        audio_data = np.frombuffer(in_data, dtype=np.float32)
        
        # Process each channel separately
        if CHANNELS == 2:
            # Process left channel
            left = audio_data[0::2].copy()
            for i in range(7):
                b, a = self.filters[i]
                left, self.filter_states_left[i] = signal.lfilter(b, a, left, zi=self.filter_states_left[i])
            
            # Process right channel (if stereo)
            right = audio_data[1::2].copy()
            for i in range(7):
                b, a = self.filters[i]
                right, self.filter_states_right[i] = signal.lfilter(b, a, right, zi=self.filter_states_right[i])
            
            # Interleave channels back together
            for i in range(len(left)):
                audio_data[i*2] = left[i]
                audio_data[i*2+1] = right[i]
        else:
            # Mono processing
            for i in range(7):
                b, a = self.filters[i]
                audio_data, self.filter_states_left[i] = signal.lfilter(b, a, audio_data, zi=self.filter_states_left[i])
        
        # Apply volume
        audio_data = audio_data * self.volume
        
        # Clip to prevent distortion
        np.clip(audio_data, -1.0, 1.0, out=audio_data)
        
        return audio_data.tobytes()
    
    def _audio_processing_loop(self):
        """Main audio processing loop - lower latency than callback"""
        try:
            # Check if we're using PulseAudio or ALSA
            if hasattr(self, 'pulse') and hasattr(self, 'source_name') and hasattr(self, 'sink_name'):
                # PulseAudio processing
                logger.info("Starting PulseAudio processing loop")
                self._pulseaudio_processing_loop()
            elif hasattr(self, 'input_device') and hasattr(self, 'output_device'):
                # ALSA processing
                logger.info("Starting ALSA processing loop")
                self._alsa_processing_loop()
            else:
                raise Exception("No audio processing method available")
        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            self.running = False

    def _pulseaudio_processing_loop(self):
        """Audio processing loop for PulseAudio using module-loopback"""
        try:
            # Create a module-loopback
            with self.pulse as pulse:
                # Check if our source and sink exist
                source_info = next((s for s in pulse.source_list() 
                                   if s.name == self.source_name), None)
                sink_info = next((s for s in pulse.sink_list() 
                                 if s.name == self.sink_name), None)
                
                if not source_info or not sink_info:
                    raise Exception(f"Source or sink not found: {self.source_name}, {self.sink_name}")
                
                # Create a loopback module
                module_id = pulse.module_load('module-loopback',
                    f"source={self.source_name} sink={self.sink_name} latency_msec=10")
                
                logger.info(f"PulseAudio loopback created: {module_id}")
                
                # Keep the loopback alive
                while self.running:
                    # Update the loopback parameters based on EQ settings
                    # This is a simplified approach - the real EQ is done in PulseAudio
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"PulseAudio processing error: {e}")
            logger.error(traceback.format_exc())
            raise

    def _alsa_processing_loop(self):
        """Original ALSA audio processing loop"""
        try:
            while self.running:
                # Read from input
                length, data = self.input_device.read()
                
                if length > 0:
                    # Process audio
                    processed_data = self.process_audio(data)
                    
                    # Write to output
                    self.output_device.write(processed_data)
                else:
                    # No data, sleep a tiny amount to prevent CPU thrashing
                    time.sleep(0.001)
                    
        except Exception as e:
            logger.error(f"ALSA processing error: {e}")
            raise

    def start(self):
        """Start audio processing and control threads"""
        try:
            # Start audio processing thread
            self.audio_thread = threading.Thread(target=self._audio_processing_loop)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            # Start control update thread
            self.control_thread = threading.Thread(target=self._control_loop)
            self.control_thread.daemon = True
            self.control_thread.start()
            
            logger.info("Audio EQ system started")
        except Exception as e:
            logger.error(f"Failed to start audio threads: {e}")
    
    def _control_loop(self):
        """Background thread for reading potentiometers"""
        try:
            while self.running:
                # Check if system is in sleep mode
                if os.path.exists("/tmp/wav_sleep_mode"):
                    # Reduce update frequency in sleep mode to save power
                    time.sleep(1.0)
                    continue
                
                # Normal operation
                self.update_controls()
                time.sleep(0.05)  # 20Hz update rate
        except Exception as e:
            logger.error(f"Control loop error: {e}")
    
    def stop(self):
        """Stop audio processing"""
        self.running = False
        
        # Wait for threads to exit
        if hasattr(self, 'audio_thread') and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.0)
            
        if hasattr(self, 'control_thread') and self.control_thread.is_alive():
            self.control_thread.join(timeout=1.0)
        
        # No need to close SPI specifically with Adafruit library
        logger.info("Audio EQ system stopped")

# Run as standalone or import as module
if __name__ == "__main__":
    try:
        logger.info("Starting AudioEQ application")
        
        # Check if MCP3008 ADC is accessible
        try:
            # Test ADC accessibility with Adafruit library
            spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            cs = digitalio.DigitalInOut(board.CE0)
            mcp = MCP3008(spi, cs)
            test_channel = AnalogIn(mcp, 0)
            logger.info(f"MCP3008 is accessible, channel 0 value: {test_channel.value}, voltage: {test_channel.voltage:.2f}V")
            # No need to explicitly close
        except Exception as e:
            logger.error(f"MCP3008 access error: {e}")
            logger.error(traceback.format_exc())
        
        # Check if PulseAudio is available
        try:
            pulse = pulsectl.Pulse('eq-processor')
            logger.info("PulseAudio is accessible")
            pulse.close()
        except Exception as e:
            logger.error(f"PulseAudio access error: {e}")
            logger.error(traceback.format_exc())
        
        # Set up PulseAudio EQ system
        setup_pulseaudio_eq()
        
        eq = AudioEQ()
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