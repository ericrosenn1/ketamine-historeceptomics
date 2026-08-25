"""Test dimensions and missingness of excluded pooled-parent authorities."""

# SPDX-License-Identifier: MIT

import pandas as pd
import pytest


@pytest.mark.external_data
def test_pooled_authority_counts_and_missingness(governed_paths):
    full = pd.read_parquet(governed_paths["pooled_full_hr"])
    strict = pd.read_csv(governed_paths["pooled_strict_hr"])
    missing = pd.read_csv(governed_paths["pooled_missing_expression"])
    assert (full["canonical_target_id"].nunique(), full["tissue_id"].nunique(), len(full)) == (58, 77, 4466)
    assert (strict["canonical_target_id"].nunique(), strict["tissue_id"].nunique(), len(strict)) == (58, 18, 1044)
    assert missing["canonical_target_id"].nunique() == 18
    assert strict["hr_numeric_collapsed"].notna().all()
