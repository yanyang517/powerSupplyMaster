# Tasks

## 1. 工作目录与技术前提验证

- [x] 1.1 按项目约定用 `git worktree` 为本 change 建立独立工作目录并在其上开分支（`feature/add-version-info-and-update-notice`），确认 `git status` 在主工作区保持干净
- [x] 1.2 Spike：用标准库 `urllib.request` 从开发机分别取回 Gitee raw 与 GitHub raw 上的任意仓库文件，记录 HTTP 状态、是否需重定向跟随、默认 `ssl` 上下文是否报证书错误，把结论写进 `doc/update_notice.md` 的"实测记录"小节
- [x] 1.3 Spike：在同一脚本里尝试 `truststore` 构造的 SSL 上下文并记录它与默认上下文的差异，据此确定第 5 组采用的上下文来源（结论先行，不带进实现阶段猜）——实测两者结果一致，第 5 组采用 `ssl.create_default_context()`，不使用 `truststore`

## 2. 版本真源与界面展示

- [x] 2.1 新增 `src/version.py`（`__version__ = "1.0.0"`、`channel`、以 `try/except ImportError` 读取 `src/_build_info.py` 的构建来源信息，缺失时为 `dev`），并新增 `src/test_version.py` 覆盖"无构建信息即 dev"与版本号格式校验，测试通过
- [x] 2.2 在 `MainWindow.setupUi()` 之后按 `_swap_voltage_dial()` 的既有方式填充 `tab_about`（版本、构建来源、检查入口占位）并覆盖窗口标题为含版本号的文案，运行 `src/views/test_client_access.py` 同套 pytest 确认无回归，并用 offscreen 模式截图确认标题与关于页可见版本
- [x] 2.3 在 `src/app.py` 启动日志首行输出版本与构建来源，并加 `--no-update-check` 启动参数（本组只接线、不实现探测），确认 `--no-gui` 与 GUI 两条路径都能启动
- [x] 2.4 为版本展示补 `doc/version_info.md`（真源位置、bump 流程、两处需同步的文件清单），确认文档里的命令与路径与实际一致

## 3. 可执行文件的版本元数据

- [x] 3.1 修改 `scripts/build_exe.ps1`：从 `src/version.py` 解析版本并生成 PyInstaller 版本资源文件传给 `--version-file`，格式不符或解析失败时 `throw`；执行一次本地构建确认产物存在
- [x] 3.2 用 `(Get-Item dist/powerSupplyMaster/powerSupplyMaster.exe).VersionInfo` 验证文件版本与产品版本等于 `src/version.py` 的值，把该命令写进 `doc/version_info.md` 作为验收手段
- [x] 3.3 验证 `_build_info.py` 已进 `.gitignore` 且被 PyInstaller 收集：清掉生成文件后构建，exe 属性仍为本次构建的版本号

## 4. 发布清单与发布期一致性闸门

- [x] 4.1 新增 `update/latest.json`（`schema_version`、`version`、`date`、`release_url`），按 D4 写好两个仓库各自的发布页地址，确认 JSON 可被 `python -m json.tool` 解析
- [x] 4.2 新增 `scripts/gen_manifest.py`，支持 `--check` 比对 `version.py` / `latest.json` / 当前 tag 三方，任一不一致时以非零码退出并打印差异；用故意改坏 `latest.json` 的方式验证其确实报错后还原
- [x] 4.3 在 `.github/workflows/release.yml` 的构建前加入 `gen_manifest.py --check` 步骤，并在 `gh release create` 之后新增回读步骤：用 app 实际会用的两个 raw URL 取回清单并断言 `version == tag`，不一致即失败
- [x] 4.4 在 `doc/version_info.md` 增加"发版动作清单"（一次 bump commit 改两处 → `--no-ff` 合入 → 打 tag → 推两源），确认清单与 `gen_manifest.py --check` 的校验范围一致

## 5. 新版本探测模块

- [x] 5.1 新增 `src/update/manifest.py`：清单解析与校验（schema 不识别、字段缺失、非法版本一律返回"本次获取失败"），配套 `src/update/test_manifest.py` 覆盖四类坏输入，测试通过
- [x] 5.2 新增 `src/update/compare.py`：`X.Y.Z` 元组解析与"严格大于"判定，预发布后缀按解析失败处理（不提示），测试覆盖相等、更低、更高、非法四种输入
- [x] 5.3 新增 `src/update/probe.py`：`urllib.request` 同步取数，按配置 URL 列表顺序回退、5 秒超时、失败返回 `None` 且只记 `logger.info`；用本地 `http.server` 起两个假源验证"首选源故障时备源生效"与"全失败静默"
- [x] 5.4 新增 `src/update/state.py`：`config/update_state.json` 的读写，路径与 `sys.frozen` 回落规则复用 `views/window_geometry.py` 的做法，文件损坏视为空状态；测试覆盖缺失、损坏、正常往返三种情况
- [x] 5.5 新增 `src/update/settings.py`（仿 `server/runtime_config.py` 的进程级配置对象：源 URL 列表、间隔、超时、启动延迟、开关），并在 `doc/update_notice.md` 记录默认值与覆盖方式

## 6. 提示接线与调度

- [x] 6.1 在探测调度处用 `asyncio.to_thread` 包裹同步取数，避免阻塞 qasync 事件循环；以"探测人为睡 3 秒而界面仍可响应"的行为验证（offscreen 或手动观察），结论记入 `doc/update_notice.md`
- [x] 6.2 在 `MainWindow` 状态栏加入提示控件（`addWidget` 而非 `showMessage`，避免被后续消息覆盖），配色通过 `theme.build_qss()` 追加的 objectName 限定规则实现，确认深色主题下文字对比度与既有 `text_dim` 一致并补进 `src/views/test_theme.py`
- [x] 6.3 实现两个用户动作：「查看发布页」用 `QDesktopServices.openUrl` 打开清单里的地址、「忽略此版本」写入 `dismissed_version`；测试覆盖"忽略后同一版本不再提示"且重启进程后仍生效
- [x] 6.4 实现判定链（dev 构建短路、版本相等或更低不提示、间隔内跳过、`--no-gui` 不探测、`disabled` 后零请求），用可注入时钟与假源写 `src/update/test_notice.py` 逐条覆盖
- [x] 6.5 在关于页实现 D7 的手动"立即检查"入口：绕过节流与 dev 短路，把结果（发现新版本 / 已是最新 / 失败原因）显示在页面上；手动执行一次并截图存档到本 change 的 `evidence/`

## 7. 控制通路的版本字段

- [x] 7.1 `SettingResponse` 增加 `version` 字段并在 `setting_query` 处理中填入真源值，确认 `src/server/test_power_control.py` 既有用例通过并新增"响应含版本、设备未连接时仍 success"两条断言
- [x] 7.2 MCP `get_status` 在限值块中带上服务端版本，补 `src/mcp_server/test_bridge.py` 断言并确认工具描述文本随之说明该字段含义

## 8. 集成验收

- [x] 8.1 端到端演练一次发版：临时把源 URL 指向本地假 HTTP 服务托管的 `update/latest.json`，把本地版本改低一档，启动 GUI 确认状态栏出现提示、浏览器动作可用、忽略后重启不再提示；全过程截图进 `evidence/`
- [x] 8.2 全量回归：跑 `pytest`（`src` 下全部用例）与 `scripts/access_control_e2e.py`，确认设备控制通路与既有限值/准入行为无回归
- [x] 8.3 校验 change 自洽：`openspec validate add-version-info-and-update-notice --strict` 无错误，且 `README.md` / `README.en.md` 的功能特性列表与新增的版本、更新提示描述一致

## Workflow follow-up

- 按项目约束以 `git merge --no-ff` 合入 master，并在汇报中说明实际使用的合并方式。
- 合入后打 tag `v1.0.0`，分别推送到 GitHub 与 Gitee 两个 remote，等 release 工作流跑完并确认 D6 的回读断言为绿。
- 满足项目评审要求后归档本 change（`/opsx:archive`），并确认 `app/version-info`、`app/update-notice` 两个新能力已落到 `openspec/specs/`。
