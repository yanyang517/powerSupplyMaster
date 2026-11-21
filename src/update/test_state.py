"""更新状态文件测试：缺失/损坏退回空状态、正常往返、路径与冻结回落（任务 5.4）。

样本版本号用 1.2.0 等与本仓库当前真源无关的值，理由同 `src/update/test_compare.py`。

运行方式（在仓库根目录）：python -m pytest src/update/test_state.py
"""
from __future__ import annotations

import json
import sys
import time

import pytest

from update import state as state_module


@pytest.fixture
def target(tmp_path):
    return tmp_path / "config" / "update_state.json"


class TestPathRule:
    def test_source_layout_puts_state_in_repo_config(self):
        path = state_module.state_file_path(__file__)
        assert path.parts[-2:] == ("config", "update_state.json")
        # 同一个 config/ 目录：与客户端登记表并列，而不是另开一处状态目录
        assert (path.parent / "clients.json").is_file()

    def test_frozen_layout_puts_state_next_to_the_exe(self, tmp_path, monkeypatch):
        exe = tmp_path / "powerSupplyMaster.exe"
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(exe))
        path = state_module.state_file_path(__file__)
        assert path == exe.parent / "config" / "update_state.json"


class TestLoad:
    def test_missing_file_is_empty_state(self, target):
        assert state_module.load_state(target) == state_module.empty_state()

    @pytest.mark.parametrize("text", ["", "{oops", "[]", '"nope"', "42"])
    def test_corrupt_file_is_empty_state(self, target, text):
        target.parent.mkdir(parents=True)
        target.write_text(text, encoding="utf-8")
        assert state_module.load_state(target) == state_module.empty_state()

    def test_unsupported_schema_is_empty_state(self, target):
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
        assert state_module.load_state(target) == state_module.empty_state()

    def test_bad_timestamp_is_dropped_but_the_rest_survives(self, target):
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({
            "schema_version": 1,
            "last_check": "not-a-date",
            "dismissed_version": "1.2.0",
        }), encoding="utf-8")
        loaded = state_module.load_state(target)
        assert loaded.last_check is None
        assert loaded.dismissed_version == "1.2.0"

    @pytest.mark.parametrize("raw,expected", [
        ("v1.2.0", "1.2.0"),      # 手写带前缀 v 也要能对上清单版本号
        ("V1.2.0", "1.2.0"),
        ("1.2.0-rc1", None),      # 预发布后缀不是发布版本，忽略记录作废
        ("1.2", None),
        (7, None),
    ])
    def test_dismissed_version_is_normalised_or_dropped(self, target, raw, expected):
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"schema_version": 1, "dismissed_version": raw}),
                          encoding="utf-8")
        assert state_module.load_state(target).dismissed_version == expected

    def test_unreadable_path_is_empty_state(self, tmp_path):
        assert state_module.load_state(tmp_path / "absent" / "update_state.json") == \
            state_module.empty_state()


class TestRoundTrip:
    def test_values_survive_save_and_load(self, target):
        moment = time.time()
        saved = state_module.UpdateState(last_check=moment, dismissed_version="1.2.0")
        assert state_module.save_state(target, saved) is True
        loaded = state_module.load_state(target)
        assert loaded.dismissed_version == "1.2.0"
        assert abs(loaded.last_check - moment) <= 1.0

    def test_empty_state_round_trips_to_empty(self, target):
        assert state_module.save_state(target, state_module.empty_state()) is True
        assert state_module.load_state(target) == state_module.empty_state()

    def test_saved_document_is_readable_json(self, target):
        state_module.save_state(target, state_module.UpdateState(
            last_check=time.time(), dismissed_version="1.2.0"))
        document = json.loads(target.read_text(encoding="utf-8"))
        assert document["schema_version"] == 1
        assert document["last_check"].endswith("Z")

    def test_save_creates_the_directory(self, target):
        assert not target.parent.exists()
        assert state_module.save_state(target, state_module.empty_state()) is True
        assert target.is_file()

    def test_save_failure_returns_false_instead_of_raising(self, tmp_path):
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        assert state_module.save_state(blocker / "update_state.json",
                                       state_module.empty_state()) is False


class TestThrottleHelpers:
    def test_never_checked_reports_none(self):
        assert state_module.empty_state().seconds_since_last_check() is None

    def test_elapsed_seconds_is_wall_clock_since_check(self):
        now = time.time()
        saved = state_module.UpdateState(last_check=now - 3600)
        assert saved.seconds_since_last_check(now=now) == pytest.approx(3600.0)

    def test_clock_skew_never_yields_negative_wait(self):
        now = time.time()
        assert state_module.UpdateState(last_check=now + 500).seconds_since_last_check(now=now) == 0.0

    def test_only_the_same_version_counts_as_dismissed(self):
        saved = state_module.UpdateState(dismissed_version="1.2.0")
        assert saved.is_dismissed("1.2.0") is True
        assert saved.is_dismissed("1.3.0") is False
        assert saved.is_dismissed(None) is False
