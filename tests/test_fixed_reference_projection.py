"""Test that query projection cannot refit the frozen reference PCA axes."""

# SPDX-License-Identifier: MIT

import numpy as np
import pandas as pd

from cardozo_ketamine_hr.multivariate import fixed_reference_pca


def test_fixed_reference_axes_are_query_invariant():
    columns = [f"f{i}" for i in range(8)]
    index = ["E1", "E2", "E3", "E4", "Q"]
    base = pd.DataFrame(np.arange(40, dtype=float).reshape(5, 8), index=index, columns=columns)
    base.loc["E2", "f3"] = np.nan
    meta = pd.DataFrame({"feature_id": columns, "target": columns, "tissue": "T"})
    first_scores, first_loadings, first_status = fixed_reference_pca(base, index[:4], ["Q"], "TEST", "synthetic", meta)
    changed = base.copy()
    changed.loc["Q"] = changed.loc["Q"] * -100
    second_scores, second_loadings, second_status = fixed_reference_pca(changed, index[:4], ["Q"], "TEST", "synthetic", meta)
    assert np.allclose(first_loadings.filter(like="loading"), second_loadings.filter(like="loading"))
    assert np.allclose(first_scores[first_scores["compound"].isin(index[:4])].filter(regex="^PC[12]$"), second_scores[second_scores["compound"].isin(index[:4])].filter(regex="^PC[12]$"))
    assert first_status["reference_axes_refit_with_query"] is False
    assert second_status["reference_axes_refit_with_query"] is False
