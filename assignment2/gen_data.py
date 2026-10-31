# gen_data.py — pip install numpy pandas
import numpy as np, pandas as pd
rng = np.random.default_rng(42)
N = 20_000
acc = pd.DataFrame({
    "account_id": [f"A{i:05d}" for i in range(N)],
    "state": rng.choice(["MH","KA","TN","UP","BR","GJ"], N, p=[.25,.15,.15,.2,.1,.15]),
    "batch": rng.choice([f"B{i}" for i in range(1, 9)], N),
    "dpd": rng.integers(1, 121, N),
    "outstanding": rng.integers(2_000, 80_000, N),
})
idx = np.repeat(np.arange(N), rng.integers(1, 7, N)); M = len(idx)
day, hour, minute = rng.integers(0, 30, M), rng.integers(8, 19, M), rng.integers(0, 60, M)
ts = (pd.Timestamp("2026-08-01") + pd.to_timedelta(day, unit="D")
      + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m"))
weekend = np.asarray(ts.dayofweek) >= 5
p_conn = 0.20 + np.select([(hour >= 10) & (hour < 12), hour >= 17], [0.10, 0.12], 0.0) + np.where(weekend, 0.05, 0.0)
connected = rng.random(M) < p_conn
batch, state, dpd = acc.batch.values[idx], acc.state.values[idx], acc.dpd.values[idx]
wrong = connected & (rng.random(M) < np.where((batch == "B7") & (state == "BR"), 0.55, 0.08))
rpc = connected & ~wrong
ptp = rpc & (rng.random(M) < 0.30 - dpd / 1000)
days_to_promise = np.where(ptp, rng.integers(1, 15, M), 0)
kept = ptp & (rng.random(M) < np.where(days_to_promise <= 5, 0.65, 0.35))
calls = pd.DataFrame({
    "account_id": acc.account_id.values[idx], "called_at": ts,
    "disposition": np.select([~connected, wrong, ptp], ["NO_ANSWER", "WRONG_NUMBER", "PTP"], "RPC_NO_PTP"),
    "days_to_promise": np.where(ptp, days_to_promise, np.nan), "ptp_kept": np.where(ptp, kept, np.nan),
})
acc.to_csv("accounts.csv", index=False); calls.to_csv("calls.csv", index=False)
