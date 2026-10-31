"""Connection and schema."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS loans (
    loan_id           TEXT PRIMARY KEY CHECK (length(trim(loan_id)) > 0),
    borrower_id       TEXT NOT NULL CHECK (length(trim(borrower_id)) > 0),
    emi_amount_paise  INTEGER NOT NULL CHECK (emi_amount_paise > 0),
    due_date          TEXT NOT NULL CHECK (date(due_date) IS due_date),   -- strict YYYY-MM-DD
    outstanding_paise INTEGER NOT NULL CHECK (outstanding_paise >= 0)
) STRICT;

CREATE TABLE IF NOT EXISTS payments (
    payment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id        TEXT NOT NULL REFERENCES loans(loan_id),
    gateway_txn_id TEXT NOT NULL UNIQUE CHECK (length(trim(gateway_txn_id)) > 0),
    amount_paise   INTEGER NOT NULL CHECK (amount_paise > 0),
    applied_paise  INTEGER NOT NULL CHECK (applied_paise BETWEEN 0 AND amount_paise),
    excess_paise   INTEGER NOT NULL CHECK (excess_paise = amount_paise - applied_paise),
    status         TEXT NOT NULL CHECK (status IN ('POSTED', 'OVERPAID')),
    paid_at        TEXT NOT NULL                                           -- UTC, ISO-8601
) STRICT;

CREATE INDEX IF NOT EXISTS ix_payments_paid_at ON payments(paid_at);
CREATE INDEX IF NOT EXISTS ix_payments_loan ON payments(loan_id, paid_at);
CREATE INDEX IF NOT EXISTS ix_loans_due_date ON loans(due_date);
"""


def connect(path) -> sqlite3.Connection:
    """Open a connection configured for this package.

    isolation_level=None puts the driver in autocommit mode so that every
    transaction boundary is explicit (BEGIN IMMEDIATE ... COMMIT) in our code.
    timeout makes concurrent writers wait for the lock instead of failing.
    """
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=True)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    return conn
