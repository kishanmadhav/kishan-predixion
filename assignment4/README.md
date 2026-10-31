# Assignment 4: Collections Assistant Agent

A text-mode collections agent built on LangChain v1 `create_agent`, with 5 tools over an in-memory backend and memory across turns via a LangGraph `InMemorySaver` checkpointer.

## Run
```
python -m pip install -r requirements.txt
cp .env.example .env                 # put ANTHROPIC_API_KEY in .env
python -m pytest -q                  # 41 offline tests: business rules + agent wiring (no key needed)
python eval.py                       # 10 scripted scenarios against the real model
python agent.py                      # chat in the terminal
```
The model defaults to `anthropic:claude-opus-5-5`. Any LangChain provider works through `AGENT_MODEL`, e.g. `AGENT_MODEL=openai:gpt-4.1` with `langchain-openai` installed.

Seeded accounts:
| Account | DOB | State |
|---|---|---|
| A1001 | 1988-04-12 | ₹45,000 outstanding, min due ₹3,000, 34 DPD |
| A1002 | 1992-11-03 | fully paid, CLOSED |
| A1003 | 1979-01-25 | ₹12,500 outstanding, 95 DPD |

## Design
| File | Role |
|---|---|
| `backend.py` | All business state and **all business rules**: plain Python, no LLM imports |
| `agent.py` | Thin `@tool` wrappers, system prompt, `create_agent`, output guardrail, CLI |
| `eval.py` | Scenarios judged on backend state and tool audit log, never on wording |
| `tests/` | Rule tests (no LLM) + wiring tests with a scripted fake model |

Each tool catches `RuleViolation` and returns `{"ok": false, "rejected": "<reason>"}`, so the model can explain the rejection and recover instead of crashing. Every call is appended to `backend.audit`, which is what `eval.py` judges.

## What is enforced where
| Rule | Prompt | Tool code | Output guardrail |
|---|---|---|---|
| No account details before verification | ✓ | ✓ `get_account` / `record_promise_to_pay` require the verified account; a verified caller can't read other accounts | |
| Don't reveal which accounts exist; lock after 3 bad DOBs | ✓ | ✓ identical response for unknown account vs wrong DOB; lockout | |
| PTP date today…today+7, min due ≤ amount ≤ outstanding | ✓ | ✓ Decimal → paise, inclusive bounds, one PTP per call | |
| Callbacks 08:00–19:00 IST | ✓ | ✓ naive times are read as IST; aware times are converted; must be in the future and ≤14 days | |
| Dispute / already paid / hardship / abusive → escalate, never push | ✓ | ✓ after a blocking escalation, `record_promise_to_pay` refuses on that account | |
| No threats, shaming, legal/police/family/employer | ✓ | | ✓ regex on every reply → replaced with a safe hand-off line and logged |
| Can't settle or change balances (injection) | ✓ | ✓ **no tool has a write path** to balance or status | |

**Which defence matters most:** tool-level enforcement. The prompt can be talked around; code can't. "Admin mode" has nothing to call.

## Eval scenarios
`happy_path_ptp`, `below_minimum_offer`, `dispute`, `already_paid` (Hinglish), `wrong_dob`, `prompt_injection`, `callback_at_22`, `hardship`, `fully_paid_account`, `wrong_person`.

Every scenario also checks that no reply tripped the conduct guardrail. The clock is fixed at Monday 2026-11-02 10:00 IST, so dates in the scripts are deterministic. Use `--repeat N` to measure flakiness, since LLM runs are not deterministic.

## Known failure modes and fixes
1. **The guardrail regex is English-only and keyword-based.** It misses Hindi threats ("police bula lenge") and paraphrases. *Fix:* a small classifier pass (Haiku-class model or fine-tuned) on each reply before TTS, plus Hindi terms.
2. **The guardrail rewrites only the user-facing reply.** The original text stays in the agent's memory. *Fix:* move it into an `after_model` middleware that edits state, so the model also sees the corrected turn.
3. **The model may record a PTP before explicit confirmation.** This is prompt-only today. *Fix:* a `confirm` flag that the tool requires, set only after the agent reads the amount and date back to the borrower.
4. **Escalation reason is chosen by the model.** It might label hardship as OTHER, and then the "never push" block wouldn't apply. *Fix:* treat every escalation as blocking, or classify intent with a separate structured-output call.
5. **Dates in natural language** ("next Friday", "parso") rely on the model converting them correctly. Tools reject non-ISO strings, but a wrong ISO date passes if it is inside the window. *Fix:* read the date back for confirmation; add deterministic date parsing in the tool.
6. **In-memory state and memory.** Everything is lost on restart. *Fix:* a Postgres checkpointer and real account APIs, with an idempotency key per PTP.
7. **Scripted user turns** can't adapt to an unexpected agent question, so a scenario can fail on dialogue drift rather than a real error. *Fix:* an LLM-simulated borrower with a persona and goal, judged on the same state checks.
