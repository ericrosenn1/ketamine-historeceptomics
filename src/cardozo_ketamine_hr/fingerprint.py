"""Call sparse historeceptomic fingerprints with one-sided upper-tail GESD.

Purpose
-------
Identify unusually high HR coordinates and represent called target-tissue
features in deterministic tables and matrices.

Scientific stage
----------------
Fingerprint calling follows HR construction and precedes fingerprint pairwise
metrics and sparse multivariate analyses.

Primary inputs
--------------
Numeric HR vectors or strict-CNS HR tables, GESD alpha values, and governed
target/tissue ordering.

Primary outputs
---------------
Called source indices, per-step GESD diagnostics, ranked call tables, sparse
target-by-tissue matrices, and feature-ID sets.

Side effects
------------
None; input arrays and frames are not mutated and no files are written.

Invariants
----------
Only finite values enter testing; the test is one-sided upper-tail; sample
standard deviation uses ``ddof=1``; ties follow source order; and unobserved
coordinates remain missing rather than being encoded as non-calls.

Execution lane
--------------
Used by Smoke call-count checks, Verify fingerprint regeneration, and Full
downstream equivalence.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from .tissue_normalization import canonical_tissue_key, display_tissue


def gesd_upper(values: np.ndarray, alpha: float, rmax: int | None = None) -> tuple[list[int], pd.DataFrame]:
    """Run the deterministic one-sided upper-tail generalized ESD procedure.

    Parameters
    ----------
    values
        One-dimensional HR values. Nonfinite entries are excluded from the
        tested universe but retain their original indices.
    alpha
        Per-step significance level used in the one-sided critical value.
    rmax
        Maximum candidate outliers. Defaults to ten percent of finite values.

    Returns
    -------
    tuple[list[int], pandas.DataFrame]
        Original indices called as upper-tail outliers and a table containing
        every attempted removal's statistic and critical value.

    Notes
    -----
    Candidate removal continues through ``rmax``; the final call set ends at
    the last significant step. ``numpy.argmax`` supplies deterministic
    first-occurrence tie handling in source order. This is not a two-sided
    absolute-deviation test.
    """

    values = np.asarray(values, dtype=float)
    finite_indices = np.flatnonzero(np.isfinite(values)).tolist()
    active = finite_indices.copy()
    if rmax is None:
        rmax = int(math.floor(0.10 * len(active)))
    removed: list[int] = []
    rows: list[dict[str, float | int]] = []
    for step in range(1, min(rmax, max(0, len(active) - 3)) + 1):
        current = values[active]
        mean = float(np.mean(current))
        sd = float(np.std(current, ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            break
        # Upper-tail GESD ranks signed standardized excess, not absolute
        # deviation. np.argmax resolves exact ties to the first active index.
        local = int(np.argmax((current - mean) / sd))
        original_index = active[local]
        n = len(active)
        # This one-sided critical value uses p = 1 - alpha/n; the familiar
        # two-sided form would use alpha/(2n) and is not the governed method.
        p = 1.0 - alpha / n
        critical_t = float(student_t.ppf(p, n - 2))
        critical_lambda = ((n - 1) * critical_t) / math.sqrt((n - 2 + critical_t**2) * n)
        statistic = float((values[original_index] - mean) / sd)
        rows.append({
            "step": step,
            "n": n,
            "removed_index": original_index,
            "removed_value": float(values[original_index]),
            "GESD_R": statistic,
            "critical_lambda": critical_lambda,
            "R_minus_lambda": statistic - critical_lambda,
        })
        removed.append(original_index)
        active.pop(local)
    steps = pd.DataFrame(rows)
    if steps.empty or not (steps["GESD_R"] > steps["critical_lambda"]).any():
        return [], steps
    # GESD retains all sequential removals through the last significant step,
    # even if an earlier attempted statistic did not cross its threshold.
    last = int(steps.index[steps["GESD_R"] > steps["critical_lambda"]].max()) + 1
    return removed[:last], steps


def regression_calls(strict_hr: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """Create a ranked fingerprint call table from strict-CNS HR coordinates.

    Parameters
    ----------
    strict_hr
        HR table containing ``hr_numeric_collapsed`` in governed source order.
    alpha
        One-sided upper-tail GESD significance level.

    Returns
    -------
    pandas.DataFrame
        Called source rows with one-based fingerprint rank and GESD diagnostics.

    Notes
    -----
    The candidate limit is ``floor(0.10 * n_finite)``. Missing coordinates are
    excluded from testing and never converted to zero.
    """

    values = pd.to_numeric(strict_hr["hr_numeric_collapsed"], errors="coerce").to_numpy(float)
    called, steps = gesd_upper(values, alpha=alpha, rmax=int(math.floor(0.10 * np.isfinite(values).sum())))
    out = strict_hr.iloc[called].copy().reset_index(drop=True)
    out.insert(0, "fingerprint_rank", np.arange(1, len(out) + 1))
    if len(out):
        out = out.merge(steps[["removed_index", "step", "GESD_R", "critical_lambda", "R_minus_lambda"]], left_index=True, right_index=True, how="left")
    return out


def build_sparse_call_matrix(calls: pd.DataFrame, targets: list[str], tissues: list[str]) -> pd.DataFrame:
    """Place called HR values into a governed target-by-tissue matrix.

    Parameters
    ----------
    calls
        Fingerprint call rows containing target, tissue, and HR fields.
    targets
        Ordered target labels for matrix rows.
    tissues
        Ordered tissue labels for matrix columns.

    Returns
    -------
    pandas.DataFrame
        Sparse matrix containing called HR values and ``NaN`` elsewhere.

    Notes
    -----
    This helper represents calls only. An empty cell is not evidence of a
    tested non-call; binary tested/non-call encoding is built separately from
    explicit support in :mod:`pairwise_fingerprint`.
    """

    tissue_keys = [canonical_tissue_key(value) for value in tissues]
    matrix = pd.DataFrame(np.nan, index=targets, columns=tissue_keys, dtype=float)
    for row in calls.itertuples(index=False):
        target = str(getattr(row, "canonical_target_id", getattr(row, "target", "")))
        source = getattr(row, "tissue_label", getattr(row, "tissue", ""))
        key = canonical_tissue_key(source)
        if target in matrix.index and key in matrix.columns:
            matrix.loc[target, key] = float(getattr(row, "hr_numeric_collapsed", getattr(row, "raw_hr", 1.0)))
    matrix.columns = [display_tissue(key) for key in matrix.columns]
    return matrix


def call_set(frame: pd.DataFrame) -> set[str]:
    """Return the nonmissing common feature IDs represented by call rows.

    Parameters
    ----------
    frame
        Call table with a ``feature_id_common`` column.

    Returns
    -------
    set[str]
        Unique feature IDs as strings.
    """

    return set(frame["feature_id_common"].dropna().astype(str))
