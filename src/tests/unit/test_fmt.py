import pytest

from src.tui.fmt import fmt_clock, fmt_duration


@pytest.mark.parametrize("secs,expected", [(0, "0:00"), (5, "0:05"), (65, "1:05"), (3599, "59:59"), (3600, "1:00:00"),
                                           (3725.9, "1:02:05")])
def test_clock(secs, expected):
    assert fmt_clock(secs) == expected


@pytest.mark.parametrize("secs,expected", [(None, ""), (0, ""), (65, "1:05"), (3725, "1:02:05")])
def test_duration_is_empty_when_unknown(secs, expected):
    assert fmt_duration(secs) == expected
