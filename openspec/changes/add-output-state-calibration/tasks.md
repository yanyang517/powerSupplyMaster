# Tasks

## 1. 实施准备

- [x] 1.1 在独立 git worktree 的功能分支实施本变更，不直接修改 `master`；验证 `git branch --show-current` 不是 `master`，并记录实际 worktree 路径与分支名。

## 2. 设备与模型输出查询

- [x] 2.1 为 SCPI 命令发送增加可选超时，并使 `get_on_off` 严格解析 `ON` / `OFF`、拒绝乱码；在 `src/device/test_scpi_power_supply.py` 覆盖两种合法响应、非法响应、超时和默认超时仍为 1 秒。
- [x] 2.2 在 `PowerSupplyModel` 暴露带校准超时的输出状态查询；用模型测试验证查询参数正确传给设备层，且不改变现有 V/I 查询路径。

## 3. Presenter 输出状态与校准

- [x] 3.1 在 Presenter 引入 `bool | None` 三态输出状态和统一发布入口；用纯 Presenter 测试验证初始为未知、成功回读发布 `ON` / `OFF`、失败发布未知。
- [x] 3.2 实现连接后立即校准、每 1 秒周期校准、单一在途查询和断开取消；用可控假模型与时钟验证立即查询、周期次数、重复连接不叠加任务、断开后无迟到更新。
- [x] 3.3 将输出切换改为“检查已确认状态 → 控制权确认 → 重新取最新状态 → 写入 → 立即回读”，并用输出操作锁串行化校准与切换；扩展 `src/presenter/test_takeover_gate.py` 覆盖取消接管、写后回读、回读失败和旧校准不覆盖新写。
- [x] 3.4 将输出校准失败与 V/I 采样失败通道隔离；扩展 `src/presenter/test_sampling_robustness.py` 和 `test_recording_wiring.py`，验证输出查询失败不终止采样、不增加每轮 V/I 读取、不改变记录成对语义。

## 4. 主窗口与悬浮窗接线

- [x] 4.1 在主窗口增加统一输出状态渲染，按钮点击只发送切换请求，未连接或未知时禁用并显示“输出状态不可用”；扩展 `src/views/test_connection_state.py` 和 `test_main_window_icons.py` 验证文字、勾选态、图标与禁用状态一致。
- [x] 4.2 将悬浮窗输出信号改为无参数切换请求，菜单按已确认状态显示“关闭输出”或“开启输出”，未知时禁用；重写 `src/views/test_floating_actions.py` 覆盖两种动态文案、信号落点、禁用态和三个动作互不串线。
- [x] 4.3 更新 `src/resources/NOTICE.md` 中电源图标对应的悬浮窗菜单说明；验证文档不再把该菜单描述为固定“关闭电源输出”。

## 5. 集成与回归

- [x] 5.1 使用仓库 `.venv` 运行设备、Presenter 和视图相关测试：`.venv/Scripts/python.exe -m pytest src/device/test_scpi_power_supply.py src/presenter/test_takeover_gate.py src/presenter/test_sampling_robustness.py src/presenter/test_recording_wiring.py src/views/test_floating_actions.py src/views/test_connection_state.py src/views/test_main_window_icons.py`，验证全部通过。
- [x] 5.2 用 COM8↔COM9 模拟器验证远程 `set_on_off` 改变输出后，下一个 1 秒校准周期内主窗口按钮与悬浮窗菜单同步；制造一次 `OUTP?` 超时，验证输出进入未知而 V/I 显示继续。
- [x] 5.3 运行至少 30 分钟模拟器压力回归，记录 V/I 周期分布、输出查询超时次数和记录缺口；验证 500ms 标称采样没有因校准出现新增系统性缺口。
- [x] 5.4 运行完整测试套件和 `openspec validate add-output-state-calibration --strict`；验证无回归且变更规划严格校验通过。

## Workflow follow-up

- 实机发布前按项目既有 bench 流程执行长时采样验收，确认输出校准没有引入新的通信缺口。
- 满足项目评审与合并要求后，使用非 fast-forward 合并保留变更拓扑。
