# Proposal

## Why

全仓库当前没有任何图标资产与图标调用：`find` 结果为 0 个 `.ico`/`.svg`/`.qrc`，`app.py` 从未调用 `setWindowIcon`，`scripts/build_exe.ps1` 未传 `--icon`，全仓 `setIcon` 出现 0 次。桌面上运行的是 PyInstaller 默认图标，界面里每一个页签、每一个状态行都只能靠中文长句辨识——尤其是「控制权由谁持有、还剩多久」「这个客户端是 AI 通路还是脚本」「设备掉线但租约未释放」这三类需要一眼扫出的状态，现在全部退化成阅读文本。

现在做这件事的时机条件是：`add-version-info-and-update-notice` 已合入 master（160b643…160bde4），本 change 要落的 `scripts/build_exe.ps1`（已含 `--version-file` 块）与 `src/views/main_window.py`（`_fill_about_tab()`）不再与在飞工作冲突。

## What Changes

- 新增**应用标识**：一张原创 master SVG，按 UI 图标同一套线稿语言绘制，派生出 16/20/24/32/40/48/64/128/256 多尺寸 ICO。落点为窗口标题栏与任务栏、exe 文件图标、关于页。
- 新增**UI 图标系统**：vendored 的开源线稿字形（Tabler Icons，MIT；Lucide，ISC）加上一个按主题 token 变色、按渲染尺寸调整描边宽度的图标助手。不引入图标字体，不引入新的运行时依赖。
- 图标落点（全部在 Python 侧注入，不改 `.ui`、不建 uic 流程）：5 个页签、`connect_Btn`/`disconnect_Btn`、`ouput_ctrl_Btn`、控制权状态行、客户端列表逐行、吊销控制权按钮、悬浮窗右键菜单。
- 修改 `scripts/build_exe.ps1`：向 PyInstaller 传 `--icon`，并把产物内图标资源的存在性纳入构建后校验。
- 附带修正一个既有缺陷：`FloatingWindow.showContextMenu` 的三个菜单项当前全部绑到 `self.close()`，「关闭电源输出」并不关闭输出。给菜单加图标会让这个错误变得不可忽略，因此在本 change 内一并接对语义动作。
- **明确不做**：系统托盘图标（属于新能力，不是图标）；波形页 `QChart` 配色（既有约定为独立 change）；`UpdateNoticeWidget` 自身的图标；读数标签的 `U=`/`I=` 前缀（那是文字而非图标，字形库也不提供）；`auto_reconnect_CB` 复选框（其 indicator 已被 QSS 接管，塞不进图标）。

实施按项目约定在 `git worktree` 建立的独立工作目录中进行，完成后以 `git merge --no-ff` 合入 master。

## Capabilities

### New Capabilities

- `ui/app-identity`: 应用标识图形的来源与形式约束，以及它在窗口、任务栏、可执行文件与关于页各落点上必须一致呈现的要求；含小尺寸档位的可读性要求。
- `ui/icon-system`: 界面图标的风格契约、第三方字形的引入与授权约束、运行时渲染路径，以及"状态变化不得只靠色相区分"在图标层的落地要求。

### Modified Capabilities

无。关于页新增标识是新增要求，归入 `ui/app-identity`；`app/version-info` 的「界面展示当前版本」既有要求内容不变，不需要 delta。

## Impact

代码：新增 `src/resources/`（字形 SVG、master SVG、生成的 `app.ico`、授权文本）、`src/views/icons.py`（图标助手）、`scripts/gen_icon.py`（字形与 ICO 生成）；修改 `src/app.py`、`src/views/main_window.py`、`src/views/access_panel.py`、`src/views/floating_window.py`、`scripts/build_exe.ps1`，以及对应的视图测试。

依赖：运行时零新增第三方依赖——`PySide6.QtSvg` 已随 PySide6 存在并在当前 `.venv` 实测可导入；ICO 生成用 Qt 自身栅格化 + 纯 Python 写容器，不引入 Pillow（`.venv` 实测无 PIL）。

风险：`QIcon("*.svg")` 依赖 Qt 的 svg iconengine 插件，PyInstaller 收集不全时表现为"开发环境正常、打包后图标静默消失"；渲染路径 MUST 走 `QSvgRenderer` 栅格化后构造 `QIcon`。按钮加图标会带来宽度增长，串口行那一排的横向余量需实测。
