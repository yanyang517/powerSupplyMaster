# Proposal

## Why

SocketServer 目前对任何能连上 :8888 的客户端全权放行：无身份、无分级、无独占，`login` 只返回硬编码假 token 且无人校验（`src/server/request_handles.py:46-49`）。随着 MCP 桥接入（`src/mcp_server/`），多个客户端会在同一时段连到同一块电源上，出现了两个无法回答的问题——**谁在连接**、**谁正在控制**。本 change 目标是客户端与会话管理，不是抵御外部攻击或 AI 幻觉。

## What Changes

- 引入**客户端登记表**（JSON 文件，`--clients` 指定路径）：`client_id` → 授权等级 + 显示名。
- 引入**三级授权**：L0 观测（只读查询）、L1 调节（设值，受限值约束）、L2 通断（输出开关 + 设备连接/断开）。未登记的命令默认拒绝。
- 引入**准入流程**：未知 `client_id` 连接后发起登录，L0 请求自动确认并写入登记表；L1/L2 请求转为待确认项，由 UI 弹窗经用户决定后写入或拒绝。
- **BREAKING** `login` 成为真实会话入口：请求必须携带 `client_id`，未完成登录的连接只允许 `echo`；假 token 字段与明文 `password` 一并移除。
- 引入**控制权租约**：同一时段只有一个客户端可执行写操作。写请求在租约空闲时隐式认领，成功后刷新 TTL；超时自动释放。
- 新增 L0 只读查询 `lease_status` / `list_clients`，分别返回控制权持有者与当前连接列表；新增 `release_lease` 供持有者主动交还。
- 面板侧（只读介入）：显示"当前由 X 控制中"，并对面板自身的写操作弹二次确认；面板可强制吊销租约。面板本身不受租约约束。
- 所有授权判定（含被拒）输出结构化审计日志。

**明确不含**：监听地址仍为 `0.0.0.0`（不以防黑客为目标，避免打断既有局域网用法）；不引入口令、哈希校验与 TLS；不做串口白名单；不改 UI 限值编辑入口。

## Capabilities

### New Capabilities

- `server/client-access-control`: 客户端身份登记、登录会话、首次连接准入、分级授权判定与审计记录。
- `server/control-lease`: 电源控制权的独占语义——认领、续期、超时释放、主动交还、第三方吊销与状态查询。

### Modified Capabilities

无。`openspec/specs/` 下现仅存 `ui/window-geometry`，本 change 不触碰其需求。

> 注：进行中的 `add-mcp-server` 携带尚未归档的 `power-supply-control` 与 `mcp-bridge` delta specs。本 change 的租约门控会叠加在其写操作之上，归档顺序需先行者落地，两者在 `request_handles.py` 与 `protocal.py` 上存在交叉。

## Impact

- **代码**：`src/server/`（新增登记表与会话/租约模块，改 `dispatcher.py`、`socket_server.py`、`request_handles.py`、`protocal/protocal.py`）；`src/presenter/` 与 `src/views/main_window.py`（只读状态显示 + 确认弹窗，避开 :278-292 接线区的并行改动）；`src/mcp_server/psu_client.py`（登录时携带 `client_id`）。
- **协议**：新增 5 个消息类型与登录字段，属增量扩展；但对既有客户端属**行为破坏**（写操作新增租约前置条件）。
- **状态**：新增可被 UI 进程内读取的单例（连接与会话列表），面板无需经 TCP 查询自身。
- **依赖**：无新增第三方依赖。
- **交付**：按项目 git 工作流约束在 worktree 分支实施，以 `git merge --no-ff` 合入 master。
