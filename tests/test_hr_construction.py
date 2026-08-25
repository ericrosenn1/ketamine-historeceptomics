"""Test HR construction, frozen equivalence, dimensions, and missingness."""

# SPDX-License-Identifier: MIT

import numpy as np
import pandas as pd
import pytest
import yaml

from cardozo_ketamine_hr.hr import construct_hr_scores


def _load_inputs(data_root):
    """Load the governed activity and expression authorities from external data."""

    activity = pd.read_csv(data_root / "core" / "pooled_target_activity.csv", low_memory=False)
    expression = pd.read_parquet(data_root / "core" / "pooled_expression58.parquet")
    return activity, expression


@pytest.mark.external_data
def test_full77_hr_dimensions_and_values_match_frozen_authority(governed_paths):
    activity, expression = _load_inputs(governed_paths["external_input_root"])
    regenerated = construct_hr_scores(activity, expression)
    authority = pd.read_parquet(governed_paths["pooled_full_hr"])
    observed = regenerated[["canonical_target_id", "tissue_id", "hr_score"]].merge(
        authority[["canonical_target_id", "tissue_id", "HR_numeric_boundary_or_exact"]],
        on=["canonical_target_id", "tissue_id"],
        how="outer",
        validate="one_to_one",
    )
    assert len(observed) == 58 * 77 == 4466
    assert regenerated["canonical_target_id"].nunique() == 58
    assert regenerated["tissue_id"].nunique() == 77
    np.testing.assert_allclose(
        observed["hr_score"], observed["HR_numeric_boundary_or_exact"], rtol=0, atol=1e-12
    )


@pytest.mark.external_data
def test_strict18_hr_dimensions_and_identifiers(governed_paths):
    root = governed_paths["project_root"]
    activity, expression = _load_inputs(governed_paths["external_input_root"])
    regenerated = construct_hr_scores(activity, expression)
    config = yaml.safe_load((root / "configs/tissues_cns18.yaml").read_text(encoding="utf-8"))
    strict_ids = {item["tissue_id"] for item in config["tissues"]}
    strict = regenerated[regenerated["tissue_id"].isin(strict_ids)]
    assert strict.shape[0] == 58 * 18 == 1044
    assert strict["feature_id"].is_unique
    assert set(strict["tissue_id"]) == strict_ids


def test_hr_missing_activity_remains_missing_not_zero():
    activity = pd.DataFrame(
        {"canonical_target_id": ["A"], "final_selected_pActivity_v4": [np.nan]}
    )
    expression = pd.DataFrame(
        {"canonical_target_id": ["A"], "tissue_id": ["T1"], "expression_z": [2.0]}
    )
    result = construct_hr_scores(activity, expression)
    assert np.isnan(result.loc[0, "hr_score"])


def test_conflicting_activity_duplicates_fail_clearly():
    activity = pd.DataFrame(
        {"canonical_target_id": ["A", "A"], "final_selected_pActivity_v4": [6.0, 7.0]}
    )
    expression = pd.DataFrame(
        {"canonical_target_id": ["A"], "tissue_id": ["T1"], "expression_z": [2.0]}
    )
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        construct_hr_scores(activity, expression)
