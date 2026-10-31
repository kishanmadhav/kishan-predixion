"""Business rules are enforced in code; these tests need no LLM."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import BANNED  # noqa: E402
from backend import IST, Backend, RuleViolation  # noqa: E402

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=IST)     # Monday 10:00 IST


@pytest.fixture
def b():
    return Backend(now=NOW)


@pytest.fixture
def verified(b):
    assert b.verify_identity("A1001", "1988-04-12")["verified"]
    return b


# ---- identity ----
def test_no_account_details_before_verification(b):
    with pytest.raises(RuleViolation, match="not verified"):
        b.get_account("A1001")
    with pytest.raises(RuleViolation, match="not verified"):
        b.record_promise_to_pay("A1001", "3000", "2026-11-03")


def test_wrong_dob_and_unknown_account_look_identical(b):
    assert b.verify_identity("A1001", "1990-01-01") == {"verified": False, "attempts_left": 2}
    assert b.verify_identity("ZZZ", "1988-04-12") == {"verified": False, "attempts_left": 1}
    assert b.verified_account is None


def test_lockout_after_three_failures_even_with_correct_dob(b):
    for _ in range(3):
        b.verify_identity("A1001", "2000-01-01")
    with pytest.raises(RuleViolation, match="locked"):
        b.verify_identity("A1001", "1988-04-12")
    assert b.verified_account is None


def test_verified_caller_cannot_read_other_account(verified):
    with pytest.raises(RuleViolation, match="different account"):
        verified.get_account("A1003")


def test_get_account_after_verification(verified):
    assert verified.get_account("A1001") == {"account_id": "A1001", "status": "ACTIVE", "outstanding": "45000.00",
                                             "minimum_due": "3000.00", "dpd": 34}


# ---- promise to pay ----
def test_valid_ptp_recorded(verified):
    assert verified.record_promise_to_pay("A1001", "3,000", "2026-11-09")["recorded"]
    assert verified.ptps == [{"account_id": "A1001", "amount_paise": 300000, "pay_date": "2026-11-09"}]


@pytest.mark.parametrize("amount, pay_date, match", [
    ("2999.99", "2026-11-05", "minimum due"),
    ("45000.01", "2026-11-05", "exceed"),
    ("3000", "2026-11-10", "between"),      # today + 8
    ("3000", "2026-11-01", "between"),      # yesterday
    ("3000", "next friday", "YYYY-MM-DD"),
    ("three thousand", "2026-11-05", "not a number"),
    ("3000.555", "2026-11-05", "2 decimals"),
])
def test_invalid_ptp_rejected(verified, amount, pay_date, match):
    with pytest.raises(RuleViolation, match=match):
        verified.record_promise_to_pay("A1001", amount, pay_date)
    assert verified.ptps == []


def test_ptp_boundaries_inclusive(verified):
    assert verified.record_promise_to_pay("A1001", "45000", "2026-11-02")["recorded"]     # today, full outstanding


def test_ptp_on_fully_paid_account_rejected(b):
    b.verify_identity("A1002", "1992-11-03")
    with pytest.raises(RuleViolation, match="nothing is outstanding"):
        b.record_promise_to_pay("A1002", "100", "2026-11-03")


@pytest.mark.parametrize("reason", ["DISPUTE", "ALREADY_PAID", "HARDSHIP", "ABUSIVE"])
def test_no_collection_after_blocking_escalation(verified, reason):
    verified.escalate_to_human("A1001", reason, "borrower says ...")
    with pytest.raises(RuleViolation, match="escalated"):
        verified.record_promise_to_pay("A1001", "3000", "2026-11-03")


def test_only_one_ptp_per_call(verified):
    verified.record_promise_to_pay("A1001", "3000", "2026-11-03")
    with pytest.raises(RuleViolation, match="already recorded"):
        verified.record_promise_to_pay("A1001", "5000", "2026-11-04")


# ---- callbacks ----
@pytest.mark.parametrize("when", ["2026-11-02T22:00", "2026-11-03T07:59", "2026-11-03T19:00",
                                  "2026-11-02T16:30:00+00:00"])          # 22:00 IST expressed in UTC
def test_callback_outside_window_rejected(b, when):
    with pytest.raises(RuleViolation, match="08:00 and 19:00"):
        b.schedule_callback("A1001", when)
    assert b.callbacks == []


@pytest.mark.parametrize("when, match", [("2026-11-02T09:00", "future"), ("2026-11-20T10:00", "within"),
                                         ("tomorrow 10am", "ISO")])
def test_callback_other_rejections(b, when, match):
    with pytest.raises(RuleViolation, match=match):
        b.schedule_callback("A1001", when)


def test_callback_in_window_booked(b):
    assert b.schedule_callback("A1001", "2026-11-03T10:00") == {"scheduled": True, "when": "2026-11-03T10:00+05:30"}
    assert b.schedule_callback("A1001", "2026-11-02T18:59")["scheduled"]


# ---- escalation ----
def test_escalation_reason_validated(b):
    with pytest.raises(RuleViolation, match="reason must be"):
        b.escalate_to_human("A1001", "SETTLE_LOAN", "")
    assert b.escalate_to_human("A1001", "dispute", "says amount wrong")["reason"] == "DISPUTE"


def test_no_tool_can_settle_or_change_balance(verified):
    """Prompt-injection defence at the tool level: there is simply no write path to balances or status."""
    public = {n for n in dir(verified) if not n.startswith("_") and callable(getattr(verified, n))}
    assert public == {"verify_identity", "get_account", "record_promise_to_pay", "schedule_callback", "escalate_to_human"}


# ---- output guardrail ----
@pytest.mark.parametrize("text", ["We may take legal action.", "We will inform your employer.",
                                  "Police complaint can be filed", "I'll call your family", "FIR"])
def test_banned_phrases_detected(text):
    assert BANNED.search(text)


@pytest.mark.parametrize("text", ["Can you pay Rs 3000 by Friday?", "I can connect you to a colleague.",
                                  "Your account shows 34 days past due."])
def test_normal_replies_pass(text):
    assert not BANNED.search(text)
