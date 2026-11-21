# Design

## Context

现状勘查（本 change 的事实前提）：

- 仓库内不存在任何应用版本定义，`git tag` 为空，无 `pyproject.toml`；唯一依赖清单是 `requirements.txt`。
- `.github/workflows/release.yml` 已由 `v*` tag 触发，tag 名只用于 zip 归档文件名与 `gh release create`，未进入 exe；Gitee 侧没有对应的发布流程。
- `scripts/build_exe.ps1` 的 PyInstaller 调用（6.22.3）未使用 `--version-file`，本地产物同样无版本元数据。
- `src/views/ui/mainWindow.ui` 的 `tab_about` 是空标签页；`QStatusBar` 已声明但 Python 侧从未使用，而 `src/views/theme.py` 已经为 `QStatusBar` 写过 QSS（`surface` 底色 + `text_dim` 前景），并有按 objectName 追加 scoped 规则的既有写法。
- `MainWindow._swap_voltage_dial()` 确立了"在 `setupUi()` 之后用 Python 构建控件并塞进 uic 生成的布局"的做法；本设计沿用它填充 `tab_about`，不改 `.ui`、不重跑 uic。
- `src/views/window_geometry.py` 确立了运行时状态文件的规则：项目本地 `config/*.json`，`sys.frozen` 时落在 exe 同级 `config/`（注释明确写了 "writable, survives upgrades"），并带 `schema_version` 校验，不匹配即回落默认而非报错。
- 运行时 venv 的 HTTP 现状：无 `requests`、无 `httpx`（只有 mcp 拖入的 `httpx2`/`httpcore2`）；`truststore` 已安装但源码中从未调用。Windows 上 CPython 的 `ssl` 默认不加载系统根证书库，这一点是探测模块能否发出的前置约束，需在实施早期实测。

约束：主职能是离线控制硬件，任何探测都不得影响串口通路；不引入需要付费或 copyleft 依赖的新增包；界面保持固定深色主题。

## Goals / Non-Goals

**Goals:**

- 版本号有一个真源，其余落点全部派生，且真源与 git tag 的一致性由机器而非记性保证。
- 探测逻辑与"提示呈现"解耦：前者是纯函数 + 一个取数函数，可脱离 Qt 单测。
- 网络层与 Qt 事件循环解耦：qasync 单线程同循环下，同步 HTTP 不得跑在循环里。

**Non-Goals:**

- 不做发布资产下载、校验和比对、自替换或重启（L2/L3 明确排除）。
- 不做 `min_supported_version` 之类的强制升级闸门。
- 不建 Gitee 侧的发布流水线，也不做 GitHub→Gitee 的自动同步。
- 不引入自动生成的 `latest.json` 提交（避免 CI 反向 push 与 `[skip ci]` 循环）。
- 不改动 `window_geometry.json` / `clients.json` 的既有 schema。

## Decisions

### D1 版本真源用 `src/version.py`，构建信息用生成的旁路文件

`__version__` 以模块常量形式存在；提交标识与构建时间不写进真源，而由构建脚本生成 `src/_build_info.py`（加入 `.gitignore`），`version.py` 以 `try/except ImportError` 读取，缺失即为 `dev` 构建。

被否决的替代方案：构建期临时改写 `version.py`（污染工作区、异常中断会留下半改状态）；`importlib.metadata`（项目从未以 distribution 形式安装，冻结环境里没有 metadata 可读）；把版本放进 `pyproject.toml`（要引入打包后端，与"只有 requirements.txt"的现状冲突，见 proposal）。

被否决的替代方案之二：以 git tag 为真源、构建时生成 `version.py`。它更"正统"，但代价是本地 `build_exe.ps1` 与源码直跑都要维护一条 `git describe` 回落分支；且 `src/` 下会出现生成物。

### D2 exe 版本元数据由构建脚本从真源派生

`build_exe.ps1` 读取 `__version__` 与 `channel`，生成 PyInstaller 版本资源文件后传 `--version-file`；解析失败或版本不符合 `X.Y.Z` 即 `throw`，不产出无元数据的 exe。不在 `.spec` 文件里硬编码版本（`.gitignore` 已忽略 `*.spec`，且会形成第二处真源）。

### D3 关于页与标题栏走 Python 注入，状态栏走 scoped QSS

`tab_about` 的内容在 `setupUi()` 后填充；窗口标题在 Python 侧覆盖 uic 生成的 `MainWindow` 文案。状态栏提示控件的配色通过 `theme.build_qss()` 追加的 objectName 限定规则实现，延续"token 层在 Python 侧、`.ui` 不动"的既有方向。

### D4 发布清单是仓库文件，两源同一 URL 形态

`update/latest.json` 随版本 bump commit 一并提交，检查端按 Gitee raw → GitHub raw 顺序尝试：

```
  Gitee   https://gitee.com/yanyang517/power-supply-master/raw/master/update/latest.json
  GitHub  https://raw.githubusercontent.com/yanyang517/powerSupplyMaster/master/update/latest.json
```

两个仓库名不同，因此配置项是**完整 URL 列表**而不是 owner/repo 拼接——这是本次唯一被迫承认的双源差异，写进模块默认值即可，用户仍可覆盖。

被否决：把清单作为 release 附件上传——资产 URL 含 tag，而"最新 tag"正是待求量，构成循环依赖。被否决：CI 自动生成并提交清单——GitHub Actions 推 Gitee 需另配部署密钥，且自动提交要处理 workflow 触发循环，为省一行手工编辑不值得；漂移风险改由 D6 的校验闸门承担。

### D5 网络与比较：标准库 + 自建解析，全部在线程池执行

取数用 `urllib.request`（`probe()` 是同步函数，返回 `LatestInfo | None`），调用方 `await asyncio.to_thread(...)`——qasync 与 Qt 共用一个事件循环，同步 HTTP 直接跑在循环里会冻住界面。候选源在同一个工作线程内**并发**发起、按优先级取第一个解析成功的结果；实测（见 `doc/update_notice.md`）本机到 `raw.githubusercontent.com` 是握手超时而非快速失败，顺序回退会让每次检查先白付 5 秒。

TLS 用 `ssl.create_default_context()`。实测显示 Windows 上默认上下文已能校验两个可用源，`truststore` 与默认上下文结果一致，故**不使用 `truststore`**：它只提供 `inject_into_ssl()` 这一进程级全局入口，会波及 MCP 通路的既有网络行为，而没有收益。

比较用自实现的 `(major, minor, patch)` 元组解析，不引入 `packaging`：它虽已在环境中，但进运行时导入图就要额外确认 PyInstaller 收集，收益仅是省十几行解析。

### D6 一致性校验放在发布流程，而不是运行期

`scripts/gen_manifest.py --check` 比对 `version.py`、`latest.json` 与当前 tag 三方；release 工作流在 `gh release create` 之后用 app 实际会用的两个 raw URL 回读并断言版本等于 tag。后者是本 change 唯一能证明"用户真的会收到提示"的自动化检查——S2 的主要失效模式是静默的：清单没到位不会报错，只会永远不提示。

### D7 关于页提供"立即检查"，绕过节流

自动检查默认 24 小时间隔且开发构建不提示，这两条叠加会让新功能在开发机上几乎不可观测。关于页因此放一个手动检查入口，不受 `dev` 短路与间隔限制，结果直接显示在页面上（含失败原因）。它同时是这套逻辑的人工验收手段，替代掉本会需要的集成测试脚手架。

### D8 提示状态文件 `config/update_state.json`

沿用 window_geometry 的路径与 `schema_version` 规则，字段为 `last_checked`、`dismissed_version`、`disabled`。文件缺失或损坏视为空状态并继续，不弹窗、不阻断启动。

## Risks / Trade-offs

- [Gitee raw 的可达性、匿名限制与 CDN 缓存刷新延迟未经实测] → 实施第一步做一次性 spike 验证两个 URL；若 Gitee raw 不可用，只调整 `update/latest.json` 的默认源顺序与 URL，不动探测逻辑与 spec。
- [Windows 冻结环境下 HTTPS 证书可能取不到] → 开发机实测已通过（默认上下文可校验并取回 Gitee raw）；剩余风险只在 onedir 产物，验收方式是构建后从关于页手动触发一次检查并确认返回的是清单内容而非证书错误。
- [静默失败：清单未同步导致永远不提示] → D6 的发布期回读断言；D7 的手动检查入口把失败暴露成可见文本。
- [启动期出站请求拖慢界面或泄露到内网测试环境] → 延迟 5 秒 + 线程池 + 超时 5 秒 + `--no-gui` 与 `disabled` 两个开关；探测失败只记 `logger.info`。
- [`latest.json` 与 `version.py` 双写有漂移窗口] → 接受：两者语义不同（代码内真源 vs 对外公告），由 `--check` 卡住；替代方案（运行时只信 tag）在本地开发场景更糟。
- [元组解析与语义化版本预发布规则的取舍] → 本次只支持 `X.Y.Z`，`-rc`/`-beta` 显式忽略并在解析失败时不提示；将来要预发布通道再改，不影响已写的提示行为。

## Migration Plan

1. 首个 bump commit：新增 `src/version.py`（取 `1.0.0`，理由见开放问题 O1）、`update/latest.json`、`config` 状态文件与探测模块，同时改 `main_window.py`、`build_exe.ps1`、release 工作流。
2. 打 tag `v1.0.0`，按项目约定以 `git merge --no-ff` 合入 master 后，分别 push 到 GitHub 与 Gitee；清单随 master 到位，无需额外发布动作。
3. 回滚：revert 合并提交即可。新增字段对 `setting_query` / `get_status` 是纯增量，旧客户端忽略即可；`config/update_state.json` 是新增文件，删除无副作用。

## Open Questions

- O1 首个版本号取 `1.0.0` 还是对齐 `doc/project_knowledge_v1.0.md` 已有的"文档 v1.0"语义取更高值；不影响任何接口，实施时按用户一句话确定。
- O2 清单是否要带 `notes`（更新说明正文）还是只给发布页 URL；取决于用户是否愿意在 bump commit 里多写几行，机制两侧都支持。
- O3 后续若加预发布/beta 通道，是走多份清单文件还是清单里的 `channel` 字段；本设计的解析与比较都留了扩展位置，暂不决定。
