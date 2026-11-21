"""记录开关与目录配置的读写。

沿用 src/views/window_geometry.py 的落盘范式：带 version 字段、tmp + os.replace
原子替换、内容不可用时回落默认值而不是抛异常，打包运行时配置落在可执行文件同级。
记录默认关闭：开关只由用户显式使能，绝不在启动时自作主张地开录。
"""

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CONFIG_DIR_NAME = "config"
SETTINGS_FILE_NAME = "record_settings.json"
RECORDS_DIR_NAME = "records"

# 面板采样循环的标称周期（毫秒），复看侧判缺口也用它做基准。
# 这是代码常量而不是用户配置：presenter 的轮询延时就是从这里算出来的，
# 配置里再放一份会让人以为改文件能改采样节奏。
NOMINAL_INTERVAL_MS = 500


@dataclass(frozen=True)
class RecordSettings:
    """落盘的只有开关与目录。"""

    enabled: bool = False
    dir: str = RECORDS_DIR_NAME


def settings_file_path(module_file: str = __file__) -> Path:
    """配置文件的绝对路径，不依赖进程 cwd。

    模块位于 <repo>/src/recording，向上两级即仓库根；被 PyInstaller 打包时模块路径
    指向解包目录，配置改为落在可执行文件同级（可写、升级后仍在）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_DIR_NAME / SETTINGS_FILE_NAME
    return Path(module_file).resolve().parents[2] / CONFIG_DIR_NAME / SETTINGS_FILE_NAME


def records_dir_for(settings: RecordSettings, base_dir: Path | None = None) -> Path:
    """记录目录：相对路径按仓库根（或打包后的 exe 同级）解析。"""
    path = Path(settings.dir)
    if path.is_absolute():
        return path
    root = (Path(base_dir) if base_dir is not None
            else settings_file_path().parents[1])
    return root / path


def load_settings(path: Path | None = None) -> RecordSettings:
    """读出记录配置；文件缺失或内容不可用时回落默认值，绝不抛异常。"""
    path = Path(path) if path is not None else settings_file_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.info("record settings missing, recording stays off: %s", path)
        return RecordSettings()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("record settings unreadable, recording stays off: %s (%s)", path, exc)
        return RecordSettings()

    if not isinstance(document, dict):
        logger.warning("record settings is not an object, recording stays off: %s", path)
        return RecordSettings()
    if document.get("version") != SCHEMA_VERSION:
        logger.warning("record settings version %r unsupported, recording stays off: %s",
                       document.get("version"), path)
        return RecordSettings()

    enabled = document.get("enabled")
    if not isinstance(enabled, bool):
        logger.warning("record settings 'enabled' is not a bool, falling back to off: %r", enabled)
        enabled = False

    directory = document.get("dir", RECORDS_DIR_NAME)
    if not isinstance(directory, str) or not directory.strip():
        logger.warning("record settings 'dir' unusable, using default: %r", directory)
        directory = RECORDS_DIR_NAME

    # 旧配置里可能还留着 interval_ms：它从来不是能生效的旋钮（采样周期在代码里），
    # 读到就忽略，别留一个"改了没反应"的键在语义里。
    return RecordSettings(enabled=enabled, dir=directory)


def save_settings(settings: RecordSettings, path: Path | None = None) -> bool:
    """原子写入记录配置；失败只记日志，不打断界面操作。"""
    return atomic_write_json(path or settings_file_path(), {
        "version": SCHEMA_VERSION,
        "enabled": bool(settings.enabled),
        "dir": settings.dir,
    })


def atomic_write_json(path, document) -> bool:
    """tmp + os.replace 写 JSON：读者永远只会看到完整文件或旧的完整文件。"""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("failed to write %s (%s)", path, exc)
        try:
            if tmp.exists():
                os.remove(tmp)
        except OSError as cleanup_exc:
            logger.warning("failed to remove temporary file %s (%s)", tmp, cleanup_exc)
        return False
    return True
