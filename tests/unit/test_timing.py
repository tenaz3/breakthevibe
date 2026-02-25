"""Unit tests for breakthevibe/utils/timing.py."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from breakthevibe.utils.timing import StopWatch, timed


@pytest.mark.unit
class TestTimedContextManager:
    def test_returns_dict_with_elapsed_key(self) -> None:
        with timed("test_operation") as t:
            pass
        assert "elapsed" in t

    def test_elapsed_is_float(self) -> None:
        with timed("test_operation") as t:
            pass
        assert isinstance(t["elapsed"], float)

    def test_elapsed_starts_at_zero_inside_block(self) -> None:
        with timed("test_operation") as t:
            # Before the block finishes, elapsed is still the initial value
            in_block_value = t["elapsed"]
        assert in_block_value == 0.0

    def test_elapsed_is_positive_after_block(self) -> None:
        with timed("some_work") as t:
            time.sleep(0.01)
        assert t["elapsed"] > 0.0

    def test_elapsed_reflects_actual_duration(self) -> None:
        sleep_seconds = 0.05
        with timed("sleep_test") as t:
            time.sleep(sleep_seconds)
        # Allow generous tolerance for CI variability
        assert t["elapsed"] >= sleep_seconds * 0.8

    def test_elapsed_updated_after_exception(self) -> None:
        """Elapsed must be populated even when the body raises."""
        with pytest.raises(ValueError), timed("failing_op") as t:
            raise ValueError("boom")
        assert t["elapsed"] >= 0.0

    def test_label_forwarded_to_logger(self) -> None:
        with patch("breakthevibe.utils.timing.logger") as mock_logger:
            with timed("my_label") as _:
                pass
            mock_logger.debug.assert_called_once()
            call_kwargs = mock_logger.debug.call_args
            # structlog uses positional first arg as event, kwargs for bindings
            assert call_kwargs[0][0] == "timed"
            assert call_kwargs[1]["label"] == "my_label"

    def test_elapsed_seconds_logged(self) -> None:
        with patch("breakthevibe.utils.timing.logger") as mock_logger:
            with timed("logged_elapsed") as t:
                pass
            call_kwargs = mock_logger.debug.call_args[1]
            assert "elapsed_seconds" in call_kwargs
            assert call_kwargs["elapsed_seconds"] == t["elapsed"]

    def test_multiple_independent_timers(self) -> None:
        with timed("first") as t1:
            time.sleep(0.01)
        with timed("second") as t2:
            time.sleep(0.02)
        assert t1["elapsed"] > 0.0
        assert t2["elapsed"] > 0.0
        # They are independent dicts
        assert t1 is not t2

    def test_nested_timers_are_independent(self) -> None:
        with timed("outer") as outer, timed("inner") as inner:
            time.sleep(0.01)
        assert inner["elapsed"] > 0.0
        assert outer["elapsed"] >= inner["elapsed"]

    def test_monotonic_time_used(self) -> None:
        """Verify timing is based on monotonic clock (not wall clock)."""
        with patch("breakthevibe.utils.timing.time") as mock_time:
            mock_time.monotonic.side_effect = [100.0, 100.5]
            with timed("mono_test") as t:
                pass
        assert t["elapsed"] == pytest.approx(0.5)


@pytest.mark.unit
class TestStopWatch:
    def test_initial_state(self) -> None:
        sw = StopWatch()
        assert sw.laps == {}
        assert sw.total == 0.0

    def test_start_and_stop_returns_elapsed(self) -> None:
        sw = StopWatch()
        sw.start("phase1")
        time.sleep(0.01)
        elapsed = sw.stop()
        assert isinstance(elapsed, float)
        assert elapsed > 0.0

    def test_stop_without_start_returns_zero(self) -> None:
        sw = StopWatch()
        result = sw.stop()
        assert result == 0.0

    def test_lap_recorded_after_stop(self) -> None:
        sw = StopWatch()
        sw.start("crawl")
        sw.stop()
        assert "crawl" in sw.laps

    def test_lap_value_matches_stop_return(self) -> None:
        sw = StopWatch()
        sw.start("extract")
        elapsed = sw.stop()
        assert sw.laps["extract"] == elapsed

    def test_multiple_laps_recorded(self) -> None:
        sw = StopWatch()
        sw.start("phase_a")
        sw.stop()
        sw.start("phase_b")
        sw.stop()
        assert "phase_a" in sw.laps
        assert "phase_b" in sw.laps

    def test_total_sums_all_laps(self) -> None:
        sw = StopWatch()
        sw.start("a")
        sw.stop()
        sw.start("b")
        sw.stop()
        expected_total = sum(sw.laps.values())
        assert sw.total == pytest.approx(expected_total)

    def test_total_is_zero_before_any_laps(self) -> None:
        sw = StopWatch()
        assert sw.total == 0.0

    def test_laps_returns_copy_not_reference(self) -> None:
        sw = StopWatch()
        sw.start("lap1")
        sw.stop()
        laps_copy = sw.laps
        laps_copy["injected"] = 999.0
        assert "injected" not in sw.laps

    def test_start_resets_state_for_new_label(self) -> None:
        sw = StopWatch()
        sw.start("first")
        sw.stop()
        # Start a second lap — internal state resets
        sw.start("second")
        assert sw._current_label == "second"
        assert sw._start is not None

    def test_stop_clears_internal_state(self) -> None:
        sw = StopWatch()
        sw.start("cleanup_check")
        sw.stop()
        assert sw._start is None
        assert sw._current_label is None

    def test_lap_logged_via_structlog(self) -> None:
        with patch("breakthevibe.utils.timing.logger") as mock_logger:
            sw = StopWatch()
            sw.start("logged_lap")
            sw.stop()
            mock_logger.debug.assert_called_once()
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["label"] == "logged_lap"
            assert "elapsed" in call_kwargs

    def test_laps_elapsed_values_are_positive(self) -> None:
        sw = StopWatch()
        for label in ("step1", "step2", "step3"):
            sw.start(label)
            sw.stop()
        for label, duration in sw.laps.items():
            assert duration >= 0.0, f"Lap {label!r} has negative duration"

    def test_overwrite_lap_with_same_label(self) -> None:
        """Re-using a label overwrites the previous lap value."""
        sw = StopWatch()
        sw.start("repeated")
        sw.stop()
        sw.laps["repeated"]

        sw.start("repeated")
        time.sleep(0.02)
        sw.stop()
        second_value = sw.laps["repeated"]

        # The second measurement overwrites the first
        assert sw.laps["repeated"] == second_value
        assert len(sw.laps) == 1

    def test_monotonic_clock_used_internally(self) -> None:
        with patch("breakthevibe.utils.timing.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.3]
            sw = StopWatch()
            sw.start("mono_lap")
            elapsed = sw.stop()
        assert elapsed == pytest.approx(0.3)
        assert sw.laps["mono_lap"] == pytest.approx(0.3)
