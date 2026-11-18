import datetime
import time

import pytest

from src.tui.fmt import fmt_clock, fmt_day_group, fmt_duration


@pytest.mark.parametrize("secs,expected", [(0, "0:00"), (5, "0:05"), (65, "1:05"), (3599, "59:59"), (3600, "1:00:00"),
                                           (3725.9, "1:02:05")])
def test_clock(secs, expected):
    assert fmt_clock(secs) == expected


@pytest.mark.parametrize("secs,expected", [(None, ""), (0, ""), (65, "1:05"), (3725, "1:02:05")])
def test_duration_is_empty_when_unknown(secs, expected):
    assert fmt_duration(secs) == expected


def _noon(y, m, d):
    return time.mktime(datetime.datetime(y, m, d, 12).timetuple())


def test_day_group_labels():
    today = datetime.date(2026, 11, 17)
    assert fmt_day_group(_noon(2026, 11, 17), today) == "Today"
    assert fmt_day_group(_noon(2026, 11, 16), today) == "Yesterday"
    assert fmt_day_group(_noon(2026, 11, 9), today) == "Mon 9 Nov"
    assert fmt_day_group(_noon(2025, 12, 25), today) == "Thu 25 Dec 2025"
    assert fmt_day_group(None, today) == "Earlier"
