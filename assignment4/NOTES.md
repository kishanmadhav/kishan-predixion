# Assignment 4: NOTES

## Assumptions
- "Today" for business rules is the IST date. `Backend.now` is injected, which makes tests and evals deterministic.
- A PTP must cover at least the minimum due (per the brief). There is one PTP per call.
- Callbacks may be booked without verification: they reveal nothing, and a busy borrower may want one before verifying. The time window still applies.
- Callbacks are limited to 14 days ahead (my choice; the brief is silent on this).
- Amounts are strings in rupees at the tool boundary, converted to integer paise with `Decimal`, never floats.

## Trade-offs
- `create_agent` (a ReAct loop) rather than a hand-built LangGraph state machine. The call flow is short, and the rules are in the tools, so a full graph adds code without adding safety. For production voice I'd move to an explicit graph (verify → inform → negotiate → close) for predictability and latency.
- The guardrail is a post-processing regex: cheap and deterministic, but shallow (see README failure modes).
- Evals use real LLM calls, so they cost money and are non-deterministic. The offline pytest suite covers the rules and wiring and runs in CI; `eval.py` is for pre-release checks.

## Status
- `pytest`: 41 passed (offline).
- `eval.py`: needs `ANTHROPIC_API_KEY` (not available when this was written). Run `python eval.py --repeat 3` before submission and paste the output here.

## With another day
- An LLM-simulated borrower and a larger scenario set (abusive caller, multilingual, partial-payment haggling, callback then PTP), each run 5× with a pass rate reported.
- An `after_model` middleware guardrail with a classifier, plus logging of rejected tool calls as an eval signal.
- Latency work for voice: streaming tokens to TTS, a smaller model for turn-level replies, and pre-fetching the account after verification.
