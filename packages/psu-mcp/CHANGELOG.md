# Changelog

本包遵循语义化版本；协议兼容要求以最低 powerSupplyMaster 应用版本记录。

## 0.1.0

- **BREAKING（对老接入方式）**：不再支持"源码仓库 + `python -m mcp_server` + cwd/PYTHONPATH"
  的接入方式；`powerSupplyMaster` 仓库的 `src/mcp_server/` 已删除。请改为安装本包并使用
  `"command": "psu-mcp"`（或 `python -m psu_mcp`）。
- 从 powerSupplyMaster 抽取 MCP 桥为独立包：4 个工具语义不变
  （`get_status` / `set_voltage` / `set_current` / `set_output`）。
- 协议要求（低于此版本的应用会拒绝本桥）：
  - SocketServer 监听 `127.0.0.1:18888`（主应用 8888→18888 迁移后的版本）；
  - 每条连接须先 `login`（`client_id=mcp-bridge`，tier `L2`），未登录请求被默认拒绝；
  - `setting_query` 返回 `max_voltage` / `max_current` / `version`
    （`version` 缺失时 `get_status` 的 `limits.server_version` 为 null，属可容忍降级）。
- 运行时依赖仅 `mcp==2.3.0`；不依赖 PySide6/qasync/pyserial 或主仓库任何模块。
