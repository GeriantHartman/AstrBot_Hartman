import pytest

from scripts.rp_bench.stats import (
    bootstrap_ci,
    mean_sd,
    merge_swapped,
    sign_test_p,
    wilson_ci,
    win_rate,
)


def test_wilson_known_values():
    lo, hi = wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)
    assert wilson_ci(0, 0) == (0.0, 1.0)


def test_sign_test():
    assert sign_test_p(10, 0) == pytest.approx(2 / 1024)
    assert sign_test_p(5, 5) == 1.0
    assert sign_test_p(0, 0) == 1.0


def test_merge_swapped_table():
    # order1 shows X as A, order2 shows X as B
    assert merge_swapped("A", "B") == (1, True)  # X wins both
    assert merge_swapped("B", "A") == (-1, True)  # X loses both
    assert merge_swapped("A", "A") == (0, False)  # judge always picks the left slot
    assert merge_swapped("tie", "tie") == (0, True)
    assert merge_swapped("A", "tie") == (1, False)
    assert merge_swapped("invalid", "B") == (1, False)


def test_win_rate_counts_ties_as_half():
    r = win_rate([1, 1, 0, -1])
    assert (r["wins"], r["ties"], r["losses"], r["n"]) == (2, 1, 1, 4)
    assert r["win_rate"] == pytest.approx(0.625)
    assert r["ci_lo"] < 0.625 < r["ci_hi"]


def test_bootstrap_is_deterministic_and_brackets_mean():
    vals = [3, 4, 4, 5, 2, 4]
    a = bootstrap_ci(vals)
    b = bootstrap_ci(vals)
    assert a == b
    m, _ = mean_sd(vals)
    assert a[0] <= m <= a[1]
    assert bootstrap_ci([]) == (None, None)
    assert mean_sd([4]) == (4.0, 0.0)
