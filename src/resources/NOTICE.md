# 第三方图标字形来源与许可

本目录下的 `icons/` 子树是第三方开源图标库的原始 SVG 文件，逐文件保留库内原名与原始内容，
未做路径改写、未做重命名、未做合并。运行时只在本仓库代码里改写其 `currentColor` 与
`stroke-width` 属性值（见 `src/views/icons.py`），文件本体保持上游状态以便追溯与升级。

## 库版本

| 库 | 版本 | 许可 | 上游 | 本仓目录 |
|---|---|---|---|---|
| Tabler Icons | 3.52.0 | MIT | https://github.com/tabler-icons/tabler-icons | `icons/tabler/` |
| Lucide | 1.77.0 | ISC | https://github.com/lucide-icons/lucide | `icons/lucide/` |

Lucide 的上游 SVG 文件自带 `<!-- @license lucide-static v1.77.0 - ISC -->` 头注释，署名随文件走；
Tabler 的文件不带注释，因此其 MIT 全文记录在本文件末尾。

## 逐文件清单

只 vendored 落点表实际用到的字形，18 个文件对 18 个落点条目。落点列与 OpenSpec change
`add-app-and-ui-icons` 的 design.md D8 一致；文件名为库内原名，未改写。

`icons/tabler/`（MIT，取自 `@tabler/icons` 的 `icons/outline/`，15 个）：

| 文件 | 落点 |
|---|---|
| `wave-sine.svg` | 页签「波形」 |
| `users.svg` | 页签「客户端」 |
| `picture-in-picture.svg` | 页签「悬浮窗」 |
| `plug-off.svg` | 按钮「断开」 |
| `power.svg` | 按钮「输出开关」、悬浮窗菜单「关闭电源输出」 |
| `circle-dot.svg` | 控制权·本机持有 |
| `circle.svg` | 控制权·他人持有 |
| `circle-dashed.svg` | 控制权·持有者断线（租约未释放） |
| `shield-x.svg` | 按钮「吊销控制权」 |
| `user-check.svg` | 客户端列表行·已登录 |
| `user.svg` | 客户端列表行·未登录 |
| `clock.svg` | 客户端列表行·待确认 |
| `user-off.svg` | 客户端列表行·断线持有 |
| `window.svg` | 悬浮窗菜单「显示主窗口」 |
| `eye-off.svg` | 悬浮窗菜单「隐藏悬浮窗」 |

`icons/lucide/`（ISC，取自 `lucide-static` 的 `icons/`，3 个）：

| 文件 | 落点 |
|---|---|
| `gauge.svg` | 页签「控制面板」 |
| `info.svg` | 页签「关于」 |
| `plug.svg` | 按钮「连接」 |

同一字形名在两个库里各有一份（`gauge.svg`）是刻意的：两者网格与描边模型相同、构图不同，
16px 档的可读性经实测各有胜负，落点按字形逐个选定。

实测淘汰、未收录的字形记录在案，避免后续重复试错：`tabler-circle-half`（16px 读作"禁止通行"）、
`tabler-wifi-off`（16px 是一堆斜线）、`tabler-network`（16px 读作地球仪，与"客户端"漂移）、
`tabler-hourglass`（16px 读作蝴蝶结）、`lucide-unplug`（16px 读作断链而非拔插头）。


## 应用标识不在本目录的第三方范围内

`app-mark.svg` 与 `app-mark-16.svg` 是本仓库原创绘制，MUST NOT 由上述任何字形拼合或改绘而来。

---

## Tabler Icons — MIT License

Copyright (c) 2018-2026 The Tabler Icons Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Lucide — ISC License

Copyright (c) 2020-2026 The Lucide Authors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
