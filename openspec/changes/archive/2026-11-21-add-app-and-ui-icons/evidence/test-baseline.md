# 10.2 回归基线对比

命令：`cd src && python -m pytest . -q -rs`，Python 3.12 venv（`.venv`，两个目录共用）。

| 阶段 | 结果 |
|---|---|
| 基线：`master` @ `160bde4` 干净树 | 8 failed / 362 passed / 1 skipped / 4 errors |
| 本次实施后：worktree `add-app-and-ui-icons` | 8 failed / **393** passed / 1 skipped / 4 errors |

failed 与 errors 的数量、用例名完全一致，新增 0 个。passed +31，与本 change 新增的测试逐条对得上：

| 文件 | 基线 | 实施后 | 新增 |
|---|---|---|---|
| `views/test_icons.py` | 文件不存在 | 16 | 16（渲染管线、token 取色、降级、档位、ICO/字形文件契约） |
| `views/test_main_window_icons.py` | 文件不存在 | 6 | 6（主窗口各落点图标） |
| `views/test_floating_actions.py` | 文件不存在 | 6 | 6（悬浮窗菜单动作修正 + 图标） |
| `test_app_startup.py` | 9 | 11 | 2（`TestIconDegradation`：资源缺失时窗口图标/悬浮窗仍可用） |
| `views/test_theme.py` | 9 | 10 | 1（10.3：图标像素色跟随 `tokens()`） |

唯一 skipped 是 `server/test_client.py:234`（"Unknown command test needs to be implemented later"），基线即有。8 failed / 4 errors 全部落在 `server/test_client.py`，是需要服务在监听 + 真实或虚拟串口的集成用例，基线已知且与图标改动无关。

## 度量过程中的两个坑

1. **`src/_build_info.py` 会改变计数。** 它是 `scripts/build_exe.ps1` 生成的 gitignored 文件；只要在工作树里存在，`views/test_version_display.py:79` 就走"发布构建"分支 skip，passed/skipped 各移一位。上表两侧都已清理后再测。**主检出 `D:/git/powerSupplyMaster/src/_build_info.py` 目前是上一个 change 打包留下的残留**，未清理（不是本次生成的文件），在它上面直接跑套件会得到 361 passed / 2 skipped。
2. **开工时随手记的 389 passed 不是 master 基线**，那是实施中途（`test_icons.py` 已经存在）的数，早期版本的本表据此得出"+4"。以 `160bde4` 干净树重测后才是上面的 +31。
