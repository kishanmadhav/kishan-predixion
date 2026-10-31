"""Load loans from CSV, rejecting bad rows with a reason instead of failing the file."""
import csv
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from .money import InvalidAmountError, to_paise
from .payments import immediate_transaction

REQUIRED_COLUMNS = ("loan_id", "borrower_id", "emi_amount", "due_date", "outstanding_amount")


@dataclass
class Rejection:
    line: int            # 1-based line number in the file (header is line 1)
    reason: str
    row: dict


@dataclass
class LoadReport:
    loaded: int = 0
    rejected: list[Rejection] = field(default_factory=list)


def _parse_row(row: dict) -> tuple:
    loan_id = (row.get("loan_id") or "").strip()
    borrower_id = (row.get("borrower_id") or "").strip()
    if not loan_id:
        raise ValueError("missing loan_id")
    if not borrower_id:
        raise ValueError("missing borrower_id")
    try:
        emi = to_paise(row.get("emi_amount") or "")
        outstanding = to_paise(row.get("outstanding_amount") or "")
    except InvalidAmountError as e:
        raise ValueError(str(e)) from None
    if emi <= 0:
        raise ValueError("emi_amount must be positive")
    if outstanding < 0:
        raise ValueError("outstanding_amount must not be negative")
    raw_date = (row.get("due_date") or "").strip()
    try:
        due = date.fromisoformat(raw_date)
    except ValueError:
        raise ValueError(f"due_date is not YYYY-MM-DD: {raw_date!r}") from None
    if due.isoformat() != raw_date:
        raise ValueError(f"due_date is not YYYY-MM-DD: {raw_date!r}")
    return loan_id, borrower_id, emi, raw_date, outstanding


def load_loans_csv(conn: sqlite3.Connection, path) -> LoadReport:
    report = LoadReport()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV is missing required columns: {missing}")

        seen: set[str] = set()
        with immediate_transaction(conn):
            for row in reader:
                line = reader.line_num
                try:
                    values = _parse_row(row)
                except ValueError as e:
                    report.rejected.append(Rejection(line, str(e), row))
                    continue
                if values[0] in seen:
                    report.rejected.append(Rejection(line, f"duplicate loan_id {values[0]} in file", row))
                    continue
                seen.add(values[0])
                try:
                    conn.execute(
                        "INSERT INTO loans (loan_id, borrower_id, emi_amount_paise, due_date, outstanding_paise)"
                        " VALUES (?, ?, ?, ?, ?)",
                        values,
                    )
                except sqlite3.IntegrityError as e:
                    # SQLite rolls back only the failed statement; the rest of the batch survives.
                    report.rejected.append(Rejection(line, f"rejected by database: {e}", row))
                    continue
                report.loaded += 1
    return report
