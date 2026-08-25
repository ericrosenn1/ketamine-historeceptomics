"""Test activity-unit normalization and governed selected-activity states."""

# SPDX-License-Identifier: MIT

import math

import pandas as pd
import pytest

from cardozo_ketamine_hr.activity import normalize_activity


def test_exact_activity_unit_normalization():
    result = normalize_activity(100, "nM", "=")
    assert result.relation_class == "EXACT"
    assert result.relation_operator == "="
    assert math.isclose(result.molar_boundary_or_exact, 1e-7)
    assert result.pactivity_boundary_or_exact == 7.0
    assert result.is_bounded is False


def test_bounded_activity_preserves_reported_boundary_and_operator():
    result = normalize_activity(10_000, "nM", ">")
    assert result.reported_value == 10_000
    assert result.relation_operator == ">"
    assert result.relation_class == "GT_BOUND"
    assert result.is_bounded is True
    assert math.isclose(result.molar_boundary_or_exact, 1e-5)
    assert result.pactivity_boundary_or_exact == 5.0


def test_zero_or_missing_activity_is_not_imputed():
    assert math.isnan(normalize_activity(0, "nM", "=").pactivity_boundary_or_exact)
    assert math.isnan(normalize_activity(None, "nM", "=").pactivity_boundary_or_exact)


@pytest.mark.external_data
def test_frozen_selected_activity_retains_exact_and_bounded_states(governed_paths):
    activity = pd.read_csv(
        governed_paths["pooled_activity"],
        low_memory=False,
    )
    assert len(activity) == 76
    assert activity["canonical_target_id"].is_unique
    assert activity["final_selected_pActivity_v4"].notna().all()
    assert activity["final_hr_input_status_v4"].value_counts().to_dict() == {
        "READY_EXACT": 40,
        "READY_BOUNDED_RELATION_PRESERVED": 36,
    }
    bounded = activity["final_selected_activity_is_bounded_v4"].astype(bool)
    assert set(activity.loc[bounded, "final_activity_relation_class_v4"]) == {"GT_BOUND"}
    assert set(activity.loc[~bounded, "final_activity_relation_class_v4"]) == {"EXACT"}
