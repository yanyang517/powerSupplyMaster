# Tasks

## 1. 工作目录与基线

- [x] 1.1 用 `git worktree` 为本 change 建立独立工作目录并在其上开功能分支，验证 `git worktree list` 出现新目录且该目录 `git rev-parse --abbrev-ref HEAD` 不为 `master`
- [x] 1.2 采集改前基线离屏渲染图（`QUiLoader` 加载 `mainWindow.ui`，`Fusion` 与默认 `windowsvista` 各一张），验证两张 PNG 均产出并可打开

## 2. 主题层

- [x] 2.1 新增 `src/views/theme.py`，实现 `TOKENS['dark']`、`build_qss(mode)` 与 `build_palette(mode)`，验证一段脚本断言 `build_qss('dark')` 非空、每个 token 值都出现在输出中、且 `build_palette('dark')` 的 Window/Base/Text 三组色与 token 一致
- [x] 2.2 加入主题层约束自检，验证脚本断言样式表不含 `font-family`、不含 `box-shadow`、不含 `gradient`、不含动画声明（依据 design.md D1 与 Risks 中已复现的豆腐块问题），并断言 `build_palette` 内不出现 `TOKENS` 之外的字面色值
- [x] 2.3 在 `src/app.py` 创建 `QApplication` 之后依次注入 `setStyle('Fusion')`、`setPalette(build_palette('dark'))`、`setStyleSheet(build_qss('dark'))`，验证启动后 `app.style().objectName() == 'fusion'`、`app.styleSheet()` 非空，且 `app.palette().color(Window)` 为深色（不依赖宿主系统配色）
      > 验收实测更正：`setStyleSheet` 会把应用样式包一层 `QStyleSheetStyle`，此后 `app.style().objectName()` 返回空串（PySide6 未暴露 `baseStyle()`）。因此 `== 'fusion'` 只能在 `setStyle` 之后、`setStyleSheet` 之前断言；样式表注入之后的正确断言是 `styleSheet()` 非空且 `palette().color(Window) == #232629`。实测：注入前 `fusion`、注入后 `#232629`、`len(styleSheet())=4095`。

## 3. 控制面板接线

- ~~3.1 在 `main_window.py` 的 `setupUi()` 之后加入 objectName 语义化映射表，并先跑键存在性校验~~ —— 已定（用户确认）：剔除。
      > 剔除依据：`theme.py` 最终只用类型选择器（`QGroupBox`、`QPushButton`、`QLineEdit` 等）加三个具体 objectName（`#volatage_label`、`#current_label`、`#connect_Btn`/`#disconnect_Btn`），没有任何规则按分组框名选色，`grep groupBox src/views/theme.py` 为空。重名 `groupBox` 因此不再造成选择器歧义，映射表无消费者。若将来要按分组差异化样式，再连同映射表一起提出。
- [x] 3.2 页签形状改为 `Rounded`，验证离屏 after 图中页签不再是锯齿梯形（对照 1.2 基线）
- [x] 3.3 让分组框、按钮、下拉框、spinbox、只读输入框的样式经 objectName/类型选择器生效，验证 after 图中这些控件呈现统一描边与圆角，且 `groupBox1` / `groupBox2` 两处不再与 `groupBox` 混淆
      > 后半句按 3.1 的发现作废：描边与圆角已由类型选择器统一，重名不再需要消歧。
- [x] 3.4 为 `volatage_label` 与 `current_label` 加 `plate` 底色容器（仅作用于 QLabel 自身，不改布局），验证 after 图中读数有独立视觉底且布局尺寸未变
- [x] 3.5 为 `ouput_ctrl_Btn` 定义 `:checked` 与未按下两态，接通态用 `success` 2px 描边 + 文字加粗、底色保持 `surface_alt`（design.md D10），未按下态沿用通用底色与 1px `border` 描边。验证三件事：实机点击两态各截一图，两图在色相、线宽、字重三个维度上都有差异；样式表中的接通规则写作 `#ouput_ctrl_Btn:checked`；`test_theme.py` 新增一条防漂移断言——选择器中不得出现裸 `QPushButton:checked`，防止将来新增的 checkable 按钮静默继承接通态。
      > 实施记录：全局 `QPushButton:checked` 填充规则已删除，改为 `#ouput_ctrl_Btn:checked` 一条限定规则。三个维度的差异都做了量化，不靠目测：色相——接通态标签区绿色着墨 81 px、未接通 5 px；字重——同一接通态去掉 `font-weight` 后着墨 60 px、保留则 81 px（+35%，证明样式表的 `font-weight` 经 `QStyleSheetStyle` 在绘制期确实生效）；线宽——左边缘扫描带未接通 1 px、接通 3 px（2px 描边加抗锯齿）。两态图：`after_switch_off.png` / `after_switch_on.png`。
      > 一条踩坑记录：`widget.font().weight()` 在两个状态下都返回 400，读不到样式表字体；`QStyle.font()` 在 PySide6 未暴露。要验证样式表字体是否生效，只能像上面那样做像素对照。
      > 防漂移断言经变异测试确认可失败：在当前样式表上匹配为假，注入旧写法 `QPushButton:checked { ... }` 后匹配为真。测试总数 7 → 8，全过；`app.py` 冒烟存活无 traceback。
      > 历史证据（描述的是被推翻的实心块方案，保留备查）：`after_output_on_green.png`（按下）与 `after_theme_draft.png`（未按下）。`.ui` 中仅 `ouput_ctrl_Btn` 的 `checkable` 为 `true`（`connect_Btn`/`disconnect_Btn` 均为 `false`），这一事实仍然成立。
- [x] 3.6 新增 `src/views/dark_dial.py`，子类化 `QDial` 在 `paintEvent` 内自绘深色盘体、描边环与指示点，色值全部取自 `tokens('dark')`；沿用 Qt 的 `225°` 起始角与 `-240°` 张角常量，不改鼠标与滚轮处理。在 `setupUi()` 内 `self.ui.setupUi(self)` 之后、`connect_signal_slots()` 之前用 `QLayout.replaceWidget` 替换 `voltage_dial` 并改写 `self.ui.voltage_dial`，验证：after 图中盘体为深色；拖动旋钮与 `max_voltage_spinbox` 联动后，指示点角度与 `value` 一致（证明接线未因替换顺序而静默失效）
      > 实施记录：角度正确性用对拍验证——同一取值下原生 `QDial` 与 `DarkDial` 并排渲染四个值（0/600/1200/2000），指示点落在同一角度，见 `evidence/dial_pair_check.png`。接线正确性用断言验证：替换后 `type(ui.voltage_dial).__name__ == 'DarkDial'`、`objectName` 保留、改 `max_voltage_spinbox` 使旋钮 `maximum` 由 2000 变 1500、`valueChanged` 仍到达槽。替换顺序约束实测有效：首版把递归查找写成了无基线的自调用，`RecursionError` 暴露后改为显式传布局；`replaceWidget` 需两个参数，首版漏传 `new`。
      > 跨 tab 后果（已定：另开 change，本次不动）：恒深色使波形 tab 的两块 `QChart` 区域成为整窗唯一的亮区——`QChart` 自绘背景，不随应用样式表与 palette 变化，见 `evidence/after_tab_chart.png`。客户端 tab 与悬浮窗 tab 无此问题。

## 4. 图表动效（已剔除）

- ~~4.1 关闭电压图与电流图的 `QChart.SeriesAnimations`~~ —— 已定（用户确认）：不纳入本次，另案处理。见 design.md D9。

## 5. 集成验收

- [ ] 5.1 实机启动 GUI 并用 `src/device/device_simulator.py` 走通连接、断开、调压、输出开关、波形采样，验证行为与改前一致、字体在真实环境下解析正常（离屏图不足以判断此项）
      > 自动化 A/B 已完成（COM8↔COM9 虚拟串口对经回环测试确认可用；模拟器 `--port COM9`，客户端连 COM8）。同一套断言分别跑 master 源码与本 change 源码，结果逐项一致，唯一差异是预期的旋钮类型：
      >
      > | 断言 | master | 本 change |
      > |---|---|---|
      > | 端口下拉含 COM8 | PASS | PASS |
      > | 连接后电压读数刷新 | PASS `12.00 V` | PASS `16.00 V` |
      > | 旋钮控件类型 | `QDial` | `DarkDial`（预期差异）|
      > | 调压设定值下发（spinBox） | PASS `16.0` | PASS `16.0` |
      > | 调压后实测跟随 | PASS `16.0` | PASS `16.0` |
      > | 输出开关按下态 | PASS | PASS |
      > | 波形数据已采样 | PASS（13 点） | PASS（1 点，采样时刻差异） |
      > | 连接后设备标识回填 | **FAIL `''`** | **FAIL `''`** |
      >
      > 最后一行是**既有缺陷，与本 change 无关**：`presenter.py:68` 调用 `self.view.update_device_id(ret)`，而 `update_device_id` 在整个 `src/` 内无定义（`src/views/__pycache__/main_window.cpython-39.pyc` 里仍有该名，说明是后来被删掉的）。两侧同样失败即为证据。另记两条运行约束：`device_simulator.py` 是串口客户端而非服务端，需先用 com0com 建串口对；它在对端断开后会退出，故每轮都要重启。验收图 `evidence/e2e_output_on.png` 用 `QT_QPA_PLATFORM=windows` 渲染，字体解析正常、无豆腐块（`offscreen` 会出豆腐块，不可用于验收）。
      >
      > 仍待 Lance 本人确认的只剩主观一项：真实屏幕上的观感。
- [x] 5.2 汇总验收证据，验证记录中包含 before/after 对比图、验收实际所用的 PySide6 版本（`.venv` 为 6.11.0 而 `requirements.txt` 钉 6.10.2）
      > 版本证据已实测：`.venv` 为 PySide6 6.11.0 / Qt 6.11.0，`requirements.txt:13-15` 钉 `==6.10.2`。本次全部渲染与冒烟均在 6.11.0 上完成，合入前需在 6.10.2 上复跑 `views/test_theme.py`。
      >
      > 证据索引（`evidence/`，22 个文件，均为 `QT_QPA_PLATFORM=windows` 真实渲染）：
      > - 改前基线：`before_windowsvista.png`（现状）、`before_Fusion.png`（证明 Fusion 跟随宿主配色，是恒深色决策的依据）。
      > - 改后主图：`after_switch_off.png` / `after_switch_on.png`（最终态与两态）、`after_dial_swap.png`（旋钮替换后）、`e2e_connected.png` / `e2e_output_on.png`（连真机端到端）。
      > - 旋钮排查：`dial2_all_plate.png`（palette 全压近黑仍压不暗，D5 关键证据）、`dial_pair_check.png`（原生与自绘同值对拍，角度正确性证据）。`dial_default.png` / `dial_button.png` / `dial_surface_alt.png` / `dial_none.png` / `dial_plate.png` / `dial2_hl_border.png` / `dial2_hl_plate.png` 是同一轮的中间产物，已被上述两张取代，留作过程记录。
      > - 被否决的方案：`after_output_on_green.png`（实心绿块，判定过抢眼）、`after_output_on_red.png`（接通取红的对照）。
      > - 跨 tab 回归：`after_tab_chart.png`（`QChart` 亮区，另案）、`after_tab_client.png`、`after_tab_floating.png`（无异常）。
      > - `after_theme_draft.png` 是主题层初稿（旋钮仍为浅盘），已被 `after_dial_swap.png` 取代。

## Workflow follow-up

- 以 `git merge --no-ff` 将功能分支合入 master，并在汇报中说明实际使用的合并方式。
- 合入满足项目评审要求后归档本 change。
- 另开一个 change 处理波形 tab 的 `QChart` 底色（已定：本次不动）。范围是把两块图表的背景、轴标签与网格线颜色接到 `tokens('dark')`，落点在 `main_window.py` 的 `_setup_chart()`；它与本 change 的主题层无耦合，可独立评审。
