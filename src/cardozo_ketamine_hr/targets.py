"""Harmonize targets at exact-protein grain against a governed contract.

Purpose
-------
Resolve source target identifiers without decomposing generic receptors,
complexes, or families into unsupported protein-level observations.

Scientific stage
----------------
Target harmonization precedes target-tissue feature construction and HR
calculation.

Primary inputs
--------------
Source target labels or mappings and a frozen feature dictionary containing
canonical target IDs, gene symbols, and target-grain classifications.

Primary outputs
---------------
Validated contract tables and immutable ``TargetResolution`` records.

Side effects
------------
``load_target_contract`` reads a Parquet file; resolution otherwise operates
on copies in memory and writes no files.

Invariants
----------
Only unique exact contract matches resolve. Generic receptor measurements are
never decomposed into subunits, and unresolved or ambiguous grain remains
explicit.

Execution lane
--------------
Used by target-governance tests and exact-feature preparation for the
reproducible analysis lanes.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


DEFAULT_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "frozen"
    / "metadata"
    / "feature_dictionary.parquet"
)


@dataclass(frozen=True)
class TargetResolution:
    """Result of exact-grain target harmonization.

    Attributes
    ----------
    status
        Resolution, ambiguity, unsupported-grain, or unresolved state.
    canonical_target_id, gene_symbol
        Governed exact-protein identity when resolved.
    target_grain
        Supplied or contract target-grain classification.
    mapping_method
        Method identifier; resolved records use the frozen exact contract.
    reason
        Human-readable basis for non-resolution or ambiguity.
    """

    status: str
    canonical_target_id: str | None
    gene_symbol: str | None
    target_grain: str | None
    mapping_method: str
    reason: str = ""


def load_target_contract(path: str | Path = DEFAULT_CONTRACT) -> pd.DataFrame:
    """Load the unique exact-target mapping from the frozen feature contract.

    Parameters
    ----------
    path
        Parquet feature dictionary containing canonical target identity fields.

    Returns
    -------
    pandas.DataFrame
        Deterministically sorted, de-duplicated exact-target contract.

    Raises
    ------
    ValueError
        If required columns are absent or a canonical target has conflicting
        gene/grain mappings.
    OSError
        If the Parquet authority cannot be read.
    """

    frame = pd.read_parquet(path)
    required = {"target_canonical_id", "gene_symbol", "target_grain_class"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Target contract is missing columns: {missing}")
    contract = (
        frame[["target_canonical_id", "gene_symbol", "target_grain_class"]]
        .drop_duplicates()
        .sort_values(["target_canonical_id", "gene_symbol"], kind="stable")
        .reset_index(drop=True)
    )
    conflicts = contract.groupby("target_canonical_id", dropna=False).size()
    if (conflicts > 1).any():
        raise ValueError("Frozen target contract has conflicting target mappings")
    return contract


def harmonize_target(
    record: str | Mapping[str, Any],
    *,
    contract: pd.DataFrame | None = None,
) -> TargetResolution:
    """Map an exact canonical ID or gene symbol without inventing subunits.

    Parameters
    ----------
    record
        Source label or mapping with optional canonical ID, gene symbol, target
        label, and target-grain fields.
    contract
        Preloaded exact-target contract. When omitted, the frozen default is
        loaded.

    Returns
    -------
    TargetResolution
        Exact match or an explicit unsupported, ambiguous, or unresolved state.

    Notes
    -----
    Generic NMDA and GABA-A receptor measurements are deliberately not split
    across protein subunits. Only exact single-protein grain enters the governed
    target-by-tissue feature space.
    """

    contract = load_target_contract() if contract is None else contract.copy()
    if isinstance(record, Mapping):
        canonical = str(record.get("canonical_target_id") or "").strip()
        gene = str(record.get("gene_symbol") or "").strip()
        label = str(record.get("target_name") or record.get("target") or "").strip()
        supplied_grain = str(record.get("target_grain") or "").strip()
    else:
        canonical = ""
        gene = ""
        label = str(record).strip()
        supplied_grain = ""

    # Reject incompatible anatomy/target grain before label matching; a generic
    # observation cannot acquire exact-protein status from a similar name.
    if supplied_grain and supplied_grain.upper() not in {
        "EXACT_SINGLE_PROTEIN",
        "EXACT PROTEIN",
        "SINGLE PROTEIN",
    }:
        return TargetResolution(
            "UNSUPPORTED_TARGET_GRAIN",
            None,
            None,
            supplied_grain,
            "NONE",
            reason="Only the frozen exact-single-protein contract is mapped",
        )

    query = canonical or gene or label
    key = query.casefold()
    generic = {
        "nmda receptor",
        "n-methyl-d-aspartate receptor",
        "gabaa receptor",
        "gaba-a receptor",
    }
    if key in generic:
        return TargetResolution(
            "AMBIGUOUS_TARGET_GRAIN",
            None,
            None,
            "GENERIC_RECEPTOR_OR_COMPLEX",
            "NONE",
            reason="Generic receptor measurement is not decomposed into subunits",
        )

    canonical_match = contract[
        contract["target_canonical_id"].astype(str).str.casefold().eq(key)
    ]
    gene_match = contract[contract["gene_symbol"].astype(str).str.casefold().eq(key)]
    matches = pd.concat([canonical_match, gene_match], ignore_index=True).drop_duplicates()
    if len(matches) == 1:
        row = matches.iloc[0]
        return TargetResolution(
            "RESOLVED",
            str(row["target_canonical_id"]),
            str(row["gene_symbol"]),
            str(row["target_grain_class"]),
            "EXACT_FROZEN_CONTRACT",
        )
    if len(matches) > 1:
        return TargetResolution(
            "AMBIGUOUS_TARGET_MAPPING", None, None, None, "NONE", reason="Multiple exact matches"
        )
    return TargetResolution(
        "UNRESOLVED", None, None, supplied_grain or None, "NONE", reason="No exact governed mapping"
    )
