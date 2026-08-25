"""Resolve compound identities using only the versioned governed registry.

Purpose
-------
Map source compound labels to explicit canonical identities without erasing
stereochemical or source-lane distinctions.

Scientific stage
----------------
Identity resolution precedes profile construction and all cross-compound
comparisons.

Primary inputs
--------------
Source names, optional source-lane labels, and ``configs/compounds.yaml``.

Primary outputs
---------------
Immutable ``IdentityResolution`` records with resolved, ambiguous, or
unresolved status and explicit candidate/reason fields.

Side effects
------------
The configuration loader reads YAML; all other operations are in-memory and
inputs are not mutated.

Invariants
----------
Only configured mappings are accepted. An unspecified ketamine record is never
promoted to confirmed racemate, and racemate observations are never borrowed
for an enantiomer or metabolite.

Execution lane
--------------
Used by governance tests and reusable identity handling across Verify and Full
processing.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from typing import Any

import yaml


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "compounds.yaml"


@dataclass(frozen=True)
class IdentityResolution:
    """Outcome of conservative compound-identity resolution.

    Attributes
    ----------
    status
        ``RESOLVED``, ``AMBIGUOUS``, or ``UNRESOLVED``.
    source_name
        Original source label after outer whitespace removal.
    canonical_id, label
        Governed identity and display label when exactly resolved.
    candidates
        Explicit possible canonical IDs for an ambiguous configured alias.
    reason
        Human-readable basis for the status.
    """

    status: str
    source_name: str
    canonical_id: str | None
    label: str | None
    candidates: tuple[str, ...] = ()
    reason: str = ""


def normalize_compound_name(value: Any) -> str:
    """Normalize typography and whitespace without erasing stereochemistry.

    Parameters
    ----------
    value
        Source label or value coercible to text.

    Returns
    -------
    str
        Unicode-normalized, case-folded comparison key.

    Notes
    -----
    Dash variants and repeated whitespace are normalized. Punctuation remains
    identity-bearing except for those explicit typographic equivalences.
    """

    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    text = text.translate(str.maketrans({"–": "-", "—": "-", "−": "-"}))
    return re.sub(r"\s+", " ", text.strip()).casefold()


def load_compound_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load and minimally validate the governed compound registry.

    Parameters
    ----------
    path
        YAML configuration containing a top-level ``compounds`` list.

    Returns
    -------
    dict
        Parsed configuration mapping.

    Raises
    ------
    ValueError
        If the YAML root or ``compounds`` member has the wrong structure.
    OSError
        If the configuration cannot be read.
    """

    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or not isinstance(config.get("compounds"), list):
        raise ValueError(f"Malformed compound configuration: {path}")
    return config


def resolve_compound_identity(
    source_name: Any,
    *,
    source_lane: str | None = None,
    config_path: str | Path = DEFAULT_CONFIG,
) -> IdentityResolution:
    """Resolve a source label or return explicit ambiguity/unresolved status.

    Parameters
    ----------
    source_name
        Label from the source record.
    source_lane
        Optional governed lane used only by an explicit ``lane_resolution``
        rule for an otherwise ambiguous alias.
    config_path
        Versioned compound-registry YAML.

    Returns
    -------
    IdentityResolution
        Resolution with a canonical ID only when exactly one governed mapping
        applies.

    Notes
    -----
    No fuzzy matching, chemical inference, or stereochemical promotion occurs.
    Ambiguous aliases retain their configured candidates for source review.
    """

    raw = "" if source_name is None else str(source_name).strip()
    key = normalize_compound_name(raw)
    if not key:
        return IdentityResolution("UNRESOLVED", raw, None, None, reason="Blank source name")

    config = load_compound_config(config_path)
    records = {str(row["canonical_id"]): row for row in config["compounds"]}

    # Ambiguous aliases are evaluated before the ordinary alias index so only
    # an explicit source-lane rule can select among their candidates.
    ambiguous = {
        normalize_compound_name(alias): rule
        for alias, rule in (config.get("ambiguous_aliases") or {}).items()
    }
    if key in ambiguous:
        rule = ambiguous[key]
        lane_map = rule.get("lane_resolution") or {}
        selected = lane_map.get(source_lane) if source_lane is not None else None
        if selected is not None:
            record = records[selected]
            return IdentityResolution(
                "RESOLVED",
                raw,
                selected,
                str(record["label"]),
                reason=f"Resolved by explicit source lane {source_lane}",
            )
        candidates = tuple(str(value) for value in rule.get("candidate_ids", []))
        return IdentityResolution(
            "AMBIGUOUS",
            raw,
            None,
            None,
            candidates=candidates,
            reason=str(rule.get("reason", "Ambiguous configured alias")),
        )

    alias_index: dict[str, list[str]] = {}
    for canonical_id, record in records.items():
        aliases = [canonical_id, record.get("label", ""), *(record.get("aliases") or [])]
        for alias in aliases:
            alias_key = normalize_compound_name(alias)
            if alias_key:
                alias_index.setdefault(alias_key, []).append(canonical_id)

    matches = tuple(dict.fromkeys(alias_index.get(key, [])))
    if len(matches) == 1:
        canonical_id = matches[0]
        record = records[canonical_id]
        return IdentityResolution(
            "RESOLVED", raw, canonical_id, str(record["label"]), reason="Explicit configured alias"
        )
    if len(matches) > 1:
        return IdentityResolution(
            "AMBIGUOUS",
            raw,
            None,
            None,
            candidates=matches,
            reason="Alias maps to multiple configured identities",
        )
    return IdentityResolution(
        "UNRESOLVED", raw, None, None, reason="No explicit governed identity mapping"
    )
