"""Test that PCA output dimensionality respects the estimable matrix rank."""

# SPDX-License-Identifier: MIT

import pandas as pd

from cardozo_ketamine_hr.multivariate import complete_case_pca


def test_rank_one_pca_does_not_force_pc2():
    frame = pd.DataFrame({"f1": [1.0, 2.0, 3.0], "f2": [2.0, 4.0, 6.0]}, index=["A", "B", "C"])
    model = complete_case_pca(frame, n_components=2)
    assert model["rank"] == 1
    assert model["n_components"] == 1
    assert model["scores"].shape[1] == 1
