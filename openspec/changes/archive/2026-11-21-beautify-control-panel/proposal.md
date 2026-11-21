# Proposal

## Why

控制面板目前完全依赖 Qt 在 Windows 上的默认 `windowsvista` 样式（`src/app.py` 从未调用 `setStyle`），全项目只有 4 处零散的内联 `setStyleSheet`，不存在任何主题层。由此产生三个可观察的缺陷：页签被设成 `tabShape: Triangular` 而呈锯齿梯形；`ouput_ctrl_Btn` 是可按下/弹起的危险操作按钮，但两种状态在屏幕上视觉无差别；电压/电流读数与 `设备信息` 等只读框、输入框共用同一套默认底色，读数虽有大字号却没有作为"仪表读数"的视觉层级。

实施阶段的实测补充了一个改变方向的事实：本机 `styleHints().colorScheme()` 为 `Dark`，`windowsvista` 忽略该信号而 `Fusion` 遵循它。因此选定 `Fusion` 之后外观方向必然是深色，本 change 据此把配色定为恒深色，而不是原设想的"在浅色外观上加圆角"。

同时，企业使用场景要求依赖的 license 必须宽松。经核查，最常被推荐的 `PySide6-Fluent-Widgets` 是 GPLv3 + 商用需另购授权，与本项目 LGPL-3.0 的组合会把整体升级为 GPL 并限制闭源分发，因此排除；`qt-material` 虽为 BSD-2-Clause 可用，但会接管整套样式表并附带字体资产，收益不抵成本。

## What Changes

- 新增主题层 `src/views/theme.py`：以字典形式承载设计 token（`primary` / `success` / `danger` / `surface` / `plate` / `text` / `text_dim` / `border` / `radius` / `gap` / 字号），并提供 `build_qss(mode)` 与 `build_palette(mode)`。本次只实现 `dark`，`mode` 参数与两份产出函数的结构即为 `light` 的预留位。
- `src/app.py` 在创建 `QApplication` 后设置 `Fusion` style，并注入深色 palette 与样式表。palette 是必需项而非可选：样式表只覆盖它写到的属性，菜单、tooltip、下拉弹出列表等仍从 palette 取色，不管 palette 就会在浅色模式机器上出现底色分裂。
- `src/views/main_window.py` 在 `setupUi()` 之后做修正：页签形状改为 `Rounded`；把 `voltage_dial` 替换为自绘旋钮；为 `ouput_ctrl_Btn` 定义 `:checked` 与未按下两态——接通取 `success` 绿的 2px 描边加粗文字、底色不变，不用实心色块（实心块在深色面板里过抢眼，且两态差异不该只落在色相一个维度）。原计划的 objectName 语义化映射已无消费者——样式表最终只用类型选择器与三个具体 objectName，重名 `groupBox` 不再造成歧义，故不做。
- `QDial` 的旋转隐喻保留，但盘体改为自绘。实测样式表与 palette 两条路都压不暗旋钮本体：把单个 `QDial` 的九个 palette 角色全设成近黑 `#12151a`，`Fusion` 渲染出的盘体仍是中亮蓝灰。故新增 `src/views/dark_dial.py` 子类化 `QDial`，在 `paintEvent` 内画深色盘面与指示点，交互处理不动。
- 放弃数码管观感，不引入任何字体资产。
- 电压/电流曲线的 `QChart.SeriesAnimations` 本次不动（已确认剔除）。它在无独显机器上的蠕动与开销是事实，但与主题层无关，另案处理。
- 不修改任何 `.ui` 文件，不建立 `.ui` → `_ui.py` 的 uic 生成流程，不新增第三方依赖。
- 范围之外：悬浮窗（`floating_window.py` 的内联样式保持原状）、波形页布局与 `QChart` 底色、客户端 tab、关于 tab、悬浮窗配置 tab。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。

本 change 不声明 capability，并在 `.openspec.yaml` 设置 `skip_specs: true`。理由：改动全部落在外观呈现层，数据流、串口通信、SCPI 语义、控件行为均未变化；状态可辨识性与无动效属于本次视觉改动的验收标准，而非需要长期存续的系统行为。项目当前没有任何 spec，把"按钮配色"作为第一个 capability 的边界过弱，会在后续 UI 演进中变成难以维护的杂物抽屉。若希望把"界面主题化"确立为项目的第一个 capability 以固化本次探明的约束（不写 `font-family`、不引入动效、依赖 license 白名单），需要扩大本次范围另行确认。

## Impact

受影响代码：

- `src/views/theme.py`（新增）
- `src/views/dark_dial.py`（新增：自绘深色旋钮）
- `src/app.py`（+5 行：style、palette、样式表注入）
- `src/views/main_window.py`（`setupUi` 后置处理：页签形状 `Rounded`、`voltage_dial` 控件替换）

不受影响：`src/views/ui/*.ui`、`src/views/ui/*_ui.py`、`src/presenter/`、`src/device/`、`src/server/`、`src/views/floating_window.py`。

需要知情的两点：

1. 本 change 会让界面从浅色变为恒深色。这是外观层面的既定目标，但对该工具的既有使用者属于可观察的变化；悬浮窗不在本次范围内，仍保持其原有配色，短期内会与深色主窗口并存。
2. 恒深色会把波形 tab 的两块 `QChart` 衬托成整窗唯一的亮区——`QChart` 自绘背景，不随应用样式表与 palette 变化（实测见 `evidence/after_tab_chart.png`）。已定（用户确认）本次不动，另开 change 处理；合入后到该 change 落地前，切到波形 tab 会看到明暗分裂。客户端 tab 与悬浮窗 tab 无此问题。

依赖：无新增。`Fusion` 是 Qt Widgets 内置样式，不依赖样式插件，跨操作系统外观一致，license 与现有 PySide6 相同。

风险与约束：

- 样式与 `.ui` 分离后，Qt Designer 预览不到美化效果，`.ui` 与真实外观开始漂移。缓解方式：样式表只按 objectName 选择、不写内联样式，将来若迁入 `.ui` 属搬运而非重写。
- 样式表中声明 `font-family` 是已验证的陷阱：离屏 spike 中指定 `"Microsoft YaHei UI"` 后解析回退失败，全屏文字变为豆腐块。主题层 MUST NOT 设定 family，只调字号、字重与颜色。
- 本机为 Windows 10 (19045)，`windows11` 样式在该机上非平台样式，离屏渲染中 `connect_Btn` / `disconnect_Btn` 几乎不可见，故不作为选项。
- `requirements.txt` 钉 `pyside6==6.10.2`，而 `.venv` 实际安装 6.11.0。本 change 不修正该漂移，但样式验证 MUST 明确记录所用版本。
- 按项目 git 约束，实施阶段须在 `git worktree` 建立的独立工作目录中进行，合入 master 使用 `git merge --no-ff`。

验收方式：沿用本次探索已验证的手段，用 `QUiLoader` 加载 `.ui` 后离屏渲染 before/after 对比图。该方法只覆盖样式层，不运行 presenter、不接串口；功能回归仍需实机启动 GUI 路径确认。
