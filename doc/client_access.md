# 客户端接入与权限管理

powerSupplyMaster 的常驻 server 允许任意多个 TCP 客户端同时连接。本文说明**谁被允许接入、谁在控制电源、以及怎么把这些信息看明白**——它是客户端管理，不是入侵防护：`client_id` 由客户端自报，登记表是准入名单，不存放口令、密钥或证书。

协议帧格式（4 字节大端长度 + JSON）见 `doc/mcp_integration.md`。

## 三道门

```
连接 --> [1 认证] --> [2 等级] --> [3 控制权] --> 业务处理器 --> 设备
          未登录即拒    等级不足即拒   他人持有即拒
```

每道门相互独立，拒绝时返回各自的 `reason`，客户端据此判断该申请提权还是该等对方交还。判定通过后仍会执行数值上限校验（`--max-voltage` / `--max-current`），上限与权限是两回事。

### 等级与命令归级

| 等级 | 含义 | 命令 |
|---|---|---|
| L0 | 只读观察 | `echo`、`login`、`logout`、`lease_status`、`list_clients`、`release_lease`、`setting_query`、`voltage_query`、`current_query`、`on_off_query`、`device_id_query` |
| L1 | 可设值 | `set_voltage`、`set_current`（+ 全部 L0） |
| L2 | 可改变设备连接与输出通断 | `open_device`、`close_device`、`set_on_off`（+ 全部 L1） |

命令按等级注册，注册时不声明等级直接报错——新增命令默认不可用，而不是默认可用。

## 登录

业务命令之前必须先登录（`echo` 探活除外）：

```json
{"type": "login", "request_id": "c1", "client_id": "operator-a", "tier": "L1"}
```

响应的 `tier` 字段是**实际生效等级**：已登记客户端一律按登记表中的等级授予，申请更高会被降格，申请更低不改变登记身份。

## 登记表

默认路径 `config/clients.json`（相对仓库根目录解析，与进程 cwd 无关；打包成 exe 后落在可执行文件同级的 `config/clients.json`）。用 `--clients` 指定其他文件：

```bash
python src/app.py --clients D:/tools/psu-clients.json
```

文件格式：

```json
{
  "schema_version": 1,
  "clients": {
    "mcp-bridge":  { "tier": "L2", "name": "AI 助手 (MCP 桥)" },
    "test-client": { "tier": "L2", "name": "集成测试客户端" }
  }
}
```

- `tier` 取 `L0`/`L1`/`L2`（大小写不敏感）；`name` 是给人看的显示名。
- 出现 `password` / `token` / `secret` / `key` 一类凭据字段会被拒绝加载——本机制不承担机密存储。
- 启动时文件缺失、JSON 不可解析、等级非法都会**终止启动并给出明确信息**，不会静默退化成空表。
- 用户在弹窗中同意准入后，新条目由 server 原子写回该文件（临时文件 + 替换）。

## 新客户端准入

未登记的 `client_id` 首次登录时：

| 申请等级 | 结果 |
|---|---|
| L0 | 自动放行并写入登记表（只读，无需打扰用户） |
| L1 / L2 | 弹出「客户端准入请求」窗，展示 `client_id`、来源地址、申请等级，由用户决定 |

- 同意：写入登记表并放行本次登录；拒绝或关闭窗口：本次登录被拒并关闭该连接，登记表不变。
- 弹窗是非模态的：等待用户应答期间其他客户端的请求照常处理。
- 无人应答 60 秒后按拒绝处理（`approval_timeout`）。
- **无界面模式（`--no-gui`）下 L1/L2 准入一律被拒**，`reason` 为 `no_approver`。要么先手工把条目写进登记表再启动，要么带界面运行一次完成准入（条目会持久化，之后无界面也能用）。

## 独占控制权

同一时刻只允许一个客户端操作电源。

- **归属键是 `client_id`，不是连接**：客户端闪断重连后仍持有控制权；崩溃的客户端只保留到租约到期。
- **认领是隐式的**：控制权空闲时，第一个成功落地的写操作即完成认领，没有独立的 acquire 往返。
- **释放条件只有一个**：距最后一次**成功写入**超过 `--lease-ttl` 秒（默认 120）。读取、登录、查询都不续期。
- 主动交还：`{"type": "release_lease", ...}`，只有持有者本人有效。
- 被他人持有时，写请求被拒（`controlled_by_other`），响应里点名持有者并给出剩余时间；只读命令不受影响。
- `lease_status` 返回持有者、剩余时限、闲置时长以及持有者当前是否在线。

## 面板侧

- **控制权卡片**显示"空闲 / 由 X 持有（等级，剩余 a/b 秒）/ X 已断线，剩余 N 秒"，并提供**吊销控制权**按钮（先二次确认）。
- **客户端列表**显示全部活动会话，区分已登录与未登录，并标记当前持有者；待确认的准入请求也列在这里。
- 面板自身写操作**不受控制权限制、也不认领控制权**：有人持有时先弹"电源正被远程控制"确认框，用户确认后由面板下发，控制权归属不变；用户取消则本次改动不下发。
- 吊销只释放归属，**不动设备输出、不改设定值**。

## 审计

每次判定都留一行日志（`server.audit`），被拒记录同样保留：

```
ACCESS session=8cb0c35e peer=127.0.0.1:52310 client=operator-a tier=L1 cmd=set_voltage allowed result=ok
ACCESS session=20266443 peer=127.0.0.1:52311 client=operator-b tier=L1 cmd=set_voltage denied reason=controlled_by_other msg=... holder='operator-a'
ADMISSION client=unknown-tool tier=L1 refused reason=no_approver
```

面板发起的吊销带 `origin=panel`。

## 拒绝原因速查

| `reason` | 含义 | 处理 |
|---|---|---|
| `not_authenticated` | 未登录就发业务命令 | 先 `login` |
| `insufficient_tier` | 命令所需等级高于生效等级 | 由用户提高登记表中的等级 |
| `controlled_by_other` | 控制权由他人持有 | 等对方交还或到期，或请用户在面板吊销 |
| `lease_lost` | 认领竞争失败（并发写入） | 重试 |
| `no_approver` | 无界面模式下申请 L1/L2 准入 | 带界面确认一次，或预填登记表 |
| `refused_by_user` / `approval_timeout` | 弹窗被拒或超时 | 确认身份后重新登录 |

## 启动参数

```bash
python src/app.py --clients config/clients.json --lease-ttl 120 --max-voltage 24 --max-current 3
```

| 参数 | 默认 | 作用 |
|---|---|---|
| `--clients` | `config/clients.json` | 登记表文件路径 |
| `--lease-ttl` | `120`（秒） | 控制权闲置时限 |
| `--max-voltage` / `--max-current` | `30` V / `5` A | 数值上限，与权限无关 |

## 端到端演示

不接硬件，自己起一个 server 并把 SCPI 设备假装成已连接，复现「一个只读、一个持有、一个争用被拒」的完整场景：

```bash
python scripts/access_control_e2e.py --lease-ttl 2
```

输出逐条 `[OK ]` 检查，任何一条不符即以非零码退出。加 `--verbose` 打印服务端日志与完整的 `list_clients` 响应。

## 相关测试

```bash
cd src
python -m pytest server/test_registry.py server/test_session.py server/test_admission.py \
    server/test_access.py views/test_client_access.py presenter/test_takeover_gate.py
```
