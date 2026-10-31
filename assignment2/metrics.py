"""Reusable, tested helpers for the dialer analysis notebook."""
import math

import numpy as np
import pandas as pd
from scipy import stats

DPD_BINS = [0, 30, 60, 90, 120]
DPD_LABELS = ["1-30", "31-60", "61-90", "91-120"]


def load(accounts_path="accounts.csv", calls_path="calls.csv") -> pd.DataFrame:
    acc = pd.read_csv(accounts_path)
    calls = pd.read_csv(calls_path, parse_dates=["called_at"])
    df = calls.merge(acc, on="account_id", how="left", validate="many_to_one")
    if df["state"].isna().any():
        raise ValueError("calls reference unknown account_ids")
    return add_flags(df)


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["connected"] = df["disposition"] != "NO_ANSWER"
    df["wrong"] = df["disposition"] == "WRONG_NUMBER"
    df["ptp"] = df["disposition"] == "PTP"
    df["rpc"] = df["disposition"].isin(["PTP", "RPC_NO_PTP"])
    df["hour"] = df["called_at"].dt.hour
    df["weekend"] = df["called_at"].dt.dayofweek >= 5
    df["dpd_band"] = pd.cut(df["dpd"], DPD_BINS, labels=DPD_LABELS)
    return df


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval: well behaved for small n and rates near 0/1."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def rate_table(df: pd.DataFrame, by, flag: str) -> pd.DataFrame:
    """Rate of boolean column `flag` per group of `by`, with n, k and a 95% Wilson CI."""
    g = df.groupby(by, observed=True)[flag].agg(k="sum", n="size")
    g["k"] = g["k"].astype(int)
    g["rate"] = g["k"] / g["n"]
    ci = [wilson_ci(k, n) for k, n in zip(g["k"], g["n"])]
    g["ci_low"] = [c[0] for c in ci]
    g["ci_high"] = [c[1] for c in ci]
    return g


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """Two-sided pooled z-test. Returns (z, p_value)."""
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (k1 / n1 - k2 / n2) / se
    return z, 2 * stats.norm.sf(abs(z))


def segment_scan(df: pd.DataFrame, cols: list[str], flag: str, min_n: int = 50) -> pd.DataFrame:
    """Compare each segment's rate against everything outside it.

    Bonferroni-adjusts p-values for the number of segments tested so that
    scanning ~60 cells doesn't produce false alarms by chance.
    """
    total_k, total_n = int(df[flag].sum()), len(df)
    rows = []
    for key, g in df.groupby(cols, observed=True):
        n, k = len(g), int(g[flag].sum())
        if n < min_n:
            continue
        z, p = two_proportion_z(k, n, total_k - k, total_n - n)
        rows.append({**dict(zip(cols, key if isinstance(key, tuple) else (key,))),
                     "n": n, "k": k, "rate": k / n, "rest_rate": (total_k - k) / (total_n - n),
                     "z": z, "p": p})
    out = pd.DataFrame(rows)
    out["p_bonferroni"] = np.minimum(out["p"] * len(out), 1.0)
    return out.sort_values("z", ascending=False).reset_index(drop=True)
