"""Posting payments: atomic and idempotent on gateway_txn_id."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .money import InvalidAmountError, to_paise

POSTED = "POSTED"
DUPLICATE = "DUPLICATE"
OVERPAID = "OVERPAID"


class LoanNotFoundError(LookupError):
    pass


class IdempotencyConflictError(ValueError):
    """Same gateway_txn_id was already posted with a different loan or amount."""


def to_utc_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("paid_at must be timezone-aware")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@contextmanager
def immediate_transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE takes the write lock up front, so check-then-write
    sequences inside cannot interleave with another writer."""
    if conn.in_transaction:
        raise RuntimeError("caller already has an open transaction; this function owns its own")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def post_payment(conn: sqlite3.Connection, loan_id: str, amount, gateway_txn_id: str,
                 *, paid_at: datetime | None = None) -> str:
    amount_paise = to_paise(amount)
    if amount_paise <= 0:
        raise InvalidAmountError(f"amount must be positive, got {amount!r}")
    if not isinstance(gateway_txn_id, str) or not gateway_txn_id.strip():
        raise ValueError("gateway_txn_id is required")
    paid_at_text = to_utc_text(paid_at or datetime.now(timezone.utc))

    with immediate_transaction(conn):
        existing = conn.execute(
            "SELECT loan_id, amount_paise FROM payments WHERE gateway_txn_id = ?",
            (gateway_txn_id,),
        ).fetchone()
        if existing is not None:
            if existing != (loan_id, amount_paise):
                raise IdempotencyConflictError(
                    f"txn {gateway_txn_id} already posted as {existing}, got {(loan_id, amount_paise)}")
            return DUPLICATE

        row = conn.execute("SELECT outstanding_paise FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
        if row is None:
            raise LoanNotFoundError(f"unknown loan_id {loan_id!r}")
        outstanding = row[0]

        applied = min(amount_paise, outstanding)
        excess = amount_paise - applied
        status = OVERPAID if excess > 0 else POSTED
        conn.execute(
            "INSERT INTO payments (loan_id, gateway_txn_id, amount_paise, applied_paise, excess_paise, status, paid_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (loan_id, gateway_txn_id, amount_paise, applied, excess, status, paid_at_text),
        )
        conn.execute(
            "UPDATE loans SET outstanding_paise = outstanding_paise - ? WHERE loan_id = ?",
            (applied, loan_id),
        )
    return status
