# Assignment 2: Dialer Campaign Analytics (Part B)

## Run
```
python -m pip install -r requirements.txt
python gen_data.py                 # writes accounts.csv, calls.csv (seed 42)
python -m pytest -q                # metric helper tests
python build_notebook.py           # rebuilds and executes analysis.ipynb
```
Deliverables: `analysis.ipynb` (executed, with outputs), `connect_rate.png`, `ptp_rates.png`, `memo.md`.

## Assumptions
- `gen_data.py` is the brief's script with only the PDF line wraps undone. No logic is changed: same seed, same calls, same outputs.
- Unit is the call attempt. RPC = `PTP` + `RPC_NO_PTP`. A wrong number is connected but not RPC. PTP rate = PTP/RPC; kept rate = kept/PTP.
- Hours are local time as given. All calls fall in 08:00–18:59.
- DPD bands are 1–30, 31–60, 61–90, 91–120 (the data's max is 120).

## Approach and trade-offs
- The metric code (`metrics.py`) is separate from the notebook and unit-tested. That includes a test that `segment_scan` finds a planted anomaly and nothing else, and checks of the z-test against a hand calculation.
- The anomaly search is a *systematic* scan of all state, batch and state×batch cells over three metrics (connect, wrong|connected, PTP|RPC), each cell against the rest, with Bonferroni correction. This avoids eyeballing a table and avoids false alarms from 62 comparisons.
- Impact sizing reuses this month's funnel ratios. Each recommendation has a sensitivity table rather than a single point estimate.
- `build_notebook.py` generates the notebook so that the committed outputs are reproducible and diffable.

## Known limitations
- Kept rate vs days-to-promise is observational. In real data the borrowers who choose short dates may differ, so the memo recommends an A/B test.
- The time-shift estimate assumes the peak connect rate holds at higher volume, and it ignores per-account fatigue.
- One month of data only, so there is no check for week-to-week seasonality.

## With another day
- Account-level analysis: probability of an eventual RPC or kept PTP per account as a function of attempt number and time slot, which directly informs the attempt cap.
- A logistic model of connect ~ hour + weekend + state + batch, to check that the effects are additive and to size the shift more precisely.
- A power calculation and design for the promise-window A/B.
