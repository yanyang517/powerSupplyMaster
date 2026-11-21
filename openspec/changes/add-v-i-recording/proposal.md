# Proposal

## Why

面板每 0.5 秒轮询到的电压/电流目前只活在内存里：曲线滚动窗口只留 100 点，x 轴是"第几次采样"而不是时间，进程一退数据就没了（`src/views/main_window.py:40-43`、`_update_chart_data` 写入 `src/views/main_window.py:452`）。调一次电源想回头看某个瞬间发生了什么，只能靠截图。需要一个"用户使能后把 V/I 记录落盘、并支持复看曲线"的能力。

## What Changes

- 新增记录使能开关，默认关闭，状态持久化；开启后把面板轮询到的 `(时间戳, 电压, 电流)` 按周期追加写入 CSV。
- 以**连接会话**为切分单位：一次"使能且设备已连接"期间 = 一个 CSV 文件；断开、关闭使能、关窗都结束当前会话，并写入 `records/index.json` 会话清单。
- 新增"记录"页：左侧会话列表，右侧按真实时间轴重绘电压/电流双曲线，支持框选放大与还原。
- 顺带修复两处承重缺陷，记录功能依赖它们：单次串口超时会让轮询任务静默终止（`src/device/scpi_power_supply.py:55` 抛 `TimeoutError`，`src/presenter/presenter.py:107` 只捕 `CancelledError`）；`QLineSeries` 只 append 从不裁剪，长跑必卡。
- **不做**：`--no-gui` 模式记录、远程客户端读取入账、事件标记（设定值变更/输出开关/控制权）、SQLite、多会话叠加对比、跨会话合并查询、磁盘自动清理。

## Capabilities

### New Capabilities

- `recording/data-capture`: 记录使能状态的语义、会话生命周期与切分边界、落盘格式与会话清单、采样缺口的时间语义、写盘失败处理。
- `recording/history-review`: 会话列表呈现、历史数据载入、点数抽稀与绘制、时间轴缩放与还原、已占容量统计。
- `ui/live-curve`: 面板实时采样循环与滚动曲线的行为约束——单次采集失败不得终止循环且需可见、曲线点数有界、时间基准。

### Modified Capabilities

无。`power-supply-control`、`server/client-access-control`、`server/control-lease`、`ui/window-geometry`、`mcp-bridge` 的现有需求均不变：记录不改限值校验、不改权限与控制权模型、不改窗口几何的存储内容。

## Impact

- `src/presenter/presenter.py`：采样循环容错、记录器挂点、使能与会话生命周期接线。
- `src/views/main_window.py`：滚动曲线裁剪修复、新增记录页入口（按项目约定在 Python 侧构建控件，不修改 `.ui`、不建 uic 流程）。
- 新增记录模块（采集侧写入 + 复看侧读取/抽稀）与对应单测；采集侧不引入界面依赖，便于脱机测试。
- 新增运行期产物：`config/record_settings.json`（沿用 `src/views/window_geometry.py:202` 的 version 字段 + tmp/`os.replace` 原子写范式）、`records/` 目录（需加入 `.gitignore`；打包运行时落在可执行文件同级目录）。
- 磁盘量级：0.5 s 采样 ≈ 2 行/秒 ≈ 17.3 万行/天 ≈ 7 MB/天，纯文本不压缩，v1 不清理。
- 无新增第三方依赖（标准库 `csv`/`json`/`datetime` + 已有 PySide6 QtCharts）；无 GPU 环境下历史图表关闭 series 动画。
- 不触碰 `src/server/`、`src/mcp_server/`：TCP 与 MCP 客户端的读取路径、限值校验、准入与控制权行为不受影响。
- 实施按 `openspec/config.yaml` 约定在 git worktree 分支上进行，合入 master 使用 `--no-ff`。
