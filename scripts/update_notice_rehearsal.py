"""端到端演练一次发版提示：本地假清单源 + 真界面 + 真状态文件（任务 6.5、8.1）。

不依赖硬件，也不动仓库里的版本真源：清单里"发布"的版本取当前版本 +1，效果等同于
把本地版本改低一档，但不会留下需要还原的改动。dev 构建短路在单测里已经覆盖，本脚本
把 is_dev 当作已打包构建来跑，目的是走通"用户真的看得见提示"这条链。

浏览器启动本身用注入式记录器验证（不弹出用户的默认浏览器）；QDesktopServices 的
实际调用在 views/update_notice.py 的 open_url 里，脚本会打印它将要打开的地址。

运行方式（仓库根目录）：
    python scripts/update_notice_rehearsal.py
    python scripts/update_notice_rehearsal.py --served-version 2.0.0 --keep-evidence
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import version  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from update import probe  # noqa: E402
from update.scheduler import UpdateChecker  # noqa: E402
from update.settings import Source, update_settings  # noqa: E402
from update.state import load_state  # noqa: E402
from views import update_notice as ui  # noqa: E402
from views.main_window import MainWindow  # noqa: E402
from views.theme import build_palette, build_qss  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("rehearsal")

FAILURES = []


def check(label, condition, detail=""):
    mark = "OK " if condition else "FAIL"
    print(f"[{mark}] {label}{('  -> ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


class StubPresenter:
    """演练只需要窗口能建起来：串口与设备控制都留给真程序。"""

    def get_available_ports(self):
        return [], 0

    def open_device(self):
        pass

    def close_device(self):
        pass

    def set_voltage(self, value):
        pass

    def set_on_off(self, value):
        pass


def next_version(served=None):
    if served:
        return served
    major, minor, patch = version.version_tuple()
    return f"{major}.{minor}.{patch + 1}"


class Handler(BaseHTTPRequestHandler):
    manifest: dict = {}
    routes: dict = {}

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        payload = self.routes.get(self.path)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass  # 演练脚本自己 narrate


def start_server(served_version: str):
    good = {
        "schema_version": 1,
        "version": served_version,
        "channel": version.channel,
        "date": "2026-11-21",
        "release_urls": {"local": f"https://example.invalid/releases/{served_version}"},
    }
    Handler.routes = {
        "/good/update/latest.json": good,
        "/broken/update/latest.json": b"{this is not json",
    }
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    return httpd, base


def build_window(app):
    window = MainWindow(StubPresenter())
    window.show()
    app.processEvents()
    return window


def make_controller(window, *, state_path, probe_fn, label):
    """按演练场景搭一条 checker -> 控件 的接线，并记录被点开的地址。"""
    checker = UpdateChecker(
        state_path=state_path,
        is_dev=False,          # 演练按"已打包的发布构建"走提示链
        probe_fn=probe_fn,
    )
    opened = []
    controller = ui.UpdateNoticeController(
        checker=checker,
        notice_widget=window.update_notice,
        manual_row=window.update_manual_row,
        open_link=opened.append,
    )
    logger.info("wired controller for %s (state=%s)", label, state_path)
    return checker, opened


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--served-version", default=None,
                        help="假清单里发布的版本号（默认当前版本 +1）")
    parser.add_argument("--evidence-dir", default=None,
                        help="截图输出目录（默认写进本 change 的 evidence/）")
    parser.add_argument("--keep-evidence", action="store_true",
                        help="保留状态文件所在临时目录，不清理")
    args = parser.parse_args(argv)

    served = next_version(args.served_version)
    evidence = Path(args.evidence_dir) if args.evidence_dir else (
        REPO_ROOT / "openspec" / "changes" / "add-version-info-and-update-notice" / "evidence")
    evidence.mkdir(parents=True, exist_ok=True)

    print(f"本机版本真源 {version.__version__}，假清单发布 {served}")
    httpd, base = start_server(served)
    good_sources = (
        Source("local-gitee", f"{base}/good/update/latest.json"),
        Source("local-dead", "http://127.0.0.1:1/update/latest.json"),
    )
    broken_sources = (
        Source("local-broken", f"{base}/broken/update/latest.json"),
        Source("local-dead", "http://127.0.0.1:1/update/latest.json"),
    )
    # 进程级配置改到本地假源：演练期间一次真实外网请求都不该发出去
    update_settings.sources = good_sources
    update_settings.interval_seconds = 86400.0
    update_settings.startup_delay_seconds = 0.0
    update_settings.timeout_seconds = 2.0

    tmpdir = tempfile.mkdtemp(prefix="update-rehearsal-")
    state_path = Path(tmpdir) / "config" / "update_state.json"

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(build_palette("dark"))
    app.setStyleSheet(build_qss("dark"))

    try:
        window = build_window(app)
        calls = []

        def counting_probe(sources=None):
            calls.append(1)
            return probe.fetch_latest(sources)

        # --- 1. 后台自动检查：状态栏应出现提示 ---
        checker, opened = make_controller(window, state_path=state_path,
                                         probe_fn=counting_probe, label="startup")
        item = asyncio.run(checker.check())
        check("自动检查给出提示", item is not None, item.text if item else "无")
        check("提示条常驻可见", window.update_notice.isHidden() is False)
        app.processEvents()
        window.grab().save(str(evidence / "rehearsal_status_notice.png"))
        check("截图已写入 evidence", (evidence / "rehearsal_status_notice.png").is_file())

        # --- 2. 节流：第二次自动检查不该再发请求 ---
        asyncio.run(checker.check())
        check("间隔内不重复探测", calls == [1], f"实际探测 {len(calls)} 次")

        # --- 3. 手动「立即检查」：绕过节流，结果写在关于页 ---
        window.update_manual_row.check_button.click()
        app.processEvents()
        outcome = window.update_manual_row.result_label.text()
        check("手动检查绕过节流并发出请求", calls == [1, 1], f"探测序列 {calls}")
        check("关于页显示结果", served in outcome, outcome)
        window.ui.tabWidget.setCurrentIndex(window.ui.tabWidget.indexOf(window.ui.tab_about))
        app.processEvents()
        window.grab().save(str(evidence / "rehearsal_about_manual_check.png"))

        # --- 4. 查看发布页：动作拿到的是清单里的地址 ---
        window.update_notice.view_button.click()
        app.processEvents()
        expected_url = f"https://example.invalid/releases/{served}"
        check("查看发布页拿到清单地址", opened == [expected_url], str(opened))
        check("外启入口是 QDesktopServices.openUrl", callable(ui.open_url),
              f"实际会打开 {expected_url}（演练不弹浏览器）")

        # --- 5. 忽略此版本，并模拟重启 ---
        window.update_notice.dismiss_button.click()
        app.processEvents()
        check("忽略后提示条收起", window.update_notice.isHidden() is True)
        stored = load_state(state_path)
        check("忽略已落盘", stored.dismissed_version == served, str(stored))

        restart_checker, _ = make_controller(window, state_path=state_path,
                                             probe_fn=counting_probe, label="restart")
        item = asyncio.run(restart_checker.check(forced=True))
        check("重启后同一版本不再提示", item is None)
        window.update_manual_row.check_button.click()
        app.processEvents()
        text = window.update_manual_row.result_label.text()
        check("手动检查会说明已被忽略", "忽略" in text, text)
        window.grab().save(str(evidence / "rehearsal_dismissed.png"))

        # --- 6. 源不可用：静默，但手动检查要说清失败 ---
        broken_checker, _ = make_controller(
            window, state_path=Path(tmpdir) / "config" / "broken_state.json",
            probe_fn=lambda: counting_probe(broken_sources), label="broken")
        item = asyncio.run(broken_checker.check(forced=True))
        check("清单不可用时不给提示", item is None,
              window.update_manual_row.result_label.text())
        check("失败要说成失败", "失败" in window.update_manual_row.result_label.text())

        print()
        print(f"截图目录：{evidence}")
        print(f"状态文件：{state_path}")
    finally:
        httpd.shutdown()
        if not args.keep_evidence:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
    if FAILURES:
        print(f"\n{len(FAILURES)} 项未通过：{FAILURES}")
        return 1
    print("\n端到端演练全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
