"""Test exact sparse heatmap call counts for the governed strict-CNS lane."""

# SPDX-License-Identifier: MIT

import pandas as pd
import pytest

from cardozo_ketamine_hr.fingerprint import build_sparse_call_matrix


@pytest.mark.external_data
def test_corrected_heatmap_call_counts(governed_paths):
    strict = pd.read_csv(governed_paths["pooled_strict_hr"])
    targets = strict["canonical_target_id"].drop_duplicates().tolist()
    tissues = strict.sort_values("tissue_display_order")["tissue_label"].drop_duplicates().tolist()
    primary = build_sparse_call_matrix(pd.read_csv(governed_paths["pooled_calls_001"]), targets, tissues)
    sensitivity = build_sparse_call_matrix(pd.read_csv(governed_paths["pooled_calls_0001"]), targets, tissues)
    assert int(primary.notna().sum().sum()) == 19
    assert int(sensitivity.notna().sum().sum()) == 14
    assert list(primary.columns) == list(sensitivity.columns)
