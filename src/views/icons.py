"""界面图标的取色与栅格化入口。

不写 QIcon("<path>.svg")：那条路径依赖 Qt 的 svg iconengine 插件，PyInstaller 对它的
收集不可靠，失败形态是最坏的——开发环境一切正常、产物里图标静默消失。QSvgRenderer 只
依赖 QtSvg 模块本身，并且让我们在栅格化之前改写颜色与线宽。

颜色一律用 token 名而不是十六进制：图标层不出现任何颜色常量，改主题即改图标。
"""

import logging
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import tokens

logger = logging.getLogger(__name__)

RESOURCES_DIR_NAME = "resources"
ICONS_DIR_NAME = "icons"
MARK_FILE_NAME = "app-mark.svg"
MARK_SMALL_FILE_NAME = "app-mark-16.svg"
MARK_SMALL_MAX_SIZE = 24

# 24 网格上的 stroke-width=2 缩到 16 实际像素只剩 1.33px，实测笔画会断；16/20 档抬到
# 2.5 后仍保持连续。第三方字形文件本体保持上游状态，只在内存里改写。
_STROKE_TIERS = ((20, 2.5), (10 ** 6, 2.0))

_STROKE_ATTR = re.compile(r'stroke-width="[^"]*"')
_TOKEN_PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")


def resources_dir() -> Path:
    """图标是只读构建产物，冻结时随 --add-data 落在 _MEIPASS 下。

    与 config/clients.json 那类用户可改写的配置刻意不同：后者必须落 exe 同级，图标
    不需要也不应该变成可被用户删掉的东西。
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or str(Path(sys.executable).resolve().parent)
        return Path(base) / RESOURCES_DIR_NAME
    return Path(__file__).resolve().parents[1] / RESOURCES_DIR_NAME


def color_for(role: str) -> str:
    try:
        return tokens()[role]
    except KeyError:
        raise ValueError(f"unknown color role: {role!r}") from None


def stroke_width_for(size: int) -> float:
    for limit, value in _STROKE_TIERS:
        if size <= limit:
            return value
    return _STROKE_TIERS[-1][1]


def _resolve_tokens(text: str) -> str:
    """把 {{token}} 占位换成主题色值，供带多色的原创图形使用。"""

    def replace(match: re.Match) -> str:
        return color_for(match.group(1))

    return _TOKEN_PLACEHOLDER.sub(replace, text)


def _glyph_text(name: str, role: str, size: int) -> str:
    path = resources_dir() / ICONS_DIR_NAME / f"{name}.svg"
    if not path.is_file():
        logger.warning("icon glyph missing: %s", path)
        return ""
    text = _resolve_tokens(path.read_text(encoding="utf-8"))
    text = text.replace("currentColor", color_for(role))
    return _STROKE_ATTR.sub(f'stroke-width="{stroke_width_for(size):g}"', text, count=1)


def _mark_text(size: int) -> str:
    name = MARK_SMALL_FILE_NAME if size <= MARK_SMALL_MAX_SIZE else MARK_FILE_NAME
    path = resources_dir() / name
    if not path.is_file():
        logger.warning("app mark missing: %s", path)
        return ""
    text = _resolve_tokens(path.read_text(encoding="utf-8"))
    return _STROKE_ATTR.sub(f'stroke-width="{stroke_width_for(size):g}"', text, count=1)


def _device_pixel_ratio() -> float:
    app = QGuiApplication.instance()
    if app is None or app.primaryScreen() is None:
        return 1.0
    return float(app.primaryScreen().devicePixelRatio())


def _render(text: str, size: int, dpr: float | None, label: str) -> QPixmap | None:
    """任何失败都返回 None 并记一条告警，不向上抛：图标缺失不能影响功能与启动。"""
    if not text:
        return None
    try:
        renderer = QSvgRenderer(text.encode("utf-8"))
        if not renderer.isValid():
            logger.warning("icon unparsable: %s", label)
            return None
        ratio = dpr if dpr else _device_pixel_ratio()
        side = max(1, round(size * ratio))
        image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
    except Exception as exc:  # noqa: BLE001 - 图标降级不得影响主流程
        logger.warning("icon render failed: %s (%s)", label, exc)
        return None
    if image.isNull():
        logger.warning("icon render produced empty image: %s", label)
        return None
    return QPixmap.fromImage(image)


def pixmap(name: str, role: str, size: int = 16, dpr: float | None = None) -> QPixmap | None:
    """栅格化一个第三方字形。name 形如 "tabler/gauge"。"""
    return _render(_glyph_text(name, role, size), size, dpr, name)


def icon(name: str, role: str, size: int = 16, dpr: float | None = None) -> QIcon:
    pm = pixmap(name, role, size, dpr)
    return QIcon() if pm is None else QIcon(pm)


def mark_pixmap(size: int = 48, dpr: float | None = None) -> QPixmap | None:
    """应用标识：<= 24 档用简化档，其余用完整档（同一契约、同一色值来源）。"""
    return _render(_mark_text(size), size, dpr, "app-mark")


def mark_icon(size: int = 48, dpr: float | None = None) -> QIcon:
    pm = mark_pixmap(size, dpr)
    return QIcon() if pm is None else QIcon(pm)


# Windows 会按落点尺寸从 QIcon 里挑现成的一档；只塞 48px 时标题栏的 16px 是缩放出来的。
MARK_ICON_SIZES = (16, 20, 24, 32, 48, 64, 256)


def app_icon(sizes: tuple[int, ...] = MARK_ICON_SIZES) -> QIcon:
    """窗口图标：常用档位各出一张。全部失败时返回空 QIcon，启动不因此中断。"""
    result = QIcon()
    for size in sizes:
        pm = mark_pixmap(size, dpr=1.0)
        if pm is not None:
            result.addPixmap(pm)
    return result
