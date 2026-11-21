"""判定链测试：五条短路与提示文案（任务 6.4）。

运行方式（在仓库根目录）：python -m pytest src/update/test_notice.py
"""
from __future__ import annotations

import pytest

from update import notice
from update.manifest import LatestInfo
from update.state import UpdateState

LOCAL = "1.4.0"
DAY = 24 * 3600.0


def remote(version="1.5.0", source="gitee", url="https://gitee.com/x/releases"):
    return LatestInfo(version=version, date="2026-11-21",
                      release_urls={"gitee": url}, channel="stable", source=source)


class TestShouldProbe:
    def test_due_by_default(self):
        assert notice.should_probe(UpdateState(), now=0.0, interval_seconds=DAY) == (True, "due")

    def test_never_checked_is_due(self):
        """没有 last_check 就不是"还在间隔内"，首启必须能探测。"""
        assert notice.should_probe(UpdateState(), now=1e9, interval_seconds=DAY)[0] is True

    def test_disabled_short_circuits(self):
        should, reason = notice.should_probe(
            UpdateState(), now=0.0, interval_seconds=DAY, enabled=False)
        assert (should, reason) == (False, "disabled")

    def test_headless_short_circuits(self):
        """--no-gui 通路只跑服务端，绝不该发网络请求。"""
        should, reason = notice.should_probe(
            UpdateState(), now=0.0, interval_seconds=DAY, gui=False)
        assert (should, reason) == (False, "headless")

    def test_dev_build_short_circuits(self):
        should, reason = notice.should_probe(
            UpdateState(), now=0.0, interval_seconds=DAY, is_dev=True)
        assert (should, reason) == (False, "dev-build")

    def test_within_interval_is_throttled(self):
        state = UpdateState(last_check=1000.0)
        should, reason = notice.should_probe(state, now=1000.0 + DAY - 1, interval_seconds=DAY)
        assert should is False
        assert reason.startswith("throttled")

    def test_after_interval_is_due_again(self):
        state = UpdateState(last_check=1000.0)
        assert notice.should_probe(state, now=1000.0 + DAY, interval_seconds=DAY)[0] is True

    def test_forced_check_ignores_throttle_and_dev_short_circuits(self):
        """关于页的"立即检查"要能在节流窗口内、在 dev 构建上照样发出去。"""
        # last_check=0 而 now=1：正常判定正被 24h 节流挡住
        state = UpdateState(last_check=0.0)
        assert notice.should_probe(state, now=1.0, interval_seconds=DAY)[0] is False
        assert notice.should_probe(state, now=1.0, interval_seconds=DAY, is_dev=True)[0] is False
        assert notice.should_probe(state, now=1.0, interval_seconds=DAY, forced=True)[0] is True
        assert notice.should_probe(state, now=1.0, interval_seconds=DAY,
                                   is_dev=True, forced=True)[0] is True

    def test_forced_still_respects_disabled_and_headless(self):
        """关掉就是关掉：手动入口不该成为绕过用户开关的后门。"""
        assert notice.should_probe(UpdateState(), now=0.0, interval_seconds=DAY,
                                   enabled=False, forced=True)[0] is False
        assert notice.should_probe(UpdateState(), now=0.0, interval_seconds=DAY,
                                   gui=False, forced=True)[0] is False


class TestBuildNotice:
    def test_newer_remote_yields_a_notice(self):
        item = notice.build_notice(remote(), local_version=LOCAL, state=UpdateState())
        assert item is not None
        assert "1.5.0" in item.text
        assert item.url == "https://gitee.com/x/releases"
        assert item.version == "1.5.0"

    def test_no_remote_means_silence(self):
        assert notice.build_notice(None, local_version=LOCAL, state=UpdateState()) is None

    @pytest.mark.parametrize("version", [LOCAL, "1.3.9"])
    def test_same_or_older_means_silence(self, version):
        assert notice.build_notice(remote(version=version), local_version=LOCAL,
                                   state=UpdateState()) is None

    def test_dismissed_version_is_silent(self):
        state = UpdateState(dismissed_version="1.5.0")
        assert notice.build_notice(remote(), local_version=LOCAL, state=state) is None

    def test_other_version_still_prompts(self):
        state = UpdateState(dismissed_version="1.5.0")
        item = notice.build_notice(remote(version="1.6.0"), local_version=LOCAL, state=state)
        assert item is not None and item.version == "1.6.0"


class TestOutcomeText:
    def test_failure_is_named_as_failure(self):
        """"检查失败"与"已是最新"必须能区分，否则排障时无从判断清单是否推到位。"""
        text = notice.outcome_text(None, None, local_version=LOCAL)
        assert "失败" in text

    def test_up_to_date_names_both_versions(self):
        assert "已是最新" in notice.outcome_text(remote(LOCAL), None, local_version=LOCAL)

    def test_equal_version_is_plain(self):
        text = notice.outcome_text(remote(LOCAL), None, local_version=LOCAL)
        assert text == f"已是最新（v{LOCAL}）"

    def test_notice_text_is_echoed_for_a_newer_release(self):
        item = notice.build_notice(remote(), local_version=LOCAL, state=UpdateState())
        assert notice.outcome_text(remote(), item, local_version=LOCAL) == item.text

    def test_dismissed_release_says_so(self):
        text = notice.outcome_text(remote(), None, local_version=LOCAL,
                                   state=UpdateState(dismissed_version="1.5.0"))
        assert "忽略" in text

    def test_local_ahead_of_manifest(self):
        text = notice.outcome_text(remote("1.3.0"), None, local_version=LOCAL)
        assert "更新" in text and "dev" in text

    def test_skipped_check_reports_the_reason(self):
        assert notice.outcome_text(None, None, local_version=LOCAL,
                                   probed=False, reason="dev-build") == "dev-build"
