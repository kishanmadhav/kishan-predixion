import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import init_db  # noqa: E402


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "ledger.db"


@pytest.fixture
def conn(db_path):
    c = init_db(db_path)
    c.execute(
        "INSERT INTO loans VALUES ('L1', 'B1', 500000, '2026-09-05', 1000000)"   # EMI 5,000.00, outstanding 10,000.00
    )
    c.execute(
        "INSERT INTO loans VALUES ('L2', 'B2', 250000, '2026-09-20', 250000)"    # EMI 2,500.00, outstanding 2,500.00
    )
    yield c
    c.close()


def outstanding(conn, loan_id):
    return conn.execute("SELECT outstanding_paise FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()[0]


def payment_count(conn):
    return conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
