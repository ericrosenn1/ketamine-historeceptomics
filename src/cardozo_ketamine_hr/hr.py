"""Construct deterministic target-by-tissue historeceptomic (HR) scores.

Purpose
-------
Join governed target-level activity to standardized tissue expression and
calculate one HR value per exact target-tissue coordinate.

Scientific stage
----------------
This is the HR-construction stage between activity/expression preprocessing and
fingerprint calling.

Primary inputs
--------------
Target-level ``pActivity`` records and long-form target-tissue expression
z-scores, optionally carrying activity relation operators.

Primary outputs
---------------
A deterministically ordered long table containing source columns, unique
feature identifiers, and the activity-by-expression HR product.

Side effects
------------
None; inputs are copied and no files are written.

Invariants
----------
Only identical duplicates may collapse, missing activity or expression remains
missing, relation metadata is retained, and every feature ID is unique.

Execution lane
--------------
Used by unit/regression tests and HR equivalence checks in Smoke, Verify, and
the recovered Full lane.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import numpy as np
import pandas as pd


def _collapse_identical_duplicates(
    frame: pd.DataFrame,
    *,
    keys: list[str],
    compared_columns: list[str],
) -> pd.DataFrame:
    """Collapse duplicate keys only when governed values are identical.

    Parameters
    ----------
    frame
        Input records that may contain duplicate key combinations.
    keys
        Columns defining record identity.
    compared_columns
        Columns that must agree within every duplicate group.

    Returns
    -------
    pandas.DataFrame
        Copy containing one stable first row per identical duplicate group.

    Raises
    ------
    ValueError
        If a duplicate key has conflicting values in any compared column.

    Notes
    -----
    Duplicate collapse is a representation cleanup, not aggregation or
    imputation; conflicts stop the calculation.
    """

    if not frame.duplicated(keys, keep=False).any():
        return frame.copy()
    rows: list[pd.Series] = []
    for _, group in frame.groupby(keys, sort=True, dropna=False):
        for column in compared_columns:
            values = group[column].drop_duplicates()
            if len(values) > 1:
                raise ValueError(f"Conflicting duplicate {keys} values in column {column}")
        rows.append(group.sort_index(kind="stable").iloc[0])
    return pd.DataFrame(rows).reset_index(drop=True)


def construct_hr_scores(
    activity: pd.DataFrame,
    expression: pd.DataFrame,
    *,
    target_col: str = "canonical_target_id",
    tissue_col: str = "tissue_id",
    activity_col: str = "final_selected_pActivity_v4",
    expression_col: str = "expression_z",
    relation_col: str = "final_activity_relation_operator_v4",
    output_col: str = "hr_score",
) -> pd.DataFrame:
    """Calculate HR as target activity multiplied by tissue expression z-score.

    Parameters
    ----------
    activity
        Target-level table containing canonical target IDs and selected
        ``pActivity`` values. A relation-operator column is retained when
        present.
    expression
        Long-form table containing canonical target IDs, tissue IDs, and
        standardized expression values.
    target_col, tissue_col
        Columns forming the exact target-tissue coordinate.
    activity_col
        Numeric exact ``pActivity`` or governed numerical activity boundary.
    expression_col
        Within-gene standardized expression value.
    relation_col
        Optional activity censoring/equality operator to propagate.
    output_col
        Name of the calculated HR column.

    Returns
    -------
    pandas.DataFrame
        Stable target/tissue-sorted HR table with unique ``feature_id`` values.

    Raises
    ------
    ValueError
        If required columns are missing, duplicates conflict, or constructed
        feature identifiers are not unique.

    Notes
    -----
    The calculation is ``pActivity * expression_z``. A bounded ``pActivity``
    remains a numerical boundary with its relation operator attached; it is not
    reinterpreted as an exact affinity. Pandas multiplication preserves missing
    activity or expression as ``NaN`` rather than creating a zero HR score.
    """

    activity_required = {target_col, activity_col}
    expression_required = {target_col, tissue_col, expression_col}
    if missing := sorted(activity_required - set(activity.columns)):
        raise ValueError(f"Activity input is missing columns: {missing}")
    if missing := sorted(expression_required - set(expression.columns)):
        raise ValueError(f"Expression input is missing columns: {missing}")

    activity_columns = [target_col, activity_col]
    if relation_col in activity.columns:
        activity_columns.append(relation_col)
    selected_activity = _collapse_identical_duplicates(
        activity[activity_columns],
        keys=[target_col],
        compared_columns=[column for column in activity_columns if column != target_col],
    )
    selected_expression = _collapse_identical_duplicates(
        expression.copy(),
        keys=[target_col, tissue_col],
        compared_columns=[expression_col],
    )
    merged = selected_expression.merge(
        selected_activity,
        on=target_col,
        how="left",
        validate="many_to_one",
        sort=False,
    )
    activity_values = pd.to_numeric(merged[activity_col], errors="coerce")
    expression_values = pd.to_numeric(merged[expression_col], errors="coerce")
    # Multiplication intentionally propagates NA. Zero is a real calculated HR
    # only when a finite factor is zero, never a placeholder for absent support.
    merged[output_col] = activity_values * expression_values
    merged["feature_id"] = merged[target_col].astype(str) + "||" + merged[tissue_col].astype(str)
    if merged["feature_id"].duplicated().any():
        raise ValueError("Duplicate target-tissue feature identifiers after HR construction")
    return merged.sort_values([target_col, tissue_col], kind="stable").reset_index(drop=True)
