# ADS1299 使用手册

本文说明如何启动采集服务、在浏览器中控制 ADS1299，以及在没有连接设备时检查软件。命令默认在 Windows PowerShell 中执行，工作目录为 `python/`。

## 1. 运行结构

系统由两个进程组成：

- `main.py` / `main.ps1`：通过串口连接 ADS1299，并在 TCP `8765` 端口提供控制和数据服务。
- `client.py web`：启动本地网页和 SSE 数据桥接，默认网页地址为 `http://127.0.0.1:8080`。

浏览器通过网页桥接调用 TCP 服务。正常使用时，两个进程都要运行。网页显示的是设备传来的原始样本；自动缩放只影响显示范围，不会对信号做滤波。

## 2. 首次准备

1. 安装 Python 3.10 或更新版本，并确认 PowerShell 能找到 `python`；也可以使用 Python Launcher `py`。
2. 打开 PowerShell，进入项目的 `python` 目录：

   ```powershell
   cd "<项目目录>\python"
   ```

3. 安装串口依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

   若使用 `py` 启动 Python，将上面的 `python` 替换为 `py -3`。

## 3. 连接真实设备并采集

1. 将 ADS1299 设备接到电脑，确认设备对应的串口号（例如 `COM3`）。设备串口参数由程序设置为 1,000,000 baud、8N1，并关闭 RTS/DTR。
2. 在第一个 PowerShell 窗口启动 TCP 采集服务：

   ```powershell
   .\main.ps1
   ```

   默认监听 `0.0.0.0:8765`。保持这个窗口运行。

3. 在第二个 PowerShell 窗口进入同一个 `python` 目录，启动网页桥接：

   ```powershell
   python .\client.py web
   ```

   浏览器打开 `http://127.0.0.1:8080`。保持第二个窗口运行。

4. 在网页左侧操作：
   - 点击串口旁的刷新按钮，从串口列表中选择 ADS1299 对应的端口。
   - 点击 **Connect**。连接成功后状态显示 `DEVICE READY`，采样参数和通道可编辑。
   - 选择采样率（250、500、1000 或 2000 SPS）、输入量程，以及要启用的通道。
   - 点击 **Start acquisition**。采集期间参数和通道选择会锁定；收到设备数据后，样本计数增加，8 路波形开始滚动。
   - 点击 **Stop** 停止采集。停止后可以调整参数并重新开始。
   - 点击 **Disconnect** 关闭设备串口连接。

5. 结束使用时，先在网页停止采集并断开设备，再分别在两个 PowerShell 窗口按 `Ctrl+C` 结束服务。

通道选择对应 8 位掩码：CH1 是 bit 0，CH8 是 bit 7。例如全通道掩码为 `0xff`。

## 4. 不连接设备时

当前版本没有内置设备模拟器或合成波形模式。因此，无设备时可以验证服务与网页是否启动，但不能开始真实采集，也不会看到实时波形。

1. 仍可按“首次准备”安装依赖，然后启动 `main.ps1` 和 `python .\client.py web`。
2. 打开 `http://127.0.0.1:8080`：网页布局、采样率/量程选项和通道开关可查看；串口列表通常为空，状态为未连接。
3. 可以使用 CLI 检查 TCP 服务响应：

   ```powershell
   python .\client.py status
   python .\client.py ports
   ```

   未连接设备时，`status` 中 `connected` 为 `false`；`ports` 只列出采集服务所在电脑可见的串口。

4. 不要在未连接设备时点击开始采集；界面会禁用开始按钮。若要检查实时绘图，需要连接设备，或另行运行符合 TCP JSON Lines 协议的模拟数据服务。当前项目没有提供后一种服务。
5. 若只运行网页桥接而没有运行 `main.ps1`，网页仍可打开，但端口、状态和实时数据请求会提示 TCP 服务不可用。

## 5. 命令行控制

网页以外，也可以用 `client.py` 调用 TCP 服务。先保持 `main.ps1` 运行，再于另一个 PowerShell 窗口执行：

```powershell
python .\client.py ports
python .\client.py connect COM3
python .\client.py configure --sample-rate 500 --range "±4.5V" --channels 0xff
python .\client.py start
python .\client.py status
python .\client.py stop
python .\client.py disconnect
```

将 `COM3` 替换成实际串口。只订阅数据而不在该命令中启动采集：

```powershell
python .\client.py stream
```

订阅后同时启动采集，并在退出时发送停止命令：

```powershell
python .\client.py stream --start --stop-on-exit
```

按 `Ctrl+C` 结束订阅。`stream` 运行期间会持续输出 JSON 数据事件。

## 6. 地址与端口

默认 TCP 服务地址是 `127.0.0.1:8765`（服务端实际监听 `0.0.0.0`），网页桥接地址是 `127.0.0.1:8080`。例如更改 TCP 服务端口：

```powershell
.\main.ps1 -HostAddress 0.0.0.0 -Port 9000
```

然后让网页桥接连接新端口：

```powershell
python .\client.py --port 9000 web
```

网页端口可以另行调整：

```powershell
python .\client.py --port 9000 web --http-host 127.0.0.1 --http-port 8081
```

浏览器改为打开 `http://127.0.0.1:8081`。注意：`--host` / `--port` 放在 `web` 子命令之前，`--http-host` / `--http-port` 放在其后。

## 7. 常见问题

- **网页提示 TCP 服务不可用**：确认 `main.ps1` 窗口仍运行，网页桥接配置的 TCP 地址和端口与服务一致，且端口没有被防火墙拦截。
- **串口列表为空**：检查 USB/串口线、设备供电、驱动和 Windows 设备管理器；刷新列表。串口在采集服务所在电脑枚举，不是在浏览器运行的电脑枚举。
- **连接时报串口占用或打开失败**：关闭其他占用该 COM 口的程序，核对端口号和设备连接状态，然后重新连接。
- **连接成功但没有波形**：确认已点击开始采集、至少启用一个通道，并确认设备确实在输出数据。看样本计数是否递增；仅有 TCP 订阅连接不代表设备正在采集。
- **找不到 `python` 命令**：使用 `py -3` 替代，或将 Python 安装目录加入 PATH。
- **端口已被占用**：用 `main.ps1 -Port <端口号>` 更换 TCP 端口，并用 `python .\client.py --port <端口号> web` 让网页桥接连接该端口。

## 8. 网络安全

TCP 采集服务当前没有身份验证，并默认绑定所有网络接口。请只在可信网络中使用，或通过防火墙限制访问；不要将该端口直接暴露到公共网络。网页桥接默认只绑定本机回环地址 `127.0.0.1`。
