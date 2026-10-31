"""Retry scheduling. Pure function of (attempt, now) so it is trivially testable."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
RETRY_GAPS_MIN = (30, 120, 240)    # gap before retry 1, 2, 3; immutable
WINDOW_START = time(8, 0)          # calling allowed 08:00 <= t < 19:00 IST
WINDOW_END = time(19, 0)


def schedule_retry(attempt: int, now: datetime) -> datetime | None:
    """Next allowed call time in IST, or None when retries are exhausted.

    attempt: number of the attempt that just completed, 0-based
             (0 = first call, so the next is retry 1 after 30 min).
    now:     timezone-aware completion time; converted to IST, never server-local.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    if attempt >= len(RETRY_GAPS_MIN):
        return None

    candidate = now.astimezone(IST) + timedelta(minutes=RETRY_GAPS_MIN[attempt])
    if candidate.time() < WINDOW_START:
        # e.g. 03:00 -> 08:00 the same day (not the day after)
        return datetime.combine(candidate.date(), WINDOW_START, IST)
    if candidate.time() >= WINDOW_END:
        return datetime.combine(candidate.date() + timedelta(days=1), WINDOW_START, IST)
    return candidate
