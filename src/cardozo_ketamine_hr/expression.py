"""Standardize tissue expression within genes and validate panel contracts.

Purpose
-------
Create the expression component used in target-by-tissue historeceptomic
scores while retaining the observed missing-data pattern.

Scientific stage
----------------
This module implements expression preprocessing immediately before HR-score
construction.

Primary inputs
--------------
Long-form expression tables with gene, tissue, and raw-expression columns,
plus expected target and tissue counts for validation.

Primary outputs
---------------
Copies of expression tables with within-gene z-scores and validation failures
when a panel violates its governed schema or dimensions.

Side effects
------------
None; input frames are not mutated and no files are written.

Invariants
----------
Standardization uses the requested degrees of freedom (governed analyses use
``ddof=1``), never fills missing observations, and rejects duplicate or
nonfinite target-tissue coordinates in a completed authority panel.

Execution lane
--------------
Used by scientific unit tests and by recovered Full expression processing.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import numpy as np
import pandas as pd


def standardize_within_gene(
    frame: pd.DataFrame,
    *,
    gene_col: str = "gene_symbol",
    value_col: str = "raw_expression",
    output_col: str = "expression_z",
    ddof: int = 1,
) -> pd.DataFrame:
    """Compute within-gene expression z-scores without filling missing values.

    Parameters
    ----------
    frame
        Long-form expression observations.
    gene_col
        Column defining the gene-specific standardization groups.
    value_col
        Raw numeric expression column.
    output_col
        Destination column for standardized expression values.
    ddof
        Degrees of freedom used for the within-gene standard deviation. The
        governed analysis uses ``1`` for the sample standard deviation.

    Returns
    -------
    pandas.DataFrame
        Copy of ``frame`` with ``output_col`` added.

    Raises
    ------
    ValueError
        If ``ddof`` is negative or required input columns are absent.

    Notes
    -----
    Groups without enough finite observations, or with zero/nonfinite sample
    standard deviation, receive ``NaN`` z-scores. Existing missing values are
    never replaced with zero.
    """

    if ddof < 0:
        raise ValueError("ddof must be nonnegative")
    missing = [column for column in (gene_col, value_col) if column not in frame.columns]
    if missing:
        raise ValueError(f"Expression input is missing columns: {missing}")
    result = frame.copy()
    values = pd.to_numeric(result[value_col], errors="coerce")

    def zscore(group: pd.Series) -> pd.Series:
        """Standardize one gene group over only its finite observations."""

        finite = group[np.isfinite(group.to_numpy(dtype=float, na_value=np.nan))]
        if len(finite) <= ddof:
            return pd.Series(np.nan, index=group.index, dtype=float)
        # The governed expression authority uses the sample SD (ddof=1), not
        # the population SD; callers may supply another explicitly tested ddof.
        sd = float(finite.std(ddof=ddof))
        if not math_is_finite_positive(sd):
            return pd.Series(np.nan, index=group.index, dtype=float)
        # Pandas aligns the finite-group mean/SD to the original indices, so
        # missing source observations remain missing in the returned series.
        return (group - float(finite.mean())) / sd

    result[output_col] = values.groupby(result[gene_col], sort=False, dropna=False).transform(zscore)
    return result


def math_is_finite_positive(value: float) -> bool:
    """Return whether a scalar is finite and strictly positive.

    Parameters
    ----------
    value
        Scalar value to test.

    Returns
    -------
    bool
        ``True`` only for finite values greater than zero.
    """

    return bool(np.isfinite(value) and value > 0.0)


def validate_expression_panel(
    frame: pd.DataFrame,
    *,
    expected_targets: int,
    expected_tissues: int,
    target_col: str = "canonical_target_id",
    tissue_col: str = "tissue_id",
    value_col: str = "expression_z",
) -> None:
    """Validate a completed target-by-tissue expression authority.

    Parameters
    ----------
    frame
        Expression panel to validate.
    expected_targets
        Required number of distinct canonical targets.
    expected_tissues
        Required number of distinct tissues.
    target_col, tissue_col, value_col
        Column names defining the coordinate key and standardized value.

    Returns
    -------
    None
        Returns only when every schema, dimension, uniqueness, and finiteness
        check passes.

    Raises
    ------
    ValueError
        If required columns, dimensions, coordinate uniqueness, row count, or
        standardized-value finiteness violate the panel contract.
    """

    required = {target_col, tissue_col, value_col}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Expression authority is missing columns: {missing}")
    if frame[target_col].nunique() != expected_targets:
        raise ValueError("Unexpected target count in expression panel")
    if frame[tissue_col].nunique() != expected_tissues:
        raise ValueError("Unexpected tissue count in expression panel")
    if frame.duplicated([target_col, tissue_col]).any():
        raise ValueError("Duplicate target-tissue expression coordinates")
    expected_rows = expected_targets * expected_tissues
    if len(frame) != expected_rows:
        raise ValueError(f"Expected {expected_rows} expression coordinates; found {len(frame)}")
    if not np.isfinite(pd.to_numeric(frame[value_col], errors="coerce")).all():
        raise ValueError("Expression panel contains nonfinite standardized values")
