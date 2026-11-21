# psu-mcp

MCP（Model Context Protocol）stdio 桥，让 AI 客户端（如 Qoder）操作
powerSupplyMaster 桌面应用所管理的 SCPI 电源。

- 串口连接由 powerSupplyMaster 的 UI 管理；本桥只操作已连接的设备。
- 运行时通过 TCP（默认 `127.0.0.1:18888`）连到主应用的 SocketServer，
  以 `client_id=mcp-bridge`（L2）登录；本包不依赖主仓库源码。
- 提供 4 个工具：`get_status` / `set_voltage` / `set_current` / `set_output`。
  限值由服务端强制，先用 `get_status` 读 `limits`。

## 安装（唯一渠道：离线 wheel 篮子）

在**有网、且与目标机同 OS 平台、同 Python 大版本**的构建机上：

    python -m build -w                     # 产出 dist/psu_mcp-<ver>-py3-none-any.whl
    pip download -d basket dist/psu_mcp-<ver>-py3-none-any.whl
    # 把 basket/ 目录（或打包成 psu-mcp-offline-<ver>.zip）拷贝到目标机

目标机（无需外网）：

    pip install --no-index --find-links=basket psu-mcp

注意：篮子内含 `rpds-py`、`cffi` 等二进制依赖轮子，跨平台/跨 Python 版本安装会失败；
需要为每个目标平台单独构建篮子（跨平台构建可用
`pip download --platform win_amd64 --python-version 312 --only-binary=:all:`）。

## 接入 MCP 客户端

    {
      "mcpServers": {
        "power-supply": { "command": "psu-mcp" }
      }
    }

或用模块方式（等价）：`"command": "python", "args": ["-m", "psu_mcp"]`。
不需要 cwd、PYTHONPATH 或源码仓库路径。

## 开发

    pip install -e .[dev]    # 或 pip install pytest pytest-asyncio
    python -m pytest tests

兼容性要求见 `CHANGELOG.md`：本包对服务端协议有版本要求（login 握手等），
旧版 powerSupplyMaster 可能拒绝连接。
