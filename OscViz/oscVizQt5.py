import sys
import pyaudio
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import pyqtgraph as pg

class AudioStreamThread(QThread):
    data_signal = pyqtSignal(np.ndarray)

    def __init__(self, device_index, chunk=4096, rate=44100):
        super().__init__()
        self.device_index = device_index
        self.CHUNK = chunk
        self.RATE = rate
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.running = True
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.CHUNK
        )

    def run(self):
        while self.running:
            try:
                data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)
                self.data_signal.emit(audio_data)
            except Exception as e:
                print(f"Error in audio thread: {e}")

    def stop(self):
        self.running = False
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

class MicrophoneOscilloscope(QMainWindow):
    def __init__(self):
        super().__init__()
        # Remove window borders
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.p = pyaudio.PyAudio()
        self.device_index = None
        self.audio_thread = None

        self.initUI()
        # Auto-connect to pulse device
        self.find_and_connect_pulse()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        # Remove margins to use full space
        layout.setContentsMargins(0, 0, 0, 0)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("black")
        self.plot_widget.setYRange(-10000, 10000)
        self.plot_widget.setXRange(0, 4096)
        self.plot_widget.showGrid(x=False, y=False)
        self.plot_widget.hideAxis("bottom")
        self.plot_widget.hideAxis("left")
        self.signal_curve = self.plot_widget.plot(pen=pg.mkPen(color="lime", width=1))
        layout.addWidget(self.plot_widget)

        main_widget.setLayout(layout)

    def get_audio_devices(self):
        devices = []
        info = {}

        for i in range(self.p.get_device_count()):
            dev_info = self.p.get_device_info_by_index(i)
            if dev_info['maxInputChannels'] > 0:
                name = dev_info['name']
                devices.append(name)
                info[name] = i
                # Print available devices for debugging
                print(f"Device {i}: {name}")

        return {'names': devices, 'indices': info}

    def find_and_connect_pulse(self):
        devices = self.get_audio_devices()
        
        # Look for pulse device
        pulse_index = None
        for name, idx in devices['indices'].items():
            if 'pulse' in name.lower() or 'iqaudio' in name.lower():
                pulse_index = idx
                print(f"Found pulse audio device: {name}")
                break
        
        # If no pulse device found, use first available device
        if pulse_index is None and devices['names']:
            pulse_index = devices['indices'][devices['names'][0]]
            print(f"No pulse device found, using: {devices['names'][0]}")
        
        if pulse_index is not None:
            self.device_index = pulse_index
            self.connect_to_device(self.device_index)
        else:
            print("No audio input devices found!")

    def connect_to_device(self, device_index):
        if self.audio_thread:
            self.audio_thread.stop()
            
        self.audio_thread = AudioStreamThread(device_index=device_index)
        self.audio_thread.data_signal.connect(self.update_plot)
        self.audio_thread.start()

    def update_plot(self, audio_data):
        self.signal_curve.setData(audio_data)

    def keyPressEvent(self, event):
        # Close on ESC key
        if event.key() == Qt.Key_Escape:
            self.close_app()
        super().keyPressEvent(event)

    def close_app(self):
        if self.audio_thread:
            self.audio_thread.stop()
        self.p.terminate()
        self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MicrophoneOscilloscope()
    # Position on second display
    window.move(1024, 0)
    window.showFullScreen()
    sys.exit(app.exec_())