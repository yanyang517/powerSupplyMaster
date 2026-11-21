# Spec Delta

## Purpose

约束哪些客户端可以连接本机 TCP 控制接口、以何种身份连接、各自被允许执行哪一类命令，并把每一次授权判定留痕，使"谁在连接"与"谁在控制"始终可回答。

## ADDED Requirements

### Requirement: 客户端登记表

系统 SHALL 从 JSON 文件加载客户端登记表，文件路径由启动参数 `--clients` 指定；每条登记项 MUST 包含 `client_id`、授权等级与展示用名称。登记表 MUST NOT 包含口令、密钥或证书字段。

#### Scenario: 启动时加载登记表

- **WHEN** 服务以 `--clients <path>` 启动且文件存在
- **THEN** 服务在开始监听前完成加载，并按登记项建立可用客户端集合

#### Scenario: 登记表缺失

- **WHEN** 指定路径不存在，或文件内容无法解析为合法登记表
- **THEN** 服务 MUST 以明确的错误信息终止启动，MUST NOT 以空登记表继续运行

#### Scenario: 未指定登记表路径

- **WHEN** 启动时未提供 `--clients`
- **THEN** 服务使用默认路径查找登记表；默认路径同样不存在时按"登记表缺失"处理

### Requirement: 连接必须先登录

除 `echo` 外，客户端在任何业务命令前 MUST 完成登录；登录请求 MUST 携带 `client_id`。登录成功后的连接 SHALL 被视为已认证会话，直至断开。

#### Scenario: 未登录即发起业务命令

- **WHEN** 一条未登录的连接发送 `set_voltage`
- **THEN** 系统 SHALL 拒绝且 MUST NOT 向设备下发任何指令，响应中说明该连接尚未登录

#### Scenario: 未登录时探活

- **WHEN** 一条未登录的连接发送 `echo`
- **THEN** 系统 SHALL 正常应答，以便客户端在服务就绪前探测可用性

#### Scenario: 登录不再返回固定凭据

- **WHEN** 登录成功
- **THEN** 响应 SHALL 只表明会话建立，MUST NOT 返回可被复用为凭据的固定 token 字段

### Requirement: 未登记客户端的分级准入

未在登记表中的客户端请求登录时，系统 SHALL 按其申请的授权等级分流：申请 L0 时自动准入并写入登记表；申请 L1 或 L2 时转为待确认项。

#### Scenario: 申请 L0 自动准入

- **WHEN** 未知客户端以 `client_id` 申请 L0 登录
- **THEN** 系统 SHALL 直接放行登录，并把该客户端以 L0 追加进登记表

#### Scenario: 申请 L1/L2 转人工确认

- **WHEN** 未知客户端申请 L1 或 L2 登录
- **THEN** 系统 SHALL 挂起该次登录，向用户发起一次准入确认，且在得出结论前该连接 MUST NOT 执行任何写操作

#### Scenario: 用户拒绝准入

- **WHEN** 用户在确认交互中拒绝该客户端
- **THEN** 系统 SHALL 拒绝本次登录、关闭该连接，并记录一条拒绝审计；登记表 MUST NOT 新增该客户端

#### Scenario: 确认超时

- **WHEN** 准入确认在约定时限内无人应答
- **THEN** 系统 SHALL 按拒绝处理并关闭该连接

### Requirement: 已登记客户端的登录

已登记客户端登录时，系统 SHALL 按其登记项中记录的授权等级授予会话，MUST NOT 因请求中声明的等级更高而提权。

#### Scenario: 请求等级高于登记等级

- **WHEN** 一个登记为 L0 的客户端在登录时申请 L2
- **THEN** 系统 SHALL 以 L0 建立会话，并在响应中说明实际生效等级

#### Scenario: 重名客户端

- **WHEN** 两个连接以同一 `client_id` 先后登录
- **THEN** 系统 SHALL 视其为同一客户端身份，并各自建立独立会话

### Requirement: 命令授权等级划分

系统 SHALL 将业务命令归入 L0 观测、L1 调节、L2 通断三级；查询类命令属 L0，设值类属 L1，输出通断与设备连接/断开属 L2。未归级的命令 MUST 默认拒绝。

#### Scenario: 等级不足

- **WHEN** L1 会话调用 `set_on_off`
- **THEN** 系统 SHALL 拒绝且 MUST NOT 下发设备指令，响应中说明所需等级与该会话当前等级

#### Scenario: 新增命令未归级

- **WHEN** 请求的命令类型未在等级表中登记
- **THEN** 系统 SHALL 拒绝该请求，而非按已有会话等级放行

#### Scenario: 只读客户端

- **WHEN** L0 会话调用任一 L0 查询命令
- **THEN** 系统 SHALL 正常返回结果，且不要求其持有任何控制权

### Requirement: 授权判定前置于业务处理

系统 MUST 在命令分发处统一完成认证与等级判定，判定通过后才进入业务处理；业务处理器 MUST NOT 各自实现权限判断。

#### Scenario: 拒绝路径无副作用

- **WHEN** 任一写请求在授权判定处被拒绝
- **THEN** 该请求 MUST NOT 触达设备对象，也 MUST NOT 产生控制状态变更

#### Scenario: 权限与租约两道判定相互独立

- **WHEN** 一个具备 L2 等级但不持有控制权的会话发起写请求
- **THEN** 系统 SHALL 因控制权原因拒绝，并说明其等级本身是足够的

### Requirement: 准入确认在无界面模式下降级

服务以 `--no-gui` 运行时不存在可应答的交互入口，系统 SHALL 只允许 L0 自动准入，对 L1/L2 的准入请求 MUST 直接拒绝。

#### Scenario: 无界面时申请写权限

- **WHEN** `--no-gui` 模式下未知客户端申请 L1 登录
- **THEN** 系统 SHALL 拒绝并在响应中说明需预先写入登记表或以带界面方式确认

### Requirement: 授权判定审计

系统 SHALL 为每一次授权判定输出一条结构化审计记录，内容至少包括时间、`client_id`、命令类型、判定结果；被拒记录 MUST 包含拒绝原因。

#### Scenario: 放行记录

- **WHEN** 一个已认证会话的 L1 写请求通过判定
- **THEN** 系统 SHALL 记录该次判定为通过，并携带其生效等级

#### Scenario: 拒绝记录

- **WHEN** 请求因未登录、等级不足、控制权被占或客户端被拒而失败
- **THEN** 系统 SHALL 记录对应拒绝原因，使事后可以回答"谁在什么时候想做什么被挡住"

#### Scenario: 准入决定记录

- **WHEN** 用户对一次准入确认作出同意或拒绝
- **THEN** 系统 SHALL 记录该人工决定及其对应的 `client_id` 与申请等级
