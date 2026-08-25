#!/usr/bin/env python3
r"""
POOLED PARENT KETAMINE — FULL-TISSUE HISTORECEPTOMIC (HR) PROFILE v1
====================================================================

PURPOSE
-------
Generate the exploratory pooled-parent-ketamine HR profile from the FINAL v4
target-level activity table and the existing authoritative HUMAN tissue-expression
matrix.

This is the HR calculation step only.

INPUT ACTIVITY
--------------
Final v4 HR-input target activity table:
    76 selected targets
    40 exact measured target values
    36 measured PDSP Ki >10,000 nM boundary values

INPUT EXPRESSION
----------------
Use the read-only Feature / Expression Authority supplied explicitly with
--expression-authority.

Primary source:
    06_PRE_FINGERPRINT_MASTER\
    PRE_FINGERPRINT_MASTER_ALL_SPECIES.parquet

Human expression only.

The script uses ALL human tissues represented by the authoritative expression
profile. It does NOT restrict the analysis to the strict18 CNS subset.

HR FORMULA
----------
Historical Cardozo-style HR score:

    HR = pActivity * expression_Z

where:

    pActivity = -log10(activity concentration in molar units)

For exact activity values, HR is exact conditional on the expression Z used.

For bounded activity:
    Ki > 10,000 nM  =>  pActivity < 5.0

The numeric HR boundary is still:

    HR_boundary = 5.0 * expression_Z

BUT THE HR RELATION DEPENDS ON THE SIGN OF expression_Z:

    if expression_Z > 0:
        pActivity < 5  =>  HR < 5 * Z

    if expression_Z < 0:
        pActivity < 5  =>  HR > 5 * Z

    if expression_Z == 0:
        HR = 0

Therefore bounded HR rows are NOT mislabeled as exact scores.

IMPORTANT
---------
This script:
- calculates the full available human-tissue HR profile;
- preserves exact versus bounded activity provenance;
- preserves the direction of HR censoring/bounding;
- does NOT run GESD;
- does NOT create a fingerprint;
- does NOT run PCA, clustering, multivariate analysis, or comparator analysis;
- does NOT modify any authority;
- does NOT use CNS-only filtering;
- does NOT impute expression for a target absent from the authority;
- does NOT split a multi-gene target such as CBFB;RUNX1 into invented single-gene
  expression values.

OUTPUTS
-------
A timestamped folder:
    Full_Tissue_HR_v1_YYYYMMDD_HHMMSS

Main outputs:
    POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv
    POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.parquet
    POOLED_PARENT_KETAMINE_HR_NUMERIC_MATRIX_V1.csv
    POOLED_PARENT_KETAMINE_HR_RELATION_MATRIX_V1.csv
    POOLED_PARENT_KETAMINE_EXPRESSION_MATRIX_USED_V1.csv
    POOLED_PARENT_KETAMINE_TARGET_HR_COVERAGE_V1.csv
    POOLED_PARENT_KETAMINE_MISSING_EXPRESSION_TARGETS_V1.csv
    SUMMARY.txt
    SUMMARY.json
    RUN.log
    OUTPUT_SHA256SUMS.csv

Publication contract
--------------------
Purpose: Construct the first full-human-tissue pooled-parent HR derivative.
Stage/lane: Recovered full-tissue HR v1, after Final Activity v4.
Inputs: An explicit v4 directory and governed human expression-authority directory.
Outputs: A new timestamped directory with long CSV/Parquet HR, numerical/relation/
expression matrices, coverage/missing tables, summaries, hashes, and run log.
Side effects: Writes derivative outputs only; no authority is modified and no
fingerprint, multivariate, or comparator analysis is run.
Invariants: HR equals pActivity times expression z, relation direction follows z,
target grain is not split, absent expression stays absent, and no zero-fill occurs.
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


# =============================================================================
# Defaults
# =============================================================================

PROJECT_ROOT = None
DEFAULT_V4_DIR = None
DEFAULT_ACTIVITY = None
DEFAULT_EXPRESSION_AUTHORITY = None
DEFAULT_MASTER = None


# =============================================================================
# Utilities
# =============================================================================

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


def find_col(df_or_columns, candidates: Sequence[str]) -> Optional[str]:
    """Return the first case-insensitive matching column name."""
    columns = (
        list(df_or_columns.columns)
        if hasattr(df_or_columns, "columns")
        else list(df_or_columns)
    )
    exact = {str(c).lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in exact:
            return exact[cand.lower()]

    # Conservative normalized-name fallback.
    def key(x):
        """Return a normalized comparison key for a source label."""
        return re.sub(r"[^a-z0-9]+", "", str(x).lower())

    normalized = {key(c): c for c in columns}
    for cand in candidates:
        k = key(cand)
        if k in normalized:
            return normalized[k]

    return None


def normalize_gene(v) -> str:
    """Normalize a gene symbol for conservative authority matching."""
    return up(v).replace(" ", "")


def finite_numeric(series) -> pd.Series:
    """Coerce a series to finite numeric values while preserving missingness."""
    x = pd.to_numeric(series, errors="coerce")
    return x.where(np.isfinite(x), np.nan)


def write_csv_parquet(df: pd.DataFrame, csv_path: Path, parquet_path: Path):
    """Write equivalent CSV and Parquet representations of a table."""
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)


# =============================================================================
# Activity input validation
# =============================================================================

def load_activity(path: Path, log) -> pd.DataFrame:
    """Load and validate the finalized target-activity authority."""
    d = pd.read_csv(path, low_memory=False)

    required = [
        "analysis_compound",
        "canonical_target_id",
        "gene_symbol",
        "final_selected_pActivity_v4",
        "final_activity_relation_operator_v4",
        "final_activity_relation_class_v4",
        "final_activity_value_status_v4",
        "final_hr_input_status_v4",
    ]
    missing = [c for c in required if c not in d.columns]
    if missing:
        raise RuntimeError(
            f"Final v4 HR-input table is missing required columns: {missing}"
        )

    if len(d) != 76:
        raise RuntimeError(
            f"Safety stop: expected 76 selected target rows; found {len(d)}."
        )

    if d["canonical_target_id"].astype(str).duplicated().any():
        dup = d.loc[
            d["canonical_target_id"].astype(str).duplicated(keep=False),
            "canonical_target_id",
        ].tolist()
        raise RuntimeError(
            f"Safety stop: duplicate canonical_target_id values in activity input: {dup}"
        )

    p = finite_numeric(d["final_selected_pActivity_v4"])
    if p.isna().any():
        bad = d.loc[p.isna(), "canonical_target_id"].tolist()
        raise RuntimeError(
            f"Safety stop: selected activity rows with missing/nonfinite pActivity: {bad}"
        )

    status = d["final_hr_input_status_v4"].astype(str)
    if not status.isin(
        ["READY_EXACT", "READY_BOUNDED_RELATION_PRESERVED"]
    ).all():
        bad = d.loc[
            ~status.isin(
                ["READY_EXACT", "READY_BOUNDED_RELATION_PRESERVED"]
            ),
            ["canonical_target_id", "final_hr_input_status_v4"],
        ]
        raise RuntimeError(
            "Safety stop: HR input contains target(s) not marked ready:\n"
            + bad.to_string(index=False)
        )

    exact_n = int(
        d["final_activity_relation_class_v4"].astype(str).eq("EXACT").sum()
    )
    gt_n = int(
        d["final_activity_relation_class_v4"].astype(str).eq("GT_BOUND").sum()
    )

    if exact_n != 40 or gt_n != 36:
        raise RuntimeError(
            "Safety stop: expected v4 composition exact=40 and GT_BOUND=36; "
            f"observed exact={exact_n}, GT_BOUND={gt_n}."
        )

    d = d.copy()
    d["activity_pactivity_numeric"] = p

    # The affinity relation and pActivity relation are inverse under -log10().
    def p_rel(row):
        """Return the governed pActivity relation for one activity row."""
        rc = s(row["final_activity_relation_class_v4"])
        if rc == "EXACT":
            return "="
        if rc == "GT_BOUND":
            return "<"
        if rc == "LT_BOUND":
            return ">"
        return "?"

    d["pactivity_relation"] = d.apply(p_rel, axis=1)

    log(
        f"Activity input PASS: {len(d)} targets "
        f"({exact_n} exact; {gt_n} bounded GT)"
    )
    return d


# =============================================================================
# Expression authority extraction
# =============================================================================

def locate_master(authority: Path, preferred: Path, log) -> Path:
    """Resolve an explicit or uniquely governed expression master table."""
    if preferred.is_file():
        return preferred

    # Search only inside the designated expression authority.
    exact_names = [
        "PRE_FINGERPRINT_MASTER_ALL_SPECIES.parquet",
        "PRE_FINGERPRINT_REPRESENTATION_LONG.parquet",
        "PRE_FINGERPRINT_HUMAN_ACTIVITY.parquet",
    ]

    for name in exact_names:
        hits = list(authority.rglob(name))
        hits = [p for p in hits if p.is_file()]
        if hits:
            hits.sort(key=lambda p: (len(str(p)), str(p).lower()))
            log(f"Expression master fallback selected: {hits[0]}")
            return hits[0]

    raise FileNotFoundError(
        "Could not locate a pre-fingerprint master within the designated "
        f"expression authority: {authority}"
    )


def expression_from_master(
    master: pd.DataFrame,
    activity: pd.DataFrame,
    log,
) -> Tuple[pd.DataFrame, dict]:
    """
    Build one authoritative expression-Z row per gene x human tissue.

    Prefer a direct expression-Z column. If absent, derive expression Z from
    existing governed HR rows:
        expression_Z = raw_HR / activity_strength
    and require consistency across duplicated rows.
    """
    # Candidate schema fields.
    gene_col = find_col(
        master,
        [
            "gene_symbol",
            "canonical_gene_symbol",
            "target_gene_symbol",
            "gene",
        ],
    )
    target_col = find_col(
        master,
        [
            "canonical_target_id",
            "target_canonical_id",
            "target_id",
            "target_concept_id",
        ],
    )
    tissue_id_col = find_col(
        master,
        [
            "tissue_id",
            "tissue_canonical_id",
            "anatomy_id",
            "anatomy_canonical_id",
        ],
    )
    tissue_label_col = find_col(
        master,
        [
            "tissue_label",
            "anatomy_label",
            "native_tissue_label",
            "governed_anatomy",
            "tissue",
        ],
    )

    expr_z_col = find_col(
        master,
        [
            "expression_z",
            "expression_Z",
            "normalized_expression_z",
            "gene_expression_z",
            "expression_z_score",
        ],
    )
    raw_expr_col = find_col(
        master,
        [
            "raw_expression",
            "expression_value",
            "expression_raw",
            "gene_expression",
        ],
    )
    expr_profile_col = find_col(
        master,
        [
            "expression_profile_id",
            "expression_dataset_id",
            "expression_profile",
        ],
    )
    expr_species_col = find_col(
        master,
        [
            "expression_species",
            "expression_organism",
        ],
    )
    expr_taxon_col = find_col(
        master,
        [
            "expression_species_taxon_id",
            "expression_taxon_id",
        ],
    )

    raw_hr_col = find_col(
        master,
        [
            "raw_hr",
            "raw_HR",
            "latent_hr_raw",
            "LATENT_HR_RAW_mean",
            "hr_raw",
        ],
    )
    strength_col = find_col(
        master,
        [
            "latent_activity_strength",
            "activity_strength_score",
            "activity_strength",
            "pactivity",
            "transformed_pactivity",
            "scenario_pactivity",
        ],
    )

    if gene_col is None:
        raise RuntimeError(
            "Could not identify gene_symbol in expression authority master."
        )
    if tissue_label_col is None and tissue_id_col is None:
        raise RuntimeError(
            "Could not identify tissue/anatomy fields in expression authority master."
        )

    m = master.copy()

    # Human-expression filter. If the explicit fields exist, enforce them.
    human_filter_applied = False

    if expr_taxon_col:
        tx = pd.to_numeric(m[expr_taxon_col], errors="coerce")
        finite = tx.notna()
        if finite.any():
            m = m[~finite | tx.eq(9606)].copy()
            human_filter_applied = True

    if expr_species_col:
        vals = m[expr_species_col].fillna("").astype(str).str.lower()
        known = vals.ne("")
        if known.any():
            human = (
                vals.str.contains("homo sapiens", na=False)
                | vals.str.fullmatch("human", na=False)
            )
            m = m[~known | human].copy()
            human_filter_applied = True

    # Prefer the established human BioGPS/GeneAtlas profile if multiple profile IDs
    # are present.
    selected_profile = ""
    if expr_profile_col:
        profiles = (
            m[expr_profile_col]
            .dropna()
            .astype(str)
            .loc[lambda x: x.str.len().gt(0)]
        )
        unique_profiles = sorted(set(profiles))

        preferred = [
            p
            for p in unique_profiles
            if "HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1" in p.upper()
        ]
        if preferred:
            selected_profile = preferred[0]
            m = m[
                m[expr_profile_col].astype(str).eq(selected_profile)
            ].copy()
        elif len(unique_profiles) == 1:
            selected_profile = unique_profiles[0]
        elif len(unique_profiles) > 1:
            # Use the modal profile, but report this explicitly.
            selected_profile = profiles.value_counts().index[0]
            m = m[
                m[expr_profile_col].astype(str).eq(selected_profile)
            ].copy()

    # Keep only genes relevant to the new activity table, but do not split composite
    # symbols such as CBFB;RUNX1.
    activity_genes = set(
        activity["gene_symbol"].map(normalize_gene).loc[lambda x: x.ne("")]
    )
    m["_gene_key"] = m[gene_col].map(normalize_gene)
    m = m[m["_gene_key"].isin(activity_genes)].copy()

    if m.empty:
        raise RuntimeError(
            "No expression-authority rows matched the selected pooled-ketamine genes."
        )

    # Determine expression Z.
    expression_mode = ""
    if expr_z_col:
        m["_expression_z"] = finite_numeric(m[expr_z_col])
        expression_mode = f"DIRECT_COLUMN::{expr_z_col}"
    elif raw_hr_col and strength_col:
        hr = finite_numeric(m[raw_hr_col])
        strength = finite_numeric(m[strength_col])
        good = hr.notna() & strength.notna() & strength.abs().gt(1e-15)
        m["_expression_z"] = np.nan
        m.loc[good, "_expression_z"] = (
            hr.loc[good] / strength.loc[good]
        )
        expression_mode = (
            f"DERIVED_RATIO::{raw_hr_col}/{strength_col}"
        )
    else:
        raise RuntimeError(
            "Expression Z cannot be obtained: no direct expression-Z column and "
            "no usable raw-HR/activity-strength pair were found."
        )

    # Standardize tissue fields.
    if tissue_id_col:
        m["_tissue_id"] = m[tissue_id_col].map(s)
    else:
        m["_tissue_id"] = m[tissue_label_col].map(
            lambda x: "TISSUE_LABEL::" + s(x)
        )

    if tissue_label_col:
        m["_tissue_label"] = m[tissue_label_col].map(s)
    else:
        m["_tissue_label"] = m["_tissue_id"]

    # Remove missing expression or missing tissue.
    m = m[
        m["_expression_z"].notna()
        & m["_tissue_id"].ne("")
        & m["_tissue_label"].ne("")
        & m["_gene_key"].ne("")
    ].copy()

    # One expression value per gene x tissue. Expression should be invariant to
    # compound/activity evidence. Use median only after measuring the span.
    group_cols = ["_gene_key", "_tissue_id", "_tissue_label"]

    agg = (
        m.groupby(group_cols, dropna=False)["_expression_z"]
        .agg(["median", "min", "max", "count"])
        .reset_index()
        .rename(
            columns={
                "median": "expression_z",
                "count": "authority_support_rows",
            }
        )
    )
    agg["expression_z_span"] = agg["max"] - agg["min"]

    # Preserve optional raw expression where it is consistent enough to summarize.
    if raw_expr_col:
        rawx = (
            m.groupby(group_cols, dropna=False)[raw_expr_col]
            .agg(lambda x: pd.to_numeric(x, errors="coerce").median())
            .reset_index()
            .rename(columns={raw_expr_col: "raw_expression_median"})
        )
        agg = agg.merge(rawx, on=group_cols, how="left")

    # Expression values should be the same repeated target/tissue values. Very small
    # floating differences from reconstruction are permitted.
    conflict_tol = 1e-8
    conflicts = agg[agg["expression_z_span"].abs().gt(conflict_tol)].copy()

    # Add representative authority target IDs, if available.
    if target_col:
        tids = (
            m.groupby(group_cols, dropna=False)[target_col]
            .agg(lambda x: " | ".join(sorted(set(map(str, x.dropna())))))
            .reset_index()
            .rename(columns={target_col: "authority_target_ids"})
        )
        agg = agg.merge(tids, on=group_cols, how="left")

    agg = agg.rename(
        columns={
            "_gene_key": "gene_key",
            "_tissue_id": "tissue_id",
            "_tissue_label": "tissue_label",
        }
    )

    meta = {
        "gene_column": gene_col,
        "target_column": target_col,
        "tissue_id_column": tissue_id_col,
        "tissue_label_column": tissue_label_col,
        "expression_z_source": expression_mode,
        "raw_expression_column": raw_expr_col,
        "expression_profile_column": expr_profile_col,
        "selected_expression_profile": selected_profile,
        "human_expression_filter_applied": human_filter_applied,
        "matched_authority_rows_before_aggregation": len(m),
        "expression_gene_tissue_rows": len(agg),
        "unique_genes": int(agg["gene_key"].nunique()),
        "unique_tissues": int(agg["tissue_id"].nunique()),
        "expression_conflict_rows_gt_1e-8": len(conflicts),
    }

    log(
        "Expression extraction: "
        f"{meta['unique_genes']} matched genes x "
        f"{meta['unique_tissues']} tissues; "
        f"mode={expression_mode}; conflicts={len(conflicts)}"
    )

    return agg, meta


# =============================================================================
# HR calculation
# =============================================================================

def hr_relation(p_rel: str, z: float) -> Tuple[str, str]:
    """
    Return (HR relation, status) for HR = pActivity * expression_Z.
    """
    if not math.isfinite(z):
        return "?", "MISSING_EXPRESSION"

    if p_rel == "=":
        return "=", "EXACT"

    if abs(z) <= 1e-15:
        return "=", "EXACT_ZERO_FROM_EXPRESSION_Z_ZERO"

    if p_rel == "<":
        if z > 0:
            return "<", "BOUNDED_UPPER"
        else:
            return ">", "BOUNDED_LOWER"

    if p_rel == ">":
        if z > 0:
            return ">", "BOUNDED_LOWER"
        else:
            return "<", "BOUNDED_UPPER"

    return "?", "RELATION_UNRESOLVED"


def build_hr(
    activity: pd.DataFrame,
    expression: pd.DataFrame,
    log,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Join activity and expression and compute bounded or exact HR coordinates."""
    a = activity.copy()
    a["gene_key"] = a["gene_symbol"].map(normalize_gene)

    # Expression matching is by exact gene symbol from the final target mapping.
    # Composite gene symbols are matched only if the authority contains that exact
    # composite key.
    merged = a.merge(
        expression,
        on="gene_key",
        how="left",
        validate="one_to_many",
        indicator=True,
    )

    missing_targets = (
        merged.loc[merged["_merge"].eq("left_only"), activity.columns]
        .drop_duplicates("canonical_target_id")
        .copy()
    )

    m = merged[merged["_merge"].eq("both")].copy()
    m = m.drop(columns=["_merge"])

    if m.empty:
        raise RuntimeError("No target could be matched to authoritative expression.")

    p = finite_numeric(m["activity_pactivity_numeric"])
    z = finite_numeric(m["expression_z"])
    m["HR_numeric_boundary_or_exact"] = p * z

    rels = []
    statuses = []
    for pr, zz in zip(m["pactivity_relation"], z):
        rel, status = hr_relation(s(pr), fnum(zz))
        rels.append(rel)
        statuses.append(status)

    m["HR_relation"] = rels
    m["HR_value_status"] = statuses

    # Explicit semantics.
    m["HR_formula"] = "pActivity * expression_Z"
    m["expression_species"] = "Homo sapiens"
    m["expression_species_taxon_id"] = 9606
    m["analysis_profile"] = "POOLED_PARENT_KETAMINE_FULL_HUMAN_TISSUE_HR_V1"

    # Preserve the distinction between affinity relation and pActivity relation.
    m["affinity_relation_operator"] = m[
        "final_activity_relation_operator_v4"
    ]
    m["affinity_relation_class"] = m[
        "final_activity_relation_class_v4"
    ]

    # Human-readable bound interpretation.
    def interpretation(row):
        """Render the scientific interpretation for one HR coordinate."""
        if s(row["HR_value_status"]) == "EXACT":
            return "HR exact conditional on selected activity and expression Z."
        if s(row["HR_value_status"]) == "EXACT_ZERO_FROM_EXPRESSION_Z_ZERO":
            return "HR equals zero because expression Z equals zero."
        if s(row["HR_value_status"]) == "BOUNDED_UPPER":
            return (
                f"HR {s(row['HR_relation'])} "
                f"{fnum(row['HR_numeric_boundary_or_exact']):.15g}; "
                "numeric value is a boundary, not an exact HR score."
            )
        if s(row["HR_value_status"]) == "BOUNDED_LOWER":
            return (
                f"HR {s(row['HR_relation'])} "
                f"{fnum(row['HR_numeric_boundary_or_exact']):.15g}; "
                "numeric value is a boundary, not an exact HR score."
            )
        return "HR relation unresolved."

    m["HR_interpretation"] = m.apply(interpretation, axis=1)

    # Stable useful ordering.
    front = [
        "analysis_compound",
        "analysis_profile",
        "canonical_target_id",
        "gene_symbol",
        "target_name",
        "tissue_id",
        "tissue_label",
        "activity_pactivity_numeric",
        "pactivity_relation",
        "affinity_relation_operator",
        "affinity_relation_class",
        "final_activity_value_status_v4",
        "expression_z",
        "HR_numeric_boundary_or_exact",
        "HR_relation",
        "HR_value_status",
        "HR_formula",
        "HR_interpretation",
        "expression_species",
        "expression_species_taxon_id",
    ]
    remaining = [c for c in m.columns if c not in front]
    m = m[front + remaining]

    m = m.sort_values(
        ["canonical_target_id", "tissue_label", "tissue_id"],
        kind="stable",
    ).reset_index(drop=True)

    # Target-level coverage.
    cov = (
        m.groupby(
            ["canonical_target_id", "gene_symbol"],
            dropna=False,
        )
        .agg(
            tissue_count=("tissue_id", "nunique"),
            finite_HR_count=("HR_numeric_boundary_or_exact", lambda x: pd.to_numeric(x, errors="coerce").notna().sum()),
            exact_HR_coordinate_count=("HR_value_status", lambda x: x.astype(str).str.startswith("EXACT").sum()),
            bounded_HR_coordinate_count=("HR_value_status", lambda x: x.astype(str).str.startswith("BOUNDED").sum()),
            min_expression_z=("expression_z", "min"),
            max_expression_z=("expression_z", "max"),
            min_HR_numeric=("HR_numeric_boundary_or_exact", "min"),
            max_HR_numeric=("HR_numeric_boundary_or_exact", "max"),
        )
        .reset_index()
    )

    # Attach selected activity classification.
    cov = cov.merge(
        a[
            [
                "canonical_target_id",
                "final_activity_relation_class_v4",
                "final_hr_input_status_v4",
                "activity_pactivity_numeric",
            ]
        ],
        on="canonical_target_id",
        how="left",
    )

    log(
        f"HR calculation generated {len(m):,} target-tissue rows "
        f"for {m['canonical_target_id'].nunique()} targets."
    )

    return m, cov, missing_targets


# =============================================================================
# Wide matrices
# =============================================================================

def build_wide(hr: pd.DataFrame):
    """Pivot long HR coordinates into stable numerical and status matrices."""
    numeric = hr.pivot_table(
        index=["canonical_target_id", "gene_symbol"],
        columns="tissue_label",
        values="HR_numeric_boundary_or_exact",
        aggfunc="first",
    ).reset_index()
    numeric.columns.name = None

    relation = hr.pivot_table(
        index=["canonical_target_id", "gene_symbol"],
        columns="tissue_label",
        values="HR_relation",
        aggfunc="first",
    ).reset_index()
    relation.columns.name = None

    status = hr.pivot_table(
        index=["canonical_target_id", "gene_symbol"],
        columns="tissue_label",
        values="HR_value_status",
        aggfunc="first",
    ).reset_index()
    status.columns.name = None

    return numeric, relation, status


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    parser = argparse.ArgumentParser(
        description="Generate full-tissue pooled-parent-ketamine HR profile."
    )
    parser.add_argument("--v4-dir", type=Path, required=True)
    parser.add_argument(
        "--expression-authority",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    v4_dir = args.v4_dir.resolve()
    activity_path = (
        v4_dir
        / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv"
    )
    expression_authority = args.expression_authority.resolve()

    output_dir = v4_dir / f"Full_Tissue_HR_v1_{stamp()}"
    output_dir.mkdir(parents=True, exist_ok=False)
    log_path = output_dir / "RUN.log"

    def log(msg: str):
        """Write one timestamped run-log message."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    try:
        log("=== POOLED PARENT KETAMINE FULL-TISSUE HR V1 START ===")
        log(f"V4 directory: {v4_dir}")
        log(f"Activity input: {activity_path}")
        log(f"Expression authority: {expression_authority}")
        log(f"Output: {output_dir}")

        if not activity_path.is_file():
            raise FileNotFoundError(
                f"Final v4 HR-input target activity table not found: {activity_path}"
            )
        if not expression_authority.is_dir():
            raise FileNotFoundError(
                f"Expression authority directory not found: {expression_authority}"
            )

        activity = load_activity(activity_path, log)
        master_path = locate_master(
            expression_authority,
            expression_authority
            / "06_PRE_FINGERPRINT_MASTER"
            / "PRE_FINGERPRINT_MASTER_ALL_SPECIES.parquet",
            log,
        )

        log(f"Expression master: {master_path}")
        master = pd.read_parquet(master_path)
        log(
            f"Loaded expression/master authority rows: {len(master):,}; "
            f"columns: {len(master.columns)}"
        )

        expression, expr_meta = expression_from_master(
            master,
            activity,
            log,
        )

        # Save expression conflicts separately; do not silently suppress material
        # conflicts. If any exist, fail before treating HR as ready.
        conflicts = expression[
            expression["expression_z_span"].abs().gt(1e-8)
        ].copy()
        conflicts.to_csv(
            output_dir / "EXPRESSION_CONFLICTS_GT_1E-8.csv",
            index=False,
        )
        if len(conflicts):
            raise RuntimeError(
                f"Safety stop: {len(conflicts)} gene-tissue expression coordinates "
                "have expression-Z span > 1e-8 across the authoritative source rows. "
                "Inspect EXPRESSION_CONFLICTS_GT_1E-8.csv."
            )

        hr, coverage, missing = build_hr(
            activity,
            expression,
            log,
        )

        numeric_matrix, relation_matrix, status_matrix = build_wide(hr)

        # Expression matrix used.
        expr_matrix = expression[
            expression["gene_key"].isin(
                set(activity["gene_symbol"].map(normalize_gene))
            )
        ].pivot_table(
            index="gene_key",
            columns="tissue_label",
            values="expression_z",
            aggfunc="first",
        ).reset_index()
        expr_matrix.columns.name = None

        # Main outputs.
        hr_csv = output_dir / "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv"
        hr_pq = output_dir / "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.parquet"
        write_csv_parquet(hr, hr_csv, hr_pq)

        numeric_matrix.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_HR_NUMERIC_MATRIX_V1.csv",
            index=False,
        )
        relation_matrix.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_HR_RELATION_MATRIX_V1.csv",
            index=False,
        )
        status_matrix.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_HR_STATUS_MATRIX_V1.csv",
            index=False,
        )
        expr_matrix.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_EXPRESSION_MATRIX_USED_V1.csv",
            index=False,
        )
        expression.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_EXPRESSION_LONG_USED_V1.csv",
            index=False,
        )
        coverage.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_TARGET_HR_COVERAGE_V1.csv",
            index=False,
        )
        missing.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_MISSING_EXPRESSION_TARGETS_V1.csv",
            index=False,
        )
        activity.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_ACTIVITY_INPUT_V4_SNAPSHOT.csv",
            index=False,
        )

        # Useful coordinate review table — not a fingerprint.
        ranked = hr.copy()
        ranked["_abs_hr"] = ranked["HR_numeric_boundary_or_exact"].abs()
        ranked = ranked.sort_values(
            ["_abs_hr", "canonical_target_id", "tissue_label"],
            ascending=[False, True, True],
            kind="stable",
        ).drop(columns="_abs_hr")
        ranked.to_csv(
            output_dir / "POOLED_PARENT_KETAMINE_HR_COORDINATES_SORTED_BY_ABS_NUMERIC_V1.csv",
            index=False,
        )

        n_targets = int(hr["canonical_target_id"].nunique())
        n_tissues = int(hr["tissue_id"].nunique())
        n_rows = len(hr)
        exact_coords = int(
            hr["HR_value_status"].astype(str).str.startswith("EXACT").sum()
        )
        bounded_coords = int(
            hr["HR_value_status"].astype(str).str.startswith("BOUNDED").sum()
        )
        missing_n = int(len(missing))

        # Count target categories represented in HR output.
        hr_target_class = (
            hr[
                [
                    "canonical_target_id",
                    "final_activity_relation_class_v4",
                ]
            ]
            .drop_duplicates()
            ["final_activity_relation_class_v4"]
            .value_counts()
            .to_dict()
        )

        # Coverage status.
        if missing_n == 0 and n_targets == 76:
            run_status = "PASS_FULL_ACTIVITY_TARGET_EXPRESSION_COVERAGE"
        else:
            run_status = "PASS_WITH_MISSING_EXPRESSION_TARGETS"

        summary = {
            "status": run_status,
            "activity_input": str(activity_path),
            "activity_input_sha256": sha256(activity_path),
            "expression_authority": str(expression_authority),
            "expression_master": str(master_path),
            "expression_master_sha256": sha256(master_path),
            "expression_metadata": expr_meta,
            "selected_activity_targets": len(activity),
            "HR_targets_with_expression": n_targets,
            "HR_targets_missing_expression": missing_n,
            "human_tissues_in_HR": n_tissues,
            "HR_target_tissue_rows": n_rows,
            "HR_target_activity_classes": hr_target_class,
            "exact_HR_coordinates": exact_coords,
            "bounded_HR_coordinates": bounded_coords,
            "formula": "pActivity * expression_Z",
            "bounded_semantics": (
                "For Ki > boundary, pActivity < boundary pActivity; "
                "HR relation is sign-aware with respect to expression_Z."
            ),
            "fingerprint_calculated": False,
            "GESD_calculated": False,
            "CNS_filter_applied": False,
        }

        (output_dir / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )

        lines = [
            "=== POOLED PARENT KETAMINE FULL-TISSUE HR V1 COMPLETE ===",
            "",
            f"Status: {run_status}",
            "",
            "ACTIVITY INPUT",
            f"Selected activity targets: {len(activity)}",
            "Exact measured targets: 40",
            "Bounded Ki >10,000 nM targets: 36",
            "",
            "EXPRESSION",
            f"Expression authority: {expression_authority}",
            f"Expression master: {master_path}",
            f"Expression-Z method: {expr_meta['expression_z_source']}",
            f"Expression profile: {expr_meta.get('selected_expression_profile','')}",
            f"Human tissues represented in HR: {n_tissues}",
            "",
            "HR OUTPUT",
            f"Targets with authoritative expression: {n_targets}",
            f"Targets missing authoritative expression: {missing_n}",
            f"Target-tissue HR rows: {n_rows}",
            f"Exact HR coordinates: {exact_coords}",
            f"Bounded HR coordinates: {bounded_coords}",
            "",
            "FORMULA",
            "HR = pActivity * expression_Z",
            "",
            "BOUNDED SEMANTICS",
            "For Ki >10,000 nM:",
            "  pActivity < 5",
            "  numeric HR boundary = 5 * expression_Z",
            "  expression_Z > 0 => HR < numeric boundary",
            "  expression_Z < 0 => HR > numeric boundary",
            "  expression_Z = 0 => HR = 0",
            "",
            "NO CNS-ONLY FILTER WAS APPLIED.",
            "NO GESD OR FINGERPRINT WAS CALCULATED.",
            "NO PCA / CLUSTERING / MULTIVARIATE ANALYSIS WAS PERFORMED.",
            "",
            f"Main long HR table: {hr_csv}",
            f"Output folder: {output_dir}",
            "QA: PASS",
        ]

        (output_dir / "SUMMARY.txt").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        # Hash all outputs.
        hashes = []
        for p in sorted(output_dir.iterdir()):
            if p.is_file() and p.name != "OUTPUT_SHA256SUMS.csv":
                hashes.append(
                    {
                        "filename": p.name,
                        "bytes": p.stat().st_size,
                        "sha256": sha256(p),
                    }
                )
        pd.DataFrame(hashes).to_csv(
            output_dir / "OUTPUT_SHA256SUMS.csv",
            index=False,
        )

        log(f"Status: {run_status}")
        log(
            f"HR rows={n_rows:,}; targets={n_targets}; tissues={n_tissues}; "
            f"exact coordinates={exact_coords:,}; bounded coordinates={bounded_coords:,}"
        )
        log("QA: PASS")
        log("NO FINGERPRINT CALCULATED")

        print()
        print("\n".join(lines))
        return 0

    except Exception as exc:
        tb = traceback.format_exc()
        log("=== FAILED ===")
        log(repr(exc))
        log(tb)
        (output_dir / "FAILURE.json").write_text(
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
        print(
            f"\nFAILED: {exc}\nSee {log_path}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
