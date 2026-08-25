# SPDX-License-Identifier: MIT
"""Orient query pairs and summarize nearest reference compounds.

Stage
-----
Nearest-reference summaries are derived after the unordered pairwise metric
table and class registry have passed QA.

Inputs
------
Functions consume in-memory pairwise metrics, a governed query identity, and
optional eligibility or class memberships.

Outputs
-------
Returned pandas tables contain query-oriented pairs or ranked nearest-neighbor
summaries; no files are written.

Side Effects
------------
None.

Invariants
----------
The unordered source metrics are not recomputed, eligibility is applied only to
comparators, and lower RMS but higher similarity values define nearest status.

Lane
----
Portable pairwise interpretation lane.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def orient_query_pairs(pairwise: pd.DataFrame, query: str, eligible: set[str] | None = None) -> pd.DataFrame:
    """Orient unordered pairwise rows toward one query compound.

    Parameters
    ----------
    pairwise : pandas.DataFrame
        Unordered pair table containing ``drug_a`` and ``drug_b``.
    query : str
        Query identity to select.
    eligible : set of str, optional
        Allowed comparator identities.

    Returns
    -------
    pandas.DataFrame
        Defensive copy of query rows with a normalized ``comparator`` column.
    """
    selected = pairwise[(pairwise["drug_a"].eq(query)) | (pairwise["drug_b"].eq(query))].copy()
    selected["comparator"] = np.where(selected["drug_a"].eq(query), selected["drug_b"], selected["drug_a"])
    if eligible is not None:
        selected = selected[selected["comparator"].isin(eligible)].copy()
    return selected


def nearest_summary(pairwise: pd.DataFrame, query: str, eligible: set[str]) -> pd.DataFrame:
    """Summarize nearest and runner-up comparators across governed metrics.

    Parameters
    ----------
    pairwise : pandas.DataFrame
        Unordered pairwise metrics.
    query : str
        Query identity.
    eligible : set of str
        Comparator roster eligible for ranking.

    Returns
    -------
    pandas.DataFrame
        One row per metric with nearest value, runner-up, absolute margin, and
        explicit estimability status.
    """
    selected = orient_query_pairs(pairwise, query, eligible)
    metrics = [
        ("rms_common_rhr", True, "RMS"),
        ("cosine_common_rhr", False, "COSINE"),
        ("spearman_common_rhr", False, "SPEARMAN"),
        ("alpha001_call_jaccard", False, "FINGERPRINT_JACCARD"),
        ("support_jaccard", False, "SUPPORT_JACCARD"),
    ]
    rows = []
    for column, ascending, label in metrics:
        # RMS is a distance and is minimized; similarities are maximized.
        values = selected.dropna(subset=[column]).sort_values(column, ascending=ascending)
        if values.empty:
            rows.append({"metric": label, "nearest_comparator": "", "nearest_value": np.nan, "runner_up": "", "runner_up_value": np.nan, "margin": np.nan, "status": "NOT_ESTIMABLE"})
            continue
        first = values.iloc[0]
        second = values.iloc[1] if len(values) > 1 else None
        margin = abs(float(first[column]) - float(second[column])) if second is not None else np.nan
        rows.append({"metric": label, "nearest_comparator": first["comparator"], "nearest_value": first[column], "runner_up": second["comparator"] if second is not None else "", "runner_up_value": second[column] if second is not None else np.nan, "margin": margin, "status": "PASS"})
    return pd.DataFrame(rows)


def class_nearest(pairwise: pd.DataFrame, query: str, classes: pd.DataFrame) -> pd.DataFrame:
    """Identify the nearest RMS comparator within each drug class.

    Parameters
    ----------
    pairwise : pandas.DataFrame
        Unordered pairwise metrics containing ``rms_common_rhr``.
    query : str
        Query identity.
    classes : pandas.DataFrame
        Membership table with class IDs, labels, and drug identities.

    Returns
    -------
    pandas.DataFrame
        One row per class with nearest comparator, RMS, within-class percentile,
        margin, and estimability status.
    """
    selected = orient_query_pairs(pairwise, query)
    rows = []
    for class_id, membership in classes.groupby("class_id"):
        candidates = selected[selected["comparator"].isin(set(membership["drug"]))].dropna(subset=["rms_common_rhr"])
        candidates = candidates.sort_values("rms_common_rhr")
        if candidates.empty:
            rows.append({"class_id": class_id, "class_label": membership["class_label"].iloc[0], "status": "NOT_ESTIMABLE", "nearest_comparator": "", "rms_common_rhr": np.nan, "distance_percentile_within_class": np.nan, "nearest_neighbor_margin": np.nan})
            continue
        first = candidates.iloc[0]
        margin = float(candidates.iloc[1]["rms_common_rhr"] - first["rms_common_rhr"]) if len(candidates) > 1 else np.nan
        rows.append({"class_id": class_id, "class_label": membership["class_label"].iloc[0], "status": "PASS", "nearest_comparator": first["comparator"], "rms_common_rhr": first["rms_common_rhr"], "distance_percentile_within_class": float(candidates["rms_common_rhr"].rank(pct=True).iloc[0]), "nearest_neighbor_margin": margin})
    return pd.DataFrame(rows)
