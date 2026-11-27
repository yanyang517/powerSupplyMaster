# AI 协作规则

## 分支与合并

- 开始修改任何工程文件前，必须确认当前分支不是 `master`。如果当前位于 `master`，先创建并切换到独立工作分支，禁止直接更新 `master`。
- 所有代码、配置和文档改动都必须通过工作分支合并回 `master`，不得直接提交、推送或改写 `master`。
- 合并回 `master` 时必须保留合并提交，使用非 fast-forward 合并（`git merge --no-ff <工作分支>`），不得使用 fast-forward 合并。
- 需要同步 `master` 的最新改动时，应将 `master` 合并到工作分支，而不是反向直接更新 `master`。

## 界面维护

- 界面统一由 `src/views/` 下的 Python 代码构建，不再维护 `.ui` 文件，也不使用 Qt Designer/uic 生成代码。
- 修改 `src/views/ui/*_ui.py` 或窗口类时直接改 Python 布局、文案和样式；这些文件不是只读生成物。
- 控件 `objectName` 是窗口逻辑、Presenter 和测试的公共契约，改名时必须同步检查所有引用。
- UI 改动至少运行离屏测试：`QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest src/views -q`。
