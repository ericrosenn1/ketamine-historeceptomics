# SPDX-License-Identifier: MIT
"""Aggregate recurrent query residuals across pairwise comparisons.

Stage
-----
Residual recurrence is derived after feature-level pair details have been
computed and oriented pairwise metrics have passed QA.

Inputs
------
The input mapping contains feature-level detail tables keyed by unordered
compound pairs, plus the governed query identity.

Outputs
-------
Target- and tissue-level recurrence tables are returned in memory.

Side Effects
------------
None.

Invariants
----------
Every retained comparison is oriented as query minus comparator, source detail
tables are copied before orientation, and missing comparisons are not filled.

Lane
----
Portable pairwise residual-synthesis lane.
"""

from __future__ import annotations

import pandas as pd

from .tables import target_summary, tissue_summary


def recurrence(details: dict[tuple[str, str], pd.DataFrame], query: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate target and tissue residual recurrence for a query.

    Parameters
    ----------
    details : dict of tuple to pandas.DataFrame
        Feature-level pair details keyed by ``(drug_a, drug_b)``.
    query : str
        Query identity to orient as side ``a``.

    Returns
    -------
    target : pandas.DataFrame
        Target-level comparator counts and residual summaries.
    tissue : pandas.DataFrame
        Tissue-level comparator counts and residual summaries.

    Notes
    -----
    Pairs that do not contain ``query`` are ignored. Empty eligible input yields
    empty target and tissue tables.
    """
    target_rows = []
    tissue_rows = []
    for (a, b), detail in details.items():
        if query not in {a, b}:
            continue
        oriented = detail.copy()
        comparator = b if a == query else a
        if b == query:
            # The persisted pair may store the query on side b; swap values and
            # invert the signed difference to preserve query-minus-comparator.
            oriented["signed_difference_a_minus_b"] *= -1
            oriented[["value_a", "value_b"]] = oriented[["value_b", "value_a"]].to_numpy()
        targets = target_summary(oriented)
        targets["comparator"] = comparator
        target_rows.append(targets)
        tissues = tissue_summary(oriented)
        tissues["comparator"] = comparator
        tissue_rows.append(tissues)
    target = pd.concat(target_rows, ignore_index=True) if target_rows else pd.DataFrame()
    tissue = pd.concat(tissue_rows, ignore_index=True) if tissue_rows else pd.DataFrame()
    if len(target):
        target = target.groupby("target", as_index=False).agg(comparator_count=("comparator", "nunique"), mean_difference=("mean_difference", "mean"), median_difference=("mean_difference", "median"), mean_absolute_difference=("mean_absolute_difference", "mean"), positive_comparator_count=("mean_difference", lambda x: int((x > 0).sum())), negative_comparator_count=("mean_difference", lambda x: int((x < 0).sum()))).sort_values("mean_absolute_difference", ascending=False)
    if len(tissue):
        tissue = tissue.groupby("tissue", as_index=False).agg(comparator_count=("comparator", "nunique"), mean_difference=("mean_difference", "mean"), median_difference=("mean_difference", "median"), mean_absolute_difference=("mean_absolute_difference", "mean"), positive_comparator_count=("mean_difference", lambda x: int((x > 0).sum())), negative_comparator_count=("mean_difference", lambda x: int((x < 0).sum()))).sort_values("mean_absolute_difference", ascending=False)
    return target, tissue
