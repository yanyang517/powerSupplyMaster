# Tasks

## 1. 实时图表视图与深色主题

- [x] 1.1 新增 `src/views/live_chart_view.py`，实现 `LiveChartView` 的基础构造，使用主题 token 设置 chart/view 双层 `plate` 背景、标题、轴线、网格、标签和曲线色；在 `src/views/test_live_curve_window.py` 增加两张实时图表背景与可辨识配色测试，并运行该文件确认通过。
- [x] 1.2 在 `LiveChartView` 实现 `replace_points()`、`follow_latest()` 和默认横纵轴范围，保持 100 点滚动窗口与采样序号语义；增加初始范围、自动跟随和点数有界测试，运行 `./.venv/Scripts/python.exe -m pytest src/views/test_live_curve_window.py -q` 确认通过。

## 2. 滚轮缩放与视口复位

- [x] 2.1 实现 Ctrl + 滚轮只缩放 X 轴、Shift + 滚轮只缩放 Y 轴，使用鼠标在目标轴上的位置作为锚点、Qt 坐标映射、1.2 级进比例和目标轴跨度边界，同时按下时 Ctrl 优先；增加 Ctrl、Shift、滚轮方向、目标轴锚点、非目标轴不变、双键优先、无修饰键和连续缩放边界测试，运行 `./.venv/Scripts/python.exe -m pytest src/views/test_live_curve_window.py -q` 确认通过。
- [x] 2.2 实现两张图独立缩放、仅横轴缩放暂停横轴自动跟随、纵轴缩放保持实时跟随，以及双击恢复双轴默认范围和实时跟随；增加两张图互不影响、Ctrl 缩放后追加采样不移动横轴视口、Shift 缩放后横轴继续跟随、双击恢复后重新跟随测试，运行同一测试文件确认通过。

## 3. 邻近采样点提示

- [x] 3.1 在 `LiveChartView` 实现基于屏幕距离的最近采样点查找和深色悬浮提示，显示采样序号、两位小数值与单位，并在远离采样点、离开绘图区、数据替换和图表禁用时隐藏；增加近点显示、远点隐藏、离开隐藏、更新后隐藏和禁用态测试，运行 `./.venv/Scripts/python.exe -m pytest src/views/test_live_curve_window.py -q` 确认通过。

## 4. 接入主窗口并移除旧交互

- [x] 4.1 将 `src/views/main_window.py` 的重复图表创建替换为两个 `LiveChartView`，保留现有 chart、series、axis 属性别名，并把数据更新接入 `replace_points()` / `follow_latest()`；删除旧白底提示标签和 `hovered` 查点处理，保持 `.ui`、Presenter 和显示波形门控不变；运行既有滚动窗口、波形开关和中断指示测试确认全部通过。
- [x] 4.2 增加主窗口级交互回归测试，确认缩放、复位和悬浮提示不改变电压/电流读数、悬浮窗、采样点计数和曲线有界窗口；运行 `./.venv/Scripts/python.exe -m pytest src/views/test_live_curve_window.py -q` 确认通过。

## 5. 集成回归与变更校验

- [x] 5.1 运行 `./.venv/Scripts/python.exe -m pytest src/views src/presenter -q`，确认实时图表交互未破坏记录页、采样鲁棒性和记录接线；核对实际测试结果并处理本次改动引入的失败。
- [x] 5.2 审核最终差异，确认未修改 `.ui`、Presenter、服务端、协议、依赖或记录页；运行 `openspec validate enhance-waveform-chart-appearance-and-interaction --strict`，确认变更文档严格校验通过。

## Workflow follow-up

- 项目评审要求满足后归档本变更，并确认归档后的主规格包含新增的图表外观、缩放、复位和提示要求。
- 实施分支合入 master 时使用 `git merge --no-ff`，并确认保留合并提交。
- 不执行推送或发布，除非用户随后明确授权。
