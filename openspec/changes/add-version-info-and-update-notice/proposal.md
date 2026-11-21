# Proposal

## Why

软件目前没有任何自身版本标识：全仓没有 `__version__`、没有 `pyproject.toml`，`git tag` 列表为空，PyInstaller 产出的 exe 属性里版本字段空白，UI 的「关于」页 (`tab_about`) 是一个空标签页。与此同时 `.github/workflows/release.yml` 已经以 `v*` tag 为发布触发器，但 tag 只进了 zip 文件名，运行中的程序对自己是什么版本一无所知。

缺少版本标识使"用户手上跑的是哪一版"无法回答，也让"有新版本时告知用户"这件事没有可比较的基准。本次变更先把版本真源与展示做扎实，并在此之上提供**只提示、不下载**的新版本提醒。

## What Changes

- 新增版本真源 `src/version.py`：`__version__` 语义化版本号，加上仅构建期注入的 commit 与构建时间；开发环境未注入时回落为 `dev` 标识。
- 新增版本展示落点：窗口标题、启动日志、`tab_about`「关于」页内容（全部在 `views/main_window.py` 侧以 Python 注入，不修改 `.ui`、不引入 uic 重新生成流程）。
- 修改 `scripts/build_exe.ps1`：由 `src/version.py` 生成 PyInstaller `--version-file`，使 exe 的 Windows 文件属性携带产品名与版本号。
- 新增 `update/latest.json` 发布清单（`schema_version` 沿用项目既有的 JSON 约定），随版本 bump commit 一并提交，Gitee 与 GitHub 两源各存同一份。
- 新增新版本探测模块：按 Gitee raw → GitHub raw 顺序回退拉取清单，超时 5 秒，仅在远端版本严格大于本地时提示；后台任务执行，启动延迟 5 秒、间隔 24 小时，任何失败静默记日志且不影响主流程。
- 新增提示落点：复用当前从未被使用的 `QStatusBar` 显示一条提示，动作为「查看发布页」（打开系统浏览器）与「忽略此版本」；`--no-gui` 模式不探测。
- 新增状态持久化：上次检查时间与已忽略版本写入项目本地 JSON，沿用 `views/window_geometry.py` 的路径解析规则（冻结时落在 exe 同级 `config/`）。
- 修改 `setting_query` 响应与 MCP `get_status`：回包携带应用版本，使 TCP 与 AI 客户端通路也能识别上位机版本。
- 新增发布校验：`scripts/gen_manifest.py --check` 与 release 工作流中的 tag / 清单 / raw 回读三方对齐检查，任一不一致即构建失败。

非破坏性变更：`setting_query` 与 `get_status` 只增加字段，现有客户端不受影响。实施按项目约定在 `git worktree` 建立独立工作目录进行，完成后以 `git merge --no-ff` 合入 master。

## Capabilities

### New Capabilities

- `app/version-info`: 应用版本号的唯一真源、格式约定、构建期注入规则，以及在各展示与产物落点（标题、日志、关于页、exe 版本资源、协议回包）的一致性要求。
- `app/update-notice`: 远端最新发布信息的获取与解析、多源回退与失败处理、版本比较与提示判定、提示的呈现与用户动作、节流与持久化状态、可关闭性。

### Modified Capabilities

- `power-supply-control`: 「限值可经 setting_query 查询」需求扩展为响应同时返回应用版本。
- `mcp-bridge`: 「提供 get_status 聚合状态工具」需求扩展为返回值包含应用版本。

## Impact

代码：新增 `src/version.py`、`src/update/`（清单拉取、比较、状态存储）、`scripts/gen_manifest.py`、`update/latest.json` 及对应测试；修改 `src/views/main_window.py`、`scripts/build_exe.ps1`、`.github/workflows/release.yml`、`src/server/protocal/protocal.py`、`src/server/request_handles.py`、`src/mcp_server/tools.py`。

依赖：零新增第三方依赖。网络使用标准库 `urllib.request` 配合已安装的 `truststore`（走系统根证书，避免为冻结环境引入 certifi）；版本比较用自实现元组解析，不引入 `packaging` 到运行时导入图，以保证 PyInstaller 收集无额外 hidden-import 负担。

运行时风险：应用主职是离线控制硬件，因此探测必须与设备通路完全隔离——不阻塞启动、不改设备状态、失败不上抛到 UI 线程。

未知项（需实施期实测）：Gitee 公开仓库 raw URL 在冻结环境下的可达性与缓存刷新延迟；`truststore` 在 PyInstaller onedir 下的证书加载。两项均以一次性 spike 验证，验证失败则回退为纯 `urllib` 默认 SSL 上下文。
