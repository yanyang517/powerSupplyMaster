# Design

## Context

`app.py` 在 qasync 事件循环内启动 `SocketServer`（TCP :8888，4 字节大端长度前缀 + JSON/pydantic），经 `dispatcher.dispatch(raw_data: str)` 按 `request.type` 路由到 `request_handles.py` 中的处理器，最终操作 `SCPI_PowerSupply` 单例。面板侧 `presenter/model.py:19` 直接持有同一设备单例，**完全不经过 dispatcher**。

约束：

- 协议帧格式已被 `src/server/test_client.py` 与 `src/mcp_server/psu_client.py` 使用，不可破坏性修改；消息类型可增量扩展。
- `add-mcp-server` 正在进行，其 D5 已把数值限值定为 server 进程级 `RuntimeConfig`、在 handler 内读取，D7 定为"桥静置即断连、用时重连"。本设计必须与两者共存。
- 本 change 的目标是客户端与会话管理，不以抵御外部攻击为目标（见 proposal.md - Why）。
- 单进程、单 asyncio 事件循环、GUI 与 server 同循环（qasync），无跨线程问题。

## Goals / Non-Goals

**Goals:**

- "谁在连接""谁在控制"两条信息在任何时刻可查、可显示、可审计
- 认证与授权判定集中在一处，新增命令不会因为忘记加检查而形成旁路
- 控制权语义对连接闪断、进程崩溃、无人值守三种现实情况都自洽
- 权限策略外置为数据，不写进处理器分支

**Non-Goals:**

- 不做身份防伪：`client_id` 由客户端自报，登记表是准入名单而非凭据库
- 不做逐参数级/多通道级细粒度权限，粒度止于命令类型
- 不做租约持久化：服务重启后控制权一律为空
- 不做数值限值管理（属 `add-mcp-server` D5），也不做 UI 限值编辑入口
- 不改监听地址、不做串口白名单

## Decisions

### D1: Principal / Session / Lease 三个对象分离，租约归属于 Principal

一条 TCP 连接（Session）与一个客户端身份（Principal）不是一对一：`mcp_server/psu_client.py` 会静置断连后再连。若控制权挂在连接上，桥每次闪断都丢权限、回来被自己拒之门外，直接违背 `add-mcp-server` D7 的"惰性重连"设计。因此 Lease 以 `client_id` 为键，Session 断开不触碰 Lease。

备选：租约挂 Session + 断连宽限期——需要额外维护"断开后计时"和重连认领逻辑，状态更多而收益相同，故不选。

### D2: 判定集中在 `dispatcher.dispatch`，显式传入 Session

`dispatch(raw_data: str)` 现状拿不到任何连接信息，这是唯一的硬障碍。改为 `dispatch(raw_data: str, session: Session)`，在分发器内依次完成认证 → 等级 → 控制权三道判定。

- 备选 ContextVar 隐式传递：省去签名改动，但状态不可见、易被遗忘，且 `mcp_server/test_bridge.py:54` 这类直接调用 `handle_client` 的测试更难搭；一旦必须传 ctx，显式参数优于魔法。
- 备选在各 handler 内自查：与"新增命令不得形成旁路"的目标直接冲突，拒绝。

### D3: 等级随注册声明，控制权需求由等级推导

扩展现有装饰器为 `@dispatcher.register(request_type, request_model, tier=L1)`。等级在处理器定义处声明，与协议模型同文件相邻，不存在第二份需要人工同步的映射表；未带 `tier` 即无法注册，构成结构性默认拒绝。`tier >= L1` 蕴含"需要控制权"，不再单独声明，避免两个属性漂移。

备选：独立的 `type → tier` 字典——集中便于审阅，但新增处理器时容易漏配，漏配的后果是静默放行或静默拒绝，都不如注册期报错。

### D4: 控制权释放只有一个触发条件——距最后成功写入超时

```
  唯一释放条件:  now - last_write_at > lease_ttl
  刷新条件:      写操作成功（读、登录、探活一律不刷新）
  额外入口:      持有者主动交还 / 面板人工吊销
```

把断连、崩溃、空闲三种情形收敛成一条规则，是 D1 之外最重要的简化：闪断无需特判（时限内重连自然恢复），崩溃无需特判（超时自然归还），纯监控客户端天然不会霸占控制权。

代价：客户端异常退出后仍霸占至多 `lease_ttl`。`add-mcp-server` 明确把"不做 MCP 退出清理"列为 Non-Goal，因此不能指望桥调交还接口，兜底只能靠时限本身取短（默认 120 秒，`--lease-ttl` 可覆盖）加面板吊销入口。

### D5: 隐式认领，不提供显式 acquire

控制权空闲时，首个通过等级判定的写请求直接认领并执行；被拒方在响应中拿到持有者身份与剩余时限，第一次写入即可确定性地知道自己是否抢到，不存在"跑到一半才发现"。省掉一个消息类型，也省掉桥侧每次控制前多一跳往返。保留 `release_lease`（礼貌退出）与 `lease_status`（查询）。

### D6: 登记表为可读写的 JSON，准入决定即时落盘

首次连接即写入（L0 自动、L1/L2 经确认后）意味着登记表从"只读配置"变成"运行时可变状态"，采用临时文件 + 原子替换写入，避免半截文件。所有写在同一事件循环内串行，无并发写风险。

默认路径沿用项目已有的 JSON 配置先例：`src/views/window_geometry.py` 的 `geometry_file_path()` 以模块位置解析 `<repo>/config/`，且对被 PyInstaller 冻结的运行方式改为落在可执行文件同级目录（可写、跨升级保留）。本 change 的 `config/clients.json` 采用同一解析策略与同样的 frozen 处理，MUST NOT 以进程 cwd 推断路径。

`client_id` 重名视为同一身份，不做冲突检测——自报身份体系下检测也无意义。

备选：L0 自动准入只进内存不落盘，避免临时脚本污染登记表；用户明确要求"L0 自动确认即可"，故按字面实现为落盘，登记表膨胀由面板列表承担清理。

### D7: 面板经进程内单例读取状态，不走自己的 TCP

Session/Lease/PendingApproval 三张表保存在 server 侧单例，`presenter` 直接读引用。让 UI 伪装成 TCP 客户端去查询自己进程内的数据，只会引入自连死锁与序列化开销，收益为零。这也让 (c) 方案的"面板可见但豁免"落点极小：写路径一行不改，只在面板动作前插一次状态查询与确认。

### D8: 准入确认以回调注入桥接 GUI 与 server

server 侧维护待确认队列，每项持有一个 `asyncio.Future`；启动时若存在 GUI，则把 presenter 的确认回调注册进准入模块，GUI 弹窗决定后 resolve 该 Future；`--no-gui` 下无回调注册，准入模块对 L1/L2 直接拒绝。qasync 使两者共用同一事件循环，无需跨线程调度。挂起仅影响发起连接自身（每连接独立任务），不阻塞其他客户端。

备选：UI 轮询待确认队列——实现更松耦合但引入确认延迟与轮询噪声；Qt signal 桥接对象——本质与回调相同但多一层类型定义。

### D9: 审计复用现有 logging，输出单行结构化字段

在 `dispatch` 出口统一记录一次判定（通过/拒绝 + 原因 + `client_id` + 命令 + 生效等级），面板吊销与准入决定各记一条。不引入数据库、不引入新日志框架，回放需求由日志文件承担。

### D10: `login` 改造为真实会话入口并删除伪凭据

`request_handles.py:46-49` 的硬编码 `token_123` 与 `protocal.py:31` 的明文 `password` 一并移除，登录请求以 `client_id` + 申请等级为字段。保留一个"半截的假会话"比没有会话更糟——它会让客户端误以为登录后获得了保护。因此本次直接判定为 **BREAKING**，同步修改 `test_client.py` 与 `mcp_server/psu_client.py` 的登录调用。

### D11: 模块布局

```
  src/server/registry.py   Principal、登记表加载/原子写、tier 常量
  src/server/session.py    Session、Lease、PendingApproval 与进程内单例容器
  src/server/access.py     三道门判定 + 审计出口
  src/server/dispatcher.py dispatch 签名扩展，调用 access
  src/server/socket_server.py  建 Session、传入 dispatch、断开时不触碰 Lease
  src/server/request_handles.py  注册期声明 tier；新增 5 个消息的处理器
  src/server/protocal/protocal.py  新模型并入 RequestUnion
```

数值上限校验保持在 handler 内读取 `RuntimeConfig`（`add-mcp-server` D5），与控制权判定分层不重叠：分发器决定"能不能碰这台设备"，处理器决定"这个值允不允许"。

## Risks / Trade-offs

- [`client_id` 自报，任何本机进程可冒用他人身份取得其等级与控制权] → 与目标一致，明确接受；在 spec 与 doc 中写死"登记表是准入名单，不是凭据"，未来若需要防伪，只需把 `registry` 的匹配换成凭据校验，判定链不变
- [持有者崩溃后其他客户端至多被挡 120 秒] → `--lease-ttl` 可调 + 面板吊销兜底；若后续要求即刻可抢，需引入抢占语义，本期不做
- [面板写操作豁免租约，"独占"仅对远程客户端成立] → 已在 spec 中以"面板操作不受控制权约束 + 必须二次确认"显式表述，不制造虚假的独占承诺
- [`add-mcp-server` 与本 change 同时改 `request_handles.py`、`protocal.py`] → 先归档 `add-mcp-server`（其 D5/D6 是本 change 数值层的既有前提），本 change 在其产物之上 rebase；两 change 若并行实施则后者需承担合并冲突
- [L0 自动落盘使登记表随临时脚本增长] → 面板客户端列表提供可见性与吊销入口；必要时后续以"仅内存"替代，属策略调整不影响判定链
- [JSON 登记表被外部编辑器同时修改] → 写时以原子替换覆盖，最后写入者生效，不做冲突检测；文档提示改表前先停服
- [弹窗确认期间连接挂起，用户不在电脑前则远程写权限客户端长期等待] → 确认超时按拒绝处理并关闭连接，不占用 server 资源

## Migration Plan

1. 在 worktree 分支实施（项目 git 工作流约束），以 `git merge --no-ff` 合入 master。
2. 合入前在默认登记表路径预置 `mcp-bridge`（L2：桥的 `set_output` 走 `set_on_off`，按 D3 归级属 L2，以 L1 登录会让该工具永远被拒；串口通断仍只在 UI）与本机常用客户端，避免合入后桥直接落在"L0 自动准入"上而拿不到写权限。
3. 与 `add-mcp-server` 的落地顺序：其 D5/D6 先行，本 change 随后叠加控制权门控。
4. 回滚：还原 `src/server/` 与 `src/presenter/` 改动即恢复原有无门控行为；已写入的 JSON 登记表可保留，回滚后无人读取，无数据迁移。

## Open Questions

- 面板客户端列表是否提供"从登记表移除"能力（本期只保证可见与可吊销控制权，移除仍可手工改 JSON）
- `lease_ttl` 默认 120 秒的实际体感，需在真实闪断场景下调
- 本期不改监听地址（仍为 `0.0.0.0`）。若日后确认无需局域网接入，收口为仅本机可达是一行改动，且会让本设计的"准入名单"意义显著上升——留待单独决策，不在本期承诺
