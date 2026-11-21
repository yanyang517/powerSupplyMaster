# Tasks

## 1. 工作目录与基线

- [x] 1.1 用 `git worktree` 为本 change 建立独立工作目录并在其上开功能分支，验证 `git worktree list` 出现新目录且该目录 `git rev-parse --abbrev-ref HEAD` 不为 `master`
- [x] 1.2 采集改前基线：在 worktree 内启动 GUI，记录主窗口与悬浮窗的首次出现位置（截图或 `frameGeometry()` 打印），并确认此时仓库根不存在 `config/window_geometry.json`，验证两条记录均已保存供 5.1 对照
      > 实测记录见 `evidence/baseline_geometry.txt`。附带发现：本屏（A34QG，avail=(124, 0, 2653, 1152)，dpr 1.25）上 Qt/Windows 的默认摆放恰好等于可用区居中（主窗 geom 左上角 (1155, 265) 与 `default_main_rect` 计算值一致），因此「无历史 → 默认居中」这一项与基线同位属预期，不作为 3.1/5.1 的区分判据；区分判据改用「有历史时回到历史位置而非居中」。

## 2. 几何持久化单元（`src/views/window_geometry.py`）

- [x] 2.1 实现文件路径推导与目录创建（由模块位置向上两级得仓库根，落点 `config/window_geometry.json`；目录缺失时 `mkdir(parents=True, exist_ok=True)`），验证脚本从 `D:\` 与从 `src\` 两种 cwd 各调一次路径函数，断言返回同一绝对路径且末段为 `config\window_geometry.json`
- [x] 2.2 实现 `load_entries(path)` 与 `version`/字段校验：文件缺失、JSON 非法、`version` 非 1、必需字段缺失或类型非法（非整数、负尺寸、bool 混入）一律返回 `None` 并 `logger.warning`，验证以 `pytest test/test_window_geometry.py` 覆盖上述每种输入各一条断言且全绿
      > 实施更正：测试按项目既有约定与包同目录（先例 `src/server/test_client.py`），落点 `src/views/test_window_geometry.py`，命令 `python -m pytest src/views/test_window_geometry.py`（仓库根 `test/` 是空目录，git 不跟踪）。组 2 实测 41 passed。
- [x] 2.3 实现 `is_rect_usable(rect, available_rects)`（交集面积 ≥ rect 面积 50% 判有效），验证单测含「完全在内」「越过边缘 40%」「越过边缘 60%」「多屏取第二块屏」四例且断言与阈值语义一致
- [x] 2.4 实现 `clamp_into(rect, available_rect)` 与两个默认摆放函数 `default_main_rect`（可用区居中，尺寸由调用方传入）、`default_floating_pos`（可用区右下角、常量边距 24 px 且随可用区裁剪），验证单测断言居中结果的左上角坐标为 `(avail.x + (avail.w - w)//2, avail.y + (avail.h - h)//2)`，且当可用区小于窗口时悬浮窗坐标仍不越出可用区
- [x] 2.5 实现 `save_geometry(...)`：写同目录临时文件后 `os.replace` 原子替换，输出为可读 JSON（缩进 + `version` + `windows.main{x,y,width,height,screen}` + `windows.floating{x,y,screen}`），捕获 `OSError` 仅告警不抛；验证单测在只读目录场景下断言函数不抛异常且原文件内容保持不变，正常场景断言写入后可被 2.2 的 `load_entries` 读回

## 3. 主窗口接线

- [x] 3.1 在 `MainWindow.setupUi()` 之后、任何 `show()` 之前接入恢复：历史有效则 `setGeometry(clamp_into(...))`，否则按 `default_main_rect` 用界面默认尺寸居中，验证启动后 `main.geometry()` 与预期坐标一致且首帧即到位（截图不与 1.2 基线同位）
      > 判据更正（有实测支撑）：本屏 Qt 默认摆放恰等于可用区居中，故默认布局与 1.2 基线同位，「不与基线同位」不成立；改用「有历史时不居中而回历史」（场景 3 的 `not re-centered when history exists` 断言）。
- [x] 3.2 为 `MainWindow` 新增 `closeEvent`，在 `super().closeEvent(event)` 之前调用 `save_geometry` 同时落盘主窗 `self.geometry()` 与悬浮窗 `self.floating_window.geometry()`，验证关闭后 `config/window_geometry.json` 存在且其中的 `main`/`floating` 值等于关闭前两个窗口的几何

## 4. 悬浮窗接线

- [x] 4.1 在 `FloatingWindow.__init__` 的 `setFixedSize(407, 81)` 之后接入位置恢复：历史有效用 `move(clamp_into(...))`，否则用 `default_floating_pos` 落在屏幕可用区右下角，验证启动后悬浮窗 `frameGeometry()` 完整包含于所用屏幕 `availableGeometry()`，且右下角与可用区右下角落在常量边距内
- [x] 4.2 确认恢复发生在悬浮窗首次显示之前且不引入可见跳动（`MainWindow.__init__:47-48` 先构造后 `show()`），验证手段：构造期间用 `isVisible()` 断言此刻窗口尚未显示，并对照启动截图确认无「先出现在别处再移动」的痕迹
- [x] 4.3 复核拖动与置顶行为未变：`mousePressEvent`/`mouseMoveEvent` 的相对偏移逻辑、`Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint`、透明度 `enterEvent`/`leaveEvent` 均未被改动，验证 `git diff` 中这些行无变更，且实机拖动一次后行为与 1.2 基线一致

## 5. 集成验收

- [x] 5.1 两轮连续启动实测：第一轮把主窗拖到左上半屏、悬浮窗拖到中部，关闭后第二轮启动，验证两个窗口分别回到上次位置、主窗保留上次尺寸、悬浮窗尺寸仍为 407×81（对照 1.2 基线截图）
- [x] 5.2 失效回退实测：分别构造 (a) 删除配置文件、(b) 文件内容写成非法 JSON、(c) 文件里把 `x` 改到远超任何屏幕的范围，各启动一次，验证 (a)(b)(c) 对应窗口回到默认布局（主窗居中、悬浮窗右下角），应用日志出现告警且不崩溃
      > 越界 (c) 原本只有文件级告警：已在 `restored_rect` 判定越界时补一条 WARNING，使 (a)(b)(c) 均有日志。实测记录见 `evidence/acceptance_probes.txt`。
- [x] 5.3 部分有效场景验证：配置文件里 `main` 合法、`floating` 越界（或反之），启动后确认一个窗口按历史恢复、另一个按默认摆放，证明逐窗口回退而非整体丢弃
- [x] 5.4 回归确认：`--no-gui` 启动一次，验证不创建也不修改 `config/window_geometry.json`，串口服务端功能与改前一致；并在 `.venv`（实测 PySide6 6.11.0，`requirements.txt` 钉 6.10.2）上跑通 `pytest test/test_window_geometry.py`，在汇报中写明实际验证所用版本

## Workflow follow-up

- 以 `git merge --no-ff` 将功能分支合入 master，并在汇报中说明实际使用的合并方式。
- 合入满足项目评审要求后归档本 change（届时 `ui/window-geometry` 进入 `openspec/specs/`）。
- 另开 change 处理悬浮窗右键菜单三项全部误绑 `self.close` 的既有缺陷（`src/views/floating_window.py:79-81`）；本次不动，但 5.1 的「先关悬浮窗再关主窗」路径验收若被该缺陷干扰，需在汇报中说明并以直接 `close()` 绕过。
