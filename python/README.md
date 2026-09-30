# ADS1299 TCP interface

Install the server dependency with `python -m pip install -r requirements.txt`, then run the serial-to-TCP service from this directory with `./main.ps1`. The server defaults to `0.0.0.0:8765`; pass `-HostAddress` and `-Port` to change the bind address and port. The hardware serial connection uses 1,000,000 baud.

## Wire protocol

TCP uses UTF-8 JSON Lines: each request and each response is one JSON object followed by `\n`. Requests use `action`; an optional `id` is copied to the corresponding response. Successful replies are `{"type":"response","id":...,"ok":true,"result":...}`; failures set `ok` to `false` and include `error`.

Actions:

| Action                      | Fields                             | Purpose                                                                        |
| --------------------------- | ---------------------------------- | ------------------------------------------------------------------------------ |
| `ports`                     | none                               | List serial ports available on the server                                      |
| `connect`                   | `port`                             | Open the ADS1299 serial port                                                   |
| `configure`                 | `sample_rate`, `range`, `channels` | Configure 250/500/1000/2000 SPS, supported input range, and 8-bit channel mask |
| `start` / `stop`            | none                               | Start or stop acquisition                                                      |
| `disconnect`                | none                               | Stop acquisition and close serial port                                         |
| `status`                    | none                               | Get serial, acquisition, and device connection state                           |
| `subscribe` / `unsubscribe` | none                               | Enable or disable live data events for this TCP connection                     |

While subscribed, the server sends asynchronous messages shaped like `{"type":"data","timestamp":...,"sample_rate":500,"channels":8,"samples":[[ch1,...,ch8],...]}`. Samples are decoded from the device's little-endian float32 payload and are not filtered. The server broadcasts each batch to all subscribed clients.

## Client examples

```powershell
python .\client.py ports
python .\client.py connect COM3
python .\client.py configure --sample-rate 500 --range "±4.5V" --channels 0xff
python .\client.py start
python .\client.py stream
python .\client.py stop
python .\client.py disconnect
```

`python .\client.py stream --start` subscribes and starts acquisition on the same TCP connection. Press Ctrl+C to end streaming; add `--stop-on-exit` to stop acquisition on exit.

## Browser control panel

With the TCP acquisition service running, start the browser bridge from this directory:

```powershell
python .\client.py web
```

Open `http://127.0.0.1:8080`. The bridge serves the control panel and forwards commands to the TCP service at `127.0.0.1:8765`; use `--http-host` / `--http-port` to change the browser endpoint or `--backend-host` / `--backend-port` to change the TCP service address. The waveform displays raw device samples with per-channel visual auto-scaling.
