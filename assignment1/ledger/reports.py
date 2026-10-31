"""Reporting queries."""
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from .payments import to_utc_text

IST = timezone(timedelta(hours=5, minutes=30))


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def collection_efficiency(conn: sqlite3.Connection, year: int, month: int) -> float:
    """Amount collected in the month / EMI due in the month.

    "Month" is the calendar month in IST (the business timezone); paid_at is
    stored in UTC so the bounds are converted. Collected counts only the part
    of each payment applied to dues, not overpaid excess that will be refunded.
    """
    start, end = _month_bounds(year, month)
    due = conn.execute(
        "SELECT COALESCE(SUM(emi_amount_paise), 0) FROM loans WHERE due_date >= ? AND due_date < ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()[0]
    if due == 0:
        raise ValueError(f"no EMI due in {year}-{month:02d}; efficiency is undefined")

    start_utc = to_utc_text(datetime.combine(start, datetime.min.time(), IST))
    end_utc = to_utc_text(datetime.combine(end, datetime.min.time(), IST))
    collected = conn.execute(
        "SELECT COALESCE(SUM(applied_paise), 0) FROM payments WHERE paid_at >= ? AND paid_at < ?",
        (start_utc, end_utc),
    ).fetchone()[0]
    return float(Decimal(collected) / Decimal(due))
