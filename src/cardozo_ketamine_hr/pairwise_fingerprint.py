"""Build sparse fingerprint matrices and primary pairwise call metrics.

Purpose
-------
Encode tested calls without conflating unsupported coordinates and compare two
compound fingerprints at feature, target, and tissue levels.

Scientific stage
----------------
This primary sparse-fingerprint analysis follows GESD calling and feeds global
pairwise, nearest-reference, and multivariate summaries.

Primary inputs
--------------
Raw-HR support matrices, call tables at both governed alpha levels, the feature
contract, and the compound roster.

Primary outputs
---------------
Binary and signed-score call matrices plus Jaccard, overlap, jointly-tested,
and signed sparse-cosine metrics.

Side effects
------------
None; matrices are newly allocated and no files are written.

Invariants
----------
``1`` means called, ``0`` means tested non-call, and ``NaN`` means unsupported.
Call-set comparisons never zero-fill unsupported coordinates, and alpha levels
remain separate.

Execution lane
--------------
Used by Smoke synthetic metric checks and by Verify/Full pairwise regeneration.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def build_call_matrices(
    raw: pd.DataFrame,
    calls001: pd.DataFrame,
    calls0001: pd.DataFrame,
    contract: pd.DataFrame,
    drugs: list[str],
) -> dict[str, pd.DataFrame]:
    """Construct binary and signed call matrices at both governed alpha levels.

    Parameters
    ----------
    raw
        Compound-by-feature raw-HR matrix whose nonmissing cells define tested
        support.
    calls001, calls0001
        GESD call rows for alpha 0.001 and 0.0001.
    contract
        Feature contract providing deterministic feature order.
    drugs
        Required compound row order.

    Returns
    -------
    dict[str, pandas.DataFrame]
        Binary and signed-score matrices for both alpha levels.

    Notes
    -----
    Supported coordinates initialize to zero (tested non-call); unsupported
    coordinates remain ``NaN``. Called coordinates become one in binary
    matrices and carry common-RHR, or raw HR as fallback, in score matrices.
    """

    features = contract.sort_values("feature_order")["feature_id"].astype(str).tolist()

    def one(calls: pd.DataFrame, score: bool) -> pd.DataFrame:
        """Build one alpha-specific binary or signed-score call matrix."""

        matrix = pd.DataFrame(np.nan, index=drugs, columns=features, dtype=float)
        for drug in drugs:
            tested = raw.columns[raw.loc[drug].notna()]
            # Zero is assigned only where raw HR proves the coordinate was
            # tested. NaN continues to mean unsupported/not tested.
            matrix.loc[drug, tested] = 0.0
        for row in calls.itertuples(index=False):
            drug = str(row.drug)
            feature = str(row.feature_id_common)
            if drug not in matrix.index or feature not in matrix.columns:
                continue
            value = 1.0
            if score:
                common = getattr(row, "common_rhr", np.nan)
                raw_hr = getattr(row, "raw_hr", getattr(row, "hr_numeric_collapsed", np.nan))
                value = float(common) if np.isfinite(common) else float(raw_hr)
            matrix.loc[drug, feature] = value
        return matrix

    return {
        "call_binary_alpha001": one(calls001, False),
        "call_score_alpha001": one(calls001, True),
        "call_binary_alpha0001": one(calls0001, False),
        "call_score_alpha0001": one(calls0001, True),
    }


def one_alpha(a: str, b: str, binary: pd.DataFrame, score: pd.DataFrame, contract: pd.DataFrame) -> dict[str, Any]:
    """Compare one pair of fingerprints at a single alpha level.

    Parameters
    ----------
    a, b
        Compound labels indexing the matrices.
    binary
        Call matrix using 1/0/``NaN`` for call/non-call/unsupported.
    score
        Signed call-score matrix aligned to ``binary``.
    contract
        Feature metadata containing target and tissue labels.

    Returns
    -------
    dict[str, Any]
        Feature, target, tissue, jointly-tested, and signed-score comparison
        metrics plus explicit shared and exclusive feature lists.

    Notes
    -----
    Ordinary call Jaccard uses the union of called features, while the
    jointly-tested variant first restricts to coordinates observed for both
    compounds. Empty unions have identity value 1. The overlap coefficient
    divides by the smaller nonempty call set.
    """

    qa, qb = binary.loc[a], binary.loc[b]
    calls_a = set(qa.index[qa.eq(1.0)])
    calls_b = set(qb.index[qb.eq(1.0)])
    shared, union = calls_a & calls_b, calls_a | calls_b
    # The overlap coefficient asks whether the smaller call set is contained in
    # the larger; it is distinct from union-normalized Jaccard similarity.
    overlap = len(shared) / min(len(calls_a), len(calls_b)) if calls_a and calls_b else (1.0 if not calls_a and not calls_b else 0.0)
    metadata = contract.set_index("feature_id")
    targets_a = set(metadata.loc[list(calls_a), "target"]) if calls_a else set()
    targets_b = set(metadata.loc[list(calls_b), "target"]) if calls_b else set()
    target_union, target_shared = targets_a | targets_b, targets_a & targets_b
    tissues_a = set(metadata.loc[list(calls_a), "tissue"]) if calls_a else set()
    tissues_b = set(metadata.loc[list(calls_b), "tissue"]) if calls_b else set()
    tissue_union, tissue_shared = tissues_a | tissues_b, tissues_a & tissues_b
    # Signed sparse cosine is evaluated on the called-feature union. A compound
    # contributes zero where only its counterpart called, while unsupported
    # coordinates outside the union never enter the calculation.
    features = sorted(union)
    sparse_cosine = np.nan
    if features:
        av = np.array([score.loc[a, f] if f in calls_a and np.isfinite(score.loc[a, f]) else 0.0 for f in features], dtype=float)
        bv = np.array([score.loc[b, f] if f in calls_b and np.isfinite(score.loc[b, f]) else 0.0 for f in features], dtype=float)
        norms = float(np.linalg.norm(av) * np.linalg.norm(bv))
        if norms > 0:
            sparse_cosine = float(np.dot(av, bv) / norms)
    # This mask distinguishes tested non-calls (0) from unsupported cells (NA)
    # before computing the matched-support call Jaccard.
    jointly_tested = qa.notna() & qb.notna()
    joint_a = set(qa.index[jointly_tested & qa.eq(1.0)])
    joint_b = set(qb.index[jointly_tested & qb.eq(1.0)])
    joint_union = joint_a | joint_b
    return {
        "call_count_a": len(calls_a),
        "call_count_b": len(calls_b),
        "shared_calls": len(shared),
        "union_calls": len(union),
        "call_jaccard": len(shared) / len(union) if union else 1.0,
        "call_overlap_coefficient": overlap,
        "jointly_tested_call_jaccard": len(joint_a & joint_b) / len(joint_union) if joint_union else 1.0,
        "shared_called_targets": len(target_shared),
        "union_called_targets": len(target_union),
        "target_call_jaccard": len(target_shared) / len(target_union) if target_union else 1.0,
        "shared_called_tissues": len(tissue_shared),
        "union_called_tissues": len(tissue_union),
        "tissue_call_jaccard": len(tissue_shared) / len(tissue_union) if tissue_union else 1.0,
        "signed_sparse_cosine": sparse_cosine,
        "shared_feature_ids": "; ".join(sorted(shared)),
        "query_only_feature_ids": "; ".join(sorted(calls_a - calls_b)),
        "comparator_only_feature_ids": "; ".join(sorted(calls_b - calls_a)),
    }


def metric_function(matrices: dict[str, pd.DataFrame], contract: pd.DataFrame):
    """Create a pair-metric callback bound to call matrices and metadata.

    Parameters
    ----------
    matrices
        Binary and signed-score matrices from :func:`build_call_matrices`.
    contract
        Feature metadata shared by both alpha-level comparisons.

    Returns
    -------
    callable
        Function accepting two compound labels and returning metrics prefixed
        by ``alpha001_`` and ``alpha0001_``.
    """

    def calculate(a: str, b: str) -> dict[str, Any]:
        """Calculate and prefix both governed alpha-level metric bundles."""

        primary = one_alpha(a, b, matrices["call_binary_alpha001"], matrices["call_score_alpha001"], contract)
        strict = one_alpha(a, b, matrices["call_binary_alpha0001"], matrices["call_score_alpha0001"], contract)
        return {
            **{f"alpha001_{key}": value for key, value in primary.items()},
            **{f"alpha0001_{key}": value for key, value in strict.items()},
        }
    return calculate
