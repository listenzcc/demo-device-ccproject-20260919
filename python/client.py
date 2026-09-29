"""Command-line client for the ADS1299 JSON Lines TCP service."""

import argparse
import json
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
    args = parser.parse_args()

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
