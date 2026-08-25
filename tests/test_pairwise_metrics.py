"""Test symmetry and sparse-fingerprint semantics of pairwise metrics."""

# SPDX-License-Identifier: MIT

import numpy as np
import pandas as pd

from cardozo_ketamine_hr.pairwise_continuous import continuous_metrics, metric_matrix
from cardozo_ketamine_hr.pairwise_fingerprint import one_alpha


def test_pairwise_distance_symmetry_and_jaccard_identity():
    features = ["f1", "f2", "f3"]
    contract = pd.DataFrame({"feature_id": features, "target": ["A", "A", "B"], "tissue": ["X", "Y", "X"]})
    a = pd.Series([1.0, 2.0, np.nan], index=features)
    b = pd.Series([2.0, 4.0, 3.0], index=features)
    ab, _ = continuous_metrics(a, b, contract)
    ba, _ = continuous_metrics(b, a, contract)
    assert ab["rms_common_rhr"] == ba["rms_common_rhr"]
    assert ab["matched_features"] == 2
    pair = pd.DataFrame([{"drug_a": "A", "drug_b": "B", "rms_common_rhr": ab["rms_common_rhr"]}])
    matrix = metric_matrix(pair, "rms_common_rhr", ["A", "B"])
    assert np.allclose(matrix, matrix.T)
    binary = pd.DataFrame([[1, 1, 0], [0, 1, 1]], index=["A", "B"], columns=features, dtype=float)
    score = binary.copy()
    fp = one_alpha("A", "B", binary, score, contract)
    assert fp["shared_calls"] == 1
    assert fp["union_calls"] == 3
    assert fp["call_jaccard"] == 1 / 3
