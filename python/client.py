"""Command-line client for the ADS1299 JSON Lines TCP service."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys


def send_request(connection, action, **values):
    request = {"action": action, **values}
    connection.sendall(
        (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))


def read_message(reader):
    line = reader.readline()
    if not line:
        raise ConnectionError("server closed the connection")
    return json.loads(line.decode("utf-8"))


def print_message(message):
    print(json.dumps(message, ensure_ascii=False, indent=2))


def tcp_request(host, port, request):
    with socket.create_connection((host, port), timeout=5) as connection:
        connection.sendall(
            (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
        reader = connection.makefile("rb")
        response = read_message(reader)
    if not response.get("ok"):
        raise RuntimeError(response.get("error", "TCP service request failed"))
    return response.get("result")


def make_web_handler(backend_host, backend_port):
    class WebHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                page = Path(__file__).parent / "web" / "index.html"
                body = page.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path in ("/api/ports", "/api/status"):
                action = self.path.rsplit("/", 1)[-1]
                try:
                    result = tcp_request(
                        backend_host, backend_port, {"action": action})
                    self.send_json(200, {"ok": True, "result": result})
                except (OSError, RuntimeError) as exc:
                    self.send_json(502, {"ok": False, "error": str(exc)})
                return

            if self.path == "/events":
                self.stream_events()
                return

            self.send_error(404)

        def do_POST(self):
            if self.path != "/api/command":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError(
                        "request body must be between 1 byte and 64 KiB")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("request must be a JSON object")
                result = tcp_request(backend_host, backend_port, request)
                self.send_json(200, {"ok": True, "result": result})
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})

        def stream_events(self):
            try:
                connection = socket.create_connection(
                    (backend_host, backend_port), timeout=5)
                connection.sendall(b'{"action":"subscribe"}\n')
                reader = connection.makefile("rb")
                response = read_message(reader)
                if not response.get("ok"):
                    connection.close()
                    self.send_json(502, {
                        "ok": False,
                        "error": response.get("error", "subscription failed"),
                    })
                    return
                connection.settimeout(15)
            except (OSError, ConnectionError, json.JSONDecodeError) as exc:
                self.send_json(502, {"ok": False, "error": str(exc)})
                return

            self.send_response(200)
            self.send_header(
                "Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                while True:
                    try:
                        message = read_message(reader)
                    except socket.timeout:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        continue
                    if message.get("type") == "data":
                        event = json.dumps(
                            message, ensure_ascii=False, separators=(",", ":"))
                        self.wfile.write(f"data: {event}\n\n".encode("utf-8"))
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                connection.close()

        def log_message(self, format_string, *args):
            print(f"web: {args[0]}", flush=True)

    return WebHandler


def main():
    parser = argparse.ArgumentParser(description="ADS1299 TCP client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "ports", help="list serial ports visible to the server")
    connect_parser = commands.add_parser(
        "connect", help="connect the server to a serial port")
    connect_parser.add_argument("port_name")
    configure_parser = commands.add_parser(
        "configure", help="set sampling parameters")
    configure_parser.add_argument(
        "--sample-rate", type=int, choices=(250, 500, 1000, 2000), default=500)
    configure_parser.add_argument(
        "--range", dest="signal_range", default="±4.5V")
    configure_parser.add_argument(
        "--channels", type=lambda value: int(value, 0), default=0xFF)
    for action in ("start", "stop", "disconnect", "status"):
        commands.add_parser(action)
    stream_parser = commands.add_parser(
        "stream", help="subscribe to live samples")
    stream_parser.add_argument(
        "--start", action="store_true", help="start acquisition after subscribing")
    stream_parser.add_argument("--stop-on-exit", action="store_true")
    web_parser = commands.add_parser(
        "web", help="serve the browser-based control panel and live waveform")
    web_parser.add_argument("--http-host", default="127.0.0.1")
    web_parser.add_argument("--http-port", type=int, default=8080)
    web_parser.add_argument("--backend-host", default=None)
    web_parser.add_argument("--backend-port", type=int, default=None)
    args = parser.parse_args()

    if args.command == "web":
        backend_host = args.backend_host or args.host
        backend_port = args.backend_port or args.port
        server = ThreadingHTTPServer(
            (args.http_host, args.http_port),
            make_web_handler(backend_host, backend_port),
        )
        display_host = "127.0.0.1" if args.http_host == "0.0.0.0" else args.http_host
        print(
            f"ADS1299 web control: http://{display_host}:{args.http_port} "
            f"(TCP backend {backend_host}:{backend_port})",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopping web control server", flush=True)
        finally:
            server.server_close()
        return 0

    request_values = {}
    action = args.command
    if action == "connect":
        request_values["port"] = args.port_name
    elif action == "configure":
        request_values = {
            "sample_rate": args.sample_rate,
            "range": args.signal_range,
            "channels": args.channels,
        }

    try:
        with socket.create_connection((args.host, args.port), timeout=5) as connection:
            connection.settimeout(None)
            reader = connection.makefile("rb")
            if action != "stream":
                send_request(connection, action, **request_values)
                response = read_message(reader)
                print_message(response)
                return 0 if response.get("ok") else 1

            send_request(connection, "subscribe")
            print_message(read_message(reader))
            if args.start:
                send_request(connection, "start")
                print_message(read_message(reader))
            try:
                while True:
                    print_message(read_message(reader))
            except KeyboardInterrupt:
                if args.stop_on_exit:
                    send_request(connection, "stop")
                    print_message(read_message(reader))
    except (OSError, ConnectionError, json.JSONDecodeError) as exc:
        print(f"client error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
