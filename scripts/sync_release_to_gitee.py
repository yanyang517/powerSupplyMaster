"""把 GitHub Release 的制品镜像到 Gitee 同名发行版，给国内下载用。

用法（仓库根目录，令牌走环境变量）：
    $env:GITEE_TOKEN = "..."
    .venv\\Scripts\\python.exe scripts\\sync_release_to_gitee.py --tag v0.1.0 --file powerSupplyMaster-v0.1.0-windows-x64.zip
    .venv\\Scripts\\python.exe scripts\\sync_release_to_gitee.py --tag v0.1.0 --file x.zip --dry-run

判定一律以"回读"为准：上传接口说成功不算成功，发行版里真能看到同名同尺寸的附件才算。
清单没推到位时应用侧的表现是"永远不提示"，同理附件没上去时 Gitee 页面也只是少一行，
所以这里宁可报错也不要静默半成品。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://gitee.com/api/v5"
DEFAULT_GITEE_REPO = "yanyang517/power-supply-master"
DEFAULT_GITHUB_REPO = "yanyang517/powerSupplyMaster"
API_TIMEOUT = 60
UPLOAD_TIMEOUT = 900  # 留出余量给 build job 自身的 30 分钟上限


class SyncError(RuntimeError):
    pass


def _decode(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", "replace")


def _send(request: urllib.request.Request, label: str, timeout: int):
    """把 HTTPError 的响应体摊开——Gitee 的拒因只在 body 里，状态码一律含糊。"""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _decode(response.read())
    except urllib.error.HTTPError as exc:
        body = _decode(exc.read())
        detail = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        raise SyncError(f"{label}: HTTP {exc.code} {detail}") from None
    except urllib.error.URLError as exc:
        raise SyncError(f"{label}: 网络不可达 ({exc.reason})") from None


def api_get(path: str, token: str | None = None, params: dict | None = None):
    query = dict(params or {})
    if token:
        query["access_token"] = token
    url = f"{API}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    return _send(urllib.request.Request(url), f"GET {path}", API_TIMEOUT)


def api_post_form(path: str, fields: dict, token: str):
    """Gitee 的写接口只认表单体；发 JSON 会被丢掉字段，表现为"参数缺失"。"""
    body = urllib.parse.urlencode({**fields, "access_token": token}).encode("utf-8")
    request = urllib.request.Request(
        f"{API}{path}", data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"})
    return _send(request, f"POST {path}", API_TIMEOUT)


def find_release(owner: str, repo: str, tag: str, token: str | None):
    _, body = api_get(f"/repos/{owner}/{repo}/releases/tags/{urllib.parse.quote(tag, '')}", token)
    return body if isinstance(body, dict) else None


def release_assets(release: dict) -> list[dict]:
    assets = release.get("assets") or []
    return [asset for asset in assets if isinstance(asset, dict)]


def asset_url(asset: dict) -> str:
    return asset.get("browser_download_url") or asset.get("download_url") or "(无下载链接)"


def tag_is_on_gitee(owner: str, repo: str, tag: str) -> bool | None:
    """True/False 为确定结论，None 表示 tag 太多没翻到，不下判断。"""
    _, tags = api_get(f"/repos/{owner}/{repo}/tags", params={"per_page": 100})
    if not isinstance(tags, list):
        return None
    if any(item.get("name") == tag for item in tags if isinstance(item, dict)):
        return True
    return None if len(tags) >= 100 else False


def ensure_release(owner: str, repo: str, tag: str, token: str, body_text: str) -> dict:
    existing = find_release(owner, repo, tag, token)
    if existing:
        print(f"Gitee 发行版已存在: id={existing.get('id')} {existing.get('html_url', '')}")
        return existing
    if tag_is_on_gitee(owner, repo, tag) is False:
        raise SyncError(
            f"Gitee 上还没有 tag {tag}，平台侧的 GitHub→Gitee 同步没到位；"
            f"等它跟上再重跑这一步，别在这里凭空的 commitish 建发行版")
    print(f"Gitee 上没有 {tag} 的发行版，按 tag 新建")
    # target_commitish 是 Gitee 必填而 GitHub 可省的字段，缺它直接 400。
    # 填 tag 本身：tag 已存在时它只是定位用，不会把发行版挪到分支尖端去。
    _, created = api_post_form(f"/repos/{owner}/{repo}/releases",
                               {"tag_name": tag, "name": tag, "body": body_text,
                                "target_commitish": tag}, token)
    if not isinstance(created, dict) or not created.get("id"):
        detail = json.dumps(created, ensure_ascii=False)
        raise SyncError(f"创建发行版后没拿到 id: {detail}")
    print(f"已创建: id={created['id']} {created.get('html_url', '')}")
    return created


def upload_asset(owner: str, repo: str, release_id: int, path: str, name: str, token: str) -> None:
    """大文件走 curl：自己拼 multipart 只能分块传输，Gitee 前置不认没有 Content-Length 的上传。"""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise SyncError("找不到 curl，无法上传附件")
    url = f"{API}/repos/{owner}/{repo}/releases/{release_id}/attach_files"
    command = [
        curl, "--silent", "--show-error", "--fail-with-body",
        "--max-time", str(UPLOAD_TIMEOUT),
        "--request", "POST", url,
        "--form", f"access_token={token}",
        "--form", f"file=@{path};filename={name}",
    ]
    print(f"上传 {name} ({os.path.getsize(path) / 1048576:.1f} MB) —— 令牌只进 curl 参数，不写进日志")
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        detail = (done.stdout or done.stderr or "").strip()[:500]
        raise SyncError(f"上传失败 (curl 退出码 {done.returncode}): {detail}")
    body = _decode(done.stdout.encode("utf-8", "replace"))
    print(f"Gitee 应答: {json.dumps(body, ensure_ascii=False)[:300] if not isinstance(body, str) else body[:300]}")


def verify(owner: str, repo: str, release_id: int, tag: str, name: str, size: int, token: str | None) -> dict:
    _, release = api_get(f"/repos/{owner}/{repo}/releases/{release_id}", token)
    if not isinstance(release, dict):
        raise SyncError(f"回读发行版 {release_id} 失败（tag {tag}）")
    for asset in release_assets(release):
        if asset.get("name") != name:
            continue
        reported = asset.get("size")
        if reported is not None and int(reported) != size:
            raise SyncError(
                f"附件 {name} 在 Gitee 上的尺寸是 {int(reported)} 字节，本地是 {size} 字节。"
                f"多半是上一次中断留下的残包，请到 {release.get('html_url')} 手动删掉这个附件再重跑。")
        return asset
    raise SyncError(
        f"上传接口没报错，但回读 {release.get('html_url')} 里找不到附件 {name}——"
        f"视为同步未完成，别把这条发布当作已镜像。")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", required=True, help="Gitee 上要存在（或新建）的发行版 tag")
    parser.add_argument("--file", required=True, help="待上传的制品路径")
    parser.add_argument("--repo", default=DEFAULT_GITEE_REPO, help="Gitee owner/name")
    parser.add_argument("--name", default=None, help="附件名，默认取文件名")
    parser.add_argument("--github-repo", default=DEFAULT_GITHUB_REPO, help="正文里回链的 GitHub owner/name")
    parser.add_argument("--token-env", default="GITEE_TOKEN", help="存放 Gitee 私人令牌的环境变量名")
    parser.add_argument("--dry-run", action="store_true", help="只读校验现状，不写任何东西")
    args = parser.parse_args(argv)
    if "/" not in args.repo or "/" in (args.name or ""):
        raise SystemExit("repo 需要 owner/name；--name 不能带路径分隔符")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    owner, repo = args.repo.split("/", 1)
    name = args.name or os.path.basename(args.file)

    if not os.path.isfile(args.file):
        print(f"MISMATCH: 找不到制品 {args.file}", file=sys.stderr)
        return 1
    size = os.path.getsize(args.file)
    if size > 100 * 1048576:
        print(f"MISMATCH: {name} 有 {size / 1048576:.1f} MB，超过 Gitee 单附件 100 MB 上限", file=sys.stderr)
        return 1

    token = None
    if not args.dry_run:
        token = os.environ.get(args.token_env, "").strip()
        if not token:
            print(f"MISMATCH: 环境变量 {args.token_env} 里没有 Gitee 私人令牌", file=sys.stderr)
            return 1

    source_url = f"https://github.com/{args.github_repo}/releases/tag/{args.tag}"
    body_text = f"由 GitHub Actions 从 {source_url} 同步的镜像发布，供国内下载。"

    release = find_release(owner, repo, args.tag, token)
    if release is None:
        print(f"Gitee 上 tag {args.tag} 还没有发行版" + ("（--dry-run：到此为止）" if args.dry_run else ""))
        if args.dry_run:
            return 0
        release = ensure_release(owner, repo, args.tag, token, body_text)
    else:
        print(f"Gitee 发行版: id={release.get('id')} {release.get('html_url')}")

    already = [a for a in release_assets(release) if a.get("name") == name]
    if already:
        asset = verify(owner, repo, release["id"], args.tag, name, size, token)
        print(f"附件已存在且尺寸一致，跳过上传: {asset_url(asset)}")
        return 0

    if args.dry_run:
        print(f"--dry-run：准备上传 {name} ({size / 1048576:.1f} MB) 到发行版 {release['id']}")
        return 0

    upload_asset(owner, repo, release["id"], args.file, name, token)
    asset = verify(owner, repo, release["id"], args.tag, name, size, token)
    print(f"镜像完成: {asset_url(asset)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        raise SystemExit(1)
