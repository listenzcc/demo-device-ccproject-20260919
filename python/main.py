"""ADS1299 acquisition TCP server using newline-delimited JSON."""

import argparse
import json
import socketserver
import threading
import time

from util.ads1299_device import Ads1299Device


class ClientRegistry:
    def __init__(self):
        self._clients = set()
        self._lock = threading.Lock()

    def add(self, handler):
        with self._lock:
            self._clients.add(handler)

    def remove(self, handler):
        with self._lock:
            self._clients.discard(handler)

    def publish(self, samples, sample_rate):
        message = {
            "type": "data",
            "timestamp": time.time(),
            "sample_rate": sample_rate,
            "channels": 8,
            "samples": samples,
        }
        with self._lock:
            clients = tuple(self._clients)
        for handler in clients:
            try:
                handler.send_message(message)
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.remove(handler)


class AcquisitionTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, device, clients):
        self.device = device
        self.clients = clients
        super().__init__(address, AcquisitionRequestHandler)


class AcquisitionRequestHandler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self._send_lock = threading.Lock()
        self._subscribed = False

    def handle(self):
        for raw_line in self.rfile:
            if len(raw_line) > 1024 * 1024:
                self.send_response(None, error="request exceeds 1 MiB")
                break
            try:
                request = json.loads(raw_line)
                if not isinstance(request, dict):
                    raise ValueError("each request must be a JSON object")
                self.handle_request(request)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                self.send_response(None, error=str(exc))

    def handle_request(self, request):
        request_id = request.get("id")
        action = request.get("action")
        device = self.server.device
        try:
            if action == "ports":
                result = device.list_ports()
            elif action == "connect":
                result = device.connect(request.get("port", ""))
            elif action == "configure":
                result = device.configure(
                    sample_rate=request.get("sample_rate", 500),
                    signal_range=request.get("range", "±4.5V"),
                    channels=request.get("channels", 0xFF),
                )
            elif action == "start":
                result = device.start()
            elif action == "stop":
                result = device.stop()
            elif action == "disconnect":
                result = device.disconnect()
            elif action == "status":
                result = device.status()
            elif action == "subscribe":
                self.server.clients.add(self)
                self._subscribed = True
                result = {"subscribed": True}
            elif action == "unsubscribe":
                self.server.clients.remove(self)
                self._subscribed = False
                result = {"subscribed": False}
            else:
                raise ValueError(
                    "action must be one of: ports, connect, configure, start, stop, disconnect, status, subscribe, unsubscribe")
            self.send_response(request_id, result=result)
        except Exception as exc:
            self.send_response(request_id, error=str(exc))

    def send_response(self, request_id, result=None, error=None):
        message = {"type": "response", "id": request_id, "ok": error is None}
        if error is None:
            message["result"] = result
        else:
            message["error"] = error
        self.send_message(message)

    def send_message(self, message):
        encoded = (json.dumps(message, separators=(",", ":"),
                   ensure_ascii=False) + "\n").encode("utf-8")
        with self._send_lock:
            self.wfile.write(encoded)
            self.wfile.flush()

    def finish(self):
        if self._subscribed:
            self.server.clients.remove(self)
        super().finish()


def main():
    parser = argparse.ArgumentParser(
        description="ADS1299 serial-to-TCP acquisition server")
    parser.add_argument("--host", default="0.0.0.0",
                        help="TCP bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765,
                        help="TCP port (default: 8765)")
    args = parser.parse_args()

    clients = ClientRegistry()
    device = Ads1299Device(on_samples=clients.publish)
    server = AcquisitionTCPServer((args.host, args.port), device, clients)
    print(
        f"ADS1299 TCP server listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping ADS1299 TCP server", flush=True)
    finally:
        server.server_close()
        device.close()


if __name__ == "__main__":
    main()
