# Design

## Context

采样源只有一条：`Presenter.refresh_voltage_current()`（`src/presenter/presenter.py:98`）在设备连接成功后由 `asyncio.create_task` 启动（`src/presenter/presenter.py:92`），每 0.5 秒串行发出 `MEASure:VOLTage?` 与 `MEASure:CURRent?`，把两个值分别推给 `view.update_voltage()` / `view.update_current()`，视图再写进 `QLineSeries`（`src/views/main_window.py:452`）。全链路没有时间戳，曲线横轴是采样序号。

约束条件：

- 记录被定义为面板轮询的副产品，`--no-gui`（`src/app.py:163`）与 TCP/MCP 侧的 `voltage_query`（`src/server/request_handles.py:226`）不入账，因此记录器必须留在 GUI 进程内、且不能侵入服务端。
- GUI 与 SocketServer 跑在同一个 qasync 事件循环里。任何在采样循环内做的同步阻塞都会直接体现在界面卡顿上。
- 串口访问由 `SCPI_PowerSupply` 的进程级单例 + `asyncio.Lock` 串行化。记录若自己发起读取，会把每个周期的串口往返翻倍。
- 项目既有约定：`.ui` 文件不改、不建 uic 流程，新控件在 Python 侧构建（`src/views/access_panel.py`、`src/views/dark_dial.py` 是现成范式）。
- 落盘已有可复用范式：`src/views/window_geometry.py:202` 的 version 字段 + tmp/`os.replace` 原子写 + 坏文件降级为默认值而不抛异常，以及 frozen 时配置落在可执行文件同级目录。
- 开发机无独显（避免渐变、阴影、模糊与动画开销）。

需求见 `proposal.md - Why` 与 `specs/recording/data-capture/spec.md`、`specs/recording/history-review/spec.md`、`specs/ui/live-curve/spec.md`。

## Goals / Non-Goals

**Goals:**

- 记录器与 GUI 解耦到可以脱离 Qt、脱离串口单例做单测的程度。
- 记录的正确性可验证：会话边界、缺口、崩溃恢复三类语义都有确定的实现含义，而不是"大概会这样"。
- 复看在 24 小时量级会话（约 17 万条记录）下守住响应底线，且不为此引入新依赖。
- 修复采样循环与滚动曲线两处缺陷时，不改变面板现有的控制语义与限值行为。

**Non-Goals:**

- 不为记录设计跨会话查询、聚合或索引结构；不做 SQLite 迁移路径的预先实现，只保证接口不写死 CSV。
- 不做采样时刻的时钟校正（时区变更、手工改时、NTP 回拨一律按墙钟原样记录）。
- 不改 `src/server/`、`src/mcp_server/`，不为记录新增任何 TCP/MCP 协议命令。
- 不处理波形页现有图表的背景配色与动画（`beautify-control-panel` 明确留作独立 change）。

## Decisions

### D1 记录器挂在 presenter 的采样回调点，而不是视图层或设备层

`presenter.py:101-102` 一次循环里同时拿到 V 和 I，是"一条记录 = 一个周期成对读数"这个语义的天然出处。在这里调用 `recorder.on_sample(ts_ms, voltage, current)`，视图层不碰文件 IO，设备单例不被写入侧污染，`--no-gui` 路径零影响。

曾考虑：视图层 `_update_chart_data()` 顺带写盘（把 IO 塞进 view，且 V/I 分两次进入，无法成对）；设备层拦截 `get_voltage`（会捕获远程读取，但两次调用分属不同调用方、拿不到一致的周期，且让单例设备类承担存储职责）。

### D2 CSV 逐会话分文件 + `records/index.json` 清单，不用 SQLite

0.5 s 采样 ≈ 2 行/秒 ≈ 17.3 万行/天 ≈ 7 MB/天。复看的访问模式是"整读一个会话、抽稀、画出来"，没有按条件筛选的需求，SQLite 的索引优势用不上，却会失去"直接用 Excel/pandas 打开"这条最常被用到的出路。

代价：跨会话合并对比要重扫文件；清单需要自己维护一致性。缓解：读写各自收敛在两个薄接口后面（采集侧只暴露 `on_sample` / `start` / `stop`，复看侧只暴露"列会话"与"读会话"），将来换存储不动调用方。

### D3 会话在开始时登记，结束时更新；启动时把遗留的"进行中"条目改判为中断

`records/index.json` 结构：`{"version": 1, "sessions": [{id, file, port, started_at, ended_at, rows, bytes, status}]}`，`status ∈ {recording, closed, interrupted}`。

会话一建立就原子写清单（`status=recording`），结束时改写为 `closed` 并补齐 `ended_at`/`rows`/`bytes`。这样进程被强杀后清单里仍留有可发现入口，重启时凡是 `status=recording` 的条目一律改判 `interrupted` 并按文件实际行数回填统计——这正好实现"异常退出后已落盘数据仍可复看"。曾考虑只在会话结束时写清单（实现更省，但强杀后文件成孤儿）与复看时扫描目录重建清单（会把文件命名规则变成硬契约）。

数据文件名 `records/<YYYYMMDDTHHMMSS>_<串口>.csv`（如 `20261121T132200_COM8.csv`），CSV 首行为固定列头 `ts_ms,iso_local,voltage_v,current_a`。

### D4 同步缓冲写 + 每 2 秒 flush，不引入线程或 asyncio 文件任务

单行约 40 字节的 `write()` 成本远低于 0.5 s 周期，`asyncio.to_thread` 或后台队列在这里是过度设计，还会引入关闭时序问题。风险在于 flush 抖动的尾延迟：因此 flush 周期化到每 2 秒一次（约 4 个采样），正常退出时 flush + close，异常退出最多丢最后 4 行——这已写进 D3 的可发现性设计。曾考虑每行 flush（崩溃零丢失，但每 0.5 秒一次同步 IO，在无独显的机械盘或杀软扫描下最容易拖住事件循环）；纯内存攒够再写（崩溃丢失窗口不可控）。

### D5 时间戳在成功取得成对读数之后取，记 epoch 毫秒 + 本地 ISO 两列

`ts_ms` 供绘图与排序直接使用（免解析字符串），`iso_local` 供人脱离应用判读。多一列约 20 字节/天使日增从 7 MB 涨到约 10 MB，可接受。

取"读数成功后"而不是"周期开始时"：串口往返本身是主要耗时来源，周期开始时刻会让记录时间与实际采样时刻系统性偏离。曾考虑单调时钟计数（可精确反映间隔，但脱离进程无意义）与沿用采样序号（复看必须要真实时间，直接否决）。

### D6 缺口由复看侧按间隔阈值断开，不写占位行

采集失败的周期不产生任何记录（需求"采样缺口不得补造数据"）。复看侧载入时以 `相邻 ts_ms 差 > 2.5 × 标称周期` 判定分段，每段一条独立 series，段间自然留空。曾考虑写空值占位行（污染列格式，Excel 里成片空白，且占位行的"周期"本身就是编造的）。

标称周期取自代码里的单一常量 `recording.settings.NOMINAL_INTERVAL_MS`（面板轮询延时就是由它算出的 `SAMPLE_INTERVAL_SECONDS`），不从数据反推，也不作为用户可配项：配置里放一份"改了没反应"的周期只会让阈值与实况脱节。曾打算把它做成 `record_settings.json` 的 `interval_ms`，实现后确认没有任何一侧按它改变采样，遂删掉该字段（旧文件里残留的键读到即忽略，有单测钉住）。

实现取舍：每段一条 series，所以段数就是绘图对象数。曾打算给段数封顶（`MAX_SERIES = 250`，超出只画前面这些并在读数里说明），但那直接违背需求"两条曲线覆盖该会话全部已落盘的记录"——截断掉的不是精度而是发生过的事实，于是改为不设上限，读数行改成"中断 N 次"把次数明说。实测（1200×800 窗口、offscreen）：300 段 0.075 s、3000 段 0.815 s、连续 17.3 万条无中断 0.203 s，2 秒上限内可接受的段数量级为数千；每 2 s 抖动一次的病态会话（约 4.3 万段）会越线，作为已知限制写在 Risks。

### D7 抽稀用分桶 min/max 包络，抽稀函数与实时曲线的窗口裁剪共用一个纯函数模块

按绘图区像素列分桶，每桶输出最小值与最大值两点，横轴取桶内首末记录时刻。800 px 宽下约 1600 点，既流畅又不吞掉单点毛刺——而单点毛刺正是电源曲线要看的对象，所以等间隔跳点被否决。

桶数按段长在全局预算内分配，段多时每段至少留 2 点，因此总点数下界是 `2 × 段数`（实现见 `HistoryChartView.plot`：`share = max(2, buckets * len(segment) // total)`）：连续会话的点数只随宽度定，抖动到上千段时才随段数涨。放大后区间内回到原始点密度，实测 10 分钟窗口 1201 点对 1201 条样本。

同一模块提供"把 series 限制在 N 点内"的裁剪能力，供实时曲线修掉 `main_window.py:459/479` 只 append 的问题。抽稀与裁剪都写成不依赖 Qt 输入输出为 `(ts_ms, value)` 序列的纯函数，便于直接断言。

### D8 载入采用分块 cooperative 读取，不用线程

整读一次 24 小时会话约 270 ms，同步做其实够用，但"载入期间无指示地冻结"是需求红线。实现为：读入固定行数（如 2 万行）→ 更新进度 → `await asyncio.sleep(0)` 让出循环 → 继续。这样在 qasync 单循环下既不需要线程与锁，又能保证进度指示真的刷得出来。抽稀在累积完全量后一次做，避免边读边重算包络。

### D9 复看页作为代码构建的新 tab，不改 `.ui`

新增 `src/views/record_panel.py`：`QWidget` + 左侧 `QListWidget` 会话列表、右侧两个 `QChartView`、顶部使能开关与状态标签。挂载方式沿用 `AccessPanel` 的思路，在 `MainWindow.setupUi()` 里 `self.ui.tabWidget.addTab(...)`，而不是新增 `.ui` 页——项目无 `.ui → _ui.py` 生成脚本，已提交的生成文件为适配 PySide6 严格枚举手工改过，动 `.ui` 会重开那件事。

使能开关放在记录页内而非全局工具栏：它是低频设置，且与记录状态、故障提示、容量统计同属一个关注面。曾考虑放在"波形"页里做成实时/历史模式切换（少一个 tab，但两种 x 轴语义共用一套控件会让状态机变脏）。

### D10 使能状态存 `config/record_settings.json`，沿用现有原子写范式

内容 `{"version": 1, "enabled": false, "dir": "records"}`——只有这两项真的是用户可控的状态，采样周期是代码常量（见 D6）。读写复用 `window_geometry.py` 已验证的写法（原子替换、字段校验失败即回落默认、frozen 时落在 exe 同级）。记录目录默认 `<repo>/records`。曾考虑 `QSettings`（与项目既有 JSON 范式不一致，且注册表里的状态不便用户自查）。

### D11 历史图表显式设背景并关闭动画，波形页图表维持现状

`QChart` 自绘背景、不吃应用 QSS 与 QPalette，所以复用的新建图表要从 `src/views/theme.py` 的 `TOKENS['dark']` 取色显式设置 `backgroundBrush`/轴与标题颜色，并显式设 `QChart.NoAnimation`（默认即无动画，写出来是为了让它成为可断言的意图而不是巧合）。波形页那两个图表的背景与 `SeriesAnimations` 属既有欠账，本 change 不动，避免把主题 change 的范围卷进来。

两层背景都要管：`QChartView` 是 `QGraphicsView`，图表画布之外那一圈仍归它自己的 `backgroundBrush` 与 `chart.margins()` 决定。实测只给 chart 设色的话，截图四周会留一圈系统浅灰（`#efefef`）；因此视图层底色同样设成 `plate`，并把 `chart.setMargins(0,0,0,0)`。

序列色取自 token 表（电压用 `danger`、电流用 `primary`），与实时曲线的红/蓝同序，避免在 `TOKENS` 之外出现第二套配色。

### D12 采样循环改为"捕获异常、计入连续失败、置界面异常态、继续循环"

`refresh_voltage_current()` 的 `try/except` 从只捕 `CancelledError` 扩为：`CancelledError` 照常退出；其他异常记录日志、递增连续失败计数、按计数驱动视图的通信异常指示，成功一次即清零并撤掉指示。串口断开这类不可恢复错误仍由 `disconnect` 路径结束会话，不在循环里自作主张重连。

曾考虑给循环加外层守护任务（失败就重建 task，改动更局部，但会掩盖真实的取消语义并使会话结束时机难以确定）。

## Risks / Trade-offs

- **无 GPU + 单事件循环下同步 IO 抖动** → flush 周期化（D4）、抽稀后点数控制在约 2 千（D7）、载入分块让出循环（D8）；实测以 24 小时会话为基准。
- **中断极多时段数不受上限约束，绘图对象随段数涨** → 已知限制：实测 3000 段 0.815 s 仍在 2 秒内，量级到上万段（例如每 2 秒抖一次的 4.3 万段）会越线。取舍是"宁可慢也不藏起落过盘的中断"；真要处理这种会话，方向是把段合并成一次 scatter 绘制而不是回头加截断。
- **CSV 被外部程序（Excel）占用导致写入失败** → 按需求"记录故障不伤及控制与显示"处理：停记录、明示原因，绝不重试成环；清单不登记零记录会话。
- **系统时钟被改或回拨，时间轴错乱** → 复看侧按 `ts_ms` 排序而非文件行序，使乱序写入仍可读出；时钟跳变在图上表现为缺口或重叠，本设计不做校正，作为已知限制。
- **一次长实验因短暂掉线被切成多个会话，趋势被打断** → 这是"连接期是唯一诚实边界"的有意取舍；用户要看连续趋势时保持连接即可，跨会话叠加对比已列为后续。
- **修 `QLineSeries` 裁剪会改变实时曲线的观感** → 需求"滚动曲线点数有界"是新增约束，窗口宽度沿用现有 100 点；若实测观感变化明显，只调窗口宽度而不放宽上界。
- **清单与实际文件不一致（手工删文件、拷盘）** → 复看列表以清单为主、逐个校验文件存在性，缺失条目标记为不可用而不是直接从列表消失。

## Migration Plan

无数据迁移：功能默认关闭，不产生文件，`records/` 与 `config/record_settings.json` 均为运行期产物并加入 `.gitignore`。

回滚：关闭使能即停止产生数据；代码回退不影响既有 `records/` 内容，历史 CSV 仍可被任何表格工具打开。已落盘会话在功能移除后只是不可复看，不丢数据。

## Open Questions

- 记录页是否需要"打开记录目录"的快捷入口，等实际用起来再定。
- 复看时是否要把面板设定值（`VOLTage`/`CURR` 设定）作为水平参考线叠上去——需要事件侧数据，属本 change 明确排除的范围。
