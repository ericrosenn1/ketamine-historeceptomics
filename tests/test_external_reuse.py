"""Test exact recomputation of pairwise results from prior external profiles."""

# SPDX-License-Identifier: MIT

import numpy as np
import pandas as pd
import pytest

from cardozo_ketamine_hr.pairwise_continuous import all_pairwise, build_profile_matrices
from cardozo_ketamine_hr.pairwise_fingerprint import build_call_matrices, metric_function
from cardozo_ketamine_hr.query_freeze import feature_contracts


@pytest.mark.external_data
def test_external_only_recomputation_equals_validated_baseline(governed_paths):
    profiles = pd.read_parquet(governed_paths["prior_profiles"])
    external = [drug for drug in profiles["drug"].drop_duplicates() if drug != "S-ketamine"]
    profiles = profiles[profiles["drug"].isin(external)]
    _, contract = feature_contracts(governed_paths["feature_dictionary"])
    matrices = build_profile_matrices(profiles, contract, external)
    primary = pd.read_parquet(governed_paths["prior_calls_001"])
    sensitivity = pd.read_parquet(governed_paths["prior_calls_0001"])
    for frame in (primary, sensitivity):
        frame["feature_id_common"] = frame["feature_id"]
    calls = build_call_matrices(matrices["raw_hr"], primary[primary["drug"].isin(external)], sensitivity[sensitivity["drug"].isin(external)], contract, external)
    recomputed, _ = all_pairwise(matrices, contract, external, metric_function(calls, contract))
    expected = pd.read_parquet(governed_paths["prior_pairwise"])
    expected = expected[expected["drug_a"].isin(external) & expected["drug_b"].isin(external)].reset_index(drop=True)
    assert len(recomputed) == len(expected) == 300
    for column in expected.select_dtypes(include=[np.number]).columns:
        assert np.allclose(recomputed[column], expected[column], rtol=0, atol=1e-10, equal_nan=True), column
