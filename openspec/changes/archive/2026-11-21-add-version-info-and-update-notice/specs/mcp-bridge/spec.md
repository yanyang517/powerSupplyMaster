# Spec Delta

## MODIFIED Requirements

### Requirement: 提供 get_status 聚合状态工具
MCP server SHALL 暴露 `get_status` 工具，一次性返回电压读数、电流读数、输出开关状态及设备标识（*IDN），并在服务端限值可用时附带当前生效的电压/电流限值范围与服务端运行实例的应用版本。该工具为只读，MUST NOT 改变设备状态。

#### Scenario: 设备已连接时查询
- **WHEN** AI 调用 `get_status` 且设备已在 UI 中连接
- **THEN** 返回电压（V）、电流（A）、输出状态（ON/OFF）与设备标识

#### Scenario: 返回上位机版本
- **WHEN** AI 调用 `get_status` 且服务端限值可用
- **THEN** 返回值包含服务端应用版本号

#### Scenario: 设备未连接时查询
- **WHEN** AI 调用 `get_status` 且设备未连接
- **THEN** 返回明确提示"设备未连接，请在 UI 中连接串口"的错误信息
