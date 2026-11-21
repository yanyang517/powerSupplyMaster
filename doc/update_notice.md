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
