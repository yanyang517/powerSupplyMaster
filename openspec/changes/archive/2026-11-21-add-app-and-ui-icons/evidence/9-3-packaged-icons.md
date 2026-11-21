# 9.3 产物内图标：降级为可选，改由冻结路径自检兜底

## 决议

9.3 原本要求的"启动 exe 肉眼看页签/按钮/列表行/标题栏/exe 图标"依赖真机截图，而本会话的桌面不可交互
（`QScreen::grabWindow` 只返回壁纸，截不到窗口），自动化覆盖不到人眼这一环。用户选择**降级为可选、
直接合入**。

降级不等于放弃验证：它要防的其实是"开发有图标、产物静默消失"，而这一条可以自动证明——第 9.1/9.2 组已把
"资源没被收集"变成构建失败，本次再把"收集了但在冻结路径下渲染不出来"也纳入实测，剩下的只有肉眼审美部
分，随 9.4 一起留到发布前。

## 兜底证据（本次实测）

1. **收集完整性（9.1/9.2 已验，此处复述）**：`dist/powerSupplyMaster/_internal/resources/`
   文件数与 `src/resources/` 一致（22 个），`-VerifyOnly` 对故意删除的 `app.ico`、整个 `icons/`
   目录、以及单个 `icons/tabler/power.svg` 都能退出码 1 并报出缺失相对路径。
2. **冻结路径渲染等价（本条新增）**：一次性脚本把 `sys.frozen`/`sys._MEIPASS` 指向 `dist/.../_internal`，
   让 `views/icons.resources_dir()` 走打包分支，逐个字形 × 4 个角色 × {16,20,24} 档 + 标识 ×
   `MARK_ICON_SIZES` 共 **223 次渲染**与开发目录做 ARGB32 逐像素哈希比对：**0 处差异**；
   `app.ico` 与 `src/resources/app.ico` 逐字节相同（20603 字节）；`app_icon().availableSizes()`
   = {16,20,24,32,48,64,256}，标题栏的 16px 用的是现成档位而不是缩放。

复现：`python <临时脚本> D:/git/wt/add-app-and-ui-icons/dist/powerSupplyMaster/_internal`
（脚本不进仓库，与 3.1 的出图脚本同等处理）。

## 仍未覆盖的部分

- **exe 真机外观**：靠启动一次确认。静态证据已尽力：`_internal/` 内含 `QtSvg.pyd` 与 `Qt6Svg.dll`，
  且 `plugins/iconengines/qsvgicon.dll` 这次也被收集了；再加上 `views/icons.py` 在模块级硬
  `from PySide6.QtSvg import QSvgRenderer`，缺模块的失败形态是启动即崩，而不是静默无图标。
  D2 仍禁止 `QIcon("<path>.svg")`：插件这次被收集是运气，且那条路径拿不到 D3 的改写能力。
- **exe 文件图标在资源管理器里的呈现**、任务栏/标题栏实际绘制：属于发布前手动清单一类，与 9.4 一并补。
- D9 的路径规则（图标进 `_MEIPASS`、配置留 exe 同级）已由 9.1/9.2 的构建脚本与 `resources_dir()`
  双向锁定，本次未改动。
