"""Test within-gene expression standardization and its frozen panel contract."""

# SPDX-License-Identifier: MIT

import numpy as np
import pandas as pd
import pytest

from cardozo_ketamine_hr.expression import (
    standardize_within_gene,
    validate_expression_panel,
)


def test_expression_standardization_uses_within_gene_sample_sd():
    source = pd.DataFrame(
        {
            "gene_symbol": ["A", "A", "A", "B", "B", "B"],
            "raw_expression": [1.0, 2.0, 3.0, 5.0, 5.0, 5.0],
        }
    )
    result = standardize_within_gene(source, ddof=1)
    np.testing.assert_allclose(result.loc[:2, "expression_z"], [-1.0, 0.0, 1.0])
    assert result.loc[3:, "expression_z"].isna().all()


def test_expression_standardization_preserves_missingness():
    source = pd.DataFrame(
        {"gene_symbol": ["A", "A", "A"], "raw_expression": [1.0, np.nan, 3.0]}
    )
    result = standardize_within_gene(source, ddof=1)
    assert np.isclose(result.loc[0, "expression_z"], -np.sqrt(0.5))
    assert np.isnan(result.loc[1, "expression_z"])
    assert np.isclose(result.loc[2, "expression_z"], np.sqrt(0.5))


@pytest.mark.external_data
def test_frozen_expression_panel_is_58_by_77_ddof1(governed_paths):
    expression = pd.read_parquet(governed_paths["pooled_expression"])
    validate_expression_panel(expression, expected_targets=58, expected_tissues=77)
    grouped = expression.groupby("canonical_target_id")["expression_z"].agg(["mean", "std"])
    np.testing.assert_allclose(grouped["mean"], 0.0, atol=1e-12)
    np.testing.assert_allclose(grouped["std"], 1.0, atol=1e-12)
    assert set(expression["expression_recovery_source"]) <= {
        "HR_V1_EXISTING_AUTHORITY_EXPRESSION",
        "FROZEN_FINAL_FEATURE_DICTIONARY",
        "LEGACY_CLEANED_BIOGPS_RECOMPUTED_DDOF1",
    }
