"""ADS1299 serial command and data frame helpers."""

import struct


CMD_CONN_STATE = 0x03
CMD_START = 0x04
CMD_SAMPLE_PARAMS = 0x05
CMD_RAW_DATA = 0x06

SAMPLE_RATES = (250, 500, 1000, 2000)
RANGES = {
    "±4.5V": 1,
    "±2.2V": 2,
    "±1.1V": 4,
    "±750mV": 6,
    "±560mV": 8,
    "±375mV": 12,
    "±186mV": 24,
}


def pack_command(command, payload=b""):
    """Build a host-to-device command frame."""
    payload = bytes(payload)
    header = bytes((0xA5,)) + struct.pack("<H", len(payload) + 8)
    header += bytes((0x00, command & 0x7F))
    header_xor = 0
    for value in header[1:]:
        header_xor ^= value
    payload_xor = 0
    for value in payload:
        payload_xor ^= value
    return header + bytes((header_xor,)) + payload + bytes((payload_xor, 0x5A))


def connection_status_command(state=0x02):
    return pack_command(CMD_CONN_STATE, bytes((state,)))


def start_command():
    return pack_command(CMD_START, b"\x01")


def stop_command():
    return pack_command(CMD_START, b"\x00")


def sample_params_command(sample_rate=500, signal_range="±4.5V", channels=0xFF):
    if sample_rate not in SAMPLE_RATES:
        raise ValueError(f"sample_rate must be one of {SAMPLE_RATES}")
    if signal_range not in RANGES:
        raise ValueError(f"range must be one of {tuple(RANGES)}")
    if not 1 <= channels <= 0xFF:
        raise ValueError("channels must be an integer from 1 to 255")
    payload = struct.pack("<HBBB", sample_rate,
                          RANGES[signal_range], channels, 0)
    return pack_command(CMD_SAMPLE_PARAMS, payload)


class Ads1299FrameParser:
    """Incrementally decode device frames into batches of eight-channel samples."""

    def __init__(self):
        self._buffer = bytearray()
        self.sample_rate = 500
        self.connection_state = 0

    def feed(self, chunk):
        self._buffer.extend(chunk)
        decoded = []

        while len(self._buffer) >= 6:
            if self._buffer[0] != 0xAA:
                del self._buffer[0]
                continue

            frame_length = struct.unpack_from("<H", self._buffer, 1)[0]
            if frame_length < 8:
                del self._buffer[0]
                continue
            if len(self._buffer) < 6:
                break

            header_xor = 0
            for value in self._buffer[1:5]:
                header_xor ^= value
            if self._buffer[5] != header_xor:
                del self._buffer[0]
                continue
            if len(self._buffer) < frame_length:
                break
            if self._buffer[frame_length - 1] != 0x55:
                del self._buffer[0]
                continue

            frame = bytes(self._buffer[:frame_length])
            del self._buffer[:frame_length]
            frame_type = frame[4] & 0x7F

            if frame_type == CMD_CONN_STATE and len(frame) > 6:
                self.connection_state = frame[6]
            elif frame_type == CMD_SAMPLE_PARAMS and len(frame) >= 8:
                self.sample_rate = struct.unpack_from("<H", frame, 6)[0]
            elif frame_type == CMD_RAW_DATA:
                payload = frame[6:-2]
                if len(payload) % 32:
                    continue
                values = struct.unpack(f"<{len(payload) // 4}f", payload)
                samples = [list(values[i:i + 8])
                           for i in range(0, len(values), 8)]
                if samples:
                    decoded.append(samples)

        return decoded
