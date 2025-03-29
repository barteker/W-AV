#!/usr/bin/env python3
import time
import numpy as np
import pulsectl
import spidev
import threading
import scipy.signal as signal
import os
import logging
import traceback
from logging.handlers import RotatingFileHandler

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
SPI_BUS = 0
SPI_DEVICE = 0
ADC_CHANNELS = 8  # 7 for EQ bands + 1 for volume

# EQ bands center frequencies (Hz)
EQ_FREQS = [63, 250, 500, 1000, 2000, 4000, 8000]
Q_FACTOR = 1.414  # Standard Q factor for audio EQ

def setup_pulseaudio_eq():
    """Set up PulseAudio EQ system"""
    try:
        # Create virtual sinks
        os.system('pactl load-module module-null-sink sink_name=pre_eq sink_properties=device.description="Pre-EQ Input"')
        os.system('pactl load-module module-null-sink sink_name=post_eq sink_properties=device.description="Post-EQ Output"')
        
        # Create EQ sink
        os.system('pactl load-module module-ladspa-sink sink_name=eq_sink master=post_eq plugin=mbeq_1197 label=mbeq control="0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0"')
        
        # Connect them with loopback
        os.system('pactl load-module module-loopback source=pre_eq.monitor sink=eq_sink latency_msec=10')
        
        # Set default sink
        os.system('pactl set-default-sink pre_eq')
        
        logger.info("PulseAudio EQ system configured")
        return True
    except Exception as e:
        logger.error(f"Failed to set up PulseAudio EQ: {e}")
        return False

class AudioEQ:
    def __init__(self):
        # Initialize SPI for MCP3008
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_DEVICE)
        self.spi.max_speed_hz = 1000000  # 1MHz
        
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
        """Read from MCP3008 ADC channel (0-7)"""
        if 0 <= channel <= 7:
            try:
                # Correct command format for MCP3008
                # Start bit (1), followed by single-ended mode (1), then channel bits
                cmd = [0x01, (0x08 + channel) << 4, 0]
                r = self.spi.xfer2(cmd)
                
                # Debug the raw response
                logger.debug(f"Raw SPI response channel {channel}: {r}")
                
                # Correct bit extraction from response
                data = ((r[1] & 0x03) << 8) + r[2]
                
                # Additional debug for calculation
                logger.debug(f"Channel {channel} calculation: {r[1]}&0x03={r[1]&0x03}, shifted={(r[1]&0x03)<<8}, r[2]={r[2]}, result={data}")
                
                return data
            except Exception as e:
                logger.error(f"SPI read error on channel {channel}: {e}")
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
        
        # Close SPI
        if hasattr(self, 'spi'):
            self.spi.close()
            
        logger.info("Audio EQ system stopped")

# Run as standalone or import as module
if __name__ == "__main__":
    try:
        logger.info("Starting AudioEQ application")
        
        # Check if SPI device is accessible
        try:
            spi_test = spidev.SpiDev()
            spi_test.open(SPI_BUS, SPI_DEVICE)
            spi_test.close()
            logger.info("SPI device is accessible")
        except Exception as e:
            logger.error(f"SPI device access error: {e}")
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