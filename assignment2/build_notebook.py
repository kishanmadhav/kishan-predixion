"""Builds and executes analysis.ipynb so the committed notebook always matches the code.

    python build_notebook.py
"""
import nbformat as nbf
from nbclient import NotebookClient

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("# Dialer campaign analysis\n"
       "Data: `gen_data.py` (unmodified, seed 42), with 20,000 accounts and ~70k call attempts in Aug 2026.\n\n"
       "Unit of analysis is the **call attempt** unless stated. Definitions: connect = disposition != NO_ANSWER; "
       "RPC = PTP or RPC_NO_PTP (connected and not a wrong number); PTP rate = PTP / RPC; kept rate = kept / PTP. "
       "Every rate is shown with a 95% Wilson CI, and helpers live in `metrics.py` (unit-tested)."),
    code("import pandas as pd, numpy as np\n"
         "import matplotlib.pyplot as plt\n"
         "%matplotlib inline\n"
         "from scipy import stats\n"
         "from metrics import load, rate_table, segment_scan, two_proportion_z\n"
         "pd.set_option('display.float_format', '{:.4f}'.format)\n"
         "df = load('accounts.csv', 'calls.csv')\n"
         "print(len(df), 'calls |', df.account_id.nunique(), 'accounts |', df.called_at.min(), '->', df.called_at.max())\n"
         "print(df.disposition.value_counts())\n"
         "assert df[['called_at','disposition','state','batch','dpd']].notna().all().all()\n"
         "assert df.hour.between(8, 18).all()   # all calls inside 08:00-19:00"),

    md("## 1. Connect rate by hour and weekday vs weekend"),
    code("by_hour = rate_table(df, 'hour', 'connected')\n"
         "by_we = rate_table(df, 'weekend', 'connected').rename(index={False: 'weekday', True: 'weekend'})\n"
         "by_hour_we = df.pivot_table(index='hour', columns='weekend', values='connected', aggfunc='mean')\n"
         "by_hour_we.columns = ['weekday', 'weekend']\n"
         "display(by_hour[['n','k','rate','ci_low','ci_high']]); display(by_we[['n','k','rate','ci_low','ci_high']])\n"
         "chi2, p, *_ = stats.chi2_contingency(pd.crosstab(df.hour, df.connected))\n"
         "print(f'hour vs connect: chi2={chi2:.0f}, p={p:.1e}')\n"
         "z, p = two_proportion_z(by_we.loc['weekend','k'], by_we.loc['weekend','n'], by_we.loc['weekday','k'], by_we.loc['weekday','n'])\n"
         "print(f'weekend vs weekday: z={z:.1f}, p={p:.1e}')"),
    code("fig, ax = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={'width_ratios': [3, 1]})\n"
         "for col, m in [('weekday', 'o'), ('weekend', 's')]:\n"
         "    ax[0].plot(by_hour_we.index, by_hour_we[col] * 100, marker=m, label=col)\n"
         "ax[0].errorbar(by_hour.index, by_hour.rate * 100, yerr=[(by_hour.rate - by_hour.ci_low) * 100, (by_hour.ci_high - by_hour.rate) * 100],\n"
         "               fmt='k--', alpha=.6, label='all (95% CI)')\n"
         "ax[0].set(xlabel='Hour of day (local)', ylabel='Connect rate %', title='Connect rate by hour', xticks=range(8, 19)); ax[0].legend()\n"
         "ax[1].bar(by_we.index, by_we.rate * 100, yerr=[(by_we.rate - by_we.ci_low) * 100, (by_we.ci_high - by_we.rate) * 100], capsize=6)\n"
         "ax[1].set(ylabel='Connect rate %', title='Weekday vs weekend')\n"
         "plt.tight_layout(); plt.savefig('connect_rate.png', dpi=110); plt.show()"),
    code("peak = df.hour.isin([10, 11, 17, 18])\n"
         "peak_rate, off_rate = df[peak].connected.mean(), df[~peak].connected.mean()\n"
         "print(f'peak hours 10-12 & 17-19: {peak_rate:.1%} ({peak.sum()} calls) | other hours: {off_rate:.1%} ({(~peak).sum()} calls)')\n"
         "print(f'relative lift of peak hours: {peak_rate / off_rate - 1:.0%}')"),
    md("**Finding.** Connect rate has two clear peaks, **10:00–12:00 and 17:00–19:00 (~32–34%)**, against a flat ~21–22% "
       "in every other hour. Weekends connect at **29.3% vs 23.8%** on weekdays, and the weekend lift holds in every hour, "
       "so the two effects add up. Both are highly significant (see the chi-square / z output). Calls are spread evenly "
       "across hours today, so the dialer is not exploiting this."),

    md("## 2. PTP rate by DPD band, and PTP kept rate by days-to-promise"),
    code("rpc = df[df.rpc]\n"
         "ptp_dpd = rate_table(rpc, 'dpd_band', 'ptp')\n"
         "display(ptp_dpd[['n','k','rate','ci_low','ci_high']])\n"
         "slope, intercept, r, p, se = stats.linregress(rpc.dpd, rpc.ptp.astype(float))\n"
         "print(f'linear fit: PTP rate falls {-slope*30:.1%} per 30 DPD (p={p:.1e})')"),
    code("ptp = df[df.ptp].copy()\n"
         "ptp['kept'] = ptp.ptp_kept.astype(bool)\n"
         "kept_days = rate_table(ptp, 'days_to_promise', 'kept')\n"
         "display(kept_days[['n','k','rate','ci_low','ci_high']])\n"
         "ptp['window'] = np.where(ptp.days_to_promise <= 5, '1-5 days', '6-14 days')\n"
         "kept_win = rate_table(ptp, 'window', 'kept'); display(kept_win[['n','k','rate','ci_low','ci_high']])\n"
         "z, p = two_proportion_z(kept_win.k.iloc[0], kept_win.n.iloc[0], kept_win.k.iloc[1], kept_win.n.iloc[1])\n"
         "print(f'1-5 vs 6-14 days: z={z:.1f}, p={p:.1e}')"),
    code("fig, ax = plt.subplots(1, 2, figsize=(12, 4))\n"
         "ax[0].bar(ptp_dpd.index.astype(str), ptp_dpd.rate * 100, yerr=[(ptp_dpd.rate-ptp_dpd.ci_low)*100, (ptp_dpd.ci_high-ptp_dpd.rate)*100], capsize=6)\n"
         "ax[0].set(xlabel='DPD band', ylabel='PTP / RPC %', title='PTP rate by DPD band')\n"
         "ax[1].bar(kept_days.index.astype(int), kept_days.rate * 100, yerr=[(kept_days.rate-kept_days.ci_low)*100, (kept_days.ci_high-kept_days.rate)*100], capsize=3,\n"
         "          color=['tab:green' if d <= 5 else 'tab:red' for d in kept_days.index])\n"
         "ax[1].set(xlabel='Days to promised date', ylabel='Kept %', title='PTP kept rate by days-to-promise', xticks=range(1, 15))\n"
         "plt.tight_layout(); plt.savefig('ptp_rates.png', dpi=110); plt.show()"),
    md("**Finding.** PTP rate falls steadily with delinquency, from **28.1% at 1–30 DPD to 19.2% at 91–120** (about 3 pp "
       "per 30 days). Kept rate is a **step function, not a slope**: about **65% for promises 1–5 days out against "
       "about 34% for 6–14 days**, flat within each side. The cliff is between day 5 and day 6. "
       "Caveat: in real data, the borrowers who pick short dates may differ from those who pick long ones (selection), "
       "so the causal effect of *asking* for a short date should be confirmed with an A/B test."),

    md("## 3. Anomalous segment\n"
       "I scan every state, batch and state×batch cell for connect rate, wrong-number rate (among connected) and "
       "PTP rate (among RPC), each cell against the rest, with Bonferroni correction for the number of cells tested."),
    code("conn = df[df.connected]\n"
         "results = {}\n"
         "for name, frame, flag in [('connect', df, 'connected'), ('wrong_number|connected', conn, 'wrong'), ('ptp|rpc', rpc, 'ptp')]:\n"
         "    for cols in (['state'], ['batch'], ['state', 'batch']):\n"
         "        r = segment_scan(frame, cols, flag)\n"
         "        sig = r[r.p_bonferroni < 0.01]\n"
         "        results[(name, tuple(cols))] = r\n"
         "        print(f'{name:24s} by {\"x\".join(cols):12s}: {len(r):2d} cells, significant after Bonferroni: '\n"
         "              + (', '.join(f\"{'/'.join(str(row[c]) for c in cols)} ({row.rate:.1%} vs {row.rest_rate:.1%})\" for _, row in sig.iterrows()) or 'none'))"),
    code("display(results[('wrong_number|connected', ('state', 'batch'))].head(6))\n"
         "seg = (df.state == 'BR') & (df.batch == 'B7')\n"
         "c = df[df.connected]\n"
         "tbl = pd.DataFrame({\n"
         "    'BR x B7': [c[seg[c.index]].wrong.mean()],\n"
         "    'BR, other batches': [c[(c.state == 'BR') & (c.batch != 'B7')].wrong.mean()],\n"
         "    'B7, other states': [c[(c.batch == 'B7') & (c.state != 'BR')].wrong.mean()],\n"
         "    'everything else': [c[~seg[c.index]].wrong.mean()]}, index=['wrong-number rate among connected'])\n"
         "display(tbl)"),
    code("acc = pd.read_csv('accounts.csv')\n"
         "seg_acc = acc[(acc.state == 'BR') & (acc.batch == 'B7')]\n"
         "s = df[seg]\n"
         "base_wrong = c[~seg[c.index]].wrong.mean()\n"
         "seg_conn, seg_wrong = int(s.connected.sum()), int(s.wrong.sum())\n"
         "excess_wrong = seg_wrong - seg_conn * base_wrong\n"
         "print(f'accounts: {len(seg_acc)} ({len(seg_acc)/len(acc):.1%} of book), outstanding: Rs {seg_acc.outstanding.sum():,} ')\n"
         "print(f'calls: {len(s)}, connected: {seg_conn}, wrong numbers: {seg_wrong} ({seg_wrong/seg_conn:.1%}) vs baseline {base_wrong:.1%}')\n"
         "print(f'excess wrong-number connects/month: {excess_wrong:.0f}')\n"
         "print(f'segment connect rate {s.connected.mean():.1%} vs book {df.connected.mean():.1%}; PTP|RPC {s[s.rpc].ptp.mean():.1%} vs book {rpc.ptp.mean():.1%}')\n"
         "acct_wrong = s.groupby('account_id').wrong.any()\n"
         "print(f'accounts in segment with >=1 wrong-number call this month: {acct_wrong.sum()} of {len(seg_acc)} ({acct_wrong.mean():.0%})')"),
    md("**Finding.** One cell stands out across all three metrics: **Bihar × batch B7**, with a **~54% wrong-number rate among "
       "connected calls against ~8% everywhere else** (z ≈ 24, Bonferroni-adjusted p < 1e-6). It is the *intersection* that is bad: "
       "Bihar in other batches and B7 in other states are normal (~7–9%), connect rate is normal (25.0% vs 25.7%) and PTP|RPC is not significantly different after correction (30.3% on only ~99 RPCs)."
       "So the borrowers are not harder to persuade; we are reaching the wrong people. That points to a contact-data problem in "
       "the B7 allocation file for Bihar (e.g. a vendor/skip-trace source or a column shift in the upload), not a behavioural one.\n\n"
       "**Operationally:** (1) suppress BR×B7 from the dialer today; each wrong-number call risks disclosing a debt to a third party, which is a compliance issue, "
       "not just wasted dials. (2) Ask the lender/data team for the source of B7-Bihar phone numbers and diff against the previous allocation. "
       "(3) Re-skip-trace those 238 accounts and re-verify numbers (e.g. a penny-drop or SMS OTP) before re-enabling them. (4) Add a daily monitor: "
       "wrong-number rate by state×batch with an alert at more than 3× baseline and n ≥ 50 connects."),

    md("## 4. Impact sizing for the memo\nAll inputs are computed from this month's data. Assumptions are explicit and varied in a sensitivity table."),
    code("rpc_per_conn = df.rpc.sum() / df.connected.sum()\n"
         "ptp_per_rpc = df.ptp.sum() / df.rpc.sum()\n"
         "kept_per_ptp = ptp.kept.mean()\n"
         "print(f'funnel: connect {df.connected.mean():.1%} -> RPC|conn {rpc_per_conn:.1%} -> PTP|RPC {ptp_per_rpc:.1%} -> kept|PTP {kept_per_ptp:.1%}')\n"
         "base = dict(attempts=len(df), connects=int(df.connected.sum()), rpc=int(df.rpc.sum()), ptp=int(df.ptp.sum()), kept=int(ptp.kept.sum()))\n"
         "print(base)\n"
         "\n"
         "# R1: move a share of off-peak weekday attempts into peak hours, same number of attempts\n"
         "rows = []\n"
         "for share in (0.10, 0.20, 0.30):\n"
         "    moved = (~peak).sum() * share\n"
         "    extra_conn = moved * (peak_rate - off_rate)\n"
         "    extra_kept = extra_conn * rpc_per_conn * ptp_per_rpc * kept_per_ptp\n"
         "    rows.append({'share_of_offpeak_moved': share, 'attempts_moved': round(moved), 'extra_connects': round(extra_conn),\n"
         "                 'connect_lift': extra_conn / base['connects'], 'extra_ptp': round(extra_conn * rpc_per_conn * ptp_per_rpc), 'extra_kept': round(extra_kept)})\n"
         "r1 = pd.DataFrame(rows); display(r1)"),
    code("# R2: anchor promise dates to <= 5 days. Assumption: a share of borrowers who would have said 6-14 days accept <= 5 days\n"
         "# and then keep at the short-window rate. Upper bound because of selection (see section 2 caveat).\n"
         "n_long = int((ptp.days_to_promise > 5).sum())\n"
         "k_short, k_long = kept_win.rate.iloc[0], kept_win.rate.iloc[1]\n"
         "r2 = pd.DataFrame([{'accept_share': a, 'ptps_converted': round(n_long * a), 'extra_kept': round(n_long * a * (k_short - k_long)),\n"
         "                    'kept_lift': n_long * a * (k_short - k_long) / base['kept']} for a in (0.25, 0.50, 0.75)])\n"
         "print(f'PTPs with 6-14 day dates this month: {n_long} of {len(ptp)} ({n_long/len(ptp):.0%}); kept {k_short:.1%} vs {k_long:.1%}')\n"
         "display(r2)\n"
         "\n"
         "# R3: fix BR x B7 contact data -> wrong-number rate back to baseline\n"
         "extra_rpc = excess_wrong\n"
         "print(f'R3: +{extra_rpc:.0f} RPCs/month, +{extra_rpc*ptp_per_rpc:.0f} PTPs, +{extra_rpc*ptp_per_rpc*kept_per_ptp:.0f} kept; '\n"
         "      f'{seg_wrong} third-party contacts/month avoided immediately by suppression; Rs {seg_acc.outstanding.sum()/1e5:.1f} lakh outstanding re-reachable')"),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": "."}}).execute()
nbf.write(nb, "analysis.ipynb")
print("wrote analysis.ipynb")
