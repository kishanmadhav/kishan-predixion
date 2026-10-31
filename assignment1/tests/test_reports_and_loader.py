from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ledger import collection_efficiency, load_loans_csv, post_payment

IST = timezone(timedelta(hours=5, minutes=30))


def test_collection_efficiency_basic(conn):
    # EMI due in Sep 2026: L1 5,000 + L2 2,500 = 7,500
    post_payment(conn, "L1", Decimal("3000"), "T1", paid_at=datetime(2026, 9, 10, 12, tzinfo=IST))
    post_payment(conn, "L2", Decimal("1500"), "T2", paid_at=datetime(2026, 9, 21, 12, tzinfo=IST))
    assert collection_efficiency(conn, 2026, 9) == pytest.approx(4500 / 7500)


def test_collection_efficiency_uses_ist_month_boundaries(conn):
    # 1 Oct 00:30 IST is still 30 Sep in UTC -> belongs to October, not September.
    post_payment(conn, "L1", Decimal("1000"), "T-EDGE", paid_at=datetime(2026, 10, 1, 0, 30, tzinfo=IST))
    # 30 Sep 23:59 IST belongs to September.
    post_payment(conn, "L1", Decimal("750"), "T-IN", paid_at=datetime(2026, 9, 30, 23, 59, tzinfo=IST))
    assert collection_efficiency(conn, 2026, 9) == pytest.approx(750 / 7500)


def test_collection_efficiency_excludes_overpaid_excess(conn):
    post_payment(conn, "L2", Decimal("4000"), "T-OVER", paid_at=datetime(2026, 9, 25, tzinfo=IST))
    assert collection_efficiency(conn, 2026, 9) == pytest.approx(2500 / 7500)


def test_collection_efficiency_no_dues_raises(conn):
    with pytest.raises(ValueError, match="no EMI due"):
        collection_efficiency(conn, 2026, 3)


def test_collection_efficiency_bad_month(conn):
    with pytest.raises(ValueError):
        collection_efficiency(conn, 2026, 13)


def test_load_loans_csv_reports_rejections(conn, tmp_path):
    csv_path = tmp_path / "loans.csv"
    csv_path.write_text(
        "loan_id,borrower_id,emi_amount,due_date,outstanding_amount\n"
        "L10,B10,1500.00,2026-09-05,30000.00\n"     # line 2 ok
        "L11,B11,abc,2026-09-05,30000\n"            # line 3 bad emi
        "L12,B12,1500,2026-02-30,30000\n"           # line 4 impossible date
        "L13,B13,1500,2026-09-05,-1\n"              # line 5 negative outstanding
        "L10,B10,1500,2026-09-05,30000\n"           # line 6 dup in file
        "L1,B1,1500,2026-09-05,30000\n"             # line 7 already in DB
        ",B14,1500,2026-09-05,30000\n"              # line 8 missing id
        "L15,B15,0,2026-09-05,30000\n"              # line 9 zero emi
        "L16,B16,1500.555,2026-09-05,30000\n"       # line 10 sub-paise
        "L17,B17,999.99,2026-10-01,0\n",            # line 11 ok (fully paid loan)
        encoding="utf-8",
    )
    report = load_loans_csv(conn, csv_path)

    assert report.loaded == 2
    reasons = {r.line: r.reason for r in report.rejected}
    assert set(reasons) == {3, 4, 5, 6, 7, 8, 9, 10}
    assert "not a number" in reasons[3]
    assert "YYYY-MM-DD" in reasons[4]
    assert "negative" in reasons[5]
    assert "duplicate" in reasons[6]
    assert "database" in reasons[7]
    assert "loan_id" in reasons[8]
    assert "positive" in reasons[9]
    assert "decimal places" in reasons[10]
    assert conn.execute("SELECT emi_amount_paise FROM loans WHERE loan_id = 'L17'").fetchone() == (99999,)
    # pre-existing row untouched
    assert conn.execute("SELECT outstanding_paise FROM loans WHERE loan_id = 'L1'").fetchone() == (1000000,)


def test_load_loans_csv_missing_column(conn, tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("loan_id,borrower_id\nL1,B1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required columns"):
        load_loans_csv(conn, p)
