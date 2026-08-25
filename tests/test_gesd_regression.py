"""Test governed and synthetic generalized-ESD upper-tail behavior."""

# SPDX-License-Identifier: MIT

import numpy as np
import pandas as pd
import pytest

from cardozo_ketamine_hr.fingerprint import gesd_upper, regression_calls


@pytest.mark.external_data
def test_gesd_call_regression(governed_paths):
    strict = pd.read_csv(governed_paths["pooled_strict_hr"])
    expected_primary = pd.read_csv(governed_paths["pooled_calls_001"])
    expected_sensitivity = pd.read_csv(governed_paths["pooled_calls_0001"])
    observed_primary = regression_calls(strict, 0.001)
    observed_sensitivity = regression_calls(strict, 0.0001)
    assert len(observed_primary) == 19
    assert len(observed_sensitivity) == 14
    assert set(observed_primary["feature_id"]) == set(expected_primary["feature_id"])
    assert set(observed_sensitivity["feature_id"]) == set(expected_sensitivity["feature_id"])
    assert set(observed_sensitivity["feature_id"]).issubset(set(observed_primary["feature_id"]))


def test_gesd_synthetic_known_upper_outlier():
    values = np.r_[np.linspace(-1.0, 1.0, 100), 100.0]
    called, steps = gesd_upper(values, alpha=0.01, rmax=10)
    assert called == [100]
    assert int(steps.iloc[0]["removed_index"]) == 100
    assert float(steps.iloc[0]["GESD_R"]) > float(steps.iloc[0]["critical_lambda"])


def test_gesd_deterministic_tie_handling_uses_source_order():
    values = np.r_[np.linspace(-1.0, 1.0, 50), 10.0, 10.0]
    first_calls, first_steps = gesd_upper(values, alpha=0.05, rmax=2)
    second_calls, second_steps = gesd_upper(values, alpha=0.05, rmax=2)
    assert first_calls == [50, 51]
    assert second_calls == first_calls
    assert first_steps["removed_index"].tolist() == second_steps["removed_index"].tolist() == [50, 51]


def test_gesd_is_signed_upper_tail_not_absolute_value():
    negative_only = np.r_[np.linspace(-1.0, 1.0, 100), -100.0]
    positive_only = np.r_[np.linspace(-1.0, 1.0, 100), 100.0]
    negative_calls, _ = gesd_upper(negative_only, alpha=0.01, rmax=10)
    positive_calls, _ = gesd_upper(positive_only, alpha=0.01, rmax=10)
    assert negative_calls == []
    assert positive_calls == [100]


@pytest.mark.external_data
def test_gesd_stricter_threshold_is_subset_on_governed_strict18(governed_paths):
    strict = pd.read_csv(governed_paths["pooled_strict_hr"])
    alpha001 = set(regression_calls(strict, 0.001)["feature_id"])
    alpha0001 = set(regression_calls(strict, 0.0001)["feature_id"])
    assert alpha0001
    assert alpha0001.issubset(alpha001)


def test_gesd_has_no_fixed_twenty_call_cap():
    values = np.r_[np.linspace(-1.0, 1.0, 500), np.full(30, 10.0)]
    called, _ = gesd_upper(values, alpha=0.001)
    assert len(called) == 30
    assert called == list(range(500, 530))
