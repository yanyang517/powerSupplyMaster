# Spec Delta

## MODIFIED Requirements

### Requirement: 限值可经 setting_query 查询
SocketServer SHALL 注册 `setting_query` 请求处理，返回当前生效的电压限值与电流限值，并返回服务端运行实例的应用版本，供客户端（含 MCP 桥的 `get_status` 聚合）展示允许范围与上位机版本。该查询 MUST NOT 依赖设备串口已连接。

#### Scenario: 查询当前限值
- **WHEN** 客户端发送 `setting_query`
- **THEN** 响应包含电压限值（V）与电流限值（A）

#### Scenario: 响应包含应用版本
- **WHEN** 客户端发送 `setting_query`
- **THEN** 响应包含与运行实例一致的应用版本号

#### Scenario: 设备未连接时仍可查询
- **WHEN** 串口未连接而客户端发送 `setting_query`
- **THEN** 响应仍为 `status="success"` 并携带限值与版本
