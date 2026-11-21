# 新版本提示（update notice）

本文档说明应用如何发现"上游发布了更新的版本"，以及如何关闭或调整该行为。范围仅限提示：应用不会下载发布资产，也不会替换自身文件。

## 实测记录

在开发机（Windows 10 19045 / Python 3.13.14 / OpenSSL 3.0.21，无系统代理）用标准库 `urllib.request` 直接探测，时间为 2026-11-21。

| 目标 | 结果 | 耗时 | 结论 |
|---|---|---|---|
| `gitee.com/.../raw/master/requirements.txt` | 200，重定向到 `raw.giteeusercontent.com` | 339 ~ 740 ms | 可用；**必须允许跟随重定向**，不得把主机名写死 |
| `raw.githubusercontent.com/...` | TLS 握手超时 | >6 s | 本机不可达（DNS 可解析、握手挂死），作为兜底源保留 |
| `github.com/.../raw/master/...` | 握手超时 | >8 s | 与上一行同因（最终落到同一主机），无替代价值 |
| `api.github.com/.../releases/latest` | 404 | 1690 ms | 主机可达；404 是"尚无 release"，不是网络故障 |
| `gitee.com/<仓库主页>` | 404 | 370 ms | 疑为对非浏览器 UA 的反爬；发布页链接交给系统浏览器打开，不受影响 |
| `gitee.com/api/v5/.../releases/latest` | 404 | 164 ms | 主机可达；未验证鉴权要求，本方案不依赖平台 API |

TLS：`ssl.create_default_context()` 与 `truststore.SSLContext` 两种上下文在可用源上的结果**完全一致**，Windows 上默认上下文已经加载系统根证书库并可正常校验。因此探测模块使用默认上下文，**不引入 `truststore`**，也不调用 `inject_into_ssl()`（那是进程级全局副作用，会波及 MCP 通路）。

由这组数据得出的两条设计要求，已回写进 design.md D5：

1. 候选源**并发拉取**、按优先级取第一个解析成功的结果。顺序回退会让本机用户每次都先付一次 GitHub 的握手超时（>5 s）才拿到其实早已到手的 Gitee 结果。
2. 默认源顺序为 Gitee raw → GitHub raw；两者 URL 形态不同（不同主机、不同仓库名），因此配置项是完整 URL 列表，而不是 owner/repo 拼接。

未覆盖、仍需在冻结构建上确认的一项：PyInstaller onedir 产物里 `ssl.create_default_context()` 是否同样能取到系统根证书（`_ssl.pyd` 随包，理论成立）。验收方式是第 3 组构建后手动触发一次检查。

## 默认参数

| 项 | 值 | 覆盖方式 |
|---|---|---|
| 检查间隔 | 24 小时 | `src/update/settings.py` |
| 启动延迟 | 5 秒 | 同上 |
| 单源超时 | 5 秒 | 同上 |
| 候选源 | 见上表两个 raw URL | `src/update/settings.py`，可整体替换 |

## 开关与状态

- `--no-update-check`：本次运行完全不发起检查请求；`--no-gui` 模式下本就不检查。
- 状态文件 `config/update_state.json`：记录上次成功检查时间与已忽略版本，与窗口位置文件同一存放规则（打包运行时落在 exe 同级 `config/`，源码运行时落在仓库根 `config/`）。删除该文件即回到"从未检查过"的状态。
- 开发构建（无构建期来源信息）不会收到自动提示；关于页的"立即检查"不受此限制，用于验证本功能本身。

## 为什么探测必须进线程

应用与 Qt 共用 qasync 的一个事件循环，循环里任何一次阻塞都直接表现为界面卡住。探测用的是
`urllib.request` 同步调用，因此调度层（`src/update/scheduler.py`）把它包进
`asyncio.to_thread`，结果再回到循环里交给界面回调。

实测方式不是"看着不卡"，而是让假探测在 `to_thread` 里睡 0.3 秒，同时在同一循环里跑一个
10 ms 的心跳协程：`src/update/test_scheduler.py::TestEventLoopStaysResponsive` 断言探测期间
心跳不少于 10 次。若哪天有人把 `to_thread` 改成直接调用，这条用例会立刻失败——界面表现为
冻结 5 秒（单源超时），而设备控制通路也在同一次冻结里停摆。

## 端到端演练

`scripts/update_notice_rehearsal.py` 在离屏 Qt 上起真界面，配一个本地假清单服务（首选源正常、
备源端口不通、另有一个返回坏 JSON 的源），走一遍：自动检查出提示 → 间隔内不重复探测 →
关于页手动检查绕过节流 → 「查看发布页」拿到清单里的地址 → 「忽略此版本」落盘 → 用同一状态文件
重建控制器后不再提示 → 清单不可用时把失败说成失败。

清单里"发布"的版本取当前真源 +1，等价于任务里说的"把本地版本改低一档"，但不动版本真源、
不需要还原任何文件。演练期间 `update_settings.sources` 被整体换成本地地址，一次真实外网请求都不发。

```powershell
.venv\Scripts\python.exe scripts\update_notice_rehearsal.py
```

截图落在本 change 的 `evidence/`：`rehearsal_status_notice.png`（状态栏提示条与两个动作按钮）、
`rehearsal_about_manual_check.png`（关于页检查行与结果）、`rehearsal_dismissed.png`（忽略后的手动检查结果）。

离屏平台没有中文字体，截图里的中文一律渲染成方框，这是既有限制（见 `doc/version_info.md`）：
图能证明布局与可见性，不能证明字形。文案本身由用例断言，不靠看图。

「查看发布页」的真实外启走 `QDesktopServices.openUrl`。演练用注入式记录器断言它拿到的正是清单里
`release_urls` 给出的地址，不会真的弹出浏览器——那会打断使用者。

