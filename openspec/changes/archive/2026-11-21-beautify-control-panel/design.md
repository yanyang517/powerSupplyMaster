# Design

## Context

样式现状是散点式的：`src/app.py` 创建 `QApplication` 后从未调用 `setStyle`，因此实际生效的是 Qt 在 Windows 上的默认 `windowsvista` 平台样式；全项目仅有 4 处 `setStyleSheet` 调用，其中 2 处在悬浮窗给电压/电流标签硬编码颜色（`src/views/floating_window.py:35`），2 处在主窗口给图表 tooltip 标签设置边框（`src/views/main_window.py:117` 与 `:180`）。不存在主题层、token、深浅色概念，也没有任何 `.qss` 或资源文件。

控制面板的控件树由 `src/views/ui/mainWindow.ui` 描述、经 uic 生成 `src/views/ui/mainWindow_ui.py` 后提交进仓库。生成物曾被手工修改以适配 PySide6 的严格枚举（见提交 `decd07b`），而仓库内不存在任何 uic 重新生成脚本。此外 `.ui` 中 `groupBox` 名称被重复使用三次，uic 把后两个自动改名为 `groupBox1`（输出电压）与 `groupBox2`（输出开关），使按 objectName 编写选择器时语义不可读。

约束本设计的三条外部事实：本机是 Windows 10 (19045) 且无独显；项目自身为 LGPL-3.0，新增依赖必须宽松授权；`requirements.txt` 钉 `pyside6==6.10.2` 而 `.venv` 实装 6.11.0。

第四条事实是实施阶段实测得到的，它改变了原计划的配色取向：`QGuiApplication.styleHints().colorScheme()` 在本机返回 `ColorScheme.Dark`，而 `windowsvista` 忽略该信号（Window 色 `#f0f0f0`）、`Fusion` 遵循它（Window 色 `#1e1e1e`）。也就是说切到 `Fusion` 不是"浅色 + 圆角"，而是"跟随系统配色"。本 change 据此选定**恒深色**方向，见 D1 与 D8。

动机与范围见 proposal.md - Why / What Changes。

## Goals / Non-Goals

**Goals:**

- 样式定义收敛到单一入口，任何外观调整只改一个文件。
- 样式表全部由 token 插值产出，不留硬编码色值，使 `dark` 成为纯数据扩展。
- 危险操作（输出通断）的状态在屏幕上可一眼辨识，且**不只靠色相**：颜色之外还要有形态线索（描边宽度、字重），使两态在色觉不便与低对比环境下同样可分。
- 改动可完全回退。回退成本实测为：删除 `app.py` 的 5 行注入、删除 `theme.py` 与 `dark_dial.py` 两个新模块、撤销 `setupUi()` 内的页签形状与旋钮替换两处；不涉及 `.ui` 与依赖。
- 外观在任意机器的任意系统配色偏好下都呈现同一套深色界面，不随宿主设置漂移。

**Non-Goals:**

- 不调整布局结构、控件尺寸、窗口大小或标签层级；本次只改呈现属性。
- 不做响应式/自适应缩放，`tab_client` 的绝对定位问题另案处理。
- 不提供深浅色切换的界面入口，不做主题偏好持久化，本次也不产出 `light` token 集。
- 不改 `.ui`、不建立 uic 生成流程、不新增依赖。
- 不触碰悬浮窗与其余空壳 tab 的样式。
- 不改波形 tab 的 `QChart` 底色。`QChart` 自绘背景，不吃应用样式表与 palette，接色需要在 `_setup_chart()` 单独处理；已定（用户确认）另开 change，因为它与本 change 的主题层无耦合，混进来只会扩大评审面。

## Decisions

### D1 采用 `Fusion` 样式，而非 `windows11` 或第三方主题库

`Fusion` 内置于 Qt Widgets 模块，不依赖样式插件，跨操作系统外观一致，且对 Qt Style Sheets 的支持最完整。

- 对比 `windows11`：它是插件式平台样式，在 Windows 11 上才是默认与目标形态。本机为 Win10，离屏渲染下 `connect_Btn` 与 `disconnect_Btn` 几乎不可见，且社区存在 spinbox 显示异常的报告。选它等于把外观押在一个非平台样式上。
- 对比 `qt-material`（BSD-2-Clause，授权可用）：它接管整套样式表并引入 Roboto 字体资产，与自绘 token 层的目标冲突，收益不抵一个长期依赖。
- 对比 `PySide6-Fluent-Widgets`：GPLv3 + 商用需购买授权，与本项目 LGPL-3.0 组合会把整体升级为 GPL，直接排除。

选定 `Fusion` 后必须一并接受它的配色行为：`Fusion` 遵循 `styleHints().colorScheme()`，因此本 change 的外观方向是深色，而非在旧外观上描圆角。这是 D8 的由来。

### D2 token 字典 + 字符串模板留在 Python 内，不落地 `.qss` 文件、不用 qrc

`src/views/theme.py` 内以 `TOKENS[mode]` 承载变量，`build_qss(mode)` 返回完整样式表字符串。

- 对比独立 `.qss` 文件 + 运行时 `open()`：仓库没有打包与数据文件管理流程，一旦将来用 PyInstaller 冻结，运行时相对路径就会失效；而现在写文件读取等于提前引入一个构建期关切。
- 对比 `.qrc` + `pyside6-rcc`：需要新增资源编译流程，与"不建立生成流程"的约束相悖。
- 留在 Python 的代价是样式无法脱离代码编辑，本次接受。

### D3 objectName 语义化在 Python 侧用映射表完成，不改 `.ui`

在 `setupUi()` 之后集中执行一批 `setObjectName()`，把 `groupBox1` / `groupBox2` 这类 uic 自动改名结果替换为语义名。映射表以 `.ui` 中的现有 objectName 为键，实施时先校验全部键存在，避免与生成物脱节后静默失效。

选择 Python 侧而非 `.ui` 侧的根本原因是 D3 的前提：改 `.ui` 就必须重新生成 `_ui.py`，而生成物需要手工修补严格枚举，这正是本次要避免的成本。代价见 Risks。

### D4 状态用 Qt 原生伪类，语义色绑定 objectName，不引入自定义 `class` 属性机制

按下/hover/禁用等状态一律用 `:checked`、`:hover`、`:disabled` 伪类表达，由 Qt 状态机驱动重绘；`ouput_ctrl_Btn` 的通断两态即通过 `#ouput_ctrl_Btn:checked` 着色。

**状态规则 MUST 用 objectName 限定，不得写成裸类型伪类。** 实施中实测到一次偏离：样式表把接通态写成了全局 `QPushButton:checked { background-color: success }`，后果有两层——一是接通态变成整块饱和色，在深色面板里过于抢眼；二是作用域越界，将来任何新增的 checkable 按钮都会静默继承这块实心填充。类型级伪类只用于与状态无关的通用底色，带语义色的状态规则一律限定到具体 objectName。

- 对比 `setProperty('class', 'danger')` 一类的自定义属性方案（qt-material 的做法）：自定义动态属性生效需要确保 style 重新 polish，属性变更时不会自动重绘，属于容易静默失效的一类坑。伪类没有这个问题。
- 语义 token 与控件的绑定关系统一收在样式表内，不散落进控件构造代码。

### D5 保留 `QDial`，样式只作用于衬托部分

实测证据（样式表）：给 `QDial` 施加 `background-color` 与 `border` 后底盘与边框生效，旋钮本体的立体高光与指示点仍由 style 绘制、样式表无法改变。

实测证据（palette，本次新增）：`Fusion` 的 `drawDial` 同样不吃 palette。把单个 `QDial` 的 `Button`、`Base`、`Window`、`Light`、`Midlight`、`Mid`、`Dark`、`Shadow`、`Highlight` 全部设为 `#12151a`（近黑），渲染出的盘体仍是中偏亮的蓝灰；只改 `Highlight` 只能去掉蓝色调，盘体明度不变。证据见 `evidence/dial_none.png`、`evidence/dial_plate.png`、`evidence/dial2_all_plate.png`。

结论修正：D5 原以为「旋钮偏浅但可接受」，实测是在整片 `#232629` 深色面板中留一块无法压暗的浅色圆盘，视觉权重还是面板上最大的一块。该代价超出本决策当初的假设。

**已定（用户确认）：子类化 `QDial` 自绘深色盘体。** 新增 `src/views/dark_dial.py`，在 `paintEvent` 内画盘面、描边环与指示点，色值全部取自 `tokens('dark')`，不留字面色。

角度约定必须与 Qt 自身一致，否则自绘的指示点会和鼠标拖拽算出来的值错位：`QDial` 用起始角 `225°`、张角 `-240°`，本类沿用同一组常量，只替换绘制、不改 `mousePressEvent`，交互仍由 `QDial` 本身负责。

替换方式：在 `MainWindow.setupUi()` 内 `self.ui.setupUi(self)` 之后、`connect_signal_slots()` 之前做控件替换，并同步改写 `self.ui.voltage_dial` 属性。顺序是硬要求——现有接线有 4 处引用 `self.ui.voltage_dial`（`main_window.py:205`、`:211`、`:286`），若替换发生在接线之后，旧控件的 `valueChanged` 连接会随旧控件一起失效而不会报错。`voltage_dial` 由嵌套 layout 持有，替换须用 `QLayout.replaceWidget`，不能只 `setParent`。

未采用的替代方案：换成可完整 QSS 的 `QSlider`（改变旋转隐喻，且要重接调压链路），已由用户否决。

### D6 读数容器用 `QLabel` 自身的样式实现，不新增包裹 widget

电压/电流的 `plate` 底色、内边距、圆角全部作用在既有 `volatage_label` / `current_label` 上。新增容器 widget 意味着改布局即改 `.ui`，与 D3 前提冲突。

### D7 主题注入点在应用启动处，而非窗口构造内

`app.setStyle('Fusion')`、`app.setPalette(build_palette('dark'))` 与 `app.setStyleSheet(build_qss('dark'))` 放在 `src/app.py` 创建 `QApplication` 之后。样式表与 palette 都是应用级单例，放在窗口构造内会在多窗口场景重复注入。

已知副作用：单独实例化 `MainWindow` 而不经过 `app.py` 的测试或脚本路径拿不到主题，验收渲染必须显式设置样式，或改为复用 `app.py` 的启动函数。

另一处实测副作用：应用级 `setStyleSheet` 会把当前 style 包一层 `QStyleSheetStyle`，此后 `app.style().objectName()` 变成空串（PySide6 未暴露 `baseStyle()`）。注入顺序因此必须是先 `setStyle` 后 `setStyleSheet`，且「当前是否 Fusion」只能在包装前断言，包装后改用 palette 与样式表长度断言。

### D8 本次只出 `dark` 一套，并由主题层同时产出 palette

`src/views/theme.py` 提供 `TOKENS['dark']`、`build_qss(mode)` 与 `build_palette(mode)`。`mode` 参数保留，`light` 后续只是再填一份字典。

关键点是**样式表不足以单独保证恒深色**：Qt Style Sheets 只覆盖它写到的属性，未覆盖的部分——菜单、tooltip、滚动条、消息框、下拉弹出列表——仍从 `QPalette` 取色。若只注入深色样式表而不管 palette，在系统处于浅色配色的机器上就会出现深色面板配浅色弹出层的两套底色打架。因此主题层必须同时把深色 palette 显式设给 `QApplication`，让外观与宿主设置彻底解耦。

- 对比只写样式表：省一个函数，但在浅色模式机器上必然出现底色分裂，属于会被当成 bug 回报的缺陷。
- 对比跟随系统（按 `colorScheme` 选 mode）：需要两套 token 才能成立，已由用户明确排除在本次范围外。
- 深色 palette 的色值同样从 token 派生，不允许在 `build_palette` 内出现第二套独立色值来源。

### D9 图表动画不在本次范围

`voltage_chart.setAnimationOptions(QChart.SeriesAnimations)`（`src/views/main_window.py:77`，电流图同）在滚动采样下会让曲线持续蠕动，在无独显机器上还是额外重绘开销。它不属于"美化"，此前在 tasks 中单列为可单独剔除的任务。

**已定（用户确认）：本次剔除。** 本 change 不动动画，`SeriesAnimations` 的取舍另案处理，因此第 4 组任务整体从 tasks 移除。

### D10 输出开关两态用「描边 + 字重」表达，不用实心色块

接通态的样式定为 `#ouput_ctrl_Btn:checked`：`success` 色 2px 描边、文字取 `success` 并加粗、底色保持 `surface_alt`。未按下态沿用通用按钮底色与 `border` 描边。这样两态之间同时存在三类线索——色相（绿/灰）、线宽（2px/1px）、字重（粗/常规），任一失效都不至于让通断状态看不出来。

**不新增 token。** 主方案只改样式表文本，`success` 已存在；线宽与字重不是色值，不违反"色值一律来自 token"的约束，也不触碰 `test_theme.py` 里"样式表不得声明 `font-family`/`font-size`"的自检——本条只加 `font-weight`，且限定在单个 objectName 上，不会影响 `.ui` 设定的 36pt 读数。

备选方案是新增 `success_dim` 一类的暗绿 token 做低饱和填充。它视觉上比描边更"实"，代价是 token 表扩一项、且两态差异仍只落在色相一个维度上，与 Goals 中"不只靠色相"这条相悖，故不采用。

诚实的代价：改为描边后，接通态与 `disconnect_Btn` 同属"描边语义色"这一类，区分不再靠色块面积，只能依赖该按钮 100×100 的尺寸、2px 线宽与加粗。若实机观察下来仍不足以一眼分辨，退路是给未按下态也加一条 `border_strong` 描边，让差异落在"有无绿色"而非"绿得多不多"。

## Risks / Trade-offs

- [样式与 `.ui` 漂移，Qt Designer 预览不到美化结果] → 样式表只按 objectName 与类型选择、不写内联样式；将来若决定迁回 `.ui`，属于搬运而非重写。同时接受"Designer 不再是外观的唯一真相源"这一变化。
- [样式表中声明 `font-family` 导致整屏文字变豆腐块] → 已在离屏 spike 中复现（指定 `"Microsoft YaHei UI"` 后回退失败）。主题层禁止设定 family，只调字号、字重、颜色；验收渲染需在能解析真实字体环境下复核一次，不能只看离屏图。
- [objectName 映射表与生成物脱节，改名静默失效] → 映射表以现有 objectName 为键，实施时先跑一次键存在性校验，缺失即报错而非跳过。
- [样式表与 palette 两套色值来源漂移，改一个忘一个导致底色分裂] → `build_palette` 只从同一份 `TOKENS[mode]` 取色，禁止出现第二套字面色值；自检脚本断言样式表与 palette 的关键色一致。
- [深色方向使悬浮窗与主窗口分属两套观感] → 悬浮窗本次明确不动（proposal 范围外），其内联浅色假设下的配色在深色主窗口旁可能显得突兀，属已知遗留，另案处理。
- [无独显机器上大面积渐变/阴影带来重绘成本] → 样式表不使用渐变、阴影、半透明叠加与过渡动画；效果靠描边、圆角、留白与配色达成。深色底上更依赖描边区分层级，验收需确认层级仍可分辨。
- [离屏渲染验收不等于真机观感] → 双轨验收：离屏 before/after 对比图覆盖样式层，实机启动 GUI 路径目测确认字体与控件度量。
- [PySide6 版本漂移（钉 6.10.2 / 实装 6.11.0）导致样式结论不可复现] → 本 change 不修正该漂移，但验收记录 MUST 写明实际验证所用版本。
- [回退成本] → 极低。删除 `app.py` 两行注入即完全回到现状，`theme.py` 成为无引用文件；无数据迁移、无接口变更。

## Migration Plan

1. 按项目约束用 `git worktree` 建独立工作目录并在其上开功能分支。
2. 新增 `src/views/theme.py`，实现 `light` token 与 `build_qss()`。
3. 在 `src/app.py` 注入 style 与样式表。
4. 在 `src/views/main_window.py` 完成页签形状、objectName 映射、读数容器、开关状态色。
5. 离屏渲染 before/after 对比图，确认样式层无回归；实机启动 GUI 目测。
6. 以 `git merge --no-ff` 合入 master。

回滚策略：revert 合并提交，或就地删除 `app.py` 的两行注入。

## Open Questions

- 色板的具体色值。不影响 token 结构、选择器策略或任务拆分，可在实施阶段用对比图迭代确定。
- ~~`输出开关` 接通态取 `success` 绿还是 `danger` 红。~~ **已定（用户确认）：绿（`success`）**，即沿用"运行中=正常"的直觉。表达形态另见 D10：原以"接通是实心色块、连接是描边，形态上已可区分"论证，该论证已作废——实心块被判定过抢眼，两态改由描边宽度与字重区分，接通与断开因此同属描边语义。
- ~~旋钮浅盘怎么处理。~~ **已定（用户确认）：子类化自绘深色盘体**，见 D5。
- ~~图表动画是否纳入。~~ **已定（用户确认）：不纳入**，见 D9。
- `plate` 底色是否也用于 `device_info_lineEdit` 一类的只读展示控件。属于同一机制下的取舍，可在看到对比图后决定。
