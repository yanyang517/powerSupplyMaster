"""从版本真源生成 PyInstaller 的 Windows 版本资源文件。

版本号只有 src/version.py 一处定义；本脚本读取它并渲染 exe 属性需要的结构，
格式不合规时以非零码退出，让构建失败而不是静默产出一个属性空白的 exe。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe scripts\\make_version_info.py --out build\\pyinstaller\\version_info.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import version  # noqa: E402  （需要在插入 src 之后导入）

APP_NAME = "powerSupplyMaster"
COMPANY = "yanyang517"
LICENSE_TAG = "LGPL-3.0"

_TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({quad}),
    prodvers=({quad}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', '{company}'),
        StringStruct('FileDescription', '{app}'),
        StringStruct('FileVersion', '{plain}'),
        StringStruct('InternalName', '{app}'),
        StringStruct('LegalCopyright', '{license}'),
        StringStruct('OriginalFilename', '{app}.exe'),
        StringStruct('ProductName', '{app}'),
        StringStruct('ProductVersion', '{plain}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def render() -> str:
    """返回版本资源文件内容；`__version__` 不合三段数字约定时抛 ValueError。"""
    major, minor, patch = version.version_tuple()
    return _TEMPLATE.format(
        quad=f"{major}, {minor}, {patch}, 0",
        plain=version.__version__,
        app=APP_NAME,
        company=COMPANY,
        license=LICENSE_TAG,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, metavar="PATH", help="版本资源文件输出路径")
    parser.add_argument("--print-version", action="store_true", help="只打印版本号，不写文件")
    args = parser.parse_args(argv)

    if not version.is_valid_version():
        print(f"invalid __version__ in {SRC_DIR / 'version.py'}: {version.__version__!r}",
              file=sys.stderr)
        return 2

    if args.print_version:
        print(version.__version__)
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # PyInstaller 按 UTF-8 读取该文件，且首行必须是 `# UTF-8` 声明。
    out.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {out} for {version.display_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
