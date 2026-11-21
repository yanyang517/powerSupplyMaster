"""记录配置的读盘底线：任何不确定的内容都回落成"不记录"。

对应 specs/recording/data-capture 的"记录默认关闭且使能状态持久化"。这里刻意不抛
异常：启动路径上一次配置读取失败不该让应用起不来，但也绝不能因此开始写盘。
"""
import json

from recording import settings as st


def write(path, document):
    path.write_text(json.dumps(document) if not isinstance(document, str) else document,
                    encoding="utf-8")
    return path


class TestLoadDefaults:
    def test_missing_file_keeps_recording_off(self, tmp_path):
        loaded = st.load_settings(tmp_path / "absent.json")

        assert loaded == st.RecordSettings(enabled=False)

    def test_broken_json_keeps_recording_off(self, tmp_path):
        path = write(tmp_path / "broken.json", "{oops")

        assert st.load_settings(path).enabled is False

    def test_unsupported_version_keeps_recording_off(self, tmp_path):
        path = write(tmp_path / "v2.json", {"version": 999, "enabled": True})

        assert st.load_settings(path).enabled is False

    def test_non_object_document_keeps_recording_off(self, tmp_path):
        path = write(tmp_path / "array.json", [1, 2, 3])

        assert st.load_settings(path).enabled is False

    def test_missing_fields_fall_back_one_by_one(self, tmp_path):
        path = write(tmp_path / "partial.json", {"version": st.SCHEMA_VERSION, "enabled": True})
        loaded = st.load_settings(path)

        assert loaded.enabled is True
        assert loaded.dir == st.RECORDS_DIR_NAME

    def test_a_stale_interval_knob_is_ignored_not_half_applied(self, tmp_path):
        """采样周期在代码里，配置里那份旧键改了没反应——读到就当作不存在。"""
        path = write(tmp_path / "old.json",
                     {"version": st.SCHEMA_VERSION, "enabled": True, "interval_ms": 250})

        loaded = st.load_settings(path)

        assert loaded == st.RecordSettings(enabled=True, dir=st.RECORDS_DIR_NAME)
        assert not hasattr(loaded, "interval_ms")

    def test_non_bool_enabled_is_not_a_truthy_accident(self, tmp_path):
        path = write(tmp_path / "sneaky.json",
                     {"version": st.SCHEMA_VERSION, "enabled": "yes please"})

        assert st.load_settings(path).enabled is False


class TestSaveRoundTrip:
    def test_enabled_state_survives_a_restart(self, tmp_path):
        path = tmp_path / "config" / "record_settings.json"

        assert st.save_settings(st.RecordSettings(enabled=True), path) is True
        assert st.load_settings(path).enabled is True

    def test_save_leaves_no_temporary_file_behind(self, tmp_path):
        path = tmp_path / "config" / "record_settings.json"
        st.save_settings(st.RecordSettings(enabled=True), path)

        assert list(path.parent.glob("*.tmp")) == []

    def test_unwritable_target_reports_failure_instead_of_raising(self, tmp_path):
        path = tmp_path / "config" / "record_settings.json"
        path.mkdir(parents=True)  # 目录占据目标路径，写入必然失败

        assert st.save_settings(st.RecordSettings(enabled=True), path) is False

    def test_document_carries_the_schema_version(self, tmp_path):
        path = tmp_path / "record_settings.json"
        st.save_settings(st.RecordSettings(enabled=True, dir="samples"), path)

        assert json.loads(path.read_text(encoding="utf-8"))["version"] == st.SCHEMA_VERSION


class TestRecordsDir:
    def test_relative_dir_resolves_against_the_given_base(self, tmp_path):
        resolved = st.records_dir_for(st.RecordSettings(dir="records"), base_dir=tmp_path)

        assert resolved == tmp_path / "records"

    def test_absolute_dir_is_used_as_is(self, tmp_path):
        target = tmp_path / "elsewhere" / "samples"

        assert st.records_dir_for(st.RecordSettings(dir=str(target))) == target
