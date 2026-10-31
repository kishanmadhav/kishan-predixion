# Memo: Dialer campaign, August 2026

**To:** Head of Collections | **From:** Kishan | **Data:** 70,235 call attempts on 20,000 accounts, 1–30 Aug 2026

**Where we are.** Of every 100 dials, 25.7 connect, 23.5 reach the right party, 5.5 give a promise to pay, and 2.5 keep it. That is 1,766 kept PTPs this month. Three changes, in order of impact:

### 1. Anchor promise dates to within 5 days *(largest lever)*
- **Evidence:** promises 1–5 days out are kept **65%** of the time; 6–14 days, **34%**. It is a cliff between day 5 and day 6, not a gradual slope (z = 18). Today **64% of PTPs (2,493/month) are set 6–14 days out.**
- **Action:** change the agent script to propose a date within 5 days first (offer a part-payment within 5 days if needed). Allow longer dates only on request.
- **Expected impact:** if half of the long-dated promisers accept ≤5 days, **+380 kept PTPs/month (+22%)**. Range: +190 (25% accept) to +570 (75% accept).
- **Risk:** borrowers who choose short dates may simply be more able to pay. Run it as a 2-week A/B on 50% of agents before full rollout. The A/B needs about 1,000 PTPs per arm, which takes roughly 1 week of volume.

### 2. Shift dialing into the hours people answer
- **Evidence:** 10:00–12:00 and 17:00–19:00 connect at **32.6%**; every other hour connects at **21.7%** (+50% relative). Weekends connect at **29.3% vs 23.8%** on weekdays, and the lift holds in every hour. Dials are currently spread evenly across the day.
- **Action:** weight the scheduler toward the two peak windows and weekends. Use off-peak hours for callbacks and first-attempt fresh accounts.
- **Expected impact:** moving 20% of off-peak attempts (~9,000/month) into peak windows gives **+980 connects (+5.4%), +212 PTPs and +96 kept PTPs/month** at the same dial volume. 10% / 30% moved gives +48 / +144 kept.
- **Cost:** peak-window line load rises about 36%. Either add lines for those 4 hours or cap the shift at the existing headroom. Expect some diminishing returns as the same borrowers are tried repeatedly at peak.

### 3. Stop dialing Bihar × batch B7 until its phone numbers are fixed *(compliance first)*
- **Evidence:** in this one segment, **54% of connected calls reach the wrong person**, against 8% everywhere else (z = 24). Bihar in other batches and B7 in other states are normal, so this is a bad contact-data file, not borrower behaviour. It covers **238 accounts and ₹92.7 lakh outstanding**. 99 of them (42%) hit a wrong number this month.
- **Action:** suppress the segment today, ask the lender for the source of B7-Bihar numbers, re-skip-trace and re-verify before re-enabling. Add a daily alert on wrong-number rate by state × batch (more than 3× baseline with at least 50 connects).
- **Expected impact:** **114 wrong-party contacts/month avoided immediately.** Each one risks disclosing a debt to a third party, which is a regulatory exposure. Once fixed, **+97 right-party contacts, +23 PTPs, about +10 kept/month.** The volume is small; the point is the compliance risk, and the monitor will catch the next bad file early.

**Also noted:** PTP rate falls from 28% at 1–30 DPD to 19% at 91–120 DPD (−3 pp per 30 days). Early-bucket accounts should get first claim on the new peak-hour capacity.

*Method:* rates have 95% Wilson CIs, and segment tests are Bonferroni-corrected across 62 cells. Impacts use this month's funnel ratios (RPC|connect 91.6%, PTP|RPC 23.6%, kept|PTP 45.4%). Full workings are in `analysis.ipynb`.
