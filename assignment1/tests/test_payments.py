from datetime import datetime, timezone
from decimal import Decimal

import pytest
from conftest import outstanding, payment_count

from ledger import (DUPLICATE, OVERPAID, POSTED, IdempotencyConflictError,
                    InvalidAmountError, LoanNotFoundError, post_payment)


def test_happy_path_reduces_outstanding_and_records_payment(conn):
    assert post_payment(conn, "L1", Decimal("1234.56"), "TXN-1") == POSTED
    assert outstanding(conn, "L1") == 1000000 - 123456
    row = conn.execute(
        "SELECT loan_id, amount_paise, applied_paise, excess_paise, status FROM payments"
    ).fetchone()
    assert row == ("L1", 123456, 123456, 0, "POSTED")


def test_string_amount_is_accepted(conn):
    assert post_payment(conn, "L1", "100.10", "TXN-S") == POSTED
    assert outstanding(conn, "L1") == 1000000 - 10010


def test_exact_payoff_is_posted_not_overpaid(conn):
    assert post_payment(conn, "L2", Decimal("2500.00"), "TXN-EXACT") == POSTED
    assert outstanding(conn, "L2") == 0


def test_duplicate_txn_is_noop(conn):
    assert post_payment(conn, "L1", Decimal("100"), "TXN-D") == POSTED
    assert post_payment(conn, "L1", Decimal("100"), "TXN-D") == DUPLICATE
    assert outstanding(conn, "L1") == 1000000 - 10000
    assert payment_count(conn) == 1


def test_same_txn_id_with_different_amount_is_conflict(conn):
    post_payment(conn, "L1", Decimal("100"), "TXN-C")
    with pytest.raises(IdempotencyConflictError):
        post_payment(conn, "L1", Decimal("999"), "TXN-C")
    assert outstanding(conn, "L1") == 1000000 - 10000
    assert payment_count(conn) == 1


def test_overpayment_zeroes_outstanding_and_records_excess(conn):
    assert post_payment(conn, "L2", Decimal("3000.00"), "TXN-O") == OVERPAID
    assert outstanding(conn, "L2") == 0
    assert conn.execute("SELECT applied_paise, excess_paise, status FROM payments").fetchone() == (
        250000, 50000, "OVERPAID")


def test_payment_on_fully_paid_loan_is_all_excess(conn):
    post_payment(conn, "L2", Decimal("2500"), "TXN-A")
    assert post_payment(conn, "L2", Decimal("10"), "TXN-B") == OVERPAID
    assert outstanding(conn, "L2") == 0
    assert conn.execute(
        "SELECT applied_paise, excess_paise FROM payments WHERE gateway_txn_id = 'TXN-B'").fetchone() == (0, 1000)


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-5"), "-0.01", 0])
def test_non_positive_amount_rejected(conn, bad):
    with pytest.raises(InvalidAmountError):
        post_payment(conn, "L1", bad, "TXN-BAD")
    assert payment_count(conn) == 0
    assert outstanding(conn, "L1") == 1000000


@pytest.mark.parametrize("bad", [100.0, "abc", "1.234", Decimal("NaN"), Decimal("Infinity"), True, ""])
def test_malformed_amount_rejected(conn, bad):
    with pytest.raises(InvalidAmountError):
        post_payment(conn, "L1", bad, "TXN-BAD")
    assert payment_count(conn) == 0


def test_unknown_loan_rejected_and_nothing_written(conn):
    with pytest.raises(LoanNotFoundError):
        post_payment(conn, "NOPE", Decimal("100"), "TXN-U")
    assert payment_count(conn) == 0
    assert not conn.in_transaction


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_missing_txn_id_rejected(conn, bad):
    with pytest.raises(ValueError):
        post_payment(conn, "L1", Decimal("100"), bad)
    assert payment_count(conn) == 0


def test_naive_paid_at_rejected(conn):
    with pytest.raises(ValueError):
        post_payment(conn, "L1", Decimal("100"), "TXN-N", paid_at=datetime(2026, 9, 1, 10, 0))


def test_failure_mid_transaction_rolls_back_insert(conn):
    """If the UPDATE fails after the INSERT, the INSERT must not survive."""
    conn.execute(
        "CREATE TRIGGER boom BEFORE UPDATE ON loans BEGIN SELECT RAISE(ABORT, 'boom'); END")
    with pytest.raises(Exception, match="boom"):
        post_payment(conn, "L1", Decimal("100"), "TXN-RB", paid_at=datetime.now(timezone.utc))
    assert payment_count(conn) == 0
    assert outstanding(conn, "L1") == 1000000
    assert not conn.in_transaction
