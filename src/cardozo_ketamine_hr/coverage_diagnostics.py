# SPDX-License-Identifier: MIT
"""Diagnose profile support and distance-model coverage.

Stage
-----
Coverage diagnostics run after frozen profiles and pairwise metrics have been
loaded, before comparative results are interpreted or packaged.

Inputs
------
Long-lived in-memory tables use the frozen feature contract and preserve
missing observations as ``NaN``.

Outputs
-------
Functions return tabular coverage summaries or selected confounding columns;
this module writes no files.

Side Effects
------------
None.

Invariants
----------
Missing values are never converted to zero, and target coverage is computed
only from supported feature identifiers in the supplied contract.

Lane
----
Portable analysis and QA lane.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def profile_coverage(raw: pd.DataFrame, contract: pd.DataFrame) -> pd.DataFrame:
    """Summarize feature and target support for each compound profile.

    Parameters
    ----------
    raw : pandas.DataFrame
        Compound-by-feature matrix whose missing cells denote unavailable
        measurements.
    contract : pandas.DataFrame
        Feature contract containing at least ``feature_id`` and ``target``.

    Returns
    -------
    pandas.DataFrame
        One row per compound with supported feature and target counts and
        fractions.

    Notes
    -----
    A feature is supported only when its source value is non-missing.
    """
    targets = contract.set_index("feature_id")["target"]
    rows = []
    for compound in raw.index:
        supported = raw.loc[compound].notna()
        feature_ids = list(raw.columns[supported])
        rows.append({
            "compound": compound,
            "supported_feature_count": int(supported.sum()),
            "total_feature_count": int(len(raw.columns)),
            "feature_coverage_fraction": float(supported.mean()),
            "supported_target_count": int(targets.reindex(feature_ids).nunique()),
            "total_target_count": int(contract["target"].nunique()),
            "target_coverage_fraction": float(targets.reindex(feature_ids).nunique() / contract["target"].nunique()),
        })
    return pd.DataFrame(rows)


def distance_confounding(query_pairs: pd.DataFrame) -> pd.DataFrame:
    """Select support variables used to assess distance confounding.

    Parameters
    ----------
    query_pairs : pandas.DataFrame
        Pairwise results oriented to a query compound.

    Returns
    -------
    pandas.DataFrame
        A defensive copy of the available comparator, coverage, and distance
        columns in their governed display order.
    """
    columns = ["comparator", "matched_features", "matched_targets", "support_jaccard", "rms_common_rhr", "cosine_common_rhr", "spearman_common_rhr"]
    return query_pairs[[column for column in columns if column in query_pairs.columns]].copy()
