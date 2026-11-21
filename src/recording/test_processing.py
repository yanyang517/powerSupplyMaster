"""滚动窗口与抽稀的纯函数行为（不依赖 Qt）。"""
import pytest

from recording.processing import POINTS_PER_BUCKET, decimate_min_max, trim_to_window


class TestTrimToWindow:
    def test_keeps_the_newest_items(self):
        assert trim_to_window([1, 2, 3, 4, 5], 3) == [3, 4, 5]

    def test_short_sequence_passes_through(self):
        assert trim_to_window([1, 2], 10) == [1, 2]

    def test_accepts_any_sequence(self):
        assert trim_to_window((p for p in range(5)), 2) == [3, 4]

    def test_rejects_non_positive_window(self):
        with pytest.raises(ValueError):
            trim_to_window([1], 0)


class TestDecimateMinMax:
    def test_short_sequence_is_returned_untouched(self):
        samples = [(0, 1.0), (1, 2.0), (2, 3.0)]
        assert decimate_min_max(samples, 100) == samples

    def test_output_never_exceeds_two_points_per_bucket(self):
        samples = [(i, float(i % 7)) for i in range(10000)]
        assert len(decimate_min_max(samples, 300)) <= 300 * POINTS_PER_BUCKET

    def test_single_sample_spike_survives(self):
        """尖峰只持续一个采样：等间隔跳点会把它整段抽掉，包络法不会。"""
        samples = [(i, 12.0) for i in range(10000)]
        samples[5000] = (5000, 99.0)
        samples[6000] = (6000, 1.0)

        result = decimate_min_max(samples, 200)

        assert 99.0 in [y for _x, y in result]
        assert 1.0 in [y for _x, y in result]

    def test_envelope_brackets_every_bucket(self):
        samples = [(i, float(i % 50)) for i in range(2000)]
        result = decimate_min_max(samples, 40)

        # 抽稀后的极值必须与原始数据的极值一致。
        assert max(y for _x, y in result) == max(y for _x, y in samples)
        assert min(y for _x, y in result) == min(y for _x, y in samples)

    def test_output_stays_in_time_order(self):
        samples = [(i, float((i * 37) % 100)) for i in range(3000)]
        result = decimate_min_max(samples, 50)

        assert [x for x, _y in result] == sorted(x for x, _y in result)

    def test_rejects_non_positive_buckets(self):
        with pytest.raises(ValueError):
            decimate_min_max([(0, 1.0)], 0)
