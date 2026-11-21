# Proposal

## Why

主窗口和悬浮窗每次启动都由操作系统/Qt 默认摆放：主窗口落在系统默认位置、悬浮窗出现在屏幕左上区域附近，用户每轮调试都要重新拖动一次才能把悬浮读数放到电源屏幕旁边。项目目前完全没有持久化机制（无 QSettings、无配置文件读写），也没有任何 `move()`/`closeEvent()` 定位代码，这个重复成本是可以一次性消掉的。

## What Changes

- 新增窗口几何历史的持久化：主窗口记录位置 + 尺寸，悬浮窗记录位置（其尺寸由 `setFixedSize` 固定）。
- 新增历史载体：项目内 JSON 文件 `config/window_geometry.json`，随仓库便携、可直接查看与手工修正。
- 启动时恢复：读到合法历史 → 按历史摆放两个窗口；历史缺失、损坏或落在当前屏幕之外 → 回退默认布局。
- 新增默认布局（历史不可用时）：主窗口在所在屏幕可用区水平/垂直居中；悬浮窗在屏幕可用区右下角，留固定边距且不越界。
- 新增保存时机：主窗口关闭时集中写入两个窗口的当前几何。
- 不改变任何窗口的可见性、层级、透明度、拖动等既有行为；悬浮窗右键菜单三项误绑 `self.close` 的缺陷**不在本次范围**（见 Impact 备注）。

## Capabilities

### New Capabilities
- `ui/window-geometry`: 窗口（主窗口与悬浮窗）几何的持久化、启动恢复、历史失效判定与默认摆放行为。

### Modified Capabilities
（无。`openspec/specs/` 当前为空，本项目尚无已归档 capability spec。）

## Impact

- 受影响代码：
  - `src/views/main_window.py`（构造期恢复几何；新增 `closeEvent` 触发保存）
  - `src/views/floating_window.py`（构造期恢复/默认摆放）
  - 新增几何持久化模块（读写 JSON、屏幕有效性校验、默认布局计算）
- 受影响目录：新建 `config/`，其中 `window_geometry.json` 为运行期产物（机器相关，是否纳入版本控制见 design 决策）。
- 依赖：仅用 Python 标准库 `json` + PySide6 已有 `QGuiApplication.screens()` / `QScreen.availableGeometry()`，不引入新第三方依赖。
- 兼容性：`--no-gui`（`src/app.py:29`）路径不受影响；旧版本无历史文件，首次启动即走默认布局。
- 范围外备注：悬浮窗右键菜单「显示主窗口 / 关闭电源输出 / 隐藏悬浮窗」全部绑定 `self.close`（`src/views/floating_window.py:79-81`），属独立缺陷，建议另开 change。
- 工作方式：按项目约束，实施在 `git worktree` 独立工作目录 + 功能分支上进行，合入 `master` 使用 `git merge --no-ff`。
