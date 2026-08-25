# SPDX-License-Identifier: MIT
"""Select an optional GPU backend under an explicit equivalence gate.

Stage
-----
Backend selection precedes matrix-heavy numerical stages.
Inputs
------
Matrix dimensions and upstream hardware detection are consumed.
Outputs
-------
``BackendDecision`` records describe the validated route.
Side Effects
------------
CuPy may be imported lazily for a deterministic equivalence check.
Invariants
----------
CPU float64 is the fallback; GPU discrepancy must be at most 1e-10.
Lane
----
Portable compute-resource selection lane.
"""

from __future__ import annotations  # type: ignore

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class BackendDecision:
    """Describe a validated numerical-backend decision.

    Attributes
    ----------
    backend : str
        Stable backend identifier.
    gpu_used : bool
        Whether GPU execution was authorized.
    reason : str
        Human-readable routing or equivalence result.
    cpu_gpu_max_discrepancy : float, optional
        Maximum absolute validation discrepancy when a GPU check ran.
    """

    backend: str
    gpu_used: bool
    reason: str
    cpu_gpu_max_discrepancy: float | None = None


def choose_backend(matrix_shape: tuple[int, int], gpu_detected: bool) -> BackendDecision:
    """Choose CPU or GPU execution using size and equivalence gates.

    Parameters
    ----------
    matrix_shape : tuple of int
        Rows and columns of the intended numerical matrix.
    gpu_detected : bool
        Result of upstream NVIDIA hardware detection.

    Returns
    -------
    BackendDecision
        Selected backend, usage flag, reason, and optional discrepancy.

    Notes
    -----
    Import failure or failed equivalence returns a CPU decision rather than
    weakening the tolerance.
    """
    elements = int(matrix_shape[0]) * int(matrix_shape[1])
    if not gpu_detected:
        return BackendDecision("numpy_cpu_float64", False, "No NVIDIA GPU detected")
    if elements < 2_000_000:
        return BackendDecision("numpy_cpu_float64", False, "Matrix below GPU transfer/startup benefit threshold")
    try:
        import cupy as cp  # pyright: ignore[reportMissingImports]
    except Exception:
        return BackendDecision("numpy_cpu_float64", False, "GPU detected but CuPy/RAPIDS unavailable")
    # Fixed seed and shape make the authorization check reproducible without
    # coupling it to a scientific input matrix.
    rng = np.random.default_rng(20260813)
    sample = rng.normal(size=(64, 32))
    cpu = sample @ sample.T
    gpu = cp.asnumpy(cp.asarray(sample) @ cp.asarray(sample).T)
    discrepancy = float(np.max(np.abs(cpu - gpu)))
    if discrepancy > 1e-10:
        return BackendDecision("numpy_cpu_float64", False, "CPU/GPU equivalence failed", discrepancy)
    return BackendDecision("cupy_gpu_float64", True, "GPU equivalence passed", discrepancy)
