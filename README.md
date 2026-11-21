# powerSupplyMaster

[English](README.en.md) | **中文**

面向 SCPI 可编程直流电源的 PC 上位机 —— PySide6 图形界面 + TCP/JSON 控制服务 + MCP 桥接，让 AI 助手也能安全地操作硬件。

通过串口（pyserial）连接任意支持 SCPI 的台式电源（基于 RIGOL DP832 一类仪器开发），随后可以在桌面 UI、远程 TCP 程序，或 Qoder Desktop / Claude Desktop 等 AI 客户端中控制它。

## 功能特性

- **桌面 GUI（PySide6）** — 串口选择、电压旋钮 + 数字框联动、输出开关、电压/电流实时曲线、置顶半透明悬浮小窗、深色主题、窗口位置记忆。
- **TCP/JSON 控制服务** — 监听 `:18888`，4 字节长度前缀 + UTF-8 JSON 帧协议；远程程序可经同一设备会话查询/设置电压、电流、输出。
- **面向 AI 的 MCP 服务** — stdio 传输的 MCP 桥，暴露 `get_status` / `set_voltage` / `set_current` / `set_output` 四个工具，让 LLM 在与 GUI 相同的安全限值内读取和驱动电源。
- **全通路统一安全限值** — `--max-voltage` / `--max-current` 由服务端强制，GUI、TCP 客户端、AI 一律受限。
- **设备模拟器** — 独立进程的 SCPI 虚拟电源，配合虚拟串口即可在无硬件环境下开发与联调。
- **无头模式** — `--no-gui` 仅运行控制服务。
- **版本标识与更新提示** — 版本号唯一定义在 `src/version.py`，出现在窗口标题、关于页、启动日志、exe 文件属性与 `setting_query`/MCP 返回值中；后台按 `update/latest.json` 清单检查新版本，只在状态栏提示，不下载、不自动替换（`--no-update-check` 或 `--no-gui` 时不探测）。详见 [doc/version_info.md](doc/version_info.md)、[doc/update_notice.md](doc/update_notice.md)。
- **图标与应用标识** — 界面图标是 vendored 的开源线稿字形（Tabler 3.52.0 / MIT、Lucide 1.77.0 / ISC，共 18 个），取色走主题 token、线宽按尺寸档位调整，缺失时降级为无图标而不是中断启动；应用标识为原创的实心圆角方块 + ⏻ 镂空，窗口图标与 exe 的 `app.ico` 都由同一份 SVG 派生（`scripts/gen_icon.py`）。来源、版本与落点清单见 [src/resources/NOTICE.md](src/resources/NOTICE.md)。

## 架构

```
┌──────────────┐      串口 (SCPI)         ┌──────────────────┐
│ PySide6 GUI  │ ─────────────────────── │  直流电源设备     │
└──────┬───────┘                         └──────────────────┘
       │ qasync（Qt 与 asyncio 单线程同循环）
       │
┌──────┴───────┐   TCP JSON（4B 长度前缀 + UTF-8）  ┌─────────────┐
│ app.py       │ ◄───────────────────────────────── │ TCP 客户端  │
│ + server     │                                     └─────────────┘
└──────┬───────┘
       │ stdio MCP
┌──────┴───────┐
│ MCP 桥接进程 │ ← AI 客户端（Qoder Desktop、Claude Desktop 等）
└──────────────┘
```

单进程设计：GUI 与 asyncio 服务经 [qasync](https://github.com/CQFDotIO/qasync) 共用一个事件循环。SCPI 驱动是进程级单例，因此 GUI / TCP / MCP 三条控制通路最终汇合于同一个串口会话与同一把事务锁。

## 快速开始

需要 Python ≥ 3.10（主要面向 Windows；GUI/服务端代码本身跨平台）。

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # Linux/macOS

# GUI 模式（在界面中选择 COM 口，点击"连接"）
.venv/Scripts/python.exe src/app.py

# 仅运行服务（无界面），监听 0.0.0.0:18888
.venv/Scripts/python.exe src/app.py --no-gui

# 配置安全限值（默认 30 V / 5 A）
.venv/Scripts/python.exe src/app.py --max-voltage 24 --max-current 3
```

> 注意：项目内绝对导入以 `src/` 为根，请按上述路径在仓库根目录运行（或 `cd src` 后执行 `python app.py`）。

### 没有硬件？用模拟器联调

先创建一对虚拟串口（如 [com0com](https://com0com.sourceforge.net/) → `COM8 ↔ COM9`），然后：

```bash
# 终端 1 —— 在 COM9 上模拟电源
python src/device/device_simulator.py --port COM9 --baud 115200

# 终端 2 —— 运行本程序，在 UI 中选择 COM8
python src/app.py
```

## AI 控制（MCP 接入）

内置 MCP 服务让 AI 客户端用自然语言读取和操控电源。串口所有权始终在桌面应用——AI 只能使用协议开放的能力，越权限值会被服务端拒绝。

1. 运行 powerSupplyMaster（GUI 或 `--no-gui`），保证 TCP 服务在监听。
2. 在 UI 中完成一次串口连接。
3. 在 MCP 客户端配置中加入：

```json
{
  "mcpServers": {
    "power-supply": {
      "command": "<仓库路径>/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server"],
      "cwd": "<仓库路径>/src",
      "env": { "PYTHONPATH": "<仓库路径>/src" }
    }
  }
}
```

可用工具：

| 工具 | 参数 | 说明 |
|---|---|---|
| `get_status` | 无 | 聚合返回电压(V)、电流(A)、输出开关、设备标识、生效限值 `limits`（含上位机版本 `limits.server_version`） |
| `set_voltage` | `voltage` (V) | 超出 `limits.max_voltage_v` 会被拒绝并提示允许范围 |
| `set_current` | `current` (A) | 超出 `limits.max_current_a` 会被拒绝 |
| `set_output` | `enable` (bool) | 接通/断开输出 |

详见 [doc/mcp_integration.md](doc/mcp_integration.md)。

## TCP 协议

帧格式：`uint32 大端长度 | UTF-8 JSON`，一问一答，端口 **18888**。

请求字段：`type`（判别字段）、`request_id`、`timestamp`，以及各命令的专属参数。支持的 type 包括 `echo`、`login`/`logout`、`open_device`/`close_device`、`set_voltage`、`set_current`、`set_on_off`、`voltage_query`、`current_query`、`on_off_query`、`device_id_query`、`setting_query`（响应含生效限值与上位机版本）。契约定义见 [src/server/protocal/protocal.py](src/server/protocal/protocal.py)，客户端示例见 [src/server/test_client.py](src/server/test_client.py)。

## 打包 Windows 可执行文件

```powershell
# 需要仓库根目录下存在 .venv，产物输出到 dist/
powershell -File scripts/build_exe.ps1
```

GitHub Actions 工作流（[.github/workflows/release.yml](.github/workflows/release.yml)）会在打 `v*` 标签时自动构建并发布 exe。

## 项目结构

```
src/
├── app.py              # 入口（GUI + 服务同循环运行）
├── version.py          # 应用版本号唯一定义处
├── presenter/          # MVP：展示逻辑 + 周期采样调度
├── views/              # PySide6 界面（主窗口、悬浮窗、深色主题、更新提示）
├── device/             # SCPI 串口驱动（单例）+ 设备模拟器
├── server/             # TCP/JSON 服务、分发器、请求契约
├── mcp_server/         # 面向 AI 客户端的 stdio MCP 桥
└── update/             # 新版本探测：清单解析、比较、状态、调度
update/latest.json      # 对外公告的发布清单（Gitee 与 GitHub 同源）
doc/                    # 架构文档、MCP 接入指南
scripts/                # PyInstaller 打包脚本、清单生成与校验
```

## 测试

集成测试（需服务已运行 + 真实或虚拟串口）位于服务端代码同层：

```bash
cd src
python -m pytest server/test_client.py -v
```

## 已知限制

- GUI 与远程 TCP/AI 通路共享同一串口会话，尚无所有权仲裁层——多通路并发控制可以发生但不受协调。
- 写类命令（`VOLT`、`OUTP`）不回读设备错误队列，设备侧错误对操作者不可见。
- 部分协议 type 已声明但无处理器；测试套件依赖真实/虚拟串口。

欢迎提交 PR 改进 —— 参见 issue 区。

## 许可

本项目以 GNU 宽通用公共许可证 v3.0（LGPL-3.0）发布，见 [LICENSE](LICENSE)。
