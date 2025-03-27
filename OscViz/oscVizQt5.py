import sys
import pyaudio
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QComboBox, QPushButton, QHBoxLayout
from PyQt5.QtCore import QThread, pyqtSignal
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
        self.setWindowTitle("Bruh")
        self.setGeometry(100, 100, 900, 500)

        self.p = pyaudio.PyAudio()
        self.device_index = None
        self.audio_thread = None

        self.initUI()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()

        device_layout = QHBoxLayout()
        self.device_selector = QComboBox()
        self.devices = self.get_audio_devices()
        self.device_selector.addItems(self.devices['names'])
        device_layout.addWidget(self.device_selector)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_device)
        device_layout.addWidget(self.connect_button)

        layout.addLayout(device_layout)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("black")
        self.plot_widget.setYRange(-10000, 10000)
        self.plot_widget.setXRange(0, 4096)
        self.plot_widget.showGrid(x=False, y=False)
        self.plot_widget.hideAxis("bottom")
        self.plot_widget.hideAxis("left")
        self.signal_curve = self.plot_widget.plot(pen=pg.mkPen(color="lime", width=1))
        layout.addWidget(self.plot_widget)

        control_layout = QHBoxLayout()

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        control_layout.addWidget(self.pause_button)

        self.exit_button = QPushButton("Exit")
        self.exit_button.clicked.connect(self.close_app)
        control_layout.addWidget(self.exit_button)

        layout.addLayout(control_layout)
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

        return {'names': devices, 'indices': info}

    def connect_device(self):
        if self.audio_thread:
            self.audio_thread.stop()

        device_name = self.device_selector.currentText()
        self.device_index = self.devices['indices'].get(device_name)

        if self.device_index is not None:
            self.audio_thread = AudioStreamThread(device_index=self.device_index)
            self.audio_thread.data_signal.connect(self.update_plot)
            self.audio_thread.start()

    def update_plot(self, audio_data):
        self.signal_curve.setData(audio_data)

    def toggle_pause(self):
        if self.audio_thread and self.audio_thread.isRunning():
            self.audio_thread.stop()
            self.audio_thread = None
            self.pause_button.setText("Resume")
        else:
            self.connect_device()
            self.pause_button.setText("Pause")

    def close_app(self):
        if self.audio_thread:
            self.audio_thread.stop()
        self.p.terminate()
        self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MicrophoneOscilloscope()
    window.move(1024, 0)
    window.showFullScreen()
#     window.show()
    sys.exit(app.exec_())