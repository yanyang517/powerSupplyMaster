# MCP 接入指南（AI 操作电源设备）

powerSupplyMaster 提供一个 stdio 传输的 MCP server，让 AI 客户端（Qoder Desktop、Claude Desktop 等）通过语义化工具读取和控制 SCPI 电源。

## 架构

```
AI 客户端 --stdio--> mcp_server（按需拉起） --TCP JSON(4B长度前缀)--> SocketServer(常驻) --串口--> 电源
```

- 串口连接**由桌面应用 UI 管理**，AI 无法打开/关闭串口。
- 电压/电流限值**由 server 端强制执行**（启动参数配置），GUI 与 AI 共享同一保护。
- MCP 进程退出/崩溃不影响设备状态。
- 桥在 TCP 连接建立后先以固定身份 `login`，之后每次读写都经过 server 侧的等级与控制权判定，详见 [doc/client_access.md](client_access.md)。

## 前置条件

1. 已安装依赖：`pip install -r requirements.txt`（含 `mcp` SDK，要求 Python ≥ 3.10）。
2. powerSupplyMaster 常驻运行（GUI 或 `python src/app.py --no-gui`），默认监听 `127.0.0.1:8888`。
3. 在 UI 中完成串口连接（AI 侧无需处理，未连接时工具会返回引导提示）。
4. 桥的身份 `mcp-bridge` 已在随附的 `config/clients.json` 中预置。换机器、换登记表或改 `client_id` 时，需带界面运行一次并在准入弹窗中确认，或先把条目写进登记表（无界面模式下 L1/L2 准入一律被拒）。

## AI 客户端配置示例

Qoder Desktop（MCP 配置 JSON，其他客户端同理）：

```json
{
  "mcpServers": {
    "power-supply": {
      "command": "D:/git/powerSupplyMaster/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server"],
      "cwd": "D:/git/powerSupplyMaster/src",
      "env": { "PYTHONPATH": "D:/git/powerSupplyMaster/src" }
    }
  }
}
```

若在 worktree/其他目录运行，把 `cwd` 与 `PYTHONPATH` 指向对应的 `src` 目录即可。

## 工具清单

| 工具 | 参数 | 说明 |
|---|---|---|
| `get_status` | 无 | 聚合返回电压(V)、电流(A)、输出开关、设备标识、生效限值 `limits`。只读 |
| `set_voltage` | `voltage: float` (V) | 范围以 `limits.max_voltage_v` 为准，超限被拒绝并提示允许范围 |
| `set_current` | `current: float` (A) | 范围以 `limits.max_current_a` 为准 |
| `set_output` | `enable: bool` | 接通/断开输出。AI 应先 `get_status` 确认状态 |

`get_status` 之外的三个工具都会改变设备状态：桥的默认身份 `mcp-bridge` 登记为 L2，覆盖设值与输出通断（串口通断不在其中，仍只在 UI），且在写成功的那一刻取得/持有独占控制权。控制权在最后一次成功写入后 `--lease-ttl` 秒内归属桥；期间 GUI 面板仍可下发改动（会先向用户确认），GUI 的改动不会夺走归属。语义详见 [doc/client_access.md](client_access.md)。

## 限值配置

server 启动参数（不传则用默认 30 V / 5 A）：

```bash
python src/app.py --max-voltage 24 --max-current 3
```

修改后对 GUI 和 AI 同时生效；AI 通过 `get_status` 返回的 `limits` 感知当前范围。
UI 内动态编辑限值的能力规划在后续 change。

## 常见错误提示

| 提示 | 含义 | 处理 |
|---|---|---|
| 电源控制应用未运行 | MCP 桥连不上 127.0.0.1:8888 | 启动 powerSupplyMaster |
| 设备未连接，请在 UI 中连接串口 | server 在跑但串口未开 | 在 GUI 里选择串口并连接 |
| voltage X V out of allowed range | 超出限值 | 按提示范围调整重试 |
| 电源控制应用拒绝了本桥的登录 | 该 `client_id` 未登记，且没有可批准的界面（`no_approver`） | 带界面运行并在准入弹窗确认，或把条目写进 `config/clients.json` |
| needs L2 but client is L1 | 命令等级高于桥的生效等级（`insufficient_tier`） | 在登记表中提高该 `client_id` 的等级 |
| device is under control of 'X' | 控制权由他人持有（`controlled_by_other`），消息里有剩余时间 | 等对方交还或到期，或请用户在面板吊销控制权 |

## 测试

```bash
cd src
python -m pytest server/test_power_control.py mcp_server/test_bridge.py
# 权限与控制权相关
python -m pytest server/test_registry.py server/test_session.py server/test_admission.py server/test_access.py
```
