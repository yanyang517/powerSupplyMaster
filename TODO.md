# 待办项：对标成熟内部工具

审计时间：2026-11-27
审计基线：`master` @ `db6e92f`
本轮 P0 集成：`fix/p0-integration`（工作树 `D:/git/wt/p0-integration`，尚未提交或合并）
审计方式：核对当前代码、配置、工作流、发布标签与测试结果，不以旧勾选项作为完成依据。

总体判断：**P0 五项安全与门禁缺口已完成集成验证；发布、日志、数据记录、输出状态校准和图表交互已经达到内部工具的基本形态。下一阶段缺口主要是产物冒烟、串口生命周期、协议契约、设备诊断能力和工程卫生。**

优先级定义：P0 = 会直接造成误操作、拒绝服务或错误发布；P1 = 成熟内部工具必备；P2 = 功能缺口；P3 = 工程卫生。

---

## 一、未完成

### P1：成熟内部工具必备

#### P1-1 发布链路还缺产物启动冒烟与构建卫生

- [ ] 在 CI 中启动构建后的 exe，做 `--no-gui` 启动/退出冒烟；当前构建后直接打 ZIP。
- [ ] 修正 [scripts/build_exe.ps1](/D:/git/powerSupplyMaster/scripts/build_exe.ps1) 中无效的 `--hidden-import serial.asyncio`，实际模块为 `serial_asyncio`。
- [ ] 固定 PyInstaller 版本，并考虑把远程 manifest 回读前移为发布前闸门。
- [ ] 发布 `master` 当前新增的串口记忆、日志兜底与自动重连等改动；`v0.4.0` 标签为 `6778215`，当前基线 `db6e92f` 尚未包含在发布标签中。

#### P1-2 数据生命周期需要收尾

- [ ] 为记录目录提供保留、清理或轮转策略；当前可长期无上限增长，只能显示容量。
- [ ] 明确“导出”产品体验：CSV 文件本身可外部使用，但是否需要应用内导出、筛选和单位转换仍需定稿；SQLite 已不在当前设计范围。
- [ ] 将写命令错误队列 `SYST:ERR?` 接入响应、日志和记录。
- [ ] 记录 OVP/OCP 等保护事件，以及关键控制动作/输出状态变化。

#### P1-3 设备连接与所有权仍有缺陷

- [ ] `open_device()` 在连接失败后不要继续调用 `get_device_id()`，避免对空 writer 发命令。
- [ ] 统一 GUI 与服务端的串口生命周期所有权；当前两端共享单例，但 open/close 和事务锁并未统一。
- [ ] 将 GUI 选择的波特率传入 Model/驱动，去掉 115200 的隐式默认。

#### P1-4 协议契约需要收敛

- [ ] 为 `output_query` 注册处理器，或从协议中删除并明确不支持。
- [ ] 将 `SetMaxVoltageRequest` / `SetMaxCurrentRequest` 纳入 `RequestUnion` 并实现，或删除死定义。
- [ ] 让 Pydantic 校验错误返回结构化 `validation_error` 和 `request_id`，不要退化为通用 `internal_error`。

#### P1-5 日志覆盖边界

- [ ] 评估是否需要在第三方依赖导入前安装最小异常落盘钩子；当前模块导入阶段的异常仍可能早于 `configure_logging()`。

### P2：功能缺口

#### P2-1 设备能力仍以单通道为主

- [ ] 支持通道选择 `INSTrument:NSELect`，并让 GUI、TCP、MCP 明确操作通道。
- [ ] 补齐 `*RST`、保护设定、`SAV` / `RECL`、`KEY:LOCK` 等常用 SCPI 能力。
- [ ] 为多通道命令语义、通道状态和模拟器行为补测试。

#### P2-2 界面仍有死控件

- [ ] 清理或接线字体、颜色、背景、透明度及遗留电流上限等控件。
- [ ] 更新 README 的“已知限制”：串口所有权已有租约和接管确认，文档仍称没有仲裁。

#### P2-3 安装与实例管理

- [ ] 在 ZIP 之外提供安装包或至少一键启动入口。
- [ ] 增加单实例锁，避免多个进程同时抢占串口和 18888 端口。

### P3：工程卫生

#### P3-1 代码卫生

- [ ] 删除 [src/server/command_handle_base.py](/D:/git/powerSupplyMaster/src/server/command_handle_base.py) 及 `socket_server.py` 中未使用的导入。
- [ ] 重构 [src/server/request_handles.py](/D:/git/powerSupplyMaster/src/server/request_handles.py)：当前有 9 个同名 `handle` 函数，靠闭包注册避免功能损坏，但可读性差。
- [ ] 修复 [scripts/access_control_e2e.py](/D:/git/powerSupplyMaster/scripts/access_control_e2e.py) 的过期导入；当前会因 `mcp_server.psu_client` 不存在而无法运行。

#### P3-2 依赖与配置

- [ ] 将 `requirements.txt` 从混合 freeze 拆成直接依赖与 lock；当前仍混入运行时、传递依赖和测试依赖。
- [ ] 收敛演示、模拟器和测试中的硬编码 COM 口；生产串口记忆已完成，但 `COM4` / `COM8` / `COM9` / `COM255` 仍有残留。
- [ ] 暴露服务端口的 CLI/配置项，替换单一 `SERVER_PORT` 常量；监听地址已由本轮 P0-5 的 `--listen` 提供。
- [ ] 决定是否为主桌面应用增加根级 `pyproject.toml`；当前只有 MCP 子包有打包元数据。

#### P3-3 静态检查与仓库配套

- [ ] 增加 lint、type-check、pre-commit 和覆盖率门禁。
- [ ] 增加根级 `CONTRIBUTING`、`CHANGELOG`、issue/PR 模板；目前只有 MCP 子包有 CHANGELOG。
- [ ] 完善 i18n：生成 UI 已走 `translate`，但手写代码仍有中文硬编码，且没有翻译器加载和 `.ts` / `.qm` 资产。

#### P3-4 文档与 OpenSpec 收尾

- [ ] 更新 README 中英文的已知限制和测试入口；网络默认值已由本轮 P0-5 统一。
- [ ] 重写或删除 `doc/project_knowledge_v1.0.md` 的过期缺陷清单；该文件不在 master，主工作区中的未跟踪副本已明显落后。
- [ ] 归档输出状态校准和波形交互两个 OpenSpec change，并把新需求同步回主 specs。
- [ ] 统一 MCP 文档中“UI 管理串口”的表述与实际 TCP `open_device` / `close_device` 能力。

---

## 二、已完成

以下项目已在 `master` 落地，或已在本轮 P0 集成分支完成验证；尚未合并的项目会单独标注。

### P0：本轮集成完成（尚未合并 `master`）

- [x] **P0-1 自包含测试门禁**：新增根级 `pytest.ini` 与独立 CI 测试工作流，发布构建前执行同一门禁；测试服务改用临时端口与 socket-backed SCPI 模拟，真实硬件测试改为显式启用；MCP 子包测试进入默认、CI 和发布门禁。
- [x] **P0-2 GUI/TCP/MCP 共用安全限值**：共享 fail-closed 限值校验与 mV/mA 归一化；Presenter/Model 在设备写入前校验，GUI 只在写入成功后发布设置值，电压/电流上限显示与旋钮跟随启动限值。
- [x] **P0-3 首次失败不占租约**：租约增加 reserve/commit/rollback/quarantine；明确写前失败回滚，取消、超时和结果不明的写入隔离，释放与吊销遇到活跃写入时拒绝。
- [x] **P0-4 TCP/MCP 边界**：限制 64 KiB 帧与 32 个并发连接，覆盖读取、空闲、dispatch、写回和关闭超时；MCP 限制响应大小与连接超时，只允许明确的只读命令重试一次。
- [x] **P0-5 回环默认与内网定位**：默认 `127.0.0.1`，显式 `--listen` 才可绑定其他地址；按实际 socket 地址 fail-closed 分类并告警，增加注册表、准入速率与身份长度边界；文档明确仅限隔离可信实验网，不提供 token/mTLS。

**P0 验证**：集成树 `pytest src` 为 **891 passed / 1 skipped / 3 deselected**；默认总门禁 `pytest` 为 **922 passed / 1 skipped / 3 deselected**（含 MCP 31 项）；`compileall` 与 staged/unstaged `git diff --check` 通过。剩余告警为既有 Qt Charts 弃用提示。

### 构建与启动

- [x] **产物内置客户端登记表**：构建时复制 `config/clients.json`，缺失、空文件或非法 JSON 会使构建失败；`-VerifyOnly` 可单独复检。
- [x] **无控制台启动失败可见**：保留退出码 2，exe 同级 `logs/startup_error.log`，无 stderr 时显示原生弹窗。
- [x] **发布链路端到端已验证**：版本、manifest 和 `v0.4.0` 标签对齐，GitHub/Gitee 发布及远程 manifest 回读成功。

### 日志与可观测性

- [x] **单一日志入口与轮转落盘**：源码写仓库根 `logs/`，frozen 写 exe 同级；5 MiB/份，保留 5 份。
- [x] **全局与 asyncio 异常兜底**：完整 traceback 落盘，同时保留原 stderr/事件循环处理行为。
- [x] **Socket 生命周期日志化**：移除运行时 `print`，记录实际绑定地址并正确格式化 IPv6。

### 数据与长时间运行

- [x] **V/I 测量记录**：按连接写 CSV 会话和 `index.json`，支持中断会话恢复、容量统计和历史浏览。
- [x] **采样健壮性**：单次读取失败不会终止采样，不完整 V/I 对不会写入半条记录。
- [x] **历史曲线交互**：支持缺口分段、异步加载、缩放、悬停和恢复。
- [x] **实时图表有界**：Python 缓冲和 `QLineSeries` 都限制为 100 点，不再无限增长。

### 控制与设备状态

- [x] **输出状态校准**：按 1 秒周期读取 `OUTP?`，UI 使用 ON/OFF/UNKNOWN 三态，切换后写读回确认。
- [x] **客户端准入与授权基础**：L0/L1/L2、自动准入、审批、审计和控制租约已实现；首次失败与结果不明写入的租约处理由本轮 P0-3 补齐。
- [x] **面板接管确认**：远程写操作与面板操作冲突时可要求用户确认。
- [x] **串口记忆与自动重连**：记住最后一次成功连接的串口并在启动时预选，设置采用原子写入；自动重连已接线。
- [x] **串口健壮性**：修复迟到响应处理和 Windows 串口轮询问题。
- [x] **关闭流程判空**：`close_device()` 不再对空任务调用 `.cancel()`。

### 界面与交互

- [x] **关于页与状态栏**：版本、构建信息、更新检查和连接/更新状态已接线。
- [x] **实时波形交互**：支持跟随最新、Ctrl/Shift 滚轮缩放、悬停提示和双击复位。
- [x] **窗口几何记忆**：位置和大小持久化。
- [x] **界面主题与图标**：深色 QSS、旋钮自绘和资源打包校验已落地。

### 包与协作工程

- [x] **MCP 桥接包**：独立 `packages/psu-mcp` 已有打包元数据、客户端工具和协议互操作测试。
- [x] **版本与更新提示**：版本真源、exe 元数据、manifest、更新检查和关于页展示已贯通。

---

## 建议动手顺序

1. 先验收并合并本轮 **P0 集成分支**，让五项安全与门禁修复进入 `master`。
2. 随后做 **P1-1 发布冒烟**、**P1-3 连接所有权**和 **P1-4 协议收敛**。
3. 设备错误队列、保护事件和多通道能力按实际台架需求排期。
4. 最后收尾依赖分层、静态检查、安装包、i18n 和文档/OpenSpec。
