"""从 app-mark.svg 派生 Windows 图标容器 src/resources/app.ico。

不引入 Pillow：ICO 的每个条目就是目录项 + 一个 PNG blob，纯 Python 写目录表约 20 行。
SVG 的取色、线宽与栅格化一律复用 views.icons，避免"打包用的图标与界面里的图标是两套
东西"——那种分叉只会让产物里的图标悄悄和开发环境不一样。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe scripts\\gen_icon.py
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

DEFAULT_OUT = SRC_DIR / "resources" / "app.ico"

# 40 与 20 是 Windows 任务栏与"大图标"视图实际会取用的档位，缺了会由系统缩放别的档。
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_bytes(pixmap) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice

    buffer_ = QBuffer()
    buffer_.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer_, "PNG"):
        raise RuntimeError("PNG 编码失败")
    return bytes(buffer_.data())


def build_ico(entries: list[tuple[int, bytes]]) -> bytes:
    """ICONDIR + ICONDIRENTRY[] + 各条目的 PNG blob。256 档的宽高字节写 0。"""
    header = struct.pack("<HHH", 0, 1, len(entries))
    blob_start = 6 + 16 * len(entries)
    directory = bytearray()
    payload = bytearray()
    offset = blob_start
    for size, blob in entries:
        side = size if size < 256 else 0
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        payload += blob
    return header + bytes(directory) + bytes(payload)


def verify(path: Path) -> list[str]:
    """读回头字节，返回问题列表；空列表即合法。"""
    data = path.read_bytes()
    if len(data) < 6:
        return [f"{path.name} 只有 {len(data)} 字节，连 ICONDIR 都放不下"]
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    problems = []
    if (reserved, kind) != (0, 1):
        problems.append(f"图标类型字节异常：reserved={reserved} kind={kind}")
    if count != len(SIZES):
        problems.append(f"条目数 {count}，期望 {len(SIZES)}")
    for index in range(count):
        entry = data[6 + 16 * index: 6 + 16 * (index + 1)]
        width, height = entry[0], entry[1]
        size = width or 256, height or 256
        blob_len, blob_at = struct.unpack("<II", entry[8:16])
        blob = data[blob_at: blob_at + blob_len]
        if not blob.startswith(PNG_SIGNATURE):
            problems.append(f"条目 {index}（{size[0]}px）不是 PNG blob")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--check-only", action="store_true",
                        help="只校验既有产物，不重新生成")
    args = parser.parse_args(argv)
    out = Path(args.out)

    if args.check_only:
        if not out.is_file():
            print(f"缺少图标产物：{out}", file=sys.stderr)
            return 1
        problems = verify(out)
        for problem in problems:
            print(f"图标产物不合法：{problem}", file=sys.stderr)
        return 1 if problems else 0

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841  QPixmap 需要它活着
    from views import icons

    entries = []
    for size in SIZES:
        pixmap = icons.mark_pixmap(size, dpr=1.0)
        if pixmap is None:
            print(f"标识在 {size}px 渲染失败，未写出 {out}", file=sys.stderr)
            return 1
        entries.append((size, png_bytes(pixmap)))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_ico(entries))

    problems = verify(out)
    if problems:
        for problem in problems:
            print(f"图标产物不合法：{problem}", file=sys.stderr)
        return 1
    print(f"{out}：{len(entries)} 档，{out.stat().st_size} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
