# Tasks

## 1. 独立工作目录

- [x] 1.1 从最新 master 创建独立 git worktree，并在其中创建修复分支 `fix/gate-waveform-refresh-on-display-toggle`；通过 `git branch --show-current` 确认当前分支不是 master，并通过 `git worktree list` 确认后续工程文件修改均在该 worktree 中完成。

## 2. 波形显示门控与视图测试

- [x] 2.1 在 `src/views/main_window.py` 的 `_update_chart_data()` 入口增加 `groupBox_8.isChecked()` 门控，确保返回发生在数据计数、列表裁剪、序列替换和坐标轴更新之前；手动或自动化验证未勾选时读数更新而曲线快照不变，勾选后电压和电流曲线均恢复更新。
- [x] 2.2 调整 `src/views/test_live_curve_window.py` 中现有滚动窗口用例的前置状态，显式勾选“显示波形”；运行 `./.venv/Scripts/python.exe -m pytest src/views/test_live_curve_window.py -q`，确认有界窗口、滚动和最新点测试全部通过。
- [x] 2.3 在同一测试文件新增显示开关测试，覆盖默认未勾选且两个图表视图禁用、复选框本身可操作、暂停时曲线点数/数据计数/坐标轴不变、读数与悬浮窗继续更新、取消勾选后快照不变，以及重新勾选后只追加后续采样；运行 `./.venv/Scripts/python.exe -m pytest src/views/test_live_curve_window.py -q`，确认新增用例全部通过。

## 3. 采样与记录回归验证

- [x] 3.1 在 worktree 中运行 `./.venv/Scripts/python.exe -m pytest src/presenter/test_sampling_robustness.py src/presenter/test_recording_wiring.py -q`；确认单次失败恢复、成对采样、每轮读取次数和记录行数断言全部通过，证明波形门控未改变采样或记录链路。
- [x] 3.2 运行 `./.venv/Scripts/python.exe -m pytest src/views src/presenter -q` 作为相关模块集成回归；记录实际结果并确认没有因默认未勾选状态导致既有视图或 Presenter 测试失败。

## 4. 审核与合入

- [x] 4.1 审核最终差异，确认工程改动仅包含波形视图门控和对应测试，未修改 `.ui`、Presenter、服务端、协议或依赖；运行 `openspec validate gate-waveform-refresh-on-display-toggle --strict`，确认变更文档严格校验通过。
- [x] 4.2 在相关测试通过并完成差异审核后提交修复，使用 `git merge --no-ff fix/gate-waveform-refresh-on-display-toggle` 合入 master；通过 `git log --merges -1` 确认生成合并提交，并通过 `git status` 确认主工作区无未提交改动。

## Workflow follow-up

- 项目评审要求满足后归档本变更，并确认归档后的主规格包含新增的波形显示开关要求。
- 不执行推送或发布，除非用户随后明确授权。
