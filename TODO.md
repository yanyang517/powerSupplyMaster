# 待办项：对标成熟内部工具

审计时间：2026-11-21
审计方式：实测（跑 `pytest src`、复现启动路径、核对打包脚本与工作流），非纯静态阅读。

总体判断：**架构与安全模型已经像工具了，但发布链路、可观测性和设备能力还不像。**

优先级定义：P0 = 现在就会咬人；P1 = 成熟内部工具标配但当前空白；P2 = 功能缺口；P3 = 工程卫生。

---

## P0

### P0-1 CI 产物在干净机器上启动不了

- [x] 修复 [scripts/build_exe.ps1](/D:/git/powerSupplyMaster/scripts/build_exe.ps1)：把 `config/clients.json` 带进产物目录（构建后拷贝到 `dist/<Name>/config/`；不用 `--add-data`，onedir 下它落在 `_internal/`，与 frozen 解析规则不一致）
- [x] 决定缺登记表时的行为：保持"拒绝启动"（退出码 2 不变），另加 exe 同级 `logs/startup_error.log` + 检测不到控制台时的 `ctypes` 原生弹窗
- [x] 补一个构建后校验步骤：产物目录内不存在 `config/clients.json` 即构建失败（`Assert-BundledRegistry`；空文件/非法 JSON 同样失败，`-VerifyOnly` 可单独复检）

**修复记录（2026-11-21，分支 `fix/bundle-client-registry`，提交 726d3ca，未 push 未合入）**

- 实测新产物：`loaded 2 client(s) from ...\dist\powerSupplyMaster\config\clients.json` → frozen 分支确实解析到产物内那份
- 实测退化保护：删掉产物内 `clients.json` 后 `build_exe.ps1 -VerifyOnly` 退出码 1；拷回后 0
- 实测无控制台（`Start-Process` 启动，无 stderr）：进程卡在标题为「powerSupplyMaster 启动失败」的模态框上，同时 `logs/startup_error.log` 追加了一条带时间戳的原因
- 实测重构建：产物内已被 app 改写过的 `clients.json` 与 `window_geometry.json` 都保留，种子步骤只补缺不覆盖
- 回归测试：新增 [src/test_startup_failure.py](/D:/git/powerSupplyMaster/src/test_startup_failure.py) 11 条（在分支上，合入后位于该路径）；`pytest src` 由 190 passed 提升到 201 passed，failed/errors 仍是 8/4（全在 P0-2）
- 顺带发现（不在本次范围）：`build_exe.ps1` 的 `--hidden-import serial.asyncio` 是写错的模块名，本仓 `.venv` 里 `import serial.asyncio` 直接 ModuleNotFoundError（代码用的是顶层 `serial_asyncio`），构建只报 ERROR 不中断

**证据**

- [src/server/registry.py:59](/D:/git/powerSupplyMaster/src/server/registry.py#L59) `clients_file_path()`：`sys.frozen` 时解析为 `exe同级/config/clients.json`
- [src/server/registry.py:130](/D:/git/powerSupplyMaster/src/server/registry.py#L130) `load()`：文件不存在即抛 `RegistryError`
- [src/app.py:40](/D:/git/powerSupplyMaster/src/app.py#L40) `bootstrap_access()`：捕获后 `SystemExit(2)`；实测 `python exit=2`
- `build_exe.ps1` 全文无 `--add-data`，对 `config/` 只做"上一次构建的备份还原"；CI 从干净 checkout 构建，该目录不存在
- 本地 `dist/powerSupplyMaster/config/` 实测只有 `window_geometry.json`
- `config/clients.json` 本身**是**入库的（`git ls-files config/` 已核实），所以缺的只是"把它搬进产物"这一步
- 叠加 `--windowed`（无控制台）→ 用户侧现象是"双击没反应"，且无任何提示

---

### P0-2 测试套件无法作为门禁

- [x] 给 [src/server/test_client.py](/D:/git/powerSupplyMaster/src/server/test_client.py) 加前置条件跳过（服务未运行 / 无串口时 `skip` 而不是 `fail`），或改造为自起自停的进程内集成测试 —— 走了后半条：进程内自起自停，只有真机层保留 `skip`
- [x] `.github/workflows/` 新增 test job：`pytest src` 绿（新增 [ci.yml](/D:/git/powerSupplyMaster/.github/workflows/ci.yml)，另在 release.yml 构建前插了同一道门禁）
- [ ] 后续 lint：test job 里没有这一步，仓库也还没有 lint 配置（ruff/flake8 属新增依赖，需先定选型与许可证）
- [x] 明确区分单元测试与集成测试的入口（marker 或目录），让"一键验绿"在干净环境成立

**修复记录（2026-11-21，分支 `feature/test-suite-as-gate`，提交 38ae14f，未 push 未合入，工作目录 `D:/git/wt/test-suite-as-gate`）**

- 实测基线（master 160bde4，非上面记录时的 190）：`pytest src` = **362 passed / 8 failed / 1 skipped / 4 errors，37.1s**
- 实测修复后：`pytest src` = **380 passed / 1 skipped / 3 deselected，12.1s**；连跑两次数字一致。用例只增不减（+9：repeat 1→5、新增 2 条链路用例、真机层 3 条）
- 分层：根 `pytest.ini` 注册 `integration` / `hardware` 两个 marker，`addopts = -m "not hardware" -ra`。默认门禁**包含**集成层——它已不依赖任何外部条件，把它排除掉等于给门禁留盲区；`-m "not integration"` 是本地快路径，`-m hardware` 才需要真机
- 实测两种入口一致：`pytest src`（仓库根）与 `cd src && pytest server/test_client.py` 同为 18 passed / 1 skipped；`src/server/pytest.ini` 删除，规则收进根配置，`pythonpath = src` 解决无 pyproject 的导入根
- 集成层自带环境：`conftest.py` 在临时端口（`start_server(..., 0)`）拉起 `SocketServer.handle_client`，并用 `device_simulator.SCPISimulator` 的 SCPI 命令经本地 socket 顶替串口；**只替换 `serial_asyncio.open_serial_connection` 一个传输调用**，`connect()` 状态机、`_send_cmd()` 加锁/超时、`*IDN?` 探活与真实字节都仍走生产代码（用例直接断言对端收到 `VOLTage 5.00`）
- 安全契约未放宽：登记表改用 `config/clients.json` 的临时副本（避免 L0 自动准入写脏入库文件），`login` 申请 L1 生效 L2 的降格、响应不含凭据字段、未登录写命令被拒、登出后重新被挡、多连接身份隔离都仍在链路层钉住；`open_device` 的伪端口名换成 `COM-SIM`
- `pytest.mark.repeat(5)` 原来静默失效（pytest-repeat 不在 requirements.txt 且未注册 marker），改 `parametrize(range(5))`，零新增依赖
- 示例角色保住并实测：`JsonSocketClient` 移到 `src/server/example_client.py`，对真实运行的 `app.py --no-gui` 跑通 echo/login/setting_query（`server_version=1.0.0`），且 `git status config/` 干净；README.md / README.en.md 的协议节、测试节、已知限制三处双语同步
- `test_power_control.py` 的 `COM255` 查清了：不是被吞掉的异常，而是 `psu.connect()` 真实尝试打开不存在的口后返回 False——它绿得靠前提。现改成显式声明「这个口当下不存在」，真存在则带原因 skip
- 删 `event_loop_policy`/`event_loop` 夹具不是为了消告警：留着时 async fixture 与用例跑在**两个不同事件循环**上，进程内服务的 accept 永远等不到（实测挂死）。删后 `PytestDeprecationWarning` 与 `PytestUnknownMarkWarning` 均为 0
- CI 实测范围：四条 ci.yml 命令在本机逐条跑过（含 `QT_QPA_PLATFORM=offscreen`、`PYTHONUTF8=1`），并用 `pip install --target` 临时拉 requirements 里 pin 的 **pytest 8.4.2** 复验得到同样数字（本机 venv 实际是 9.0.2）；YAML 用一次性 pyyaml 解析确认可加载、步骤顺序正确。**未验证**：真实 runner（PySide6 6.10.2 vs 本机 6.11.0、Actions 工作流发现）——需要 push 才能确认
- 遗留（本次不做）：`src/mcp_server/test_bridge.py:23` 仍写死 18899（今天不冲突，但同属外部端口假设）；`src/views/test_window_geometry.py:10` 还有一处与测试混写的 `logging.basicConfig`

**证据**

- `pytest src` 实测：**190 passed / 8 failed / 4 errors**，红的全在 `test_client.py`
- 失败信息为 `Failed: Could not connect! Is the server running?`（[test_client.py:379](/D:/git/powerSupplyMaster/src/server/test_client.py#L379)）——假设外部服务已运行且有真实/虚拟串口，却无 `skipif`
- [.github/workflows/release.yml](/D:/git/powerSupplyMaster/.github/workflows/release.yml) 只有构建与发布步骤，无任何 test/lint job
- 单元测试本身是健康的：registry / session / access / admission / geometry / startup 均可离线通过

---

## P1

### P1-1 版本与可追溯性

- [x] 版本真源、exe 元数据、更新提示、发布清单闸门均已落进 master（`feature/add-version-info-and-update-notice`，合并提交 `160bde4`，change 已归档）
- [ ] **收尾项：`git tag` 至今仍为空** —— `release.yml` 的 `gen_manifest.py --check` 与发布后 `--remote` 回读两道闸门从未在真实 runner 上跑过一次，发布链路端到端仍未验证

**已落地**：`src/version.py`（`__version__ = "1.0.0"` + `channel`）、`src/_build_info.py`（构建期生成、已 ignore）、`scripts/make_version_info.py` → `--version-file`、`src/update/`（manifest/compare/probe/state/settings/scheduler/notice 全套带测试）、`update/latest.json`、`scripts/gen_manifest.py`。exe 属性实测 `FileVersion/ProductVersion = 1.0.0`，与真源一致。

**仍缺**：`pyproject.toml` 依旧没有（见 P3-3），版本真源目前靠 `src/version.py` 单文件约定 + `gen_manifest.py --check` 守护。

### P1-2 日志与崩溃兜底

- [x] 收敛为单一日志初始化入口，移除 `src` 内 12 处重复 `logging.basicConfig`（10 个运行时模块 + 2 个测试模块；模块只获取 logger）
- [x] 加 `RotatingFileHandler` 落盘：源码在仓库根 `logs/`，frozen 在 exe 同级 `logs/`；5 MiB/份，保留 5 份，控制台 INFO、文件 DEBUG
- [x] 加全局异常兜底：`sys.excepthook` + asyncio 事件循环 exception handler，完整 traceback 落盘并保留原有 stderr/循环处理行为
- [x] 清掉 `src/server/socket_server.py` 运行时 `print`，启动日志报告 socket 实际绑定地址

**证据**：统一入口为 `src/logging_config.py`，重复初始化只替换自身 handler，日志目录不可写时警告一次并降级到控制台；`src/app.py` 在 GUI 的 `QEventLoop` 和 `--no-gui` 的实际运行循环上安装异常处理，并保留 `startup_error.log`/原生弹窗早启动兜底。聚焦回归见 `src/test_logging_config.py` 与 `src/server/test_socket_server_logging.py`：新增 12 项全部通过；server/MCP 子集 121 项通过；受控 18888 服务下全量 `560 passed / 7 failed / 2 skipped`，失败 node 与修改前基线 `548 passed / 7 failed / 2 skipped` 完全一致（6 个串口/设备用例 + 1 个既有 Qt 顺序依赖用例）。

### P1-3 传输与身份 —— 定位已定：**仅隔离实验网**

- [x] 监听地址默认值 `0.0.0.0` → `127.0.0.1`，跨机使用改为显式 `--listen 0.0.0.0`
- [x] 定位为「只在隔离实验网」，因此不引入凭据体系；把该前提与其后果写进文档（双语 README + `doc/client_access.md`）
- [ ] **仍未做（按定位主动搁置）**：真正的认证（token / mTLS）。若将来要跨办公网或不可信网段，这一条必须重启，而不是靠防火墙凑

**修复记录（2026-11-21，分支 `feature/loopback-listen-default`，提交 `cc39759`，未 push 未合入，工作目录 `D:/git/wt/loopback-listen-default`）**

- 原缺陷本体：[src/server/socket_server.py:32](/D:/git/powerSupplyMaster/src/server/socket_server.py#L32) 内联默认 `host="0.0.0.0"`，与准入模型不匹配——第一道门只核对自报的 `client_id` 是否在名单上，[registry.py:24](/D:/git/powerSupplyMaster/src/server/registry.py#L24) 明确拒绝凭据字段，即**没有认证**；L0/L1/L2 + 租约解决的是授权不是认证
- 真源落在 `runtime_config.SERVER_HOST`，`SocketServer` 与 `server_main` 的默认值都取它，不再各处内联字面量；`is_loopback_host()` **判定失败关闭**（空串、`0.0.0.0`/`::`、无法解析的主机名一律按「已暴露」算）
- 绑到非回环时启动日志打一条自带下一步的 WARNING（原文含 `NOT authentication` 与 `--listen 127.0.0.1` 的回退指引）；顺带把同一行的 `print` 换成 `logger.info` 并改报**内核回报的真实绑定地址**
- 实测 A 组（默认）：`netstat` 为 `127.0.0.1:18888 LISTENING`；从本机 LAN 地址 `192.168.1.5:18888` 连**被拒**，从 `127.0.0.1` 连**成功**
- 实测 B 组（`--listen 0.0.0.0`）：`0.0.0.0:18888 LISTENING`、LAN 地址可连通，且 WARNING 按预期出现——放开是显式、有效、且被说清的
- 回归：`pytest src` = 382 passed / 8 failed / 4 errors（基线 364 passed，红名单 12 条与基线**逐条 diff 一致**，全部属 P0-2 范围，本分支未引入新红）；新增 `src/server/test_listen_address.py` 20 条
- 变异检验：把 `SERVER_HOST` 改回 `0.0.0.0` 后钉确实会红。第一轮只红 1 条，暴露出我自己写了条弱断言（比的是「等于那个常量」，常量被改坏时它跟着通过），已改成断言 `is_loopback_host(...)`
- 探测后确认 `config/clients.json` 未被自动准入写脏；两次实测的服务进程均已清场，`18888` 无监听残留

### P1-4 数据留存

- [ ] 测量数据落盘与导出（CSV / SQLite），当前只进内存图表
- [ ] 写命令回读设备错误队列 `SYST:ERR?`（README「已知限制」已承认设备侧错误不可见）
- [ ] OVP/OCP 等保护事件记录

---

## P2

### P2-1 单通道驱动（对着 DP832 这类三路电源尤其明显）

- [ ] 支持通道选择 `INSTrument:NSELect`，让 GUI / TCP / MCP 明确指定操作哪一路
- [ ] 读取 UI 的 `baudrate_comboBox`，去掉驱动里硬编码的 115200（全项目 7 处重复）
- [ ] 补齐常用 SCPI 能力：`*RST`、保护设定、面板存取 `SAV`/`RECL`、远程锁定 `KEY:LOCK`

**证据**：[src/device/scpi_power_supply.py:62](/D:/git/powerSupplyMaster/src/device/scpi_power_supply.py#L62) 只发 `*IDN?` / `VOLTage` / `CURR` / `MEASure:` / `OUTP`；而 [src/device/device_simulator.py:53](/D:/git/powerSupplyMaster/src/device/device_simulator.py#L53) 自己建模了 `channels = 3`。现状后果：设的电压落在"面板当前选中的那一通道"上，语义不确定。

### P2-2 界面死控件

- [ ] 接线或删除：`auto_reconnect_CB`「自动重连」是纯摆设，零行为
- [ ] 接线或删除：`pushButton_4`~`8`、`spinBox`
- [ ] 填充 `tab_about`（空标签页）、启用 `statusbar`
- [ ] 更新 README「已知限制」：串口所有权仲裁已被 access 层租约解决了一半，文档比代码旧

**证据**：生成 UI 定义 84 个控件，手写代码只引用 17 个；`auto_reconnect` 除 [mainWindow_ui.py](/D:/git/powerSupplyMaster/src/views/ui/mainWindow_ui.py#L97) 外全项目零引用，也没有任何重连逻辑。

### P2-3 长时间运行会劣化

- [ ] `_update_chart_data` 补 `removePoints` / 滚动窗口裁剪

**证据**：[src/views/main_window.py:409](/D:/git/powerSupplyMaster/src/views/main_window.py#L409) 对 `QLineSeries` 只 `append` 从不清点；`max_data_points = 100` 裁剪的是不参与绘制的 Python 列表。0.5 s 采样下每小时累积约 7200 点，内存与重绘成本单调上升——对"整天开着"的台架工具是实质缺陷。

---

## P3

### P3-1 协议契约不一致

- [ ] `output_query`：已在 `RequestUnion` 声明但无处理器，实际走 `Unknown request type`
- [ ] `SetMaxVoltageRequest` / `SetMaxCurrentRequest`：定义了但既不进 `RequestUnion` 也不注册，连解码都做不到
- [ ] 让 [doc/project_knowledge_v1.0.md](/D:/git/powerSupplyMaster/doc/project_knowledge_v1.0.md) 的缺陷清单与实际一致（其中 D-05 记录已偏旧）

### P3-2 代码卫生

- [ ] 删除死代码 [src/server/command_handle_base.py](/D:/git/powerSupplyMaster/src/server/command_handle_base.py)
- [ ] 重构 [src/server/request_handles.py](/D:/git/powerSupplyMaster/src/server/request_handles.py)：7 个同名 `handle` 函数互相覆盖模块属性（功能靠闭包未受影响，但阅读极易误判）
- [ ] 修 `presenter.close_device`：未连接时会对 `None` 调 `.cancel()`
- [ ] GUI 与服务端各自直接实例化同一串口单例，收敛到单一所有权入口

### P3-3 依赖与配置

- [ ] [requirements.txt](/D:/git/powerSupplyMaster/requirements.txt) 是一份 `pip freeze`：传递依赖、测试依赖混在运行时里，`opentelemetry-api` 重复两行 → 改为直接依赖 + lock 两层
- [ ] 魔法数字与硬编码 COM 口（`COM4`/`COM8`/`COM9`/`COM255`）集中到配置或常量模块
- [ ] 服务端口/监听地址暴露为命令行参数或配置文件（当前只有 `runtime_config.SERVER_PORT` 常量）

### P3-4 仓库配套

- [ ] lint / type-check / pre-commit 配置（当前一个都没有）
- [ ] CONTRIBUTING、CHANGELOG、issue 模板
- [ ] 安装包（当前只有 zip）、单实例锁
- [ ] i18n：手写代码有 11 处中文硬编码，而生成 UI 走 `QCoreApplication.translate`，翻译基建只有半套

---

## 建议动手顺序

先做 **P0-1 + P0-2**，它们决定"别人能不能装上并用"。P1-1 已有完整 OpenSpec 方案，直接开工即可。P1-2 日志与 P2-3 图表劣化属于同一个"长时间运行"命题，可合并成一个 change。P1-3 需要先想清楚定位，再决定是改默认值还是引入凭据。
