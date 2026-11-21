# Proposal

## Why

当前电源设备只能通过 Qt GUI 或原始 TCP 协议（4 字节长度前缀 + JSON）操作，AI 客户端（Qoder Desktop 等本机客户端）无法直接调用。增加一个 MCP server 桥接层后，AI 可以在人的授权下用自然语言完成读状态、调电压/电流、开关输出等操作，为后续自动化测试与 AI 闭环控制打基础。

## What Changes

- 新增独立的 MCP server 进程（stdio 传输，由 AI 客户端按需拉起），暴露 4 个语义化工具：`get_status`、`set_voltage`、`set_current`、`set_output`。
- MCP 进程作为现有 SocketServer（默认 `127.0.0.1:8888`）的协议客户端，复用 dispatcher/handler 全部业务逻辑；不管理串口，不做退出清理。
- SocketServer 侧增加动态限值校验：`set_voltage` / `set_current` 超过限值时返回 `status="error"` 并携带允许范围；限值由 server 启动参数提供（UI 限值管理入口不在本次范围）。
- 注册 `setting_query` handler，向客户端暴露当前生效的限值，供 `get_status` 聚合展示。
- 修正连接状态错误语义：设备未连接时的查询/设置请求 MUST 返回明确错误（而非静默 success 或裸异常），MCP 桥将其翻译为"请在 UI 中连接设备"的引导信息。

## Capabilities

### New Capabilities

- `mcp-bridge`: MCP stdio server 的工具面——工具定义、参数与描述、到 SocketServer 的协议客户端行为、错误到 AI 可读提示的映射、app 未运行时的降级表现。
- `power-supply-control`: 电源控制服务的行为要求——限值校验与限值查询、连接状态错误语义、现有 set/query 命令的响应约定。

### Modified Capabilities

（无——项目当前没有已归档的 specs。）

## Impact

- 新增代码：`src/mcp_server/`（MCP 入口 + 长度前缀 JSON 协议客户端）。
- 修改代码：`src/server/request_handles.py`（限值校验、`setting_query` handler、连接状态错误）、`src/server/socket_server.py` / `src/app.py`（限值启动参数透传）、`src/server/protocal/protocal.py`（错误响应按需扩展字段）。
- 新增依赖：官方 Python MCP SDK（`mcp`，MIT 许可，符合企业许可约束）。
- 不影响：GUI 操作路径、串口管理、现有协议帧格式（向后兼容，仅新增字段与更严格的错误返回）。
