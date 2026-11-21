# Tasks

## 1. 工作目录与资源骨架

- [x] 1.1 按项目约定用 `git worktree` 建立独立工作目录并在其上开 `feature/add-app-and-ui-icons` 分支，验证 `git worktree list` 显示该目录且 `git -C <worktree> status` 干净
- [x] 1.2 创建 `src/resources/icons/` 与 `src/resources/`，在 `src/resources/NOTICE.md` 记录字形来源、库版本与逐文件许可（Tabler MIT / Lucide ISC），验证文件存在且列出的库版本号与后续 1.3 拉取的一致
- [x] 1.3 锁定 Tabler 与 Lucide 的具体版本号，把 design.md D8 落点表所需的字形以库内原名 vendored 进 `src/resources/icons/`，验证 `ls src/resources/icons | wc -l` 与落点表条目数一致且无文件为空

## 2. 图标助手与渲染管线

- [x] 2.1 实现 `src/views/icons.py` 的 `icon(name, role, size)`：读 SVG 文本、把 `currentColor` 换成 `TOKENS['dark'][role]`、按 `size<=20` 用 `stroke-width=2.5` / `size>=24` 用 `2.0` 改写根元素、经 `QSvgRenderer` 栅格化后返回 `QIcon`，验证 `src/views/test_icons.py` 断言同一字形在 16 与 32 档产出的 pixmap 尺寸与像素非空
- 2.1 备注：MUST NOT 出现 `QIcon("<path>.svg")` 形式（svg iconengine 插件收集不可靠，见 design.md D2）
- [x] 2.2 在 `icons.py` 加入按 `devicePixelRatio` 生成 pixmap 的处理，验证 `test_icons.py` 在 dpr=1 与 dpr=1.5 下请求同一图标时逻辑尺寸一致而物理像素不同
- [x] 2.3 实现容错降级：字形文件缺失、SVG 解析失败、渲染结果为空三种情况返回空 `QIcon` 并记 `logger.warning`，不向上抛，验证 `test_icons.py` 三种输入均不抛异常且返回 `icon.isNull() is True`
- [x] 2.4 实现 frozen 环境的资源路径解析（`sys._MEIPASS` 优先，源码运行回落到 `src/resources/`），验证 `test_icons.py` 在两种 `sys` 状态下解析到正确目录，且解析结果与 `config/clients.json` 的 exe 同级规则互不影响（design.md D9）
- [x] 2.5 确认图标层不含任何颜色常量：`grep -n "#[0-9a-fA-F]\{6\}" src/views/icons.py` 无命中，验证取色全部经 `tokens()` 完成

## 3. 字形选型实测

- [x] 3.1 用一次性脚本（不进仓库）以 2.1 的同一条管线渲染落点表全部字形在 16/20/24/32 档的实际像素，并输出 16px 档的 6x 最近邻放大图，验证两张 PNG 已产出
- [x] 3.2 依据 3.1 的实测图逐落点定稿字形，凡 16px 主体不可辨识或语义漂移的（design.md D8 已点名 `tabler-circle-half`、`tabler-wifi-off`）替换为候选并重新出图，验证定稿表写入 `design.md` 的落点表且与 `src/resources/icons/` 内文件一一对应
- [x] 3.3 解决 design.md 的 Q1：为控制权"持有者断线但租约未释放"从 `tabler-circle-dashed` / `tabler-clock` / 弱化插头类中实测选定，验证选定结果连同实测图结论记入 design.md
- [x] 3.4 为 `ui/icon-system` 的形态差异要求补测试：`test_icons.py` 断言控制权三态所用的三个字形文件名互不相同（不依赖颜色区分）

## 4. 主窗口落点接线

- [x] 4.1 在 `MainWindow.setupUi()` 给 5 个页签 `setTabIcon()`，验证以 `QUiLoader` + `QT_QPA_PLATFORM=windows` 渲染主窗口截图，页签栏五个图标全部可见且未把文字挤掉
- [x] 4.2 给 `connect_Btn`/`disconnect_Btn`/`ouput_ctrl_Btn` 设置图标，颜色 token 分别取 `primary`/`danger`/`success`，验证截图里三个按钮图标可见，且输出开关的 2px 边框与字重形态线索未被图标取代
- [x] 4.3 实测串口那一行加图标后的按钮宽度与横向余量，若溢出则按 design.md 风险条目给出的退路处理，验证截图中该行控件无被裁切、无换行
- [x] 4.4 在 `src/views/test_client_access.py` 或新增视图测试中断言五个页签与三个按钮的 `icon().isNull()` 为 False，验证 `pytest src/views` 通过

## 5. 控制权与客户端列表接线

- [x] 5.1 在 `AccessPanel.refresh()` 按控制权三态设置 `holder_label` 的图标，验证 `test_icons.py`/视图测试覆盖三种 `lease.snapshot()` 输入各自得到预期字形且互不相同
- [x] 5.2 重构 `AccessPanel._client_rows()` 使其返回 (文本, 图标角色) 结构而非纯字符串，为 `QListWidget` 每行 `setIcon()`，验证已登录/未登录/待确认/断线持有四类行各得一个字形，且原 `●` `◀` 字符标记不再作为唯一形态线索保留在文本里
- [x] 5.3 给「吊销控制权」按钮设置图标，验证截图可见且按钮禁用态（`lease.holder is None`）下图标随 `text_dim` 变弱

## 6. 悬浮窗菜单动作修正与图标

- [x] 6.1 新增 `FloatingWindow.request_show_main` / `request_output_off` 两个信号并在 `MainWindow` 侧接到 `raise_()` 与 `presenter.set_on_off(False)`，验证 `src/views/test_floating_actions.py` 断言两个信号发射后主窗口被置顶、输出被关闭，且三个菜单项不再全部指向 `close()`
- [x] 6.2 给三个菜单项加图标（主窗口 / 电源 / 可见性关闭），验证渲染菜单截图三个图标可见
- [x] 6.3 确认「隐藏悬浮窗」仍走关闭路径且不影响主窗口，验证 6.1 的测试覆盖该分支

## 7. 应用标识与评审门

- [x] 7.1 按 design.md D5 的契约绘制 `src/resources/app-mark.svg`（24 网格、`fill="none"`、`stroke-width=2`、round 端点、色值取 token），验证文件存在且 `QSvgRenderer.isValid()` 为 True
- [x] 7.2 绘制同源简化档 `src/resources/app-mark-16.svg`，验证 `<= 24` 档由派生脚本选它、`>= 32` 档选完整档
- [x] 7.3 用 2.1 的同一渲染管线出标识真渲染（16/24/48/256 实际像素 + 16px 的 6x 放大），把图交给用户确认后再继续，验证确认结论记录在 design.md 的 D5 下；未通过则只改 7.1/7.2 的两个 SVG 文件重出图

## 8. ICO 派生与标识落点

- [x] 8.1 实现 `scripts/gen_icon.py`：Qt 栅格化 16/20/24/32/40/48/64/128/256 的 PNG，再用纯 Python 写 ICO 目录表（256 档走 PNG 压缩条目），验证 `python scripts/gen_icon.py` 产出的 `src/resources/app.ico` 用 `file`/头字节检查为合法 ICO 且条目数为 9，且不引入 Pillow 依赖
- [x] 8.2 让 `gen_icon.py` 与 `icons.py` 共用同一套 SVG 改写逻辑，验证 `grep` 确认色值与线宽规则只有一处定义
- [x] 8.3 在 `src/app.py` 创建 `QApplication` 后调用 `setWindowIcon()`，资源缺失时按 D4 降级不崩溃，验证 `src/test_app_startup.py` 在临时移除图标资源的情况下仍能启动
- [x] 8.4 在 `_fill_about_tab()` 的版本标题上方加入标识（48px 档），验证截图可见且不遮挡 `app/version-info` 要求的版本号与构建来源信息
- [x] 8.5 给 `FloatingWindow` 设置窗口图标（虽然无边框，任务栏/截图场景仍需要），验证 `Qt.WindowStaysOnTopHint` 组合下图标不引发额外窗口装饰

## 9. 打包与产物一致性

- [x] 9.1 修改 `scripts/build_exe.ps1`：向 PyInstaller 传 `--icon`，并用 `--add-data src/resources;resources` 收集字形与图标资源，验证构建成功且 `dist/powerSupplyMaster/_internal/resources/` 内文件数与 `src/resources/` 一致
- [x] 9.2 增加构建后校验（沿用 `Assert-BundledRegistry` 的做法）：`_internal/resources/app.ico` 与 `icons/` 缺失即构建失败，`-VerifyOnly` 可单独复检，验证故意删除产物内资源后 `-VerifyOnly` 退出码为 1、拷回后为 0
- [ ] 9.3 实测产物中的图标表现（页签、按钮、列表行、标题栏、exe 文件图标），验证与开发环境截图一致，不存在"开发有图标、产物静默消失"，并把对比截图归档到 change 的 `evidence/`
  —— **评审后降级为可选（用户定）**：本会话桌面不可交互，`grabWindow` 只拿到壁纸，肉眼底片拿不到。
  可自动证明的部分已做完并归档 `evidence/9-3-packaged-icons.md`：冻结路径（`sys._MEIPASS`）下 223 次
  渲染与开发目录逐像素 0 差异、`app.ico` 逐字节相同、`app_icon()` 含 16/24/32/48/64/256 全档位；
  加上 9.1/9.2 的收集校验，"产物静默消失"已闭环。剩下的 exe 真机外观与 9.4 一并留到发布前手动清单。
- [ ] 9.4 在 125% 与 150% 缩放下各实测一次小尺寸图标清晰度，若偏细则调整 2.1 的线宽档位表，验证调整后的实测图与 `test_icons.py` 的档位断言一致
  —— **本次跳过（用户定，合入后再补）**：要改系统显示缩放。档位表按逻辑尺寸取档、线宽随 viewBox
  等比放大，相对粗细与 DPI 无关（见 Risks 更新），所以这条只剩观感确认。

## 10. 文档与回归

- [x] 10.1 在 `README.md`/`README.en.md` 的功能特性条目补一句图标与标识现状（含第三方字形来源），验证两份文档表述一致
- [x] 10.2 跑 `pytest src` 记录前后通过数，验证相对基线无新增 failed/errors（基线以本次开工时实测为准并写进 change）—— 基线 `master` @ `160bde4` 8 failed/362 passed/1 skipped/4 errors，实施后 8 failed/393 passed/1 skipped/4 errors，见 `evidence/test-baseline.md`
- [x] 10.3 在 `src/views/test_theme.py` 补一条断言：图标取色全部来自 `tokens()`，主题色值改动后图标色随之改变，验证测试通过

## Workflow follow-up

- 以 `git merge --no-ff` 合入 master，并在汇报中说明实际使用的合并方式。
- 合入前把 design.md 的 Q2（输出开关是否换形态字形）与 3.2/3.3 的定稿结论确认一遍，避免 artifacts 与实现分叉。
- 走 `/opsx:archive` 归档本 change，并核对 `ui/app-identity` 与 `ui/icon-system` 两个新能力已落到 `openspec/specs/`。
