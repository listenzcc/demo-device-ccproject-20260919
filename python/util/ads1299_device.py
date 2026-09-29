"""Threaded serial device access for an ADS1299 acquisition module."""

import threading
import time

from .ads1299_protocol import (
    Ads1299FrameParser,
    connection_status_command,
    sample_params_command,
    start_command,
    stop_command,
)


class Ads1299Device:
    def __init__(self, on_samples=None):
        self._serial = None
        self._reader = None
        self._stop_event = threading.Event()
        self._write_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._parser = Ads1299FrameParser()
        self._on_samples = on_samples
        self._collecting = False
        self._port = None

    @staticmethod
    def list_ports():
        try:
            from serial.tools import list_ports
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required; install it with: pip install pyserial") from exc
        return [
            {"port": item.device, "description": item.description}
            for item in list_ports.comports()
        ]

    def connect(self, port, baudrate=1000000):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required; install it with: pip install pyserial") from exc

        with self._state_lock:
            if self._serial is not None and self._serial.is_open:
                raise RuntimeError(f"already connected to {self._port}")
            serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            serial_port.setRTS(False)
            serial_port.setDTR(False)
            self._serial = serial_port
            self._port = port
            self._parser = Ads1299FrameParser()
            self._stop_event.clear()
            self._reader = threading.Thread(
                target=self._read_loop, daemon=True)
            self._reader.start()
        return self.status()

    def disconnect(self):
        with self._state_lock:
            serial_port = self._serial
            reader = self._reader
            if serial_port is None:
                return self.status()
            if self._collecting:
                self._write(stop_command())
                self._collecting = False
            self._stop_event.set()
            self._serial = None
            self._reader = None
            self._port = None

        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=1.0)
        if serial_port.is_open:
            serial_port.close()
        return self.status()

    def configure(self, sample_rate=500, signal_range="±4.5V", channels=0xFF):
        self._write(sample_params_command(sample_rate, signal_range, channels))
        return {"sample_rate": sample_rate, "range": signal_range, "channels": channels}

    def start(self):
        self._write(start_command())
        with self._state_lock:
            self._collecting = True
        return self.status()

    def stop(self):
        self._write(stop_command())
        with self._state_lock:
            self._collecting = False
        return self.status()

    def request_connection_status(self):
        self._write(connection_status_command())

    def status(self):
        with self._state_lock:
            connected = self._serial is not None and self._serial.is_open
            return {
                "connected": connected,
                "port": self._port,
                "collecting": self._collecting,
                "sample_rate": self._parser.sample_rate,
                "device_connection_state": self._parser.connection_state,
            }

    def _write(self, payload):
        with self._state_lock:
            serial_port = self._serial
        if serial_port is None or not serial_port.is_open:
            raise RuntimeError("device is not connected")
        with self._write_lock:
            serial_port.write(payload)

    def _read_loop(self):
        while not self._stop_event.is_set():
            with self._state_lock:
                serial_port = self._serial
            if serial_port is None or not serial_port.is_open:
                break
            try:
                available = serial_port.in_waiting
                if not available:
                    self._stop_event.wait(0.005)
                    continue
                batches = self._parser.feed(serial_port.read(available))
                if self._on_samples:
                    for samples in batches:
                        self._on_samples(samples, self._parser.sample_rate)
            except Exception as exc:
                if not self._stop_event.is_set():
                    print(f"Serial read error: {exc}", flush=True)
                    time.sleep(0.01)

    def close(self):
        self.disconnect()
