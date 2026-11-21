# Spec Delta

## Purpose

定义电源控制服务（SocketServer）对设置类命令的动态限值校验、限值查询与连接状态错误语义，使 GUI、MCP 桥与任何 TCP 客户端共享同一套保护行为。

## ADDED Requirements

### Requirement: 设置命令受动态限值约束
SocketServer SHALL 维护电压与电流两项运行时限值；`set_voltage` / `set_current` 请求值超出 `0 ≤ value ≤ 限值` 范围时 MUST 拒绝执行、不向设备下发 SCPI 命令，并返回 `status="error"` 且 message 中包含允许范围。

#### Scenario: 超限电压被拒绝
- **WHEN** 客户端发送 `set_voltage` 且值大于电压限值
- **THEN** 返回 `status="error"`，message 包含允许上限
- **AND** 设备输出电压保持不变

#### Scenario: 边界值允许
- **WHEN** 客户端发送 `set_voltage` 且值恰等于限值
- **THEN** 请求被接受并正常下发

### Requirement: 限值来自服务启动参数
系统 SHALL 支持通过应用启动参数配置电压/电流限值（含合理默认值），GUI 与 `--no-gui` 模式使用同一配置来源；UI 侧限值编辑入口不在本需求范围内。

#### Scenario: 启动参数指定限值
- **WHEN** 应用以自定义限值参数启动
- **THEN** 后续所有 `set_voltage` / `set_current` 校验按该限值执行

#### Scenario: 未指定时使用默认值
- **WHEN** 应用启动时未提供限值参数
- **THEN** 使用内置默认限值并同样强制执行

### Requirement: 限值可经 setting_query 查询
SocketServer SHALL 注册 `setting_query` 请求处理，返回当前生效的电压限值与电流限值，供客户端（含 MCP 桥的 `get_status` 聚合）展示允许范围。

#### Scenario: 查询当前限值
- **WHEN** 客户端发送 `setting_query`
- **THEN** 响应包含电压限值（V）与电流限值（A）

### Requirement: 设备未连接时的请求返回明确错误
当设备串口未连接时，所有依赖设备的请求（设置与查询类）MUST 返回 `status="error"` 且 message 明确指示"设备未连接"；系统 MUST NOT 返回掩盖失败的 `status="success"` 响应。

#### Scenario: 未连接时查询电压
- **WHEN** 串口未连接而客户端发送 `voltage_query`
- **THEN** 返回 `status="error"`，message 指示设备未连接

#### Scenario: 未连接时设定电压
- **WHEN** 串口未连接而客户端发送 `set_voltage`
- **THEN** 返回 `status="error"`，不发生任何串口写入

### Requirement: open_device 如实报告连接结果
`open_device` 处理 MUST 依据实际连接结果返回响应：连接成功返回 `status="success"` 并携带设备标识；失败返回 `status="error"` 并携带失败原因。

#### Scenario: 串口打开失败
- **WHEN** 客户端 `open_device` 指定的串口不存在或无法打开
- **THEN** 返回 `status="error"` 且 message 包含失败原因
