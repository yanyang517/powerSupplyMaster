# Proposal

## Why

悬浮窗的输出菜单目前只会发送一次“关闭输出”，既不能随设备实际状态切换，也没有连接门控；主窗口按钮、悬浮窗状态和远程客户端操作之间缺少统一、可信的输出状态。结果是用户可能看到相反的下一步动作，或在未连接时触发无效写操作。

## What Changes

- 新增统一的输出控制状态：`ON`、`OFF`、`UNKNOWN`，以设备 `OUTP?` 的成功回读作为实际状态来源。
- 悬浮窗右键菜单由固定的“关闭电源输出”改为动态开关：`ON` 时显示“关闭输出”，`OFF` 时显示“开启输出”。
- 主窗口输出按钮与悬浮窗菜单共用同一状态；未连接或状态未知时禁用输出操作。
- 连接成功后立即校准一次，随后每 1 秒校准一次；本机切换输出后立即回读，不等待周期任务。
- 校准失败只使输出状态变为未知，不终止电压/电流采样、不伪造状态，也不影响记录。
- 保留现有远程控制权接管确认；本机常规切换不新增二次确认。
- 不改变电压/电流 500ms 采样周期，不把输出校准塞进每一轮 V/I 采集。
- 本次不处理“隐藏悬浮窗后恢复”的入口问题，也不扩展远程事件通知。

## Capabilities

### New Capabilities

- `ui/output-control`: 定义面板输出开关的动态动作、设备实际状态校准、失败语义，以及主窗口与悬浮窗之间的状态一致性。

### Modified Capabilities

无。现有 `ui/live-curve` 与 `recording/data-capture` 的 V/I 采集和记录约束保持不变；输出校准作为独立只读通道，不改变这些能力的要求。

## Impact

- 影响 `src/device/scpi_power_supply.py`、`src/presenter/model.py`、`src/presenter/presenter.py` 的输出查询、写后回读和校准任务。
- 影响 `src/views/main_window.py`、`src/views/floating_window.py` 的输出状态渲染、菜单动作和连接门控。
- 影响 `src/views/test_floating_actions.py`、Presenter 采样与接管测试，并新增输出校准的状态同步、失败隔离和并发回归测试。
- 不新增第三方依赖，不修改 SCPI 协议或远程 API，不改变控制权归属规则。
