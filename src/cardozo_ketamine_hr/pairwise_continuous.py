"""Compute missingness-aware continuous pairwise profile comparisons.

Purpose
-------
Compare compound HR profiles only on coordinates supported by both members and
assemble deterministic pairwise metric tables and symmetric matrices.

Scientific stage
----------------
This exploratory continuous-analysis stage follows common-RHR profile assembly
and complements the primary sparse-fingerprint comparisons.

Primary inputs
--------------
Aligned compound-by-feature matrices, a feature metadata contract, compound
order, and a callback providing sparse-call metrics.

Primary outputs
---------------
Continuous metric dictionaries, coordinate-level difference tables, complete
unordered-pair tables, and symmetric metric matrices.

Side effects
------------
None; inputs are not mutated and no files are written.

Invariants
----------
Continuous metrics use matched finite support only, support overlap is kept
separate from biological call overlap, pair order is deterministic, and
insufficient/constant data remains not estimable rather than being imputed.

Execution lane
--------------
Used by Smoke synthetic checks and by Verify/Full comparative regeneration.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr


PAIR_GATE_FEATURES = 20
PAIR_GATE_TARGETS = 2


def _correlation(a: np.ndarray, b: np.ndarray, kind: str) -> float:
    """Return a guarded Pearson or Spearman correlation.

    Parameters
    ----------
    a, b
        Matched finite numeric vectors.
    kind
        ``"pearson"`` selects Pearson correlation; other values select
        Spearman correlation, matching the internal governed calls.

    Returns
    -------
    float
        Correlation coefficient or ``NaN`` when fewer than two observations,
        zero variance, or a library-level estimation failure prevents a value.
    """

    if len(a) < 2 or np.std(a) <= 0 or np.std(b) <= 0:
        return np.nan
    try:
        return float(pearsonr(a, b).statistic if kind == "pearson" else spearmanr(a, b).statistic)
    except Exception:
        return np.nan


def continuous_metrics(a: pd.Series, b: pd.Series, contract: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    """Calculate continuous distances and similarities on matched support.

    Parameters
    ----------
    a, b
        Feature-indexed common-RHR profiles.
    contract
        Feature metadata containing ``feature_id`` and ``target``.

    Returns
    -------
    tuple[dict[str, Any], pandas.DataFrame]
        Summary metrics and a coordinate-level table of matched values and
        differences.

    Notes
    -----
    A coordinate contributes only when both profiles are observed. The overlap
    gate requires at least 20 matched features spanning at least two targets;
    metrics remain descriptive even when that gate is false.
    """

    # Matched-support restriction prevents absent coordinates from becoming
    # artificial zeros or contributing asymmetrically to continuous distance.
    mask = a.notna() & b.notna()
    feature_ids = a.index[mask]
    av = a.loc[feature_ids].to_numpy(float)
    bv = b.loc[feature_ids].to_numpy(float)
    detail = contract.set_index("feature_id").reindex(feature_ids).reset_index()
    detail["value_a"] = av
    detail["value_b"] = bv
    detail["signed_difference_a_minus_b"] = av - bv
    detail["absolute_difference"] = np.abs(av - bv)
    targets = int(detail["target"].nunique()) if len(detail) else 0
    if not len(feature_ids):
        return {
            "matched_features": 0, "matched_targets": 0, "rms_common_rhr": np.nan,
            "euclidean_common_rhr": np.nan, "cosine_common_rhr": np.nan,
            "pearson_common_rhr": np.nan, "spearman_common_rhr": np.nan,
            "mean_abs_difference": np.nan, "median_abs_difference": np.nan,
            "max_abs_difference": np.nan, "overlap_gate_pass": False,
        }, detail
    difference = av - bv
    norm_a, norm_b = float(np.linalg.norm(av)), float(np.linalg.norm(bv))
    return {
        "matched_features": int(len(feature_ids)),
        "matched_targets": targets,
        "rms_common_rhr": float(np.sqrt(np.mean(difference**2))),
        "euclidean_common_rhr": float(np.linalg.norm(difference)),
        "cosine_common_rhr": float(np.dot(av, bv) / (norm_a * norm_b)) if norm_a > 0 and norm_b > 0 else np.nan,
        "pearson_common_rhr": _correlation(av, bv, "pearson"),
        "spearman_common_rhr": _correlation(av, bv, "spearman"),
        "mean_abs_difference": float(np.mean(np.abs(difference))),
        "median_abs_difference": float(np.median(np.abs(difference))),
        "max_abs_difference": float(np.max(np.abs(difference))),
        "overlap_gate_pass": bool(len(feature_ids) >= PAIR_GATE_FEATURES and targets >= PAIR_GATE_TARGETS),
    }, detail


def build_profile_matrices(profiles: pd.DataFrame, contract: pd.DataFrame, drugs: list[str]) -> dict[str, pd.DataFrame]:
    """Pivot long profiles into governed raw, common-scale, and support matrices.

    Parameters
    ----------
    profiles
        Long compound-feature table with ``raw_hr`` and ``common_rhr`` values.
    contract
        Feature contract providing deterministic ``feature_order``.
    drugs
        Required compound row order.

    Returns
    -------
    dict[str, pandas.DataFrame]
        ``raw_hr``, ``common_rhr``, and binary observed-support matrices.

    Notes
    -----
    The support matrix marks observed raw HR coordinates; it is not a
    fingerprint call matrix.
    """

    features = contract.sort_values("feature_order")["feature_id"].astype(str).tolist()
    raw = profiles.pivot(index="drug", columns="feature_id", values="raw_hr").reindex(index=drugs, columns=features)
    common = profiles.pivot(index="drug", columns="feature_id", values="common_rhr").reindex(index=drugs, columns=features)
    return {"raw_hr": raw, "common_rhr": common, "support": raw.notna().astype(int)}


def all_pairwise(
    matrices: dict[str, pd.DataFrame],
    contract: pd.DataFrame,
    drugs: list[str],
    call_metrics_function,
) -> tuple[pd.DataFrame, dict[tuple[str, str], pd.DataFrame]]:
    """Evaluate every unordered compound pair in deterministic roster order.

    Parameters
    ----------
    matrices
        Profile matrices from :func:`build_profile_matrices`.
    contract
        Feature metadata used by continuous and call-level calculations.
    drugs
        Compound roster whose list order governs pair enumeration.
    call_metrics_function
        Callable accepting two compound labels and returning sparse-call
        metrics to append to each pair.

    Returns
    -------
    tuple[pandas.DataFrame, dict]
        One row per unordered pair and coordinate-detail frames keyed by pair.

    Notes
    -----
    Support Jaccard compares availability, not fingerprint membership. An empty
    support union has identity value 1 by convention.
    """

    rows: list[dict[str, Any]] = []
    details: dict[tuple[str, str], pd.DataFrame] = {}
    common = matrices["common_rhr"]
    support = matrices["support"]
    for a, b in combinations(drugs, 2):
        metrics, detail = continuous_metrics(common.loc[a], common.loc[b], contract)
        details[(a, b)] = detail
        support_a = set(support.columns[support.loc[a].eq(1)])
        support_b = set(support.columns[support.loc[b].eq(1)])
        # Availability overlap is reported separately from GESD call overlap;
        # it must not be interpreted as a shared pharmacological fingerprint.
        shared, union = support_a & support_b, support_a | support_b
        rows.append({
            "drug_a": a,
            "drug_b": b,
            **metrics,
            "support_shared_features": len(shared),
            "support_union_features": len(union),
            "support_jaccard": len(shared) / len(union) if union else 1.0,
            **call_metrics_function(a, b),
        })
    return pd.DataFrame(rows), details


def metric_matrix(pairwise: pd.DataFrame, metric: str, drugs: list[str]) -> pd.DataFrame:
    """Expand a long pairwise metric into a symmetric roster-ordered matrix.

    Parameters
    ----------
    pairwise
        Unordered-pair table with ``drug_a``, ``drug_b``, and ``metric``.
    metric
        Metric column to expand.
    drugs
        Required row and column order.

    Returns
    -------
    pandas.DataFrame
        Symmetric square matrix. Distance-like diagonals are zero and
        similarity/overlap diagonals are one.
    """

    matrix = pd.DataFrame(np.nan, index=drugs, columns=drugs, dtype=float)
    for drug in drugs:
        if any(token in metric for token in ["rms", "distance", "euclidean"]):
            matrix.loc[drug, drug] = 0.0
        elif any(token in metric for token in ["cosine", "pearson", "spearman", "jaccard", "overlap"]):
            matrix.loc[drug, drug] = 1.0
    for row in pairwise.itertuples(index=False):
        value = getattr(row, metric)
        matrix.loc[row.drug_a, row.drug_b] = value
        matrix.loc[row.drug_b, row.drug_a] = value
    return matrix


def orient_detail(detail: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    """Label a pair-detail table with query and comparator orientation.

    Parameters
    ----------
    detail
        Coordinate-level pair comparison table.
    a
        Query compound label.
    b
        Comparator compound label.

    Returns
    -------
    pandas.DataFrame
        Copy with orientation columns inserted first.
    """

    result = detail.copy()
    result.insert(0, "query_compound", a)
    result.insert(1, "comparator", b)
    return result
