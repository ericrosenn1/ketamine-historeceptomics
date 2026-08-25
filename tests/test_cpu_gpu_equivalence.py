"""Test deterministic CPU backend selection for the governed matrix scale."""

# SPDX-License-Identifier: MIT

import numpy as np

from cardozo_ketamine_hr.gpu_backend import choose_backend


def test_small_matrix_uses_deterministic_cpu_and_repeats_exactly():
    decision = choose_backend((30, 1368), gpu_detected=True)
    assert decision.backend == "numpy_cpu_float64"
    rng = np.random.default_rng(20260813)
    a = rng.normal(size=(30, 100)).astype(np.float64)
    first = a @ a.T
    second = a @ a.T
    assert np.array_equal(first, second)
