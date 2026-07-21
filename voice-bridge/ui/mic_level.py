from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtMultimedia import QAudioSource, QMediaDevices, QAudioFormat
from PySide6.QtCore import QIODevice
import struct


class MicLevelCapture(QObject):
    mic_level = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_source = None
        self._io_device = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._read_level)
        self._buffer = b""

    def start(self):
        devices = QMediaDevices.audioInputs()
        if not devices:
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        self._audio_source = QAudioSource(devices[0], fmt)
        self._io_device = self._audio_source.start()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        if self._audio_source:
            self._audio_source.stop()
            self._audio_source = None
            self._io_device = None

    def _read_level(self):
        if not self._io_device:
            return
        data = self._io_device.read(960)
        if not data:
            return
        self._buffer += bytes(data)
        window_size = 1920
        if len(self._buffer) < window_size:
            return
        chunk = self._buffer[-window_size:]
        self._buffer = self._buffer[-window_size:]

        samples = struct.unpack("<" + "h" * (len(chunk) // 2), chunk)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        normalized = min(rms / 32768.0, 1.0)
        self.mic_level.emit(normalized)
