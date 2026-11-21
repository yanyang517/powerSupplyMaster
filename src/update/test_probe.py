"""探测模块测试：多源并发、优先级、坏源与全失败（任务 5.3）。

运行方式（在仓库根目录）：python -m pytest src/update/test_probe.py
用本地 http.server 假源，不依赖外网。
"""
from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from update import probe
from update.manifest import ManifestError
from update.settings import Source

MANIFEST = {
    "schema_version": 1,
    "version": "1.2.0",
    "channel": "stable",
    "date": "2026-01-02",
    "release_urls": {"gitee": "https://gitee.com/x/y/releases", "github": "https://github.com/x/y/releases"},
}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("fake-remote")
    (root / "latest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (root / "broken.json").write_text("{not json", encoding="utf-8")

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base
    httpd.shutdown()
    thread.join(timeout=5)


def good(name: str, server: str) -> Source:
    return Source(name, f"{server}/latest.json")


def broken(name: str, server: str) -> Source:
    return Source(name, f"{server}/broken.json")


def missing(name: str, server: str) -> Source:
    return Source(name, f"{server}/absent.json")


class TestFetchText:
    def test_plain_200_returns_body(self, server):
        assert "1.2.0" in probe.fetch_text(f"{server}/latest.json", 5.0)

    def test_http_404_raises_probe_error(self, server):
        with pytest.raises(probe.ProbeError):
            probe.fetch_text(f"{server}/absent.json", 5.0)

    def test_unreachable_host_raises_probe_error(self):
        with pytest.raises(probe.ProbeError):
            probe.fetch_text("http://127.0.0.1:1/latest.json", 0.5)


class TestProbeSource:
    def test_parses_into_latest_info(self, server):
        info = probe.probe_source(good("gitee", server))
        assert info.version == MANIFEST["version"]
        assert info.source == "gitee"

    def test_bad_json_is_a_manifest_error(self, server):
        with pytest.raises(ManifestError):
            probe.probe_source(broken("gitee", server))


class TestFetchLatest:
    def test_backup_source_used_when_first_is_broken(self, server):
        info = probe.fetch_latest([broken("gitee", server), good("github", server)])
        assert info is not None and info.source == "github"

    def test_priority_wins_when_both_are_good(self, server):
        other = Source("github", f"{server}/latest.json")
        info = probe.fetch_latest([good("gitee", server), other])
        assert info.source == "gitee"

    def test_all_sources_failing_returns_none_without_raising(self, server):
        assert probe.fetch_latest([broken("gitee", server), missing("github", server)]) is None

    def test_empty_source_list_returns_none(self):
        assert probe.fetch_latest([]) is None

    def test_404_does_not_look_like_a_new_version(self, server):
        assert probe.fetch_latest([missing("gitee", server)]) is None
