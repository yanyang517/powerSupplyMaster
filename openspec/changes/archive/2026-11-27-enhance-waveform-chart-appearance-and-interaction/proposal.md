# Proposal

## Why

波形页目前直接使用 `QChartView` 的默认黑色，没有采用记录页统一的深色底板 token；已有悬浮提示使用白底英文文案，且缺少缩放能力。实时数据持续推动横轴，使局部细节难以查看，因此需要统一视觉并补充可逆、不干扰采样的图表交互。

## What Changes

- 电压和电流实时图表的画布与视图背景统一使用主题 `plate` 深色，并与记录页保持一致的标题、刻度、网格和提示配色。
- 在图表绘图区内按住 Ctrl 滚动鼠标滚轮时，以鼠标在横轴上的对应位置为中心只缩放 X 轴；按住 Shift 滚动时只缩放 Y 轴。电压、电流图表独立操作，同时按下两个修饰键时 Ctrl 优先。
- 用户执行 X 轴缩放后暂停该图表横轴的自动跟随，但继续保留有界滚动窗口并更新曲线；Y 轴缩放不改变横轴自动跟随状态。双击图表恢复双轴默认坐标范围和实时跟随。
- 鼠标靠近采样点时显示深色提示，内容包括采样点序号、当前数值和单位；鼠标离开绘图区或没有邻近采样点时隐藏提示。
- 无修饰键滚轮、设备采样、读数、悬浮窗、采集中断提示、记录和“显示波形”开关行为保持不变。
- 本次不加入拖拽平移、跨图联动缩放、缩放状态持久化或时间戳横轴，不修改 `.ui` 和记录页。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `ui/live-curve`: 增加实时图表的深色视觉要求、分轴滚轮缩放与复位要求、邻近采样点提示要求，并明确交互不得改变采样和记录。

## Impact

- 视图实现：`src/views/main_window.py`，以及承载实时图表视图交互的 Python 控件。
- 测试：扩展 `src/views/test_live_curve_window.py`，覆盖背景、滚轮分轴缩放、自动跟随暂停/恢复和邻近点提示。
- 主题：复用 `src/views/theme.py` 的现有 token，不新增依赖或硬编码主题色。
- 不修改 Presenter、设备服务、SCPI 协议、记录页、`.ui` 或既有数据格式。
- 规划产物位于独立 worktree `D:/git/wt/waveform-chart-appearance-and-interaction` 的分支 `feature/enhance-waveform-chart-appearance-and-interaction`，避免污染主工作区。
