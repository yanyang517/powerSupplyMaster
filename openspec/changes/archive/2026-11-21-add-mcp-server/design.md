# Design

## Context

现有架构为单进程 asyncio 应用：`app.py`（qasync 或 `--no-gui`）内运行 `SocketServer`（TCP :8888，4 字节大端长度前缀 + JSON/pydantic 协议），经 `dispatcher` 路由到 `request_handles` 中的 handler，最终操作 `SCPI_PowerSupply` 单例（asyncio 串口）。串口连接由 UI 触发，`device_simulator` 可替代真机。动机见 proposal.md - Why。

约束：官方 Python MCP SDK（`mcp`，MIT）满足许可要求；协议帧格式已被 GUI/测试客户端使用，不可破坏性修改。

## Goals / Non-Goals

**Goals:**
- MCP 桥作为纯翻译层：不持有业务规则，限值判断全部留在 server 端
- app 重启、连接闪断时桥能自愈，无需 AI 干预
- 错误路径（app 未运行 / 设备未连接 / 超限）都返回 AI 可自助修正的信息

**Non-Goals:**
- 不做 MCP HTTP/SSE 远程接入（探索阶段已选定 stdio，见 Decisions）
- 不做 UI 限值编辑入口、不做 raw SCPI 逃生舱、不做 MCP 退出清理
- 不改变 GUI 现有交互流程

## Decisions

### D1: 独立 stdio 进程桥接 TCP，而非内嵌 HTTP 或直连串口
探索阶段对比过三方案：A 内嵌 app 提供 MCP-over-HTTP、B 独立 stdio 进程作为 SocketServer 的 TCP 客户端、C 独立进程直持串口。选 B：与本机 AI 客户端"配置命令行拉起"的原生模型匹配；业务逻辑零复制；C 与 UI 争抢串口被用户明确排除（串口管理归 UI）；A 留待未来远程 AI 接入需求出现时演进。

### D2: 使用官方 `mcp` SDK 的 FastMCP 高层 API
手写 JSON-RPC stdio 循环没有收益；SDK 为 MIT 许可，且 `uvicorn`/`starlette` 等传递依赖仅在 HTTP 相关 extra 中出现，stdio 路径依赖极轻。加入 `requirements.txt`。

### D3: 桥内自实现约 60 行长度前缀协议客户端
不复用 `socket_server.py` 的读帧代码（其面向 server 侧且引入 `construct` 依赖），直接用 `asyncio.open_connection` + `struct.pack(">I", len)` 实现收发；`request_id` 用 uuid 并在收响应时校验匹配，防未来 server 并发化后错帧。

### D4: `get_status` 由桥侧聚合，不改协议
单次调用按序发送 `device_id_query → voltage_query → current_query → on_off_query → setting_query`，合并为结构化结果。备选的"新增聚合 status 协议消息"被否决：需要同时动 `protocal.py` 的 RequestUnion、handler 与 UI，收益（省 4 次本机 round-trip）不匹配改动面。任一子查询失败即整体返回错误（最常见原因：设备未连接），`setting_query` 失败不阻断（限值为附加信息）。

### D5: 限值存于 server 进程级 `RuntimeConfig` 单例，handler 请求时读取
`src/server/` 新增小型配置模块（dataclass：`max_voltage`、`max_current`），`app.py` argparse 解析 `--max-voltage/--max-current` 后注入；`set_voltage/set_current` handler 每次请求时读取，天然支持未来 UI 动态修改。默认值取保守档（30 V / 5 A）。校验与 SCPI 下发在同一 handler 内完成，保证 GUI 与桥共享同一保护。不选"桥内校验"：绕过桥的 TCP 客户端将不受保护；不选"配置文件"：启动参数已够用且 MCP 客户端配置注入更方便。

### D6: 连接状态检查前置到 handler 入口
`SCPI_PowerSupply` 未连接时 `_writer` 不存在，当前表现为裸 `AttributeError` → server 兜底 `internal_error`。所有设备依赖型 handler 入口统一 `if not psu.is_connected: return BaseResponse(status="error", message="device not connected")`。同时修正 `open_device` 丢弃 `connect()` 返回值的问题，失败时透传原因并携带 identifier。

### D7: 桥对 server 保持单条长连接 + 惰性重连
首次工具调用时建连；检测到连接断开（EOF/超时）后丢弃连接，下一次调用前重连并透明重试一次。不做后台保活任务——MCP 进程生命周期由 AI 客户端控制，静置时不应有活动连接占用 server。

### D8: 代码布局与入口
`src/mcp_server/`（`__main__.py` + `psu_client.py` + `tools.py`），运行方式 `python -m mcp_server`（`PYTHONPATH=src`），AI 客户端配置示例写入 doc。Server 侧改动集中在 `request_handles.py`、`app.py` 与新配置模块。

## Risks / Trade-offs

- [单连接串行请求-响应假设] server 目前逐连接串行处理，成立；若未来 server 并发化，D3 的 request_id 校验将暴露错帧而非静默错值 → 可接受，且校验已前置埋好
- [桥聚合 get_status 需 5 次本机往返] 延迟毫秒级，换取协议零破坏；若后续压测证明是瓶颈再引入聚合消息
- [AI 误操作输出 ON 带电] 限值为硬保护；`set_output` 描述强制"先读状态"话术；本次接受该残余风险（设备侧通常还有 OCP/OVP）
- [`mcp` SDK 要求 Python ≥ 3.10] 与现有 `asyncio.timeout`/现代类型语法使用一致，视为已满足；实施首日以 `python --version` 验证
- [app 与桥的版本漂移] 新增字段均走 pydantic 默认值宽松路径，旧 server + 新桥时 `setting_query` 失败自动降级为无限值信息展示

## Migration Plan

纯增量：新代码目录 + handler 行为收紧 + 两个新启动参数（有默认值，不改现有启动方式）。回滚 = 从 AI 客户端移除 MCP 配置并还原 server 改动，无数据迁移。实施按 git 工作流约束在 worktree 分支进行，`--no-ff` 合入 master。
