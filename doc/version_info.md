# 版本信息（version info）

## 唯一真源

`src/version.py` 是应用版本号的唯一定义处：

```python
__version__ = "1.0.0"      # 主.次.修订，三段数字
channel = "stable"
```

仓库内其他位置只允许出现对它的引用，不允许再写一份需要人工同步的字面版本号。`src/test_version.py::TestSingleSourceOfTruth` 会扫描 `src/`、`scripts/`、`.github/workflows/` 并把违规者列出来。

发布用 git tag 必须是 `v` + `__version__`，由 `tag_name()` 给出，发布流程以此比对。

## 派生落点

| 落点 | 取值方式 |
|---|---|
| 窗口标题 | `display_version()`，在 `MainWindow.setupUi()` 里覆盖 uic 生成的占位文案 |
| 「关于」页 | `display_version()` + `channel` + `build_label()`，Python 侧注入，不改 `.ui` |
| 启动日志 | `summary()`，`app.main()` 的第一条日志 |
| exe 文件属性 | `scripts/build_exe.ps1` 读取后生成 PyInstaller 版本资源（见下） |
| 控制通路 | `setting_query` 响应与 MCP `get_status` 返回值 |

## 构建期来源信息

提交标识与构建时间不写在真源里，而由构建脚本生成 `src/_build_info.py`（已 gitignore）：

```python
build_commit = "dead123"
build_time = "2026-11-21T09:30:00Z"
```

该文件不存在时 `is_dev_build()` 为真，关于页与日志会明确显示 `dev build`，新版本提示也不会对开发构建弹出。这样"源码直跑"和"发布产物"在界面上一眼可分，不必靠猜。

## 改版本号的动作

1. 改 `src/version.py` 的 `__version__`。
2. 同步 `update/latest.json` 的 `version`（对外公告副本，见"发布清单"一节）。
3. 提交，合入 master 后打 tag `v<新版本>`。

第 2 步漏掉的后果是静默的：用户永远收不到提示而不会报错。因此 `scripts/gen_manifest.py --check` 与 release 工作流都会卡这一条。

## 发版动作清单

一次发布按顺序走完五步，前三步在本地，第四步推主仓库，第五步交给 release 工作流：

1. 一个 bump commit 同时改两处：`src/version.py` 的 `__version__` 与 `update/latest.json` 的
   `version`（`date` 一并更新为发版日）。两处一起提交，是为了让"改了版本但忘了公告"在
   同一个 diff 里就看得见。
2. 本地闸门：`.venv\Scripts\python.exe scripts\gen_manifest.py --check`。
3. 按项目约定用 `git merge --no-ff` 把特性分支合入 master。
4. 在合入后的 master 上打 tag `v<新版本>`（必须等于 `tag_name()`），只推主仓库：
   `git push github master` 与 `git push github v<新版本>`。Gitee 是只读镜像，不再由人工推
   代码——镜像内容由 release 工作流同步过去。
5. release 工作流跑四道动作：构建前 `--check`；发布 GitHub Release；把 master 与该 tag 快进
   到 Gitee 镜像；再把同一个 zip 镜像成 Gitee 同名发行版的附件（`scripts/sync_release_to_gitee.py`）；
   最后 `--remote` 用应用实际会访问的两个 raw URL 回读，断言远端版本等于 tag。

镜像这两道只有一个前置：仓库 secret `GITEE_TOKEN`（Gitee 私人令牌，只需 `projects` 权限）。
没配就两道都跳过并记警告，随后 `--remote` 一定红——那是真实结论：镜像还停在上一版，
一半用户收不到公告。要让它绿，要么配令牌，要么恢复人工推 Gitee。
之所以值得多这两道，是国内取 GitHub Release 资产太慢，而 `update/latest.json` 里
`release_urls` 早就同时公告了两边的发行页，只是 Gitee 那边一直是个空页。

Gitee 侧的两条硬限制写在脚本里而不是等它失败：单附件 100 MB（GVP 200 MB）、每仓库附件总量
1 GB。上传走的 `releases/{id}/attach_files` 没进官方文档，所以脚本上传后一律回读发行版，
按"同名且同尺寸"才算镜像完成；同名不同尺寸判为上次中断留下的残包，报错要人工删。

`--check` 覆盖的正是第 1 步会漏的那对文件，外加 tag：

| 校验 | 不一致时的表现 |
|---|---|
| `__version__` 是 `主.次.修订` 三段数字 | 报错退出，构建不开始 |
| `update/latest.json` 可解析且必填字段齐 | 报错退出 |
| 清单 `version` == `__version__` | 报错退出 |
| 清单 `channel` == `version.py` 的 `channel` | 报错退出 |
| tag == `v{__version__}`（tag 已知时） | 报错退出 |

`--remote` 额外覆盖"推到位没有"：任一可达源版本对不上就失败；所有源都读不到也失败（回读
什么都没验证）；只有个别源连不上则记警告不失败——源不可用是网络现实，不该把发布卡死。

tag 之外还有一处不在 `--check` 范围内：GitHub Release 的资产名与说明文本由工作流从
`GITHUB_REF_NAME` 推导，不需要人工同步，因此不构成第二处真源。

## 验收命令

在仓库根目录执行：

```powershell
# 版本相关测试
.venv\Scripts\python.exe -m pytest src/test_version.py src/views/test_version_display.py

# 构建后确认 exe 携带版本元数据
.venv\Scripts\python.exe -m pytest src/test_version.py
powershell -File scripts\build_exe.ps1
(Get-Item dist/powerSupplyMaster/powerSupplyMaster.exe).VersionInfo |
    Select-Object FileVersion, ProductVersion, ProductName
```

`FileVersion` 与 `ProductVersion` 必须等于 `src/version.py` 里的 `__version__`。

## 已知渲染限制

离屏（`QT_QPA_PLATFORM=offscreen`）截图里中文会显示成方框，那是该平台缺 CJK 字体，不是主题缺陷；界面文案的正确性由 `src/views/test_version_display.py` 的控件断言保证，截图只用于确认布局与配色。
