# SPDX-License-Identifier: MIT
"""Record and enforce scientific and artifact quality-assurance contracts.

Stage
-----
QA checks run throughout analysis and again before packaging persisted outputs.

Inputs
------
Checks accept already-computed observations, pairwise tables, numerical
matrices, or artifact paths.

Outputs
-------
``QARecorder`` accumulates normalized audit rows; helper functions return
contract results or append checks to a recorder.

Side Effects
------------
Fatal failed checks raise immediately. File checks read only metadata.

Invariants
----------
Fatal thresholds are never weakened, pairwise rows must be unique and bounded,
and limitation severity remains distinguishable from failure.

Lane
----
Cross-cutting scientific-contract and release-QA lane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class QARecorder:
    """Accumulate normalized QA results and enforce fatal failures.

    Attributes
    ----------
    rows : list of dict
        QA records in evaluation order.
    """

    rows: list[dict[str, Any]] = field(default_factory=list)

    def check(
        self,
        check_id: str,
        condition: bool,
        observed: Any,
        expected: Any,
        category: str = "SCIENTIFIC_CONTRACT",
        severity: str = "FATAL",
        notes: str = "",
    ) -> bool:
        """Record one QA condition and raise for a fatal failure.

        Parameters
        ----------
        check_id : str
            Stable check identifier.
        condition : bool
            Evaluated pass condition.
        observed, expected : Any
            Values retained as audit evidence.
        category : str, default="SCIENTIFIC_CONTRACT"
            Check family.
        severity : str, default="FATAL"
            Failure policy; ``FATAL`` raises immediately.
        notes : str, default=""
            Additional context or limitation statement.

        Returns
        -------
        bool
            Boolean form of ``condition``.

        Raises
        ------
        RuntimeError
            If the check fails with ``FATAL`` severity.
        """
        status = "PASS" if bool(condition) else "FAIL"
        self.rows.append({
            "check_id": check_id,
            "category": category,
            "status": status,
            "severity": severity,
            "observed": observed,
            "expected": expected,
            "notes": notes,
        })
        if status == "FAIL" and severity == "FATAL":
            raise RuntimeError(f"QA failure {check_id}: observed={observed}; expected={expected}")
        return bool(condition)

    def frame(self) -> pd.DataFrame:
        """Return accumulated QA rows as a new table.

        Returns
        -------
        pandas.DataFrame
            QA records in evaluation order.
        """
        return pd.DataFrame(self.rows)

    def overall(self) -> str:
        """Reduce recorded rows to the governed overall status.

        Returns
        -------
        str
            ``FAIL``, ``PASS_WITH_DOCUMENTED_LIMITATIONS``, or ``PASS``.
        """
        frame = self.frame()
        if frame.empty or (frame["status"] == "FAIL").any():
            return "FAIL"
        if (frame["severity"] == "LIMITATION").any():
            return "PASS_WITH_DOCUMENTED_LIMITATIONS"
        return "PASS"


def pairwise_contract(pairwise: pd.DataFrame, expected_pairs: int, qa: QARecorder, prefix: str) -> None:
    """Apply count, identity, uniqueness, and metric-bound checks.

    Parameters
    ----------
    pairwise : pandas.DataFrame
        Unordered pairwise result table.
    expected_pairs : int
        Exact governed row count.
    qa : QARecorder
        Recorder that receives and enforces each check.
    prefix : str
        Identifier prefix for generated check IDs.

    Returns
    -------
    None
        Results are appended to ``qa``.
    """
    qa.check(f"{prefix}_PAIR_COUNT", len(pairwise) == expected_pairs, len(pairwise), expected_pairs)
    self_pairs = int((pairwise["drug_a"] == pairwise["drug_b"]).sum())
    qa.check(f"{prefix}_NO_SELF_PAIRS", self_pairs == 0, self_pairs, 0)
    duplicate_keys = pairwise.apply(lambda row: "||".join(sorted([str(row.drug_a), str(row.drug_b)])), axis=1).duplicated().sum()
    # Sorting each identity pair makes duplicate detection independent of the
    # source row's a/b orientation.
    qa.check(f"{prefix}_UNORDERED_KEYS_UNIQUE", duplicate_keys == 0, int(duplicate_keys), 0)
    for column in ["cosine_common_rhr", "pearson_common_rhr", "spearman_common_rhr"]:
        finite = pd.to_numeric(pairwise[column], errors="coerce").dropna()
        violation = int(((finite < -1.0000001) | (finite > 1.0000001)).sum())
        qa.check(f"{prefix}_{column}_BOUNDS", violation == 0, violation, 0)
    for column in [value for value in pairwise.columns if "jaccard" in value or "overlap_coefficient" in value]:
        finite = pd.to_numeric(pairwise[column], errors="coerce").dropna()
        violation = int(((finite < -1e-12) | (finite > 1.0 + 1e-12)).sum())
        qa.check(f"{prefix}_{column}_BOUNDS", violation == 0, violation, 0)


def matrix_symmetric(matrix: pd.DataFrame, atol: float = 1e-12) -> tuple[bool, float]:
    """Check matrix symmetry at the governed absolute tolerance.

    Parameters
    ----------
    matrix : pandas.DataFrame
        Square numerical matrix.
    atol : float, default=1e-12
        Maximum accepted absolute asymmetry.

    Returns
    -------
    symmetric : bool
        Whether the maximum finite difference is within tolerance.
    maximum : float
        Maximum finite absolute asymmetry, or zero for an all-missing matrix.
    """
    values = matrix.to_numpy(float)
    difference = np.abs(values - values.T)
    if np.isnan(difference).all():
        return True, 0.0
    maximum = float(np.nanmax(difference))
    return bool(maximum <= atol), maximum


def files_nonempty(paths: list[Path], minimum_bytes: int = 100) -> tuple[bool, int]:
    """Check that all expected artifacts exist above a byte threshold.

    Parameters
    ----------
    paths : list of pathlib.Path
        Expected artifact paths.
    minimum_bytes : int, default=100
        Minimum accepted size for each file.

    Returns
    -------
    passed : bool
        True when every file passes.
    bad_count : int
        Number of missing or undersized files.
    """
    bad = sum(1 for path in paths if not path.exists() or path.stat().st_size < minimum_bytes)
    return bad == 0, bad
