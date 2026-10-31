# Assignment 1: Collections Ledger (Part B)

## Run
```
python -m pip install -r requirements.txt
python -m pytest -q
```

## Design
- **Money is integer paise.** `to_paise()` accepts `Decimal`, `int` or numeric `str`. It rejects `float`, `bool`, NaN/Infinity, and anything with more than 2 decimal places instead of rounding it. Rupees come back as `Decimal` through `from_paise()`.
- **Transaction boundary.** The connection runs with `isolation_level=None`, so the driver never opens transactions implicitly. `post_payment` opens its own `BEGIN IMMEDIATE ... COMMIT`, which takes SQLite's write lock *before* the duplicate check. The check, the insert and the outstanding update are therefore serialized against every other writer. Any exception rolls back. If the caller already has a transaction open, the function raises instead of silently nesting.
- **Idempotency.** `payments.gateway_txn_id` is `UNIQUE`. The in-transaction lookup returns `DUPLICATE`. If the same txn id comes back with a *different* loan or amount, it raises `IdempotencyConflictError`, because returning `DUPLICATE` there would hide a gateway bug.
- **Overpayment.** Each payment row stores `amount`, `applied` and `excess`, and a CHECK constraint enforces `excess = amount - applied`. Outstanding never goes below 0 (also a CHECK). Paying exactly the outstanding amount is `POSTED`, not `OVERPAID`.
- **Constraints.** `STRICT` tables (no type affinity surprises), positive amounts, a strict `YYYY-MM-DD` date check (`date(x) IS x`), and foreign keys enabled.
- **Collection efficiency.** Sums `applied_paise` (cash applied to dues; refundable excess is excluded) for payments in the **IST** calendar month. Payments are stored in UTC, so the month bounds are converted. The denominator is the sum of `emi_amount` for loans with `due_date` in that month. If nothing is due, it raises `ValueError` rather than returning a misleading 0 or inf.
- **CSV loader.** Validates each row and collects `Rejection(line, reason, row)`. Valid rows are inserted in one transaction. A DB-level `IntegrityError` (e.g. the loan already exists) rejects only that row. A missing header column fails the whole file.

## Assumptions
- The brief's `loans` schema has one `due_date` and one `emi_amount` per row, so each row is treated as one instalment due on that date. A real system needs an EMI schedule table (see below).
- "Amount collected" = applied amount, not gross receipts. If finance wants gross, change `applied_paise` to `amount_paise` in one query.
- `paid_at` defaults to now (UTC). Callers can pass the gateway's timestamp, which must be timezone-aware.

## Tests (33)
Happy path, string amounts, exact payoff, duplicate, conflicting duplicate, overpayment, a payment on an already-paid loan, non-positive and malformed amounts, unknown loan, missing txn id, naive datetime, a rollback when the UPDATE fails after the INSERT (forced with a trigger), and two concurrency tests:
- 8 threads with the same txn behind a `threading.Barrier` → exactly 1 `POSTED`, 7 `DUPLICATE`, 1 row, outstanding reduced once.
- 8 threads with distinct txns → all 8 applied (no lost updates).

**Mutation check:** replacing `BEGIN IMMEDIATE` with a deferred `BEGIN` makes both concurrency tests fail, so they really guard the locking.

## Trade-offs
- SQLite serializes all writers. That is fine here. On PostgreSQL I'd use `INSERT ... ON CONFLICT (gateway_txn_id) DO NOTHING RETURNING` plus `UPDATE loans ... WHERE loan_id = $1` (row lock) in one transaction, so writers to different loans don't block each other.
- No ORM, on purpose. The SQL is short, and the brief values explicit transaction boundaries.

## With another day
- An EMI schedule table (`loan_id, instalment_no, due_date, emi_amount`) so efficiency and DPD are per-instalment.
- Store the gateway payload hash and the received-at time, and add a refund workflow for `excess_paise`.
- Property-based tests (Hypothesis) checking that `sum(applied) + outstanding == original outstanding` for any sequence of payments.
