# mcp-bridge Specification

## Purpose
让本机 AI 客户端通过 MCP（stdio）以语义化工具读取和控制电源设备，作为常驻 SocketServer 的轻量桥接层，并保证错误与限值信息以 AI 可自助修正的方式呈现。

## Requirements

### Requirement: MCP 进程由 AI 客户端拉起且不管理设备生命周期
系统 SHALL 提供一个以 stdio 方式运行的 MCP server 进程，由 AI 客户端配置命令行按需拉起与终止。该进程 MUST NOT 打开或关闭串口，MUST NOT 在退出时改变电源输出状态或发送任何清理指令。

#### Scenario: 进程正常退出
- **WHEN** AI 客户端终止 MCP 进程
- **THEN** 电源设备的输出状态与电压/电流设定保持不变
- **AND** SocketServer 继续为其他客户端（GUI、测试）服务

#### Scenario: 宿主应用未运行
- **WHEN** MCP 进程尝试连接 SocketServer 而应用（server）未启动
- **THEN** 工具调用返回包含"电源控制应用未运行，请启动 powerSupplyMaster"提示的错误信息
- **AND** MCP 进程本身不崩溃，可在应用启动后的后续调用中恢复工作

### Requirement: 提供 get_status 聚合状态工具
MCP server SHALL 暴露 `get_status` 工具，一次性返回电压读数、电流读数、输出开关状态及设备标识（*IDN），并在服务端限值可用时附带当前生效的电压/电流限值范围。该工具为只读，MUST NOT 改变设备状态。

#### Scenario: 设备已连接时查询
- **WHEN** AI 调用 `get_status` 且设备已在 UI 中连接
- **THEN** 返回电压（V）、电流（A）、输出状态（ON/OFF）与设备标识

#### Scenario: 设备未连接时查询
- **WHEN** AI 调用 `get_status` 且设备未连接
- **THEN** 返回明确提示"设备未连接，请在 UI 中连接串口"的错误信息

### Requirement: 提供 set_voltage 与 set_current 设定工具
MCP server SHALL 暴露 `set_voltage`（单位 V）与 `set_current`（单位 A）工具，将请求转发给 SocketServer 并如实回传服务端结果。工具的参数描述 MUST 说明允许范围以 `get_status` 返回的限值为准、超限请求将被拒绝。

#### Scenario: 范围内的设定
- **WHEN** AI 调用 `set_voltage` 且值在服务端限值内
- **THEN** 设定成功并返回生效值

#### Scenario: 超出限值的设定
- **WHEN** AI 调用 `set_voltage` 且值超出服务端限值
- **THEN** 返回的失败信息 MUST 包含允许的取值范围，使 AI 无需额外查询即可重试合规值

### Requirement: 提供 set_output 输出开关工具
MCP server SHALL 暴露 `set_output` 工具用于接通或断开电源输出，并在工具描述中提示该操作直接带电、应先通过 `get_status` 确认当前状态。

#### Scenario: 开启输出
- **WHEN** AI 调用 `set_output(true)` 且设备已连接
- **THEN** 输出接通，返回当前输出状态

#### Scenario: 设备未连接时操作
- **WHEN** AI 调用 `set_output` 且设备未连接
- **THEN** 返回"设备未连接"引导信息，不产生设备侧副作用

### Requirement: 桥接层错误映射
MCP 桥 SHALL 将 SocketServer 返回的错误响应与传输层异常统一映射为 AI 可读的工具错误信息，保留服务端 message 原文并补充可执行的下一步建议；MUST NOT 将失败静默报告为成功。

#### Scenario: 服务端返回 error 状态
- **WHEN** SocketServer 对请求返回 `status="error"`
- **THEN** 对应 MCP 工具调用以失败结果返回，内容包含服务端 message
