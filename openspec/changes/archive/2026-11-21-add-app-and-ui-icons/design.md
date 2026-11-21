# Design

## Context

见 proposal.md - Why。这里只记录约束实施的技术现状：

- 主题层已收敛到 `src/views/theme.py` 的 `TOKENS['dark']`，`app.py` 在创建 `QApplication` 后依次注入 `Fusion`、`build_palette('dark')`、`build_qss('dark')`。图标取色必须挂在这条链上，而不是另起一组颜色。
- 界面结构由 uic 生成的 `src/views/ui/*_ui.py` 提供，项目既有约定是**不改 `.ui`、不建 uic 流程**，所有外观注入都在 Python 侧完成（`_swap_voltage_dial()`、`_fill_about_tab()` 是两个先例）。
- `scripts/build_exe.ps1` 已经在 PyInstaller 调用前生成 `--version-file` 资源文件，`--icon` 就在同一个调用块里加。
- 状态栏已被 `UpdateNoticeWidget` 以 `addWidget` 常驻占用（不用 `showMessage` 是有意的，见 `src/views/update_notice.py` 头注释）。
- `.venv` 实测：`PySide6.QtSvg` 可导入，`PIL` 不存在。
- 探索阶段已用真实字形文件 + 本仓 `build_qss('dark')` 做过渲染验证，结论：24 网格 stroke 字形在 16px 档把 `stroke-width` 抬到 2.5 后笔画不断裂；Tabler 的 `plug-connected` 在 16px 读成链环，Lucide 的 `plug` 仍读成插头。

## Goals / Non-Goals

**Goals:**

- 一份可执行的图标风格契约，使不同来源的字形在界面上不可分辨出差异。
- 图标取色与控件状态规则同源，改 token 即改图标。
- 应用标识与界面字形使用同一绘制语言，避免标题栏那个小方块看起来是外来的。
- 开发环境与打包产物的图标表现一致，且这条一致性有可重复的校验手段。

**Non-Goals:**

- 不做系统托盘图标（新能力，需独立 change）。
- 不改波形页 `QChart` 的配色与背景（既有约定为独立 change）。
- 不给 `UpdateNoticeWidget`、`auto_reconnect_CB`、悬浮窗设置页的颜色/字体控件加图标。
- 不处理浅色主题下的图标表现（当前恒暗）。

## Decisions

### D1 字形来源：vendored 第三方线稿 SVG，Tabler 为主、Lucide 补位

界面字形不自己画，直接引入官方 SVG 文件并锁定版本。选型依据是实测覆盖与描边是否可参数化：

```
              网格  描边模型                        许可   本仓需要的字形覆盖
 Tabler       24   stroke=currentColor 可调宽度     MIT    最高（gauge/wave-sine/
                                                                  picture-in-picture/
                                                                  shield-x/circle-dot…）
 Lucide       24   同 Tabler，结构一致              ISC    高，且独有 plug/unplug/
                                                                  plug-zap
 Bootstrap    16   fill=currentColor 实心路径        MIT    中，线宽烧死在几何里
 Phosphor     256  实心，6 种字重=6 个文件           MIT    缺 plug-connected 类
 Feather      24   stroke 可调                       MIT    287 个，2019 后停更
```

**为什么不选 Bootstrap/Phosphor**：`fill="currentColor"` 的实心路径没有"把描边抬半档"这个旋钮，而 16px 档的清晰度恰恰依赖它。**为什么不选 Feather**：覆盖不足，会逼着自绘补洞，破坏一致性契约。

**为什么允许混用两个库**：两者网格、描边模型、端点处理完全相同，混用不产生视觉差异（`ui/icon-system` 第一条要求即为验证这一点）。规则是"每个落点挑读得清的那个"，不是"只许用一个库"。具体分配见 D8 的落点表。

**为什么不用图标字体**：图标字体是许可与风险的叠加——字体侧常见 SIL OFL/CC-BY 署名传染，而本仓主题层已实测过 `font-family` 声明可能解析失败导致整片文字变豆腐块。字体一旦进入图标链路，这个风险就从可选变成必选。

### D2 渲染路径：`QSvgRenderer` 栅格化后构造 `QIcon`，禁止 `QIcon("*.svg")`

`QIcon` 直接吃 SVG 路径依赖 Qt 的 **svg iconengine 插件**（`iconengines/qsvgicon.dll`）。PyInstaller 对该插件的收集不可靠，失败形态是最坏的那一种：开发环境一切正常，产物里图标静默消失。`QSvgRenderer` 只依赖 QtSvg 模块本身，实测可导入。

副带收益：只有走 renderer 才能在栅格化前改写 SVG 文本（D3）。

替代方案：预先把每个字形每种尺寸每种颜色渲染成 PNG 表提交进仓库。被否——色值与尺寸组合会爆炸，且失去与 token 的联动。

### D3 取色与线宽：栅格化前改写 SVG 文本

`src/views/icons.py` 暴露单一入口 `icon(name, role, size=16)`：

1. 读 `src/resources/icons/<name>.svg`；
2. 把 `currentColor` 替换为 `TOKENS['dark'][role]`；
3. 按尺寸档位替换根元素的 `stroke-width`：`size <= 20` 用 `2.5`，`size >= 24` 用 `2.0`；
4. `QSvgRenderer` 渲染到 `QImage`，包成 `QIcon`/`QPixmap`。

`role` 用 token 名而不是十六进制值，是 `ui/icon-system`「图标取色来自主题」这条要求的落点：改 token 即改所有图标，图标层不出现任何颜色常量。

**为什么不靠 `QPalette` 传色**：`QSvgRenderer` 不读 palette，`currentColor` 只在 SVG 文本层面解析。

**为什么不靠 QSS 的 `image:` 属性**：需要资源路径且无法按 token 变色，还会把图标语义绑死到样式表优先级上。

### D4 容错：图标失败必须静默降级而不是抛出

`icon()` 在文件缺失、SVG 解析失败、渲染结果为空时返回空 `QIcon` 并记一条 `logger.warning`，MUST NOT 向上抛。理由与既有约定同构（`update_device_id()` 读不到就留空而不是报错）。这是 `ui/icon-system`「图标缺失不影响功能」的实现保证，也是打包后插件/资源收集出问题时不让应用崩溃的保险。

### D5 应用标识：实心圆角方块徽标 + IEC ⏻ 镂空（评审门已确认）

标识不取库字形（`ui/app-identity` 的原创要求，也因为拼出来的东西零识别度）。构图与界面图标分属两套形状语言：**徽标是块面（`fill`），面板图标是笔画（`stroke`）**——这既是要"像 app 图标"的必然结果，也顺带解决了"标识与 `tabler/power` 撞形"的顾虑：同一个 ⏻，读起来是身份与动作两种东西。

契约：24 网格、`rx=6` 的圆角方块满铺 `{{primary}}`、⏻ 由 `{{surface}}` 实心件拼出（even-odd 环带 + 独立竖笔），环带顶部的缺口用**徽标同色补块**切出，而不是把路径断开。色值仍全部走 token，图标层不出现十六进制。

**评审经过（全程真渲染，无概念图）：**

1. 「细线弧 + ⏻」四版（分离/接弧顶/环加短针/环加长针）：描边 ⏻ 在 16px 上环糊成一团，B 系又是通用电源键。用户判定"不像 app 图标、太碎、语义不明"。
2. 细线 8 版（读数屏、旋钮、开口环、描边镂空圆盘、实心闪电、环穿波）+ 实心 5 版：**只有实心徽标配实心镂空在 16px 站得住**；描边镂空（stroke 3）的环带仍只有 1.3px 且读作"被咬一口"。
3. 配重 4 档 × 外形 2 种，再放进标题栏 16px / 任务栏 24px / 关于页 48px / 浅色桌面 24px 实测：定稿 **方徽 / b 收边**——环带 `outer=6.4`、孔 `inner=3.5`、中心 `cy=13.2`、竖笔宽 3。`c 薄环`（环带 2.4 单位）淘汰：16px 上只剩 1.6px，会断。

成本上限不变：评审不通过只需改这两个 SVG 文件，派生脚本与落点接线全部不动。

### D6 小尺寸档位：手工加重，而不是自动降级

`src/resources/` 下存两份标识源：`app-mark.svg`（完整档）与 `app-mark-16.svg`（小尺寸档：同一几何，环带加厚到 3.6、竖笔加宽到 3.6，孔相应缩小）。派生脚本按目标尺寸选择源：`<= 24` 用简化档，`>= 32` 用完整档。

**为什么不用自动缩放**：16px 的重量取舍是设计判断，算法做不出"哪一笔该加粗"。这也是 `ui/app-identity`「小尺寸可读性」要求里"与之同源的简化档位"的含义——同源指同一契约与同一色值来源，不是同一份路径。

### D7 ICO 生成：Qt 栅格化 + 纯 Python 写容器，不引入 Pillow

`scripts/gen_icon.py` 用 `QSvgRenderer` 把标识栅格化为 16/20/24/32/40/48/64/128/256 的 PNG，再用约 30 行的纯 Python 写 ICO 目录表（ICO 的每个条目就是 ICONDIR + ICONDIRENTRY + 一个 PNG blob，256 档必须走 PNG 压缩条目）。产物 `src/resources/app.ico` 提交进仓库，`build_exe.ps1` 直接引用。

**为什么不装 Pillow**：`.venv` 实测无 PIL，而项目的先例是把 PyInstaller 明确留在 `requirements.txt` 之外作为 build-only 工具；为一个容器格式再拉一个运行时可见的依赖不值得。**为什么不用 ImageMagick**：外部二进制，CI 与本机行为不一致。**为什么产物要提交**：让 `--icon` 在没跑生成脚本时也能构建成功，同时让标识变更在 diff 里可见。

生成脚本与运行时渲染共用 D2/D3 的同一套改写逻辑，避免"打包图标与界面图标是两套东西"。

### D8 落点与接线

```
 落点                              接线位置                     字形
 5 个页签                          main_window.setupUi()        L:gauge / T:wave-sine /
                                                                 T:users / T:picture-in-picture /
                                                                 L:info
 连接 / 断开                       main_window.setupUi()        L:plug / T:plug-off
 输出开关（两态同字形，只换色）      main_window.setupUi()        T:power
 控制权状态行（三态）               access_panel.refresh()       T:circle-dot / T:circle /
                                                                 T:circle-dashed
 吊销控制权                        access_panel.__init__()      T:shield-x
 客户端列表逐行                    access_panel._client_rows()  T:user-check / T:user /
                                                                 T:clock / T:user-off
 悬浮窗右键菜单                    floating_window              T:window / T:power / T:eye-off
 标题栏 + 任务栏 + exe + 关于页     app.py / build_exe.ps1       标识（D5）
```

`T:` = Tabler，`L:` = Lucide。18 个字形文件对 18 个落点条目，逐文件许可与落点见
`src/resources/NOTICE.md`。

**本表按 3.1 的实测图定稿**，与提案期的直觉候选有六处不同，全部由 16px 档实际像素判出
（`sheet_grid.png` 1x 四档 + `sheet_zoom.png` 16px 6x 最近邻）：

- 页签「控制面板」用 Lucide 版 `gauge`：Tabler 版带外圈，16px 上更像指南针。
- 页签「客户端」`tabler-network` → `tabler-users`：network 在 16px 读作地球仪，语义漂到"网络/万维网"。
- 按钮「断开」`lucide-unplug` → `tabler-plug-off`：unplug 的两截插头在 16px 糊成一条断链，看不出"拔开"；
  plug-off 的插头加斜叉仍读得出"断电"。
- 控制权第三态（持有者断线、租约未释放）`tabler-circle-half` → `tabler-circle-dashed`：circle-half 在
  16px 读作"禁止通行"，与语义正好相反；虚线圆与实心点、空心圆同属圆环家族，三态靠"点/环/虚环"的
  形态差区分，不靠色相。
- 列表行「待确认」`tabler-hourglass` → `tabler-clock`：hourglass 在 16px 读作蝴蝶结。
- 列表行「断线持有」`lucide-unplug` → `tabler-user-off`：与上一条同源，列表行本就在 user 家族里，
  斜叉人形与 `user`/`user-check` 的区分度比插头高。

`tabler-wifi-off` 在 16px 是一堆斜线，从未入选。淘汰记录一并写进 NOTICE.md，避免后续重复试错。

### D9 资源解析：图标走 `sys._MEIPASS`，与配置文件的规则刻意不同

`clients.json` 那类**用户可改写**的配置在 frozen 下必须落 exe 同级（`--add-data` 在 onedir 下会把它放进 `_internal/`，这是本仓已踩过的坑，见 TODO.md P0-1）。图标相反：它是只读构建产物，用户不需要也不应该改，因此 `--add-data src/resources;resources` + 运行时 `Path(getattr(sys, "_MEIPASS", <repo>/src)) / "resources"` 是正确的解析方式。

两条规则不同是刻意的，实施时 MUST NOT 为了"统一路径解析"把图标也搬到 exe 同级——那会让图标变成可被用户删掉的东西。

### D10 悬浮窗菜单动作先修对，再加图标

`FloatingWindow.showContextMenu()` 的三个菜单项当前全部绑 `self.close()`：「关闭电源输出」不改输出状态，「显示主窗口」是把悬浮窗关掉。给菜单配图标会让这个错位变成显眼的误导，因此在本 change 内一并接对。

`FloatingWindow` 不持有 presenter 引用，而项目已有先例是**用信号 + 宿主接线**而不是让它去反向找主窗口（`doubleClicked` 信号已存在）。因此新增 `request_show_main` / `request_output_off` 两个信号，由 `MainWindow` 接到自己的 `raise_()` 与 `presenter.set_on_off(False)`。

## Risks / Trade-offs

- ~~**[按钮加图标后变宽，串口那一行横向余量不足]**~~ **实测未触发（4.3）**：QSS 生效下每个按钮
  `sizeHint` 与 `minimumSizeHint` 各 +20px（图标 16 + 间隔 4），整行需求 434→474px，而 `groupBox`
  在窗口最小宽度下仍有 859px 可用，余量 385px；五个页签的 tab rect 也都大于"文字 + 16px 图标 + 内边距"
  的需求，文字未被挤掉。缩短文字、只给单个按钮加图标这两条退路都不需要。
  注意 Fusion 默认（未套 QSS）下按钮有 80px 最小宽，图标免费塞进去——量这条必须在应用了
  `build_qss()` 之后，否则会得到"增量为 0"的假结论。
- **[高 DPI 下 16 逻辑像素 ≠ 16 物理像素，D3 的线宽档位可能偏细]** → `icon()` 按 `devicePixelRatio` 生成 pixmap 而不是固定像素；档位表 `stroke_width_for()` 以**逻辑**尺寸取档，SVG 的 `stroke-width` 是 viewBox 24 单位下的用户坐标，因此 125%/150% 下整枚字形含线宽一起放大，相对粗细按构造不变，需要 9.4 确认的是栅格化后的实际观感而不是档位换算。**9.4 本次未做**（改缩放要动用户的系统设置），留作发布前手动实测，必要时按实测调 `_STROKE_TIERS`。
- **[产物内 SVG 资源未被收集]** → 构建后校验步骤检查 `_internal/resources/` 存在且 `app.ico` 非空，缺失即构建失败（沿用 `Assert-BundledRegistry` 的做法）。
- **[混用两个库导致后续维护时来源混乱]** → `src/resources/NOTICE.md` 逐文件列来源与许可；字形文件名保留库内原名，不改写，来源可追溯。
- **[标识审美主观，可能反复]** → D5 的评审门把不确定性关在单个 SVG 文件内，契约与管线不因审美调整而变。
- **[图标变成信息唯一载体的隐性风险]** → `ui/icon-system` 已要求文字始终保留；测试用"清空所有图标后界面仍可读"这一条来守住。

## Open Questions

- ~~Q1：控制权"持有者断线但租约未释放"用哪个形态（时钟类 vs 弱化插头类）~~ **已定（3.3）**：
  `tabler-circle-dashed`。虚线圆与 `circle-dot`/`circle` 同属圆环家族，三态靠形态而非色相区分；
  时钟类让位给列表行「待确认」（那里更需要"等待"隐喻），弱化插头类在 16px 读作断链且与「断开」
  按钮撞形。依据见 D8 的实测记录。
- Q2：~~`ouput_ctrl_Btn` 的图标是否需要在 checked/unchecked 两态换字形~~ **已定（4.x 实施时）**：不换，
  只换角色 token（`main_window.py:159` 用 `success` / `text`）。该按钮的形态线索本来就有三重——文字在
  `setText("关闭输出"/"开启输出")` 时同步翻转、2px 边框、字重——图标只是第四重，色相不是状态的唯一载体，
  `ui/icon-system` 的"不得只用色相表达状态"这条由文字翻转满足。换字形反而会与悬浮窗菜单里的
  `tabler-power`（那里是动作而非状态）产生歧义。
