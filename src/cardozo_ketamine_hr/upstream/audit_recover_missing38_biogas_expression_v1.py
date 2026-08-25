#!/usr/bin/env python3
r"""
Pooled Parent Ketamine — Missing-38 BioGPS Expression Recovery Audit v1
======================================================================

GOAL
----
Determine how many of the 38 selected pooled-parent-ketamine activity targets that
were missing from the first full-tissue HR run can be recovered from the existing
human BioGPS / GeneAtlas U133A-GNF1H 77-tissue expression source while preserving
the EXACT SAME frozen normalization contract:

    expression_profile_id = HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1
    expression_species    = Homo sapiens
    expression_ddof       = 1
    77 governed human tissues
    exact target/gene mappings only
    missingness stays missing; never zero-filled

PRIMARY EXPRESSION SOURCE
-------------------------
The preferred source is the current HPF authority's frozen feature dictionary:

    ...\01_AUTHORITIES\Ketamine_HPF\
    Human_Priority_Mammalian_Fallback_U1_Fingerprint_Authority_20260807_051641_664\
    01_INPUT_AUTHORITIES\FINAL_FEATURE_DICTIONARY.parquet

This is preferable to rebuilding expression from the pre-fingerprint master because
it directly contains the frozen 77-tissue BioGPS feature contract, including:

    target_canonical_id
    gene_symbol
    tissue_canonical_id
    tissue_label
    source_sample_label
    expression_profile_id
    expression_species
    expression_raw
    expression_Z
    expression_ddof
    FULL_HUMAN_77_TISSUE_EXACT_PROTEIN
    feature_block / feature_contract_status

SECONDARY SOURCE CHECK
----------------------
If a missing target is not recoverable from the frozen feature dictionary, the script
also performs a targeted check of the existing cleaned BioGPS source
`expression_long.tsv` when available.

The secondary source is accepted as "recoverable" ONLY if:
  1. the exact gene symbol is present (no decomposition of composite symbols);
  2. all 77 governed tissue labels can be mapped uniquely to the frozen contract;
  3. one unambiguous raw expression value exists per governed tissue;
  4. Z scores recomputed from those 77 raw values with pandas/std ddof=1 are finite;
  5. the tissue normalization uses the exact same 77-tissue contract.

Composite targets such as `CBFB;RUNX1` are NEVER split into CBFB and RUNX1.

CROSS-VALIDATION
----------------
The script cross-validates the frozen feature dictionary against the 38 targets that
already entered the first HR run. It requires the feature-dictionary expression_Z
values to match the HR-v1 expression_Z values on overlapping target-tissue coordinates.

It also independently recomputes:
    Z = (x - mean(x)) / std(x, ddof=1)
from the frozen `expression_raw` values for each recovered target and reports the
maximum residual from the stored `expression_Z`.

NO HR IS RECALCULATED BY THIS SCRIPT.

EXPECTED INPUT LINEAGE
----------------------
Final activity v4:
    ...\Final_Activity_v4_20260813_084842\
    POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv

First full HR:
    ...\Full_Tissue_HR_v1_20260813_085417\

OUTPUT
------
A timestamped subfolder inside the first HR run:

    Missing38_Expression_Recovery_Audit_v1_YYYYMMDD_HHMMSS

Main outputs:
    MISSING38_EXPRESSION_RECOVERY_AUDIT.csv
    RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.csv
    RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.parquet
    STILL_UNRECOVERABLE_TARGETS.csv
    EXISTING38_EXPRESSION_CONTRACT_CROSSCHECK.csv
    FROZEN_FEATURE_DICTIONARY_CONTRACT_AUDIT.csv
    SECONDARY_BIOGPS_SOURCE_AUDIT.csv
    SUMMARY.txt
    SUMMARY.json
    RUN.log
    OUTPUT_SHA256SUMS.csv

Publication contract
--------------------
Purpose: Audit exact expression recovery for activity targets absent from HR v1.
Stage/lane: Recovered pre-Expanded58 expression-recovery audit.
Inputs: Explicit project, Final Activity v4, and first full-HR directories.
Outputs: A new timestamped recovery-audit directory with recovered/missing tables,
cross-checks, summaries, hashes, and a run log.
Side effects: Creates derivative files only; it does not alter inputs, fetch data,
or recalculate HR scores.
Invariants: The human 77-tissue ddof=1 contract, exact mappings, composite-target
integrity, accepted old coordinates, and NA-without-zero-fill are preserved.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# Recovered stages have no public-data default. Callers must identify the
# governed external tree explicitly; the portable Full lane supplies all three.
PROJECT_ROOT = None
DEFAULT_V4_DIR = None
DEFAULT_HR1_DIR = None

PROFILE_ID = "HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1"
EXPECTED_TISSUES = 77
TOL = 1e-10


def stamp() -> str:
    """Return a filesystem-safe local timestamp for a derivative run."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def s(v) -> str:
    """Normalize a nullable scalar to a stripped string."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v).strip()


def up(v) -> str:
    """Return the normalized scalar in uppercase form."""
    return s(v).upper()


def key(v) -> str:
    """Return a normalized comparison key for a source label."""
    return up(v).replace(" ", "")


def fnum(v) -> float:
    """Return a finite float or NaN when the value is not numeric."""
    try:
        x = float(v)
        return x if math.isfinite(x) else math.nan
    except Exception:
        return math.nan


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file read in bounded blocks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def find_col(df_or_cols, candidates: Sequence[str]) -> Optional[str]:
    """Return the first case-insensitive matching column name."""
    cols = list(df_or_cols.columns) if hasattr(df_or_cols, "columns") else list(df_or_cols)
    lower = {str(c).lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def boolish(series: pd.Series) -> pd.Series:
    """Normalize a pandas series to explicit Boolean values."""
    if series.dtype == bool:
        return series
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y"})
    )


def locate_feature_dictionary(project_root: Path, log) -> Path:
    """Resolve an exact feature-dictionary candidate within the supplied root."""
    candidates = [
        project_root
        / "01_AUTHORITIES"
        / "Ketamine_HPF"
        / "Human_Priority_Mammalian_Fallback_U1_Fingerprint_Authority_20260807_051641_664"
        / "01_INPUT_AUTHORITIES"
        / "FINAL_FEATURE_DICTIONARY.parquet",
        project_root
        / "Human_Priority_Mammalian_Fallback_U1_Fingerprint_Authority_20260807_051641_664"
        / "01_INPUT_AUTHORITIES"
        / "FINAL_FEATURE_DICTIONARY.parquet",
    ]
    for p in candidates:
        if p.is_file():
            return p

    # Targeted search only under current authority areas.
    roots = [
        project_root / "01_AUTHORITIES",
        project_root / "03_DRUG_ATLAS",
        project_root / "04_KETAMINE_VS_DRUGS",
    ]
    hits = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("FINAL_FEATURE_DICTIONARY.parquet"):
                if p.is_file():
                    txt = str(p).lower()
                    score = 0
                    if "human_priority_mammalian_fallback_u1_fingerprint_authority_20260807_051641_664" in txt:
                        score += 20
                    if "01_input_authorities" in txt:
                        score += 5
                    hits.append((score, len(str(p)), str(p).lower(), p))
        except Exception:
            pass
    if not hits:
        raise FileNotFoundError("Could not locate FINAL_FEATURE_DICTIONARY.parquet")
    hits.sort(key=lambda x: (-x[0], x[1], x[2]))
    log(f"Feature dictionary fallback selected: {hits[0][3]}")
    return hits[0][3]


def locate_expression_long(project_root: Path, log) -> Optional[Path]:
    """Locate a governed long-form BioGPS expression table within the root."""
    explicit = [
        project_root
        / "09_CODE_AND_PIPELINES"
        / "Historical_Project_Trees"
        / "ketamine_hr_analysis"
        / "data_intermediate"
        / "expression_cleaned"
        / "expression_long.tsv",
        project_root
        / "ketamine_hr_analysis_FREEZE_20260630_051622"
        / "data_intermediate"
        / "expression_cleaned"
        / "expression_long.tsv",
    ]
    for p in explicit:
        if p.is_file():
            return p

    roots = [
        project_root / "09_CODE_AND_PIPELINES" / "Historical_Project_Trees",
        project_root / "12_QA_AUDITS_AND_PROVENANCE",
    ]
    hits = []
    for root in roots:
        if not root.exists():
            continue
        try:
            hits.extend([p for p in root.rglob("expression_long.tsv") if p.is_file()])
        except Exception:
            pass
    if not hits:
        return None
    hits.sort(key=lambda p: (len(str(p)), str(p).lower()))
    log(f"Legacy expression_long.tsv fallback selected: {hits[0]}")
    return hits[0]


def load_activity_and_missing(v4_dir: Path, hr1_dir: Path, log):
    """Load finalized activity, first-run HR, and the audited missing-target set."""
    activity_path = v4_dir / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv"
    hr_path = hr1_dir / "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv"
    if not activity_path.is_file():
        raise FileNotFoundError(activity_path)
    if not hr_path.is_file():
        raise FileNotFoundError(hr_path)

    activity = pd.read_csv(activity_path, low_memory=False)
    hr = pd.read_csv(hr_path, low_memory=False)

    if len(activity) != 76:
        raise RuntimeError(f"Expected 76 selected activity targets; found {len(activity)}")

    represented = set(hr["canonical_target_id"].astype(str))
    missing = activity[
        ~activity["canonical_target_id"].astype(str).isin(represented)
    ].copy()

    if len(missing) != 38:
        raise RuntimeError(
            f"Expected 38 activity targets missing from HR v1; found {len(missing)}"
        )

    log(f"Selected activity targets: {len(activity)}")
    log(f"HR-v1 represented targets: {len(represented)}")
    log(f"HR-v1 missing targets: {len(missing)}")
    return activity, hr, missing


def filter_feature_dictionary(fd: pd.DataFrame, log):
    """Select the exact human BioGPS profile and normalize its coordinate fields."""
    cols = {
        "target": find_col(fd, ["target_canonical_id", "canonical_target_id"]),
        "gene": find_col(fd, ["gene_symbol", "gene"]),
        "grain": find_col(fd, ["target_grain_class", "target_grain"]),
        "tissue_id": find_col(fd, ["tissue_canonical_id", "tissue_id"]),
        "tissue_label": find_col(fd, ["tissue_label", "anatomy_label"]),
        "source_label": find_col(fd, ["source_sample_label", "source_tissue_label"]),
        "profile": find_col(fd, ["expression_profile_id"]),
        "species": find_col(fd, ["expression_species"]),
        "raw": find_col(fd, ["expression_raw", "raw_expression"]),
        "z": find_col(fd, ["expression_Z", "expression_z", "expression_z_score"]),
        "ddof": find_col(fd, ["expression_ddof"]),
        "full": find_col(fd, ["FULL_HUMAN_77_TISSUE_EXACT_PROTEIN"]),
        "block": find_col(fd, ["feature_block"]),
        "contract_status": find_col(fd, ["feature_contract_status"]),
    }
    required = ["target", "gene", "tissue_id", "tissue_label", "profile", "species", "raw", "z", "ddof"]
    missing = [x for x in required if cols[x] is None]
    if missing:
        raise RuntimeError(f"Feature dictionary missing required fields: {missing}")

    x = fd.copy()
    x = x[x[cols["profile"]].astype(str).eq(PROFILE_ID)].copy()
    x = x[
        x[cols["species"]].astype(str).str.lower().isin({"homo sapiens", "human"})
    ].copy()

    if cols["grain"]:
        x = x[x[cols["grain"]].astype(str).str.upper().eq("EXACT_SINGLE_PROTEIN")].copy()

    if cols["full"]:
        fullmask = boolish(x[cols["full"]])
        if fullmask.any():
            x = x[fullmask].copy()

    x["_target_key"] = x[cols["target"]].map(key)
    x["_gene_key"] = x[cols["gene"]].map(key)
    x["_tissue_id"] = x[cols["tissue_id"]].map(s)
    x["_tissue_label"] = x[cols["tissue_label"]].map(s)
    x["_source_label"] = x[cols["source_label"]].map(s) if cols["source_label"] else x["_tissue_label"]
    x["_raw"] = pd.to_numeric(x[cols["raw"]], errors="coerce")
    x["_z"] = pd.to_numeric(x[cols["z"]], errors="coerce")
    x["_ddof"] = pd.to_numeric(x[cols["ddof"]], errors="coerce")

    return x, cols


def audit_fd_contract(x: pd.DataFrame, cols: dict, outdir: Path, log):
    """Audit target-level tissue counts, duplicates, and z-score conventions."""
    rows = []
    for (target_key, gene_key), g in x.groupby(["_target_key", "_gene_key"], dropna=False):
        z = pd.to_numeric(g["_z"], errors="coerce")
        raw = pd.to_numeric(g["_raw"], errors="coerce")
        tissue_count = g["_tissue_id"].nunique()
        dup_coords = int(g.duplicated(["_tissue_id"], keep=False).sum())
        ddofs = sorted(set(pd.to_numeric(g["_ddof"], errors="coerce").dropna().tolist()))
        zres = math.nan
        if tissue_count == 77 and dup_coords == 0 and raw.notna().all():
            mean = raw.mean()
            sd = raw.std(ddof=1)
            if pd.notna(sd) and float(sd) > 0:
                recomputed = (raw - mean) / sd
                zres = float(np.nanmax(np.abs(recomputed.to_numpy() - z.to_numpy())))
        rows.append(
            {
                "target_key": target_key,
                "gene_key": gene_key,
                "rows": len(g),
                "unique_tissues": tissue_count,
                "finite_raw": int(raw.notna().sum()),
                "finite_z": int(z.notna().sum()),
                "duplicate_tissue_rows": dup_coords,
                "ddof_values": "|".join(map(str, ddofs)),
                "z_recompute_max_abs_residual_ddof1": zres,
                "complete_77_contract": (
                    tissue_count == 77
                    and len(g) == 77
                    and z.notna().all()
                    and raw.notna().all()
                    and dup_coords == 0
                    and ddofs == [1.0]
                    and (math.isnan(zres) or zres <= TOL)
                ),
            }
        )
    audit = pd.DataFrame(rows)
    audit.to_csv(outdir / "FROZEN_FEATURE_DICTIONARY_CONTRACT_AUDIT.csv", index=False)

    log(
        f"Frozen feature contract: {x['_target_key'].nunique()} targets, "
        f"{x['_tissue_id'].nunique()} tissues, {len(x)} rows"
    )
    return audit


def crosscheck_existing_hr(
    hr1_dir: Path,
    fd: pd.DataFrame,
    cols: dict,
    outdir: Path,
    log,
):
    """Cross-check frozen expression against accepted first-run HR coordinates."""
    expr_path = hr1_dir / "POOLED_PARENT_KETAMINE_EXPRESSION_LONG_USED_V1.csv"
    if not expr_path.is_file():
        raise FileNotFoundError(expr_path)

    e = pd.read_csv(expr_path, low_memory=False)
    egene = find_col(e, ["gene_key", "gene_symbol", "gene"])
    etissue_id = find_col(e, ["tissue_id", "tissue_canonical_id"])
    etissue_label = find_col(e, ["tissue_label"])
    ez = find_col(e, ["expression_z", "expression_Z", "expression_z_score"])
    if not egene or not ez:
        raise RuntimeError("Could not identify HR-v1 expression fields")

    e["_gene_key"] = e[egene].map(key)
    e["_tissue_id2"] = e[etissue_id].map(s) if etissue_id else ""
    e["_tissue_label2"] = e[etissue_label].map(s) if etissue_label else ""
    e["_z_hr1"] = pd.to_numeric(e[ez], errors="coerce")

    f = fd[["_gene_key", "_tissue_id", "_tissue_label", "_z"]].copy()

    # Prefer governed tissue ID, fallback to label if IDs do not overlap.
    id_overlap = len(set(e["_tissue_id2"]) & set(f["_tissue_id"]))
    if etissue_id and id_overlap > 0:
        c = e.merge(
            f,
            left_on=["_gene_key", "_tissue_id2"],
            right_on=["_gene_key", "_tissue_id"],
            how="inner",
        )
        join_mode = "GENE_PLUS_TISSUE_ID"
    else:
        c = e.merge(
            f,
            left_on=["_gene_key", "_tissue_label2"],
            right_on=["_gene_key", "_tissue_label"],
            how="inner",
        )
        join_mode = "GENE_PLUS_TISSUE_LABEL"

    c["abs_delta"] = (c["_z_hr1"] - c["_z"]).abs()
    c.to_csv(outdir / "EXISTING38_EXPRESSION_CONTRACT_CROSSCHECK.csv", index=False)

    if c.empty:
        raise RuntimeError("No existing HR-v1 expression coordinates cross-matched feature dictionary")

    max_delta = float(c["abs_delta"].max())
    log(
        f"Existing HR-v1 vs frozen feature dictionary crosscheck: "
        f"{len(c)} coordinates; join={join_mode}; max |delta Z|={max_delta:.3g}"
    )
    if max_delta > TOL:
        raise RuntimeError(
            f"Expression normalization contract mismatch: max |delta Z|={max_delta} > {TOL}"
        )
    return {
        "join_mode": join_mode,
        "coordinate_count": len(c),
        "max_abs_delta_expression_Z": max_delta,
    }


def map_missing_to_fd(
    missing: pd.DataFrame,
    fd: pd.DataFrame,
    outdir: Path,
    log,
):
    """Map missing targets only when the frozen 77-tissue contract is complete."""
    audit_rows = []
    recovered_parts = []
    pending = []

    for _, r in missing.iterrows():
        target = s(r.get("canonical_target_id"))
        gene = s(r.get("gene_symbol"))
        tk = key(target)
        gk = key(gene)

        match = fd[fd["_target_key"].eq(tk)].copy()
        method = "EXACT_CANONICAL_TARGET_ID"

        if match.empty:
            # Exact gene fallback only. Never split composite symbols.
            if ";" not in gene and "|" not in gene and "," not in gene:
                gm = fd[fd["_gene_key"].eq(gk)].copy()
                unique_target_keys = sorted(set(gm["_target_key"])) if not gm.empty else []
                if len(unique_target_keys) == 1:
                    match = gm
                    method = "EXACT_GENE_SYMBOL_UNAMBIGUOUS"

        tissues = match["_tissue_id"].nunique() if not match.empty else 0
        finite_z = int(match["_z"].notna().sum()) if not match.empty else 0
        finite_raw = int(match["_raw"].notna().sum()) if not match.empty else 0
        dup = int(match.duplicated(["_tissue_id"], keep=False).sum()) if not match.empty else 0
        ddofs = sorted(set(match["_ddof"].dropna().tolist())) if not match.empty else []

        residual = math.nan
        if (
            len(match) == EXPECTED_TISSUES
            and tissues == EXPECTED_TISSUES
            and finite_raw == EXPECTED_TISSUES
            and finite_z == EXPECTED_TISSUES
            and dup == 0
        ):
            raw = match["_raw"].astype(float)
            sd = raw.std(ddof=1)
            if pd.notna(sd) and float(sd) > 0:
                calc = (raw - raw.mean()) / sd
                residual = float(np.max(np.abs(calc.to_numpy() - match["_z"].astype(float).to_numpy())))

        recoverable = (
            len(match) == EXPECTED_TISSUES
            and tissues == EXPECTED_TISSUES
            and finite_z == EXPECTED_TISSUES
            and finite_raw == EXPECTED_TISSUES
            and dup == 0
            and ddofs == [1.0]
            and not math.isnan(residual)
            and residual <= TOL
        )

        status = (
            "RECOVERABLE_FROZEN_77TISSUE_CONTRACT"
            if recoverable
            else "NOT_COMPLETE_IN_FROZEN_FEATURE_DICTIONARY"
        )

        audit_rows.append(
            {
                "canonical_target_id": target,
                "gene_symbol": gene,
                "primary_mapping_method": method if not match.empty else "NO_FROZEN_MATCH",
                "frozen_rows": len(match),
                "frozen_unique_tissues": tissues,
                "frozen_finite_expression_raw": finite_raw,
                "frozen_finite_expression_Z": finite_z,
                "frozen_duplicate_tissue_rows": dup,
                "frozen_ddof_values": "|".join(map(str, ddofs)),
                "frozen_z_recompute_max_abs_residual": residual,
                "frozen_recovery_status": status,
            }
        )

        if recoverable:
            q = match.copy()
            q["requested_canonical_target_id"] = target
            q["requested_gene_symbol"] = gene
            q["recovery_mapping_method"] = method
            q["recovery_source"] = "FROZEN_FINAL_FEATURE_DICTIONARY"
            recovered_parts.append(q)
        else:
            pending.append((target, gene))

    audit = pd.DataFrame(audit_rows)
    recovered = pd.concat(recovered_parts, ignore_index=True) if recovered_parts else pd.DataFrame()

    log(
        f"Frozen feature-dictionary recovery: "
        f"{audit['frozen_recovery_status'].eq('RECOVERABLE_FROZEN_77TISSUE_CONTRACT').sum()}/38 targets"
    )
    return audit, recovered, pending


def secondary_source_audit(
    expression_long_path: Optional[Path],
    pending: List[Tuple[str, str]],
    fd: pd.DataFrame,
    outdir: Path,
    log,
):
    """Audit secondary expression evidence without replacing the frozen authority."""
    results = []
    recovered_parts = []

    if not pending:
        return pd.DataFrame(), pd.DataFrame()

    if expression_long_path is None or not expression_long_path.is_file():
        for target, gene in pending:
            results.append(
                {
                    "canonical_target_id": target,
                    "gene_symbol": gene,
                    "secondary_status": "SECONDARY_SOURCE_NOT_AVAILABLE",
                }
            )
        return pd.DataFrame(results), pd.DataFrame()

    e = pd.read_csv(expression_long_path, sep="\t", low_memory=False)
    dbcol = find_col(e, ["expression_db"])
    genecol = find_col(e, ["gene"])
    tissuecol = find_col(e, ["tissue"])
    source_tissue_col = find_col(e, ["source_tissue_label"])
    rawcol = find_col(e, ["expression_value"])
    zcol = find_col(e, ["expression_zscore", "expression_z"])
    if not all([dbcol, genecol, tissuecol, rawcol]):
        raise RuntimeError(
            f"Legacy BioGPS source lacks required columns: {list(e.columns)}"
        )

    e = e[
        e[dbcol].astype(str).str.contains("BioGPS_GNF1H_GCRMA", case=False, na=False)
    ].copy()
    e["_gene_key"] = e[genecol].map(key)
    e["_legacy_tissue"] = e[tissuecol].map(s)
    e["_legacy_source_tissue"] = (
        e[source_tissue_col].map(s) if source_tissue_col else e["_legacy_tissue"]
    )
    e["_raw"] = pd.to_numeric(e[rawcol], errors="coerce")
    if zcol:
        e["_legacy_z"] = pd.to_numeric(e[zcol], errors="coerce")
    else:
        e["_legacy_z"] = np.nan

    # Build governed label map from the frozen feature dictionary.
    label_rows = fd[
        ["_tissue_id", "_tissue_label", "_source_label"]
    ].drop_duplicates()
    label_map = {}
    ambiguous = set()
    for _, rr in label_rows.iterrows():
        candidates = {s(rr["_tissue_label"]), s(rr["_source_label"])}
        for lab in candidates:
            if not lab:
                continue
            k = up(lab)
            val = (s(rr["_tissue_id"]), s(rr["_tissue_label"]))
            if k in label_map and label_map[k] != val:
                ambiguous.add(k)
            else:
                label_map[k] = val
    for k in ambiguous:
        label_map.pop(k, None)

    for target, gene in pending:
        if any(sep in gene for sep in (";", "|", ",")):
            results.append(
                {
                    "canonical_target_id": target,
                    "gene_symbol": gene,
                    "secondary_status": "COMPOSITE_GENE_NOT_SPLIT",
                    "secondary_rows": 0,
                    "secondary_governed_tissues": 0,
                }
            )
            continue

        g = e[e["_gene_key"].eq(key(gene))].copy()
        if g.empty:
            results.append(
                {
                    "canonical_target_id": target,
                    "gene_symbol": gene,
                    "secondary_status": "GENE_NOT_FOUND_IN_CLEANED_BIOGPS_SOURCE",
                    "secondary_rows": 0,
                    "secondary_governed_tissues": 0,
                }
            )
            continue

        mapped_ids = []
        mapped_labels = []
        for _, rr in g.iterrows():
            candidates = [up(rr["_legacy_source_tissue"]), up(rr["_legacy_tissue"])]
            mapped = None
            for lab in candidates:
                if lab and lab in label_map:
                    mapped = label_map[lab]
                    break
            mapped_ids.append(mapped[0] if mapped else "")
            mapped_labels.append(mapped[1] if mapped else "")

        g["_governed_tissue_id"] = mapped_ids
        g["_governed_tissue_label"] = mapped_labels
        gm = g[g["_governed_tissue_id"].ne("")].copy()

        # Each governed tissue must have one unique raw value. Duplicate identical
        # representations can collapse; conflicting values are not resolved here.
        records = []
        conflict_count = 0
        for (tid, tlab), gg in gm.groupby(
            ["_governed_tissue_id", "_governed_tissue_label"],
            dropna=False,
        ):
            vals = sorted(set(pd.to_numeric(gg["_raw"], errors="coerce").dropna().tolist()))
            if len(vals) != 1:
                conflict_count += 1
                continue
            records.append(
                {
                    "requested_canonical_target_id": target,
                    "requested_gene_symbol": gene,
                    "tissue_canonical_id": tid,
                    "tissue_label": tlab,
                    "expression_raw": vals[0],
                }
            )

        rec = pd.DataFrame(records)
        tissue_count = rec["tissue_canonical_id"].nunique() if not rec.empty else 0

        if tissue_count == 77 and len(rec) == 77 and conflict_count == 0:
            raw = rec["expression_raw"].astype(float)
            sd = raw.std(ddof=1)
            if pd.isna(sd) or float(sd) <= 0:
                status = "SECONDARY_77_PRESENT_BUT_Z_UNDEFINED"
            else:
                rec["expression_Z"] = (raw - raw.mean()) / sd
                rec["expression_ddof"] = 1
                rec["expression_profile_id"] = PROFILE_ID
                rec["expression_species"] = "Homo sapiens"
                rec["recovery_mapping_method"] = "EXACT_GENE_PLUS_GOVERNED_TISSUE_LABEL"
                rec["recovery_source"] = "LEGACY_CLEANED_BIOGPS_RECOMPUTED_DDOF1"
                recovered_parts.append(rec)
                status = "RECOVERABLE_SECONDARY_BIOGPS_77TISSUE_DDOF1"
        else:
            status = "SECONDARY_BIOGPS_INCOMPLETE_OR_CONFLICTING"

        results.append(
            {
                "canonical_target_id": target,
                "gene_symbol": gene,
                "secondary_status": status,
                "secondary_source_file": str(expression_long_path),
                "secondary_source_rows_for_gene": len(g),
                "secondary_mapped_rows": len(gm),
                "secondary_governed_tissues": tissue_count,
                "secondary_conflicting_tissue_value_groups": conflict_count,
            }
        )

    audit = pd.DataFrame(results)
    recovered = pd.concat(recovered_parts, ignore_index=True) if recovered_parts else pd.DataFrame()
    audit.to_csv(outdir / "SECONDARY_BIOGPS_SOURCE_AUDIT.csv", index=False)
    return audit, recovered


def main() -> int:
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    parser = argparse.ArgumentParser(
        description="Audit recovery of the 38 pooled-parent-ketamine targets missing BioGPS expression in HR v1."
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--v4-dir", type=Path, required=True)
    parser.add_argument("--hr1-dir", type=Path, required=True)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    v4_dir = args.v4_dir.resolve()
    hr1_dir = args.hr1_dir.resolve()
    outdir = hr1_dir / f"Missing38_Expression_Recovery_Audit_v1_{stamp()}"
    outdir.mkdir(parents=True, exist_ok=False)
    log_path = outdir / "RUN.log"

    def log(msg):
        """Write one timestamped run-log message."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    try:
        log("=== MISSING-38 BIOGPS EXPRESSION RECOVERY AUDIT START ===")
        log(f"Project root: {project_root}")
        log(f"V4 dir: {v4_dir}")
        log(f"HR-v1 dir: {hr1_dir}")
        log(f"Output: {outdir}")

        activity, hr, missing = load_activity_and_missing(v4_dir, hr1_dir, log)

        fd_path = locate_feature_dictionary(project_root, log)
        log(f"Frozen feature dictionary: {fd_path}")
        fd0 = pd.read_parquet(fd_path)
        fd, cols = filter_feature_dictionary(fd0, log)

        contract_audit = audit_fd_contract(fd, cols, outdir, log)

        # Hard contract verification.
        profile_ids = sorted(set(fd[cols["profile"]].dropna().astype(str)))
        species = sorted(set(fd[cols["species"]].dropna().astype(str)))
        ddofs = sorted(set(pd.to_numeric(fd["_ddof"], errors="coerce").dropna().tolist()))
        if profile_ids != [PROFILE_ID]:
            raise RuntimeError(f"Unexpected expression profiles after filtering: {profile_ids}")
        if fd["_tissue_id"].nunique() != 77:
            raise RuntimeError(
                f"Frozen expression contract does not contain exactly 77 tissues: {fd['_tissue_id'].nunique()}"
            )
        if ddofs != [1.0]:
            raise RuntimeError(f"Frozen expression ddof is not exactly 1: {ddofs}")

        cross = crosscheck_existing_hr(hr1_dir, fd, cols, outdir, log)

        primary_audit, recovered_primary, pending = map_missing_to_fd(
            missing, fd, outdir, log
        )

        expression_long = locate_expression_long(project_root, log)
        if expression_long:
            log(f"Secondary cleaned BioGPS source: {expression_long}")
        else:
            log("Secondary cleaned BioGPS source not found; primary frozen-contract audit remains valid.")

        secondary_audit, recovered_secondary = secondary_source_audit(
            expression_long, pending, fd, outdir, log
        )

        # Merge audit status.
        audit = primary_audit.copy()
        if not secondary_audit.empty:
            audit = audit.merge(
                secondary_audit,
                on=["canonical_target_id", "gene_symbol"],
                how="left",
            )
        else:
            audit["secondary_status"] = ""

        def final_status(row):
            """Assign the explicit recovery status for one audited target."""
            if s(row["frozen_recovery_status"]) == "RECOVERABLE_FROZEN_77TISSUE_CONTRACT":
                return "RECOVERABLE"
            if s(row.get("secondary_status")) == "RECOVERABLE_SECONDARY_BIOGPS_77TISSUE_DDOF1":
                return "RECOVERABLE"
            return "NOT_RECOVERABLE_WITH_CURRENT_SOURCES"

        audit["final_recovery_status"] = audit.apply(final_status, axis=1)
        audit.to_csv(outdir / "MISSING38_EXPRESSION_RECOVERY_AUDIT.csv", index=False)

        # Build recovered expression long rows in a unified output schema.
        parts = []
        if not recovered_primary.empty:
            rp = pd.DataFrame(
                {
                    "canonical_target_id": recovered_primary["requested_canonical_target_id"],
                    "gene_symbol": recovered_primary["requested_gene_symbol"],
                    "tissue_canonical_id": recovered_primary["_tissue_id"],
                    "tissue_label": recovered_primary["_tissue_label"],
                    "source_sample_label": recovered_primary["_source_label"],
                    "expression_profile_id": PROFILE_ID,
                    "expression_species": "Homo sapiens",
                    "expression_raw": recovered_primary["_raw"],
                    "expression_Z": recovered_primary["_z"],
                    "expression_ddof": 1,
                    "recovery_mapping_method": recovered_primary["recovery_mapping_method"],
                    "recovery_source": recovered_primary["recovery_source"],
                }
            )
            parts.append(rp)

        if not recovered_secondary.empty:
            rs = recovered_secondary.copy()
            if "source_sample_label" not in rs:
                rs["source_sample_label"] = rs["tissue_label"]
            rs = rs[
                [
                    "requested_canonical_target_id",
                    "requested_gene_symbol",
                    "tissue_canonical_id",
                    "tissue_label",
                    "source_sample_label",
                    "expression_profile_id",
                    "expression_species",
                    "expression_raw",
                    "expression_Z",
                    "expression_ddof",
                    "recovery_mapping_method",
                    "recovery_source",
                ]
            ].rename(
                columns={
                    "requested_canonical_target_id": "canonical_target_id",
                    "requested_gene_symbol": "gene_symbol",
                }
            )
            parts.append(rs)

        recovered = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
            columns=[
                "canonical_target_id",
                "gene_symbol",
                "tissue_canonical_id",
                "tissue_label",
                "source_sample_label",
                "expression_profile_id",
                "expression_species",
                "expression_raw",
                "expression_Z",
                "expression_ddof",
                "recovery_mapping_method",
                "recovery_source",
            ]
        )

        recovered = recovered.sort_values(
            ["canonical_target_id", "tissue_label"],
            kind="stable",
        ).reset_index(drop=True)

        recoverable_targets = sorted(
            audit.loc[
                audit["final_recovery_status"].eq("RECOVERABLE"),
                "canonical_target_id",
            ].astype(str)
        )
        unrecoverable_targets = audit[
            ~audit["final_recovery_status"].eq("RECOVERABLE")
        ].copy()

        recovered.to_csv(
            outdir / "RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.csv",
            index=False,
        )
        recovered.to_parquet(
            outdir / "RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.parquet",
            index=False,
        )
        unrecoverable_targets.to_csv(
            outdir / "STILL_UNRECOVERABLE_TARGETS.csv",
            index=False,
        )

        # Final integrity.
        if not recovered.empty:
            counts = recovered.groupby("canonical_target_id")["tissue_canonical_id"].nunique()
            bad = counts[counts.ne(77)]
            if len(bad):
                raise RuntimeError(
                    "Recovered output contains target(s) without exactly 77 tissues:\n"
                    + bad.to_string()
                )

        n_primary = int(
            audit["frozen_recovery_status"].eq(
                "RECOVERABLE_FROZEN_77TISSUE_CONTRACT"
            ).sum()
        )
        n_secondary = int(
            audit.get("secondary_status", pd.Series(dtype=str))
            .eq("RECOVERABLE_SECONDARY_BIOGPS_77TISSUE_DDOF1")
            .sum()
        )
        n_total = int(audit["final_recovery_status"].eq("RECOVERABLE").sum())
        n_unrec = 38 - n_total

        summary = {
            "status": "PASS",
            "missing_targets_audited": 38,
            "recoverable_from_frozen_feature_dictionary": n_primary,
            "additional_recoverable_from_secondary_cleaned_biogas": n_secondary,
            "total_recoverable_missing_targets": n_total,
            "still_unrecoverable_targets": n_unrec,
            "expected_recovered_expression_rows": n_total * 77,
            "actual_recovered_expression_rows": len(recovered),
            "frozen_feature_dictionary": str(fd_path),
            "frozen_feature_dictionary_sha256": sha256(fd_path),
            "expression_profile_id": PROFILE_ID,
            "expression_ddof": 1,
            "governed_tissues": 77,
            "existing_hr_contract_crosscheck": cross,
            "secondary_expression_source": str(expression_long) if expression_long else None,
            "recoverable_target_ids": recoverable_targets,
            "unrecoverable_target_ids": unrecoverable_targets[
                "canonical_target_id"
            ].astype(str).tolist(),
            "hr_recalculated": False,
        }

        (outdir / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        lines = [
            "=== MISSING-38 BIOGPS EXPRESSION RECOVERY AUDIT COMPLETE ===",
            "",
            "CONTRACT",
            f"Expression profile: {PROFILE_ID}",
            "Expression species: Homo sapiens",
            "Normalization: within-gene Z across governed tissues",
            "ddof: 1",
            "Governed tissues: 77",
            "",
            "CROSSCHECK",
            f"Existing HR-v1 coordinates crosschecked: {cross['coordinate_count']:,}",
            f"Maximum |expression_Z delta| vs frozen feature dictionary: {cross['max_abs_delta_expression_Z']:.3g}",
            "",
            "RECOVERY",
            "Missing targets audited: 38",
            f"Recoverable directly from frozen feature dictionary: {n_primary}",
            f"Additional recoverable from secondary cleaned BioGPS source: {n_secondary}",
            f"TOTAL RECOVERABLE: {n_total} / 38",
            f"STILL UNRECOVERABLE: {n_unrec} / 38",
            f"Recovered 77-tissue expression rows: {len(recovered):,}",
            "",
            "Still unrecoverable target IDs:",
            "  " + (", ".join(summary["unrecoverable_target_ids"]) if n_unrec else "NONE"),
            "",
            "No composite gene/target was decomposed.",
            "No missing expression was zero-filled.",
            "NO HR WAS RECALCULATED.",
            "",
            f"Output folder: {outdir}",
            "QA: PASS",
        ]
        (outdir / "SUMMARY.txt").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        hashes = []
        for p in sorted(outdir.iterdir()):
            if p.is_file() and p.name != "OUTPUT_SHA256SUMS.csv":
                hashes.append(
                    {
                        "filename": p.name,
                        "bytes": p.stat().st_size,
                        "sha256": sha256(p),
                    }
                )
        pd.DataFrame(hashes).to_csv(
            outdir / "OUTPUT_SHA256SUMS.csv",
            index=False,
        )

        log(f"TOTAL RECOVERABLE = {n_total}/38; still unrecoverable = {n_unrec}")
        log("QA: PASS")
        log("NO HR RECALCULATED")
        print()
        print("\n".join(lines))
        return 0

    except Exception as exc:
        tb = traceback.format_exc()
        log("=== FAILED ===")
        log(repr(exc))
        log(tb)
        (outdir / "FAILURE.json").write_text(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": repr(exc),
                    "traceback": tb,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nFAILED: {exc}\nSee {log_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
