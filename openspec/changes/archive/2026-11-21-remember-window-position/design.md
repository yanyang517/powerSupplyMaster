# Design

## Context

现状（见 proposal.md - Why / Impact）：

- `MainWindow(QMainWindow)` 在 `src/views/main_window.py:27`，全仓无任何 `move()`/`setGeometry()`/`resize()` 调用，也没有 `closeEvent`；主窗真正显示发生在 `Presenter.__init__` 的 `self.view.show()`（`src/presenter/presenter.py:28`）。
- `FloatingWindow(QMainWindow)` 在 `src/views/floating_window.py:7`，`Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint` + `setFixedSize(407, 81)`（11、31 行），由 `MainWindow.__init__` 创建并立即 `show()`（`main_window.py:47-48`），即悬浮窗首次显示早于主窗显示；拖动通过 `mousePressEvent`/`mouseMoveEvent` 里的 `self.move(...)`（52-66 行）实现。
- 项目零持久化：无 `QSettings`、无 `configparser`/json 配置读写；`src/server/socket_server.py` 的 json 是网络协议编解码，不可复用。
- 运行期路径约束：入口 `src/app.py` 用 `from views.main_window import ...` 这类以 `src` 为包根的绝对导入，说明可导入根是 `src`，而进程 cwd 不确定。配置文件路径 MUST 由模块自身位置推导，MUST NOT 依赖 cwd 或相对路径字符串。
- 技术栈：PySide6 6.10.2 + qasync（`requirements.txt:13-18`），`pytest 8.4.2` 已在依赖里但 `test/` 目前为空。

## Goals / Non-Goals

**Goals:**
- 一个可被两个窗口共用、可脱离 Qt 窗口单测的几何读写/校验单元。
- 恢复动作严格发生在各窗口首次显示之前，避免可见跳动。
- 历史失效（缺文件、坏文件、跨屏/换分辨率/换缩放）时行为可预期：逐窗口回退默认布局。

**Non-Goals:**
- 不做窗口布局多显示器编排、不做「跟随主窗口」的相对定位策略。
- 不记忆透明度、是否可见、主窗当前 tab 等其它窗口状态。
- 不修悬浮窗右键菜单误绑 `self.close` 的缺陷（`floating_window.py:79-81`）。
- 不引入 QSettings、注册表或新的第三方依赖。

## Decisions

### D1 载体：项目内 JSON 文件，路径由模块位置推导

`config/window_geometry.json`，绝对路径由 `Path(__file__).resolve().parents[2] / "config" / "window_geometry.json"` 推导（模块位于 `src/views/`，向上两级即仓库根）。
- 为什么不用 QSettings：用户要求随仓库便携、可直接阅读与手工修正；QSettings 落在注册表，调试与跨机迁移都更麻烦。
- 为什么不用 cwd 相对路径：`--no-gui` 从任意目录启动都会写歪位置。
- 目录不存在时由保存方 `mkdir(parents=True, exist_ok=True)` 创建，仓库当前不需要预建 `config/`。

### D2 文件结构：带版本的显式窗口表

```json
{
  "version": 1,
  "windows": {
    "main":     { "x": 320, "y": 180, "width": 1000, "height": 700, "screen": "\\.\DISPLAY1" },
    "floating": { "x": 1450, "y": 980, "screen": "\\.\DISPLAY2" }
  }
}
```
- `version` 为后续结构演进留口；读取方遇到不认识的 version 一律按「历史不可用」处理，不做迁移猜测。
- 每窗口记 `screen`（`QScreen.name()`）：只作为「优先用同名屏幕做校验与 clamp」的提示，MUST NOT 单独据此判失效（设备名在不同机器/驱动下不稳定），真正的判据是可用区相交校验。
- 悬浮窗不记尺寸：尺寸由 `setFixedSize` 决定，记了反而误导。
- 字段缺失/类型非法（非整数、负尺寸、bool 混入）→ 整个文件判不可用，而不是逐字段容错，避免出现半套坐标。

### D3 单元划分：纯函数 + 一个薄 store

新增 `src/views/window_geometry.py`：
- `load_entries(path) -> dict | None`：只碰文件与 JSON，异常（`OSError`/`json.JSONDecodeError`/结构非法）统一返回 `None` 并 `logger.warning`。
- `is_rect_usable(rect, available_rects) -> bool`：判据为 **rect 与某个 available_rect 的交集面积 ≥ rect 面积的 50%**。选 50% 而非「完全包含」：允许 DPI 缩放或分辨率微调后仍保留用户位置；选它而非「左上角可见即可」：避免窗口 90% 掉出屏幕。
- `clamp_into(rect, available_rect) -> QPoint`：把左上角平移进可用区（可用区比窗口小时保证左上角可达）。
- `default_main_rect(available_rect, size)` / `default_floating_pos(available_rect, size, margin)`：居中 / 右下角边距摆放；`margin` 取常量 24 px，需 ≥ 0 且随可用区裁剪。
- `save_geometry(path, main_rect, main_screen, floating_pos, floating_screen)`：先写同目录临时文件再 `os.replace`，保证读到的永远是完整 JSON；任何 `OSError` 只告警。
- 屏幕几何获取（`QGuiApplication.screens()` / `primaryScreen()`）只出现在调用侧的薄封装里，上述函数全部接受显式矩形参数 —— 这样单测不需要真实屏幕。
- 备选：把逻辑塞进 `MainWindow` 与 `FloatingWindow` 各自的构造函数。否决原因：两个窗口要共享同一套校验与默认摆放，且无法单测。

### D4 恢复时机：各窗口 own `__init__` 内、首次 show 前

- `MainWindow`：`setupUi()` 之后立即取历史；有效则 `setGeometry(clamped)`，无效则用默认尺寸居中。此时主窗尚未 `show()`（show 在 `presenter.py:28`），无可见跳动。
- `FloatingWindow`：在 `setFixedSize(407, 81)` 之后决定左上角；有效历史用 `move(clamped)`，否则用屏幕可用区右下角。`MainWindow.__init__:47` 构造完才 `.show()`，因此也在首次显示之前。
- 悬浮窗默认摆放基准：**屏幕可用区右下角**（取承载屏幕的 `availableGeometry()`，优先历史里的同名屏幕，否则主屏），与主窗位置无关。
- 尺寸来源：默认尺寸仍由 `Ui_MainWindow.setupUi()` 决定，恢复分支只在有历史时覆盖尺寸，避免把 `.ui` 的默认值抄成硬编码常量（符合「不动 `.ui`、不建 uic 流程」的既有 UI 约束）。

### D5 保存时机：主窗 `closeEvent` 统一落盘

`MainWindow.closeEvent` 里读 `self.geometry()` 与 `self.floating_window.geometry()`，调用 store 保存后再 `super().closeEvent(event)`。
- 悬浮窗先被关闭也可用：Qt 保留已隐藏 widget 的最后几何，无需监听其销毁。
- 为什么不在 `FloatingWindow.mouseReleaseEvent` 即时写：用户选择关窗集中保存，换取「一次会话一次写盘」和单一写入点，代价是强杀进程丢本次历史 —— 记录为已接受取舍。
- 主窗关闭后进程是否退出属既有行为，本 change 不改；因此 MUST NOT 在悬浮窗关闭路径上写盘，避免同一文件出现第二个写入点。

### D6 生效范围：仅 GUI 路径

读写都发生在窗口构造/关闭时，`--no-gui`（`src/app.py:29,43`）根本不创建窗口，天然不触碰文件，无需额外开关。

## Risks / Trade-offs

- **配置文件随机器/用户不同，却保持可提交** → 每次换布局都会产生 diff 噪声。缓解：文件只影响坐标、失效即回退默认，团队若嫌吵可另开 change 把它加入 `.gitignore`；本次遵循用户选定的「便携可提交」语义，不预先忽略。
- **50% 相交判据放过了「大部分在屏幕外」的位置** → 靠 D3 的 clamp 兜底：判定有效后仍把窗口拉回可用区，用户看到的位置可能与上次略有偏差，但保证可见可拖动。
- **qasync 事件循环 + 帧率** 下若把保存放进 `mouseMoveEvent` 会频繁写盘 → 设计上只在 `closeEvent` 写一次（D5）。
- **多屏设备名不稳定**（`\\.\DISPLAY1` 在重装驱动后可能变） → 设备名只用于优先选屏，判据只看几何相交，不匹配也不致命。
- **主窗关闭但悬浮窗仍可见导致进程驻留** → 属既有行为；`closeEvent` 已在其之前完成落盘，不受驻留影响。
- **`test/` 目前为空、无 conftest 与 pytest 配置** → 新增单测需要自己把 `src` 加进导入路径，否则 `from views.window_geometry import ...` 与现有绝对导入风格对不上。

## Migration Plan

无数据迁移：老版本没有历史文件，首次启动即走默认布局，第二次启动起走恢复路径。回滚 = 还原 `main_window.py` / `floating_window.py` 的改动并删除 `src/views/window_geometry.py`；残留的 `config/window_geometry.json` 不会被旧代码读取，可直接删除。
