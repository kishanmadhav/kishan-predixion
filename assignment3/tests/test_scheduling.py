import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.scheduling import IST, schedule_retry  # noqa: E402


def ist(h, m, day=15):
    return datetime(2026, 9, day, h, m, tzinfo=IST)


@pytest.mark.parametrize("now, attempt, expected", [
    # --- the three times the brief asks for ---
    (ist(7, 30), 0, ist(8, 0)),          # 07:30 + 30m = 08:00, exactly at window start: allowed
    (ist(7, 30), 1, ist(9, 30)),         # 07:30 + 120m = 09:30, inside window
    (ist(18, 45), 0, ist(8, 0, day=16)), # 18:45 + 30m = 19:15 -> next day 08:00
    (ist(23, 0), 0, ist(8, 0, day=16)),  # 23:00 + 30m = 23:30 -> next day 08:00
    (ist(23, 0), 2, ist(8, 0, day=16)),  # 23:00 + 240m = 03:00 next day -> 08:00 that same day, not day+2
    # --- boundaries ---
    (ist(7, 0), 0, ist(8, 0)),           # 07:30 is before window -> 08:00 same day
    (ist(18, 29), 0, ist(18, 59)),       # last allowed minute
    (ist(18, 30), 0, ist(8, 0, day=16)), # 19:00 is outside (window end is exclusive)
    (ist(10, 0), 2, ist(14, 0)),         # third retry gap is 240m
])
def test_schedule_retry_ist_window(now, attempt, expected):
    result = schedule_retry(attempt, now)
    assert result == expected
    assert result.utcoffset() == expected.utcoffset()      # returned in IST


def test_utc_input_is_converted_to_ist():
    # 13:15 UTC is 18:45 IST; a server in UTC would wrongly think 13:45 is fine.
    assert schedule_retry(0, datetime(2026, 9, 15, 13, 15, tzinfo=timezone.utc)) == ist(8, 0, day=16)


def test_month_end_rollover():
    assert schedule_retry(0, datetime(2026, 9, 30, 21, 0, tzinfo=IST)) == datetime(2026, 10, 1, 8, 0, tzinfo=IST)


@pytest.mark.parametrize("attempt", [3, 4, 10])
def test_retries_exhausted(attempt):
    assert schedule_retry(attempt, ist(10, 0)) is None


def test_rejects_naive_datetime():
    with pytest.raises(ValueError):
        schedule_retry(0, datetime(2026, 9, 15, 10, 0))


def test_rejects_negative_attempt():
    with pytest.raises(ValueError):
        schedule_retry(-1, ist(10, 0))


def test_no_shared_state_between_calls():
    """The original used a mutable default list; repeated calls must be independent."""
    assert [schedule_retry(0, ist(10, 0)) for _ in range(3)] == [ist(10, 30)] * 3
