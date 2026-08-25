"""Normalize pharmacological activity records without changing evidence grain.

Purpose
-------
Expose the governed activity-unit and censoring rules through a typed result.

Scientific stage
----------------
This is the activity-normalization stage that precedes historeceptomic score
construction.

Primary inputs
--------------
Reported activity values, concentration units, comparison operators, and
measurement/evidence labels.

Primary outputs
---------------
``NormalizedActivity`` records containing the reported value, molar value,
``pActivity`` value, and preserved censoring metadata.

Side effects
------------
None; normalization is deterministic and does not mutate input objects.

Invariants
----------
Invalid or nonpositive concentrations remain missing, boundary operators are
retained, and a censored boundary is never represented as an exact estimate.

Execution lane
--------------
Used by unit tests and the recovered Full activity-processing lane.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .upstream.cleanup_pooled_parent_ketamine_activity_v2 import (
    normalize_unit,
    pactivity_from_value,
    relation_class,
)


@dataclass(frozen=True)
class NormalizedActivity:
    """Normalized activity value with its evidence and censoring semantics.

    Attributes
    ----------
    reported_value
        Numeric value as reported after safe conversion; invalid values are
        represented by ``NaN``.
    reported_unit
        Canonical concentration unit.
    relation_operator
        Original comparison operator, such as ``=`` or ``>``.
    relation_class
        Governed exact/bounded classification derived from the operator.
    molar_boundary_or_exact
        Exact concentration or reported boundary in molar units.
    pactivity_boundary_or_exact
        ``-log10`` transform of the exact molar concentration or boundary.
    is_bounded
        Whether the record carries censored rather than exact concentration.
    measured_or_modeled
        Evidence-origin label supplied by the caller.
    evidence_status
        Evidence-status label supplied by the caller.
    """

    reported_value: float
    reported_unit: str
    relation_operator: str
    relation_class: str
    molar_boundary_or_exact: float
    pactivity_boundary_or_exact: float
    is_bounded: bool
    measured_or_modeled: str
    evidence_status: str


def normalize_activity(
    value: Any,
    unit: Any,
    relation_operator: Any = "=",
    *,
    measured_or_modeled: str = "MEASURED",
    evidence_status: str = "OBSERVED",
) -> NormalizedActivity:
    """Normalize one activity record while preserving evidence semantics.

    Parameters
    ----------
    value
        Reported concentration value. Non-numeric and nonpositive values do
        not produce a finite molar or ``pActivity`` value.
    unit
        Reported concentration unit. Supported canonical units span molar
        through picomolar concentrations.
    relation_operator
        Censoring or equality operator associated with ``value``.
    measured_or_modeled
        Caller-supplied label distinguishing measured from modeled evidence.
    evidence_status
        Caller-supplied evidence-status label.

    Returns
    -------
    NormalizedActivity
        Immutable normalized representation retaining the reported operator
        and whether its numerical value is exact or a boundary.

    Notes
    -----
    ``pActivity`` is ``-log10(activity in M)``. For censored observations the
    transformed number remains a boundary, not an imputed exact affinity.
    Missing or invalid inputs remain nonfinite rather than being zero-filled.
    """

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = math.nan
    normalized_unit = normalize_unit(unit)
    relation = str(relation_operator or "").strip()
    relation_kind = relation_class(relation)
    # Convert only recognized positive concentrations to molar units; an
    # unsupported unit or invalid value remains missing instead of becoming 0.
    scale = {"M": 1.0, "MM": 1e-3, "UM": 1e-6, "NM": 1e-9, "PM": 1e-12}.get(
        normalized_unit
    )
    molar = numeric * scale if scale is not None and math.isfinite(numeric) and numeric > 0 else math.nan
    # The imported governed rule computes -log10(activity in M) while the
    # relation metadata below preserves whether that number is a bound.
    pactivity = pactivity_from_value(numeric, normalized_unit)
    return NormalizedActivity(
        reported_value=numeric,
        reported_unit=normalized_unit,
        relation_operator=relation,
        relation_class=relation_kind,
        molar_boundary_or_exact=molar,
        pactivity_boundary_or_exact=pactivity,
        is_bounded=relation_kind in {"GT_BOUND", "LT_BOUND", "BOUNDED_DIRECTION_UNKNOWN"},
        measured_or_modeled=str(measured_or_modeled),
        evidence_status=str(evidence_status),
    )
