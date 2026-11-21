# Tasks

## 1. 准备工作

- [x] 1.1 按 git 工作流约束用 `git worktree` 为本 change 建立独立工作目录并创建 `feature/add-mcp-server` 分支；验证 `git worktree list` 显示新目录且分支正确
- [x] 1.2 在工作目录添加 `mcp` 依赖到 `requirements.txt` 并安装；验证 `python -c "import mcp"` 成功且确认 Python ≥ 3.10

## 2. Server 端：限值与错误语义

- [x] 2.1 新建 `src/server/` 运行时配置模块（`max_voltage`/`max_current`，默认 30V/5A），在 `app.py` argparse 增加 `--max-voltage`/`--max-current` 并注入；验证启动参数覆盖默认值可在日志或 `setting_query` 中观察到
- [x] 2.2 `set_voltage`/`set_current` handler 增加限值校验（拒绝时不下发 SCPI，message 含允许范围；边界值放行）；验证 pytest 用 simulator 覆盖超限、边界、范围内三种用例
- [x] 2.3 注册 `setting_query` handler 返回当前电压/电流限值；验证通过 TCP 测试客户端发送 `setting_query` 收到含两项限值的响应
- [x] 2.4 所有设备依赖型 handler 入口增加连接状态检查，未连接返回 `status="error"` 且 message 为"device not connected"；验证未连接时 `voltage_query`/`set_voltage` 返回该错误而非 internal_error/假 success
- [x] 2.5 修正 `open_device` 丢弃 `connect()` 返回值的问题，成功携带 identifier、失败透传原因；验证错误串口号（如 `COM255`）返回 `status="error"`

## 3. MCP 桥：协议客户端

- [x] 3.1 创建 `src/mcp_server/` 模块骨架（`__main__.py`/`psu_client.py`/`tools.py`）；验证 `python -m mcp_server` 可启动并等待 stdio 输入
- [x] 3.2 实现长度前缀 JSON 协议客户端（asyncio 直写、uuid request_id 校验、超时）；验证 pytest  against 真实 `SocketServer`（simulator 设备）完成一轮 请求-响应
- [x] 3.3 实现单长连接 + 惰性重连 + 断连透明重试一次（D7）；验证测试中杀掉 server 再重启后，后续调用自动恢复且无需外部干预

## 4. MCP 桥：工具面

- [x] 4.1 基于 FastMCP 实现 `get_status`（按 D4 聚合 5 个查询，`setting_query` 失败不阻断）；验证对运行中 app（simulator）调用返回电压/电流/输出/ID/限值结构
- [x] 4.2 实现 `set_voltage`/`set_current`/`set_output` 工具，参数描述写明"范围以 get_status 的 limits 为准、超限会被拒绝"，`set_output` 描述含"先读状态"提示；验证超限值经 MCP 调用返回含允许范围的错误文本
- [x] 4.3 实现错误映射：app 未运行 → "请启动 powerSupplyMaster"；设备未连接 → "请在 UI 中连接串口"；server `status="error"` message 原文透传；验证断开局面的手工冒烟（不启动 app / 不连接设备各调用一次）
- [x] 4.4 在 `doc/` 新增 MCP 接入文档（AI 客户端配置 JSON 示例、启动参数、工具清单、限值说明）；验证按文档配置 Qoder 后 `get_status` 实际调通
  - 验证：按文档的 `command`/`cwd`/`PYTHONPATH` 以 stdio 拉起 `python -m mcp_server`，`list_tools` 得到四个工具，`get_status` 返回 `FAKE,RIGOL DP832` / 11.99V / 1.588A / `limits` 30V·5A（COM9 模拟器 + 面板连 COM8）。文档在 `add-client-access-control` 中已补登录与权限相关条目。

## 5. 集成验证

- [x] 5.1 端到端回归：启动 app（simulator）→ UI 连接设备 → MCP 客户端完成 读状态 → 设压 → 开输出 → 关输出 全流程；确认 GUI 同期手动操作不受影响、`pytest test/` 全绿
  - 验证：离屏驱动真实 GUI 栈跑完全流程 13 项检查全 OK——UI 连接模拟器、MCP 读状态→设压 15.5V→开输出→关输出、超限 99V 被 server 拒绝；桥持有控制权时面板写 8.0V 先弹接管确认，确认后落设备且归属不变。`test/` 目录为空，测试实际位于 `src/`：`pytest src` 190 passed（`server/test_client.py` 的 6 例需真实硬件串口，虚拟串口下另跑）。
- [x] 5.2 确认 MCP 进程被终止后设备输出状态不变、server 无残留异常日志（spec：不管理设备生命周期）

## Workflow follow-up

- 以 `git merge --no-ff` 将 `feature/add-mcp-server` 合入 master（主工作区操作，汇报实际合并方式）。
- 评审通过后用 `/opsx:archive` 归档本 change，将两个新能力写入主 specs。
