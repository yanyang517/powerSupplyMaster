# Tasks

按 `openspec/config.yaml` 的约定，实现须在 git worktree 的独立工作目录中进行，合入 master 使用 `git merge --no-ff`。测试沿用仓库既有布局（被测模块同目录 `test_*.py`）。

补记：3.x/4.x 各条原先写的"验证：单测…"在核对时只有 `recording/test_settings.py`、`recording/test_processing.py`、`presenter/test_sampling_robustness.py` 真的存在，`test_recorder.py`、`test_reader.py`、`test_record_panel.py`、`test_recording_wiring.py` 是后补的（25 + 20 + 34 + 18 个用例），补的过程中改掉了四处与 spec 不符的实现：首帧不扫列表、时长与"记录中"会话的进度总量没根据盘上事实给、复看不按 `ts_ms` 排序、中断段被 250 段上限截断。

## 1. 准备工作目录与模块骨架

- [x] 1.1 为 `add-v-i-recording` 用 `git worktree` 建立独立工作目录并在其上创建功能分支，验证：`git worktree list` 输出含该目录，且 `git -C <worktree> branch --show-current` 显示功能分支
- [x] 1.2 新建 `src/recording/` 模块骨架（配置读写、recorder、reader、采样加工四个文件）并可被导入，验证：在该工作目录下 `python -c "import recording"` 无错误
- [x] 1.3 为运行期产物补 `.gitignore` 条目（`records/`、`config/record_settings.json`），验证：生成一次记录后 `git status --porcelain` 不出现这些路径

## 2. 采样循环健壮化（specs/ui/live-curve）

- [x] 2.1 在 `presenter.refresh_voltage_current()` 把只捕 `CancelledError` 改为：取消照常退出、其他异常记录日志并继续下一周期（设计 D12），验证：新增单测用会在第 2 次 `get_voltage()` 抛 `asyncio.TimeoutError` 的假 model，断言循环随后仍产出第 3 个周期的样本
- [x] 2.2 加入连续失败计数与面板通信异常指示，成功一次即清零并撤除指示，验证：单测断言失败阈值前后视图状态变化（`presenter/test_sampling_robustness.py::TestSamplingFailureIsVisible`，阈值前不推异常、越过阈值只推一次、成功即清除）。台架上杀模拟器肉眼确认指示出现与消失属在环项，并入 5.1
- [x] 2.3 抽出"把序列限制在窗口上限内"的纯函数并让 `MainWindow._update_chart_data()` 的电压/电流两条 `QLineSeries` 使用它（修掉只 append 不裁剪），验证：单测向实时通路喂 5000 点，断言 `series.count()` 不超过窗口上限且横轴范围随之前移
- [x] 2.4 确认记录与实时显示共用同一次采集、记录侧不发起额外设备读取，验证：单测以计数桩替换 model，断言使能记录前后每个周期的 `get_voltage()`/`get_current()` 调用次数相同

## 3. 记录落盘（specs/recording/data-capture）

- [x] 3.1 实现 `config/record_settings.json` 读写：version 字段、默认关闭、tmp/`os.replace` 原子写、坏内容回落默认而不抛异常，frozen 时落在可执行文件同级（复用 `window_geometry.py` 范式，设计 D10），验证：单测覆盖缺文件、非法 JSON、版本不符、字段缺失四种情形均返回"关闭"默认值。落盘字段只有 `enabled` 与 `dir`：`interval_ms` 曾作为配置项，实现后确认没有任何一侧按它改变采样，已删除并由单测钉住"旧文件里残留该键读到即忽略"
- [x] 3.2 实现会话 CSV 写入：固定列头 `ts_ms,iso_local,voltage_v,current_a`、一个周期一条成对记录、读数不完整时不写半条、失败周期不写任何占位行（设计 D5），验证：单测在临时目录喂入含一次不完整读数的样本序列，断言文件行数与内容逐列相符
- [x] 3.3 实现会话生命周期与 `records/index.json` 登记：建立会话即以 `recording` 落清单，结束改写 `closed` 并补 `ended_at`/`rows`/`bytes`，零记录会话不登记且不留空文件（设计 D3），验证：单测断言三种路径（正常结束、未采到数据、断开重连产生第二条会话）的清单与文件名结果
- [x] 3.4 实现缓冲写与周期性 flush（每 2 秒）及退出时 flush+close（设计 D4），验证：单测用可控时钟驱动 100 个采样周期，断言 flush 次数为预期量级且关闭后行数完整
- [x] 3.5 实现启动时对遗留 `recording` 条目的改判：按文件实际行数回填统计并标 `interrupted`，数据文件保持可用（设计 D3），验证：单测预置"清单记 500 行、文件实有 320 行"的现场，断言重启后条目为 `interrupted` 且 `rows=320`
- [x] 3.6 实现写盘失败处理：目录不可创建/不可写时停止记录、向上报出原因，且不中断采样与控制（设计 D4 风险项），验证：单测 monkeypatch 使写入抛 `OSError`，断言 recorder 转为停止态、原因可见、presenter 采样循环继续
- [x] 3.7 把 recorder 接入 presenter：连接成功且使能时开录，断开、关闭使能、关窗三种路径各自结束当前会话（设计 D1），验证：单测用假 model 跑完"连接—采样—断开"，断言生成一份 CSV 与一条 `closed` 清单条目
- [x] 3.8 在 `config/` 使能开关与未连接待命语义接线：使能但未连接不建文件，连接成功后自动开录（设计 D9），验证：单测覆盖"先使能不连接→无文件无会话"与"连接成功→当刻建会话"（`presenter/test_recording_wiring.py::TestStandbyBeforeConnect`）。真实串口的插拔时序属在环项，并入 5.1
- [x] 3.9 在 `doc/` 补记录文件格式与会话清单说明（列语义、会话切分规则、缺口在数据中的表现、异常退出后的 `interrupted` 含义），验证：`doc/record_data.md` 的列序与 `recording/test_recorder.py::TestRowFormat` 断言的写盘格式逐列相符；"仅凭文档判读每列含义"需要人用表格工具打开一份真实 CSV，属人工项，并入 5.1

## 4. 历史复看（specs/recording/history-review）

- [x] 4.1 实现按像素列分桶取 min/max 包络的抽稀纯函数（设计 D7），验证：单测构造"平稳段中夹一个单点毛刺"的输入，断言毛刺出现在输出中且输出点数不超过 2×桶数
- [x] 4.2 实现会话列表读取：按开始时间倒序、校验数据文件存在性、缺失条目标记为不可用而非消失、无会话时给出明确空态，验证：单测覆盖正常/文件缺失/空目录三种清单，并断言列表项含时长、条目按新到旧排列、缺失文件那条选得中与否按 `available` 判定（`recording/test_reader.py::TestListSessions`、`views/test_record_panel.py::TestRender`）。会话刚关闭时必须无需手动重扫即出现在列表里，进面板的第一份状态快照就要已经把列表填好
- [x] 4.3 实现历史数据读取：整读 CSV 并按固定行数分块、块间让出事件循环、回报进度（设计 D8），验证：单测喂多行文件断言行数与解析值；并对含非法行的文件断言跳过并计数而非整体失败
- [x] 4.4 实现缺口分段：相邻 `ts_ms` 差超过 2.5× 标称周期（代码常量 `NOMINAL_INTERVAL_MS`，不是配置项）即断为独立段（设计 D6），验证：单测构造含 3 个缺口的序列，断言段数与每段首末时刻正确，并断言阈值随标称周期一起移动（`recording/test_reader.py::TestSplitByGaps`）
- [x] 4.5 新增 `src/views/record_panel.py` 并以代码方式 `addTab` 挂到主窗口（不改 `.ui`，设计 D9）：左侧会话列表、右侧电压/电流两个 `QChartView`、共用时间轴、纵轴独立，验证：应用启动后出现记录页，选中会话画出两条时间对齐曲线，缺口处呈空洞而非连线
- [x] 4.6 历史图表显式取 `theme.TOKENS['dark']` 设置绘图区背景与轴/标题颜色，且显式关闭 series 动画（设计 D11），验证：`QT_QPA_PLATFORM=windows` 下截图确认图表与视图两层底色均无浅色残留，并断言 `animationOptions() == NoAnimation`
- [x] 4.7 实现框选放大与还原，两条曲线时间轴同步收敛（放大后区间回到原始点密度，设计 D7），验证：单测覆盖"两图同步收敛到选区""还原回到首末记录时刻""5 秒窗内回到 11 条原始记录""框进空洞明说没有记录"（`views/test_record_panel.py::TestZoom`）。鼠标拖框的手感属在环项，并入 5.1
- [x] 4.8 实现悬停读数显示同一记录的时刻、电压与电流，光标离开即隐藏，验证：e2e 手动悬停某点，读数与 CSV 中对应行一致
- [x] 4.9 实现记录目录占用总量与会话数量显示，且全链路不提供删除/轮转/截断能力，验证：断言代码中不存在删除数据文件的路径（`views/test_record_panel.py::TestNoDestructivePath`），并断言中断段数不设上限——300 段会话画出 300 条折线、读数报出"中断 299 次"，没有任何一段被丢弃
- [x] 4.10 以 24 小时量级合成会话做性能底线验证（设计 D7/D8），验证：实测 173 000 行 / 9.18 MB 的 CSV 从选中到两图绘制完成 0.204 s（`QT_QPA_PLATFORM=windows`、绘图区宽 1200 px、画出 4800 个点），载入期间进度回调刷新 9 次；宽度取默认 240 桶时 0.203 s。3000 段中断的会话 0.815 s，同样在这条上限内
- [x] 4.11 在 `doc/` 补复看操作说明（如何找会话、载入耗时预期、框选缩放与还原、悬停读数、如何自行清理磁盘），验证：`doc/record_review.md` 的每条操作都有对应实现与单测（载入耗时的实测数字见 4.10，缺口不截断见 4.9）。按文档在台架走一遍"记录—断开—复看—放大"属在环项，并入 5.1

## 5. 集成验证

- [ ] 5.1 全链路台架验证：使能 → 连 COM8 → 采样 → 杀模拟器制造缺口并等待重连失败 → 重启模拟器重连 → 关窗，验证：磁盘上得到两份 CSV 与两条清单条目（其中一条因异常/中断路径带正确状态），复看页能分别载入且空洞位置与实际掉线时段吻合
- [ ] 5.2 长跑与回归确认：连续运行 ≥ 1 小时（含记录）后检查实时曲线点数不超窗口、内存无持续增长趋势，并跑 `src/server` 与 `src/views` 既有 pytest 全绿，验证：曲线点数采样前后一致、既有测试输出无新增失败。已完成的压缩版：10 000 个周期滚动窗口稳定在 100 点、进程 RSS 60.3 → 61.9 MB 无单调增长；`src/views`+`src/presenter`+`src/recording`+`src/mcp_server` 共 494 passed，`src/server/test_client.py` 的 8 failed/4 errors 需实机在环、在 master 上同样失败（见 5.3）。1 小时墙钟长跑待人工在台架执行
- [x] 5.3 确认服务端与 MCP 行为未受影响：`--no-gui` 模式启动不产生任何记录文件，`voltage_query`/`current_query` 与限值校验、准入与控制权流程照旧，验证：`--no-gui` 跑一轮 TCP 客户端查询后 `records/` 不存在；`src/mcp_server/test_bridge.py` 与 `src/server/test_*.py` 通过（`server/test_client.py` 是需实机在环的集成测试，在无服务端时于 master 与本草稿分支上同样失败，非本 change 引入）
- [x] 5.4 校验规划工件与实现一致，验证：`openspec validate add-v-i-recording --strict` 输出 `Change 'add-v-i-recording' is valid`。本轮回写的偏离共六处：① D6 删掉"段数封顶 250 只画前面"的截断说法，改为不设上限并把"上万段会逼近 2 秒"写进 Risks；② D6/D10 的 `interval_ms` 由配置项改为代码常量 `recording.settings.NOMINAL_INTERVAL_MS`（没有任何一侧按它改变采样，采样周期现在就是由它算出来的）；③ D7 的"总点数不随段数涨"改为"下界 2×段数"，与实现一致；④ 4.2 补上"进面板的第一份快照就要填好列表"——首帧漏扫是补测试时实测出来的缺陷；⑤ 4.9/4.10 的验证换成真实测量数字；⑥ 2.2/3.8/3.9/4.7/4.11 里必须在环的台架与人工判读步骤，逐条注明并入 5.1，不再当作已完成

## Workflow follow-up

- 在功能分支上完成后，按项目约定以 `git merge --no-ff` 合入 master，并在汇报中说明实际合并方式。
- 合入后运行 `openspec archive add-v-i-recording`，再 `openspec list --specs` 确认 `recording/data-capture`、`recording/history-review`、`ui/live-curve` 已进入主 specs。
