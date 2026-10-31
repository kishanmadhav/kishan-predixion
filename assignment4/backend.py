"""In-memory collections backend. Every business rule lives here, in code, so it holds
no matter what the LLM says or is tricked into saying. Tools in agent.py are thin wrappers."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
CALL_WINDOW = (time(8, 0), time(19, 0))      # callbacks allowed 08:00 <= t < 19:00 IST
PTP_MAX_DAYS = 7
CALLBACK_MAX_DAYS = 14
MAX_DOB_ATTEMPTS = 3

# Escalating for any of these blocks payment collection on that account for the rest of the call.
BLOCKING_REASONS = {"DISPUTE", "ALREADY_PAID", "HARDSHIP", "ABUSIVE"}
ESCALATION_REASONS = BLOCKING_REASONS | {"WRONG_PERSON", "VERIFICATION_FAILED", "CUSTOMER_REQUEST", "OTHER"}


class RuleViolation(Exception):
    """A request the business rules refuse. The message is safe to show to the model."""


@dataclass
class Account:
    account_id: str
    name: str
    dob: date
    outstanding_paise: int
    min_due_paise: int
    dpd: int
    status: str            # ACTIVE | CLOSED


def seed_accounts() -> dict[str, Account]:
    return {
        "A1001": Account("A1001", "Ravi Kumar", date(1988, 4, 12), 45_000_00, 3_000_00, 34, "ACTIVE"),
        "A1002": Account("A1002", "Priya Sharma", date(1992, 11, 3), 0, 0, 0, "CLOSED"),
        "A1003": Account("A1003", "Arjun Mehta", date(1979, 1, 25), 12_500_00, 12_500_00, 95, "ACTIVE"),
    }


def rupees(paise: int) -> str:
    return f"{Decimal(paise) / 100:.2f}"


def parse_rupees(value: str) -> int:
    try:
        d = Decimal(str(value).replace(",", "").replace("₹", "").replace("Rs", "").strip())
    except InvalidOperation:
        raise RuleViolation(f"amount '{value}' is not a number") from None
    if not d.is_finite() or d * 100 != (d * 100).to_integral_value():
        raise RuleViolation(f"amount '{value}' must be rupees with at most 2 decimals")
    return int(d * 100)


@dataclass
class Backend:
    now: datetime                                    # timezone-aware; injected so tests and evals are deterministic
    accounts: dict[str, Account] = field(default_factory=seed_accounts)
    verified_account: str | None = None              # one caller, one verified account per conversation
    failed_dob_attempts: int = 0
    ptps: list[dict] = field(default_factory=list)
    callbacks: list[dict] = field(default_factory=list)
    escalations: list[dict] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)  # every tool call, its args and outcome

    def __post_init__(self):
        if self.now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        self.now = self.now.astimezone(IST)

    @property
    def today(self) -> date:
        return self.now.date()

    # ---------- helpers ----------
    def _require_verified(self, account_id: str) -> Account:
        if self.verified_account is None:
            raise RuleViolation("identity not verified; call verify_identity first")
        if account_id != self.verified_account:
            raise RuleViolation("caller is verified for a different account")
        return self.accounts[account_id]

    def _blocking_escalation(self, account_id: str) -> str | None:
        for e in self.escalations:
            if e["account_id"] == account_id and e["reason"] in BLOCKING_REASONS:
                return e["reason"]
        return None

    # ---------- tool implementations ----------
    def verify_identity(self, account_id: str, dob: str) -> dict:
        if self.failed_dob_attempts >= MAX_DOB_ATTEMPTS:
            raise RuleViolation("verification locked after too many failed attempts; escalate to a human")
        acc = self.accounts.get(account_id.strip().upper())
        try:
            given = date.fromisoformat(dob.strip())
        except ValueError:
            given = None
        if acc is None or given != acc.dob:
            self.failed_dob_attempts += 1
            left = MAX_DOB_ATTEMPTS - self.failed_dob_attempts
            # Same message for unknown account and wrong DOB: don't reveal which accounts exist.
            return {"verified": False, "attempts_left": left}
        self.verified_account = acc.account_id
        self.failed_dob_attempts = 0
        return {"verified": True, "account_id": acc.account_id, "first_name": acc.name.split()[0]}

    def get_account(self, account_id: str) -> dict:
        acc = self._require_verified(account_id)
        return {"account_id": acc.account_id, "status": acc.status, "outstanding": rupees(acc.outstanding_paise),
                "minimum_due": rupees(acc.min_due_paise), "dpd": acc.dpd}

    def record_promise_to_pay(self, account_id: str, amount: str, pay_date: str) -> dict:
        acc = self._require_verified(account_id)
        if (reason := self._blocking_escalation(account_id)) is not None:
            raise RuleViolation(f"account is escalated for {reason}; do not collect, a human will follow up")
        if acc.outstanding_paise <= 0:
            raise RuleViolation("nothing is outstanding on this account")
        amount_paise = parse_rupees(amount)
        try:
            when = date.fromisoformat(pay_date.strip())
        except ValueError:
            raise RuleViolation(f"pay_date '{pay_date}' must be YYYY-MM-DD") from None
        last = self.today + timedelta(days=PTP_MAX_DAYS)
        if not self.today <= when <= last:
            raise RuleViolation(f"pay_date must be between {self.today} and {last}")
        if amount_paise < acc.min_due_paise:
            raise RuleViolation(f"amount must be at least the minimum due of {rupees(acc.min_due_paise)}")
        if amount_paise > acc.outstanding_paise:
            raise RuleViolation(f"amount cannot exceed the outstanding {rupees(acc.outstanding_paise)}")
        if any(p["account_id"] == account_id for p in self.ptps):
            raise RuleViolation("a promise to pay is already recorded on this call")
        ptp = {"account_id": account_id, "amount_paise": amount_paise, "pay_date": when.isoformat()}
        self.ptps.append(ptp)
        return {"recorded": True, "amount": rupees(amount_paise), "pay_date": when.isoformat()}

    def schedule_callback(self, account_id: str, when: str) -> dict:
        if account_id not in self.accounts:
            raise RuleViolation("unknown account")
        try:
            t = datetime.fromisoformat(when.strip())
        except ValueError:
            raise RuleViolation(f"when '{when}' must be ISO format YYYY-MM-DDTHH:MM (IST)") from None
        t = t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)
        if t <= self.now:
            raise RuleViolation("callback time must be in the future")
        if t > self.now + timedelta(days=CALLBACK_MAX_DAYS):
            raise RuleViolation(f"callback must be within {CALLBACK_MAX_DAYS} days")
        if not CALL_WINDOW[0] <= t.time() < CALL_WINDOW[1]:
            raise RuleViolation("callbacks are only allowed between 08:00 and 19:00 IST; offer a time in that window")
        cb = {"account_id": account_id, "when": t.isoformat(timespec="minutes")}
        self.callbacks.append(cb)
        return {"scheduled": True, "when": cb["when"]}

    def escalate_to_human(self, account_id: str, reason: str, notes: str) -> dict:
        reason = reason.strip().upper()
        if reason not in ESCALATION_REASONS:
            raise RuleViolation(f"reason must be one of {sorted(ESCALATION_REASONS)}")
        notes = re.sub(r"\s+", " ", notes).strip()[:1000]
        self.escalations.append({"account_id": account_id, "reason": reason, "notes": notes})
        return {"escalated": True, "reason": reason}
