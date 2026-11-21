"""发布清单一致性校验：版本真源、对外清单与 git tag 必须三方对齐。

清单没跟着版本号走时的失败是静默的——用户只是永远收不到提示，不会有任何报错。
所以这道检查放在发布流程里，而不是等将来有人去猜为什么没提示。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe scripts\\gen_manifest.py --check
    .venv\\Scripts\\python.exe scripts\\gen_manifest.py --check --tag v1.2.3
    .venv\\Scripts\\python.exe scripts\\gen_manifest.py --remote
    .venv\\Scripts\\python.exe scripts\\gen_manifest.py --remote --source gitee
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import version  # noqa: E402
from update import manifest, probe  # noqa: E402
from update.settings import update_settings  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "update" / "latest.json"


def resolve_tag(explicit: str | None) -> str | None:
    """依次尝试：命令行指定 → CI 环境变量 → HEAD 上正好有 tag。

    环境变量只在值确实像版本号 tag 时才采信：workflow_dispatch 跑出来的
    GITHUB_REF_NAME 是分支名，拿它当 tag 会让闸门在每次手动构建上假失败。
    """
    if explicit:
        return explicit.strip()
    from_env = os.environ.get("GITHUB_REF_NAME", "").strip()
    if from_env.startswith("v") and version.is_valid_version(from_env[1:]):
        return from_env
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "describe", "--tags", "--exact-match", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def check(tag: str | None = None) -> list[str]:
    """返回不一致的清单；空列表代表三方对齐。"""
    problems: list[str] = []

    if not version.is_valid_version():
        problems.append(
            f"src/version.py: __version__ {version.__version__!r} is not 'major.minor.patch'")

    if not MANIFEST_PATH.is_file():
        problems.append(f"missing manifest file: {MANIFEST_PATH.relative_to(REPO_ROOT)}")
        return problems

    try:
        info = manifest.parse(MANIFEST_PATH.read_text(encoding="utf-8"), source="local")
    except manifest.ManifestError as exc:
        problems.append(f"{MANIFEST_PATH.relative_to(REPO_ROOT)}: {exc}")
        return problems

    if info.version != version.__version__:
        problems.append(
            f"manifest version {info.version!r} != src/version.py {version.__version__!r}")
    if info.channel != version.channel:
        problems.append(
            f"manifest channel {info.channel!r} != src/version.py channel {version.channel!r}")

    effective_tag = resolve_tag(tag)
    if effective_tag and effective_tag != version.tag_name():
        problems.append(
            f"tag {effective_tag!r} != expected {version.tag_name()!r} for "
            f"__version__ {version.__version__!r}")

    return problems


def remote_check(tag: str | None, only: str | None = None) -> list[str]:
    """用应用会用的每个 raw URL 单独回读，断言远端确实报出本次发布的版本。

    这是本能力唯一能证明"用户真的会收到提示"的自动化检查：清单没推到位时，
    应用侧的表现只是永远不提示，不会有任何错误。

    判定尺度：某个源答了但版本不对 -> 失败（两个源内容分叉是最危险的情形）；
    所有源都答不了 -> 失败（回读什么都没验证）；一个源对、另一个源连不上 ->
    只警告，因为源不可用属于网络现实，不该把发布卡死。
    """
    expected_source = resolve_tag(tag)
    expected = (expected_source or "").strip().lstrip("vV") or version.__version__
    candidates = [source for source in update_settings.sources
                  if only is None or source.name == only]
    if not candidates:
        return [f"no update source named {only!r} is configured "
                f"({update_settings.source_names()})"]

    problems: list[str] = []
    confirmed = 0
    for source in candidates:
        info = probe.fetch_latest([source])
        if info is None:
            print(f"WARNING: source {source.name} returned no usable manifest ({source.url})")
            continue
        if info.version != expected:
            problems.append(f"source {source.name!r} serves {info.version!r}, expected {expected!r}")
            continue
        confirmed += 1
        print(f"source {source.name} serves version {info.version} (date {info.date})")

    if confirmed == 0 and not problems:
        problems.append(f"no configured source could be read back; expected version {expected!r}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="比对三方是否一致，不一致则非零退出")
    parser.add_argument("--remote", action="store_true",
                        help="用应用实际会访问的 raw URL 回读，断言远端版本等于本次 tag")
    parser.add_argument("--tag", default=None, metavar="NAME", help="按指定 tag 校验（CI 用）")
    parser.add_argument("--source", default=None, metavar="NAME",
                        help="--remote 只回读名字的源（gitee/github），排查分叉时用")
    args = parser.parse_args(argv)

    print(f"src/version.py : {version.__version__} ({version.channel}) -> {version.tag_name()}")
    if MANIFEST_PATH.is_file():
        try:
            info = manifest.parse(MANIFEST_PATH.read_text(encoding="utf-8"), source="local")
            print(f"update/latest.json: version={info.version} channel={info.channel} date={info.date}")
        except manifest.ManifestError as exc:
            print(f"update/latest.json: unparsable ({exc})")

    if not (args.check or args.remote):
        print("nothing checked; pass --check and/or --remote")
        return 0

    problems = check(args.tag) if args.check else []
    if args.remote:
        problems = problems + remote_check(args.tag, args.source)
    if problems:
        for problem in problems:
            print(f"MISMATCH: {problem}", file=sys.stderr)
        return 1
    print("all requested checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
