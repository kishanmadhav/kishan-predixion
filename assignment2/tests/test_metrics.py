import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metrics import add_flags, rate_table, segment_scan, two_proportion_z, wilson_ci  # noqa: E402


def _calls(dispositions, **extra):
    n = len(dispositions)
    base = {
        "account_id": [f"A{i}" for i in range(n)],
        "called_at": pd.to_datetime(["2026-08-03 10:15"] * n),   # a Monday
        "disposition": dispositions,
        "dpd": [10] * n,
    }
    base.update(extra)
    return add_flags(pd.DataFrame(base))


def test_flags_follow_disposition_definitions():
    df = _calls(["NO_ANSWER", "WRONG_NUMBER", "PTP", "RPC_NO_PTP"])
    assert df["connected"].tolist() == [False, True, True, True]
    assert df["rpc"].tolist() == [False, False, True, True]      # wrong number is connected but not RPC
    assert df["ptp"].tolist() == [False, False, True, False]
    assert df["hour"].tolist() == [10] * 4
    assert not df["weekend"].any()


def test_dpd_band_edges():
    df = _calls(["PTP"] * 5, dpd=[1, 30, 31, 90, 120])
    assert df["dpd_band"].astype(str).tolist() == ["1-30", "1-30", "31-60", "61-90", "91-120"]


def test_wilson_ci_known_value():
    lo, hi = wilson_ci(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3)
    assert hi == pytest.approx(0.5962, abs=1e-3)
    assert wilson_ci(0, 10)[0] == pytest.approx(0.0, abs=1e-12)    # never negative
    assert np.isnan(wilson_ci(0, 0)[0])


def test_rate_table_counts():
    df = pd.DataFrame({"g": ["a", "a", "a", "b"], "f": [True, False, True, False]})
    t = rate_table(df, "g", "f")
    assert t.loc["a", ["k", "n"]].tolist() == [2, 3]
    assert t.loc["a", "rate"] == pytest.approx(2 / 3)
    assert t.loc["b", "rate"] == 0


def test_two_proportion_z_matches_textbook():
    # A/B from Part A: 880/4000 vs 960/4000. By hand: pooled p = 0.23,
    # SE = sqrt(0.23 * 0.77 * 2/4000) = 0.00941, z = -0.02 / 0.00941 = -2.125, two-sided p = 0.0336
    z, p = two_proportion_z(880, 4000, 960, 4000)
    assert z == pytest.approx(-2.125, abs=0.001)
    assert p == pytest.approx(0.0336, abs=0.0005)


def test_segment_scan_finds_planted_anomaly_and_not_noise():
    rng = np.random.default_rng(0)
    n = 20_000
    df = pd.DataFrame({"state": rng.choice(list("ABCD"), n), "batch": rng.choice(list("WXYZ"), n)})
    p = np.where((df.state == "C") & (df.batch == "Y"), 0.5, 0.08)
    df["wrong"] = rng.random(n) < p
    res = segment_scan(df, ["state", "batch"], "wrong")
    top = res.iloc[0]
    assert (top.state, top.batch) == ("C", "Y")
    assert top.p_bonferroni < 1e-6
    assert (res.iloc[1:]["rate"] < 0.12).all()      # nothing else looks anomalous
