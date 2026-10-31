# AI usage log

> **Kishan: review and edit before submitting.** This was drafted from the actual session. Add any prompts or tools you used yourself, and remove anything you didn't do.

**Tool used for all four Part Bs:** Claude Code (VS Code extension, model Claude Opus 5.5), working in this repo with shell access. It wrote code, ran the tests, and ran Docker and Terraform against my sandbox AWS account. I chose the scope, the AWS account and the deploy/no-deploy decisions. I reviewed the outputs; each assignment folder's NOTES.md records the trade-offs.

---

## Assignment 1: Collections Ledger
**Key prompts**
1. "Help me do Part B of the attached PDF assignment … all 4 in order."
2. (Implicit in the brief) money as paise/Decimal, atomic + idempotent `post_payment`, an 8-thread concurrency test.

**Accepted**
- Integer paise storage; floats rejected outright; more than 2 decimal places rejected rather than rounded.
- `isolation_level=None` + `BEGIN IMMEDIATE` so the duplicate check and the write are serialized; `UNIQUE(gateway_txn_id)` as a backstop.
- `IdempotencyConflictError` when the same txn id arrives with a different amount (my addition to the spec).

**Rejected / corrected**
- Checked the concurrency test by **mutation**: downgrading `BEGIN IMMEDIATE` to deferred `BEGIN` made both concurrency tests fail, which shows the test really guards the locking and isn't just passing by luck.
- Collection efficiency counts *applied* amounts, not gross receipts. This is a deliberate assumption, documented in NOTES.

## Assignment 2: Dialer Campaign Analytics
**Key prompts**
1. Generate the data with `gen_data.py` unmodified; produce the four deliverables.
2. Find anomalous segments systematically, not by eyeballing.

**Accepted**
- A Bonferroni-corrected scan of every state, batch and state×batch cell across three metrics. It flagged only BR×B7 (54% wrong-number rate vs 8%).
- Impact sizing with sensitivity tables instead of single numbers.

**Rejected / corrected**
- **The AI got a test expectation wrong:** it wrote z ≈ −1.93 / p ≈ 0.053 for the A/B test (880 vs 960 of 4,000). The test failed. Recomputing by hand gives z = −2.125, p = 0.034; the code was right and the expectation was wrong. Fixed the test with the hand working in a comment.
- The first notebook build forced the `Agg` matplotlib backend, so no charts were embedded. Caught by checking the notebook for image outputs, then fixed.
- The markdown originally called PTP|RPC in BR×B7 "normal" although it reads 30% on ~99 RPCs. Reworded to "not significantly different after correction".
- `gen_data.py`: only the PDF's line wraps were undone, with no logic change.

## Assignment 3: Fix and Ship
**Key prompts**
1. Make the corrected service deployable: app, Dockerfile, Terraform, GitHub Actions with OIDC, evidence.
2. "I want to use new AWS credentials, give me the commands." I configured the `predixion` profile myself; keys were never pasted into the AI chat.
3. Chose: deploy to account 435636068826 (`predixion` profile) and run a real `terraform apply`.

**Accepted**
- A transactional outbox for CRM notifications instead of synchronous retries: a CRM outage delays a notification but never loses it.
- `call_id` as the idempotency key (an assumption: the voice platform sends one).
- The secret is created without a version, and its value is set via the CLI so it never enters Terraform state.
- Deploy order: ECR + secret first, then push the image, then the full apply, so the first ECS deployment doesn't trip the circuit breaker.

**Rejected / corrected**
- Initially it planned an "offline plan" provider hack (dummy credentials). Dropped once real sandbox credentials existed.
- A scheduling test contained a tautological assertion that could never fail. Removed.
- `put-secret-value` failed the first time because the call didn't pass `--region` explicitly. Fixed.
- SQLite on Fargate is ephemeral and per-task. Kept for the exercise but flagged as a production gap in NOTES (RDS/SQS is the real design).

## Assignment 4: Collections Assistant Agent
**Key prompts**
1. Build the agent with LangChain v1 `create_agent`, rules enforced in tool code, `eval.py` with the 7 required scenarios.

**Accepted**
- All rules in a plain `backend.py` with no LLM dependency, tested offline (38 rule tests). Tools return `{"ok": false, "rejected": reason}` instead of raising, so the model can recover.
- The API signatures were checked against the installed `langchain==1.4.7` before writing code.
- A scripted fake chat model to test the agent wiring (tool execution, memory, guardrail) without an API key.
- 10 eval scenarios (the 7 required + hardship, fully-paid account, wrong person), judged on state and the audit log only.

**Rejected / corrected / open**
- The output guardrail is regex, English-only, and doesn't rewrite memory. Listed as a known failure mode with the fix.
- `eval.py` has not been run against the live model yet (no API key in the session). See assignment4/NOTES.md.

---

## How I verified AI output
- Every assignment has tests that would fail if the code were wrong: state assertions, a mutation check on the locking, and hand-computed statistics.
- I ran everything locally: 33 + 6 + 34 + 41 tests passing. The Docker container was checked for health, a non-root uid and JSON logs. The live ALB `/health` returned 200 with 2/2 healthy targets.
