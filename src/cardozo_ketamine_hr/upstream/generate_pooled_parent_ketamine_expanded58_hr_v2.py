#!/usr/bin/env python3
r"""
POOLED PARENT KETAMINE — EXPANDED 58-TARGET FULL-TISSUE HR v2
=============================================================

PURPOSE
-------
Regenerate the pooled-parent-ketamine full human-tissue HR profile after the
missing-expression audit recovered 20 of the 38 targets that were absent from
the first HR run.

Final expected expression coverage:
    existing HR-v1 targets: 38
    newly recovered targets: 20
    still missing expression: 18
    total represented HR targets: 58

With the frozen 77-tissue BioGPS/GNF1H DDOF1 contract:
    58 x 77 = 4,466 target-tissue HR coordinates

THIS SCRIPT DOES
----------------
1. Loads the final v4 76-target activity table.
2. Loads the original HR-v1 long table for the 38 previously represented targets.
3. Loads the 20 recovered 77-tissue expression profiles from the recovery audit.
4. Reconstructs a unified 58-target x 77-tissue expression table.
5. Recalculates HR for all 58 targets from the SAME v4 target activities:
       HR = pActivity * expression_Z
6. Preserves exact vs bounded activity semantics.
7. For Ki > 10,000 nM:
       pActivity < 5
   and therefore:
       if Z > 0: HR < 5Z
       if Z < 0: HR > 5Z
       if Z = 0: HR = 0
8. Cross-checks the regenerated 2,926 old coordinates against HR-v1 and requires
   numerical/relation agreement.
9. Produces the expanded long table, matrices, expression table, coverage table,
   and an explicit 18-target missing-expression manifest.
10. DOES NOT run GESD/fingerprinting/PCA/clustering.

NO IMPUTATION
-------------
- No missing expression is zero-filled.
- The 18 unrecoverable targets remain absent from the HR matrix and are listed
  explicitly.
- Composite targets are not decomposed.

EXPECTED INPUTS
---------------
V4 activity:
  ...\Final_Activity_v4_20260813_084842\
  POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv

HR-v1:
  ...\Full_Tissue_HR_v1_20260813_085417\
  POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv

Recovery audit:
  ...\Missing38_Expression_Recovery_Audit_v1_20260813_100740\
  RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.csv
  STILL_UNRECOVERABLE_TARGETS.csv

OUTPUT
------
A timestamped sibling folder under HR-v1:
  Expanded58_Full_Tissue_HR_v2_YYYYMMDD_HHMMSS

Publication contract
--------------------
Purpose: Extend the full-tissue HR profile with exactly recovered expression targets.
Stage/lane: Recovered Expanded58 HR v2, after recovery audit and before fingerprinting.
Inputs: Explicit Final Activity v4, first full-HR, and recovery-audit directories.
Outputs: A new timestamped Expanded58 directory with long HR/expression tables,
matrices, coverage/missing manifests, cross-checks, summaries, hashes, and log.
Side effects: Creates derivative files only; it neither edits authorities nor runs
GESD, PCA, clustering, or comparator analyses.
Invariants: The 58-by-77 universe, HR formula and censoring, 2,926 old coordinates,
18 unrecoverable targets, exact mappings, and NA-without-imputation remain fixed.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd


PROJECT_ROOT = None
V4_DIR = None
DEFAULT_HR1_DIR = None
DEFAULT_RECOVERY_DIR = None

EXPECTED_TOTAL_ACTIVITY_TARGETS = 76
EXPECTED_OLD_HR_TARGETS = 38
EXPECTED_RECOVERED_TARGETS = 20
EXPECTED_FINAL_HR_TARGETS = 58
EXPECTED_MISSING_TARGETS = 18
EXPECTED_TISSUES = 77
EXPECTED_OLD_ROWS = 2926
EXPECTED_FINAL_ROWS = 4466

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
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def finite(series) -> pd.Series:
    """Coerce a series to finite numeric values while preserving missingness."""
    x = pd.to_numeric(series, errors="coerce")
    return x.where(np.isfinite(x), np.nan)


def hr_relation(p_rel: str, z: float) -> Tuple[str, str]:
    """Propagate activity censoring through the sign of expression."""
    if not math.isfinite(z):
        return "?", "MISSING_EXPRESSION"

    if p_rel == "=":
        return "=", "EXACT"

    if abs(z) <= 1e-15:
        return "=", "EXACT_ZERO_FROM_EXPRESSION_Z_ZERO"

    if p_rel == "<":
        return ("<", "BOUNDED_UPPER") if z > 0 else (">", "BOUNDED_LOWER")

    if p_rel == ">":
        return (">", "BOUNDED_LOWER") if z > 0 else ("<", "BOUNDED_UPPER")

    return "?", "RELATION_UNRESOLVED"


def pactivity_relation_from_affinity_class(v: str) -> str:
    """Map an affinity class to its governed pActivity relation."""
    x = s(v)
    if x == "EXACT":
        return "="
    if x == "GT_BOUND":
        return "<"   # Ki > bound => pActivity < boundary
    if x == "LT_BOUND":
        return ">"   # Ki < bound => pActivity > boundary
    return "?"


def load_inputs(v4_dir: Path, hr1_dir: Path, recovery_dir: Path, log):
    """Load the accepted activity, HR, and expression-recovery inputs."""
    activity_path = v4_dir / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv"
    hr1_path = hr1_dir / "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv"
    rec_path = recovery_dir / "RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.csv"
    missing_path = recovery_dir / "STILL_UNRECOVERABLE_TARGETS.csv"

    for p in (activity_path, hr1_path, rec_path, missing_path):
        if not p.is_file():
            raise FileNotFoundError(f"Required input not found: {p}")

    activity = pd.read_csv(activity_path, low_memory=False)
    hr1 = pd.read_csv(hr1_path, low_memory=False)
    recovered = pd.read_csv(rec_path, low_memory=False)
    missing = pd.read_csv(missing_path, low_memory=False)

    log(f"Activity targets: {len(activity)}")
    log(f"HR-v1 rows: {len(hr1)}")
    log(f"Recovered expression rows: {len(recovered)}")
    log(f"Still-unrecoverable target rows: {len(missing)}")

    if len(activity) != EXPECTED_TOTAL_ACTIVITY_TARGETS:
        raise RuntimeError(
            f"Expected {EXPECTED_TOTAL_ACTIVITY_TARGETS} activity targets; found {len(activity)}"
        )
    if len(hr1) != EXPECTED_OLD_ROWS:
        raise RuntimeError(
            f"Expected {EXPECTED_OLD_ROWS} HR-v1 rows; found {len(hr1)}"
        )
    if len(recovered) != EXPECTED_RECOVERED_TARGETS * EXPECTED_TISSUES:
        raise RuntimeError(
            f"Expected {EXPECTED_RECOVERED_TARGETS * EXPECTED_TISSUES} recovered expression rows; "
            f"found {len(recovered)}"
        )
    if len(missing) != EXPECTED_MISSING_TARGETS:
        raise RuntimeError(
            f"Expected {EXPECTED_MISSING_TARGETS} still-unrecoverable targets; found {len(missing)}"
        )

    return (
        activity,
        hr1,
        recovered,
        missing,
        activity_path,
        hr1_path,
        rec_path,
        missing_path,
    )


def extract_old_expression(hr1: pd.DataFrame, log) -> pd.DataFrame:
    """Recover accepted expression coordinates from the first HR run."""
    required = [
        "canonical_target_id",
        "gene_symbol",
        "tissue_id",
        "tissue_label",
        "expression_z",
    ]
    missing = [c for c in required if c not in hr1.columns]
    if missing:
        raise RuntimeError(f"HR-v1 long table missing required columns: {missing}")

    cols = required.copy()
    optional_map = {
        "raw_expression_median": ["raw_expression_median", "expression_raw"],
        "expression_species": ["expression_species"],
        "expression_species_taxon_id": ["expression_species_taxon_id"],
    }

    old = hr1[required].copy()

    for outcol, candidates in optional_map.items():
        c = find_col(hr1, candidates)
        if c:
            old[outcol] = hr1[c]
        else:
            old[outcol] = np.nan

    old = old.drop_duplicates(
        ["canonical_target_id", "tissue_id"],
        keep="first",
    ).copy()

    if len(old) != EXPECTED_OLD_ROWS:
        raise RuntimeError(
            "HR-v1 expression extraction did not produce exactly one row per "
            f"old target-tissue coordinate: {len(old)}"
        )

    counts = old.groupby("canonical_target_id")["tissue_id"].nunique()
    if len(counts) != EXPECTED_OLD_HR_TARGETS or not counts.eq(EXPECTED_TISSUES).all():
        raise RuntimeError(
            "HR-v1 old expression does not satisfy 38 targets x 77 tissues."
        )

    old["expression_recovery_source"] = "HR_V1_EXISTING_AUTHORITY_EXPRESSION"
    old["expression_recovery_mapping_method"] = "EXISTING_HR_V1_COORDINATE"
    log("Old expression extracted: 38 targets x 77 tissues")
    return old


def normalize_recovered_expression(recovered: pd.DataFrame, log) -> pd.DataFrame:
    """Normalize recovered expression rows to the stable coordinate schema."""
    required = [
        "canonical_target_id",
        "gene_symbol",
        "tissue_canonical_id",
        "tissue_label",
        "expression_Z",
        "expression_ddof",
        "expression_profile_id",
        "expression_species",
    ]
    missing = [c for c in required if c not in recovered.columns]
    if missing:
        raise RuntimeError(f"Recovered expression table missing required columns: {missing}")

    x = pd.DataFrame(
        {
            "canonical_target_id": recovered["canonical_target_id"].astype(str),
            "gene_symbol": recovered["gene_symbol"].astype(str),
            "tissue_id": recovered["tissue_canonical_id"].astype(str),
            "tissue_label": recovered["tissue_label"].astype(str),
            "expression_z": finite(recovered["expression_Z"]),
            "raw_expression_median": finite(recovered["expression_raw"])
            if "expression_raw" in recovered.columns
            else np.nan,
            "expression_species": recovered["expression_species"].astype(str),
            "expression_species_taxon_id": 9606,
            "expression_recovery_source": recovered["recovery_source"].astype(str)
            if "recovery_source" in recovered.columns
            else "MISSING38_RECOVERY_AUDIT",
            "expression_recovery_mapping_method": recovered["recovery_mapping_method"].astype(str)
            if "recovery_mapping_method" in recovered.columns
            else "RECOVERY_AUDIT",
        }
    )

    if x["expression_z"].isna().any():
        raise RuntimeError("Recovered expression contains missing/nonfinite expression_Z")

    ddof = sorted(set(pd.to_numeric(recovered["expression_ddof"], errors="coerce").dropna()))
    profiles = sorted(set(recovered["expression_profile_id"].dropna().astype(str)))
    species = sorted(set(recovered["expression_species"].dropna().astype(str)))

    if ddof != [1.0]:
        raise RuntimeError(f"Recovered expression ddof mismatch: {ddof}")
    if profiles != ["HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1"]:
        raise RuntimeError(f"Recovered expression profile mismatch: {profiles}")
    if species not in (["Homo sapiens"], ["human"], ["Human"]):
        # Be strict but case-agnostic.
        if {z.lower() for z in species} != {"homo sapiens"}:
            raise RuntimeError(f"Recovered expression species mismatch: {species}")

    if x.duplicated(["canonical_target_id", "tissue_id"]).any():
        raise RuntimeError("Recovered expression contains duplicate target-tissue coordinates")

    counts = x.groupby("canonical_target_id")["tissue_id"].nunique()
    if len(counts) != EXPECTED_RECOVERED_TARGETS or not counts.eq(EXPECTED_TISSUES).all():
        raise RuntimeError(
            "Recovered expression does not satisfy 20 targets x 77 tissues."
        )

    log("Recovered expression validated: 20 targets x 77 tissues")
    return x


def build_unified_expression(old_expr: pd.DataFrame, rec_expr: pd.DataFrame, log) -> pd.DataFrame:
    """Combine old and recovered expression without filling missing targets."""
    overlap = set(old_expr["canonical_target_id"]) & set(rec_expr["canonical_target_id"])
    if overlap:
        raise RuntimeError(
            f"Recovered target set unexpectedly overlaps old HR-v1 targets: {sorted(overlap)}"
        )

    x = pd.concat([old_expr, rec_expr], ignore_index=True, sort=False)

    if x.duplicated(["canonical_target_id", "tissue_id"]).any():
        bad = x.loc[
            x.duplicated(["canonical_target_id", "tissue_id"], keep=False),
            ["canonical_target_id", "tissue_id"],
        ]
        raise RuntimeError(
            "Unified expression has duplicate target-tissue coordinates:\n"
            + bad.head(30).to_string(index=False)
        )

    counts = x.groupby("canonical_target_id")["tissue_id"].nunique()
    if len(counts) != EXPECTED_FINAL_HR_TARGETS:
        raise RuntimeError(
            f"Expected {EXPECTED_FINAL_HR_TARGETS} expression-covered targets; found {len(counts)}"
        )
    if not counts.eq(EXPECTED_TISSUES).all():
        bad = counts[~counts.eq(EXPECTED_TISSUES)]
        raise RuntimeError(
            "Unified expression contains targets without 77 tissues:\n"
            + bad.to_string()
        )
    if len(x) != EXPECTED_FINAL_ROWS:
        raise RuntimeError(
            f"Expected {EXPECTED_FINAL_ROWS} unified expression rows; found {len(x)}"
        )

    if x["expression_z"].isna().any():
        raise RuntimeError("Unified expression contains missing expression_z")

    log("Unified expression PASS: 58 targets x 77 tissues = 4,466 rows")
    return x


def calculate_hr(activity: pd.DataFrame, expr: pd.DataFrame, log) -> pd.DataFrame:
    """Calculate HR as selected pActivity times expression z-score."""
    if activity["canonical_target_id"].astype(str).duplicated().any():
        raise RuntimeError("Activity input has duplicate canonical_target_id values")

    a = activity.copy()
    a["activity_pactivity_numeric"] = finite(a["final_selected_pActivity_v4"])
    a["pactivity_relation"] = a["final_activity_relation_class_v4"].map(
        pactivity_relation_from_affinity_class
    )

    if a["activity_pactivity_numeric"].isna().any():
        raise RuntimeError("Activity input contains missing pActivity")

    m = expr.merge(
        a,
        on=["canonical_target_id"],
        how="left",
        validate="many_to_one",
        suffixes=("_expression", ""),
    )

    if m["activity_pactivity_numeric"].isna().any():
        bad = sorted(
            set(
                m.loc[
                    m["activity_pactivity_numeric"].isna(),
                    "canonical_target_id",
                ].astype(str)
            )
        )
        raise RuntimeError(f"Expression-covered targets missing activity after merge: {bad}")

    # Ensure expression gene mapping and activity gene mapping agree exactly where both exist.
    if "gene_symbol_expression" in m.columns and "gene_symbol" in m.columns:
        disagree = m[
            m["gene_symbol_expression"].astype(str).str.upper()
            != m["gene_symbol"].astype(str).str.upper()
        ]
        if len(disagree):
            raise RuntimeError(
                "Activity gene symbol disagrees with recovered/existing expression gene mapping "
                "for one or more targets."
            )

    z = finite(m["expression_z"])
    p = finite(m["activity_pactivity_numeric"])
    m["HR_numeric_boundary_or_exact"] = p * z

    rels = []
    statuses = []
    for pr, zz in zip(m["pactivity_relation"], z):
        rel, status = hr_relation(s(pr), fnum(zz))
        rels.append(rel)
        statuses.append(status)

    m["HR_relation"] = rels
    m["HR_value_status"] = statuses
    m["HR_formula"] = "pActivity * expression_Z"
    m["analysis_profile"] = "POOLED_PARENT_KETAMINE_EXPANDED58_FULL_HUMAN_TISSUE_HR_V2"
    m["expression_profile_id"] = "HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1"
    m["expression_ddof"] = 1
    m["expression_species"] = "Homo sapiens"
    m["expression_species_taxon_id"] = 9606
    m["affinity_relation_operator"] = m["final_activity_relation_operator_v4"]
    m["affinity_relation_class"] = m["final_activity_relation_class_v4"]

    def interp(row):
        """Render the exact or censored HR interpretation for one coordinate."""
        status = s(row["HR_value_status"])
        val = fnum(row["HR_numeric_boundary_or_exact"])
        rel = s(row["HR_relation"])
        if status == "EXACT":
            return "HR exact conditional on selected activity and expression Z."
        if status == "EXACT_ZERO_FROM_EXPRESSION_Z_ZERO":
            return "HR equals zero because expression Z equals zero."
        if status.startswith("BOUNDED"):
            return (
                f"HR {rel} {val:.15g}; numeric value is a boundary, "
                "not an exact HR score."
            )
        return "HR relation unresolved."

    m["HR_interpretation"] = m.apply(interp, axis=1)

    if len(m) != EXPECTED_FINAL_ROWS:
        raise RuntimeError(
            f"Expected {EXPECTED_FINAL_ROWS} HR rows; found {len(m)}"
        )
    if m["canonical_target_id"].nunique() != EXPECTED_FINAL_HR_TARGETS:
        raise RuntimeError(
            f"Expected {EXPECTED_FINAL_HR_TARGETS} HR targets; found "
            f"{m['canonical_target_id'].nunique()}"
        )
    if m["tissue_id"].nunique() != EXPECTED_TISSUES:
        raise RuntimeError(
            f"Expected {EXPECTED_TISSUES} tissues; found {m['tissue_id'].nunique()}"
        )

    log("Expanded HR calculation generated 4,466 rows for 58 targets x 77 tissues")
    return m


def crosscheck_old_coordinates(hr2: pd.DataFrame, hr1: pd.DataFrame, outdir: Path, log):
    """Confirm accepted coordinates are unchanged in the expanded derivative."""
    cols = [
        "canonical_target_id",
        "tissue_id",
        "HR_numeric_boundary_or_exact",
        "HR_relation",
        "HR_value_status",
        "expression_z",
    ]
    missing = [c for c in cols if c not in hr1.columns]
    if missing:
        raise RuntimeError(f"HR-v1 missing crosscheck columns: {missing}")

    old_targets = set(hr1["canonical_target_id"].astype(str))
    h2 = hr2[hr2["canonical_target_id"].astype(str).isin(old_targets)].copy()

    if len(h2) != EXPECTED_OLD_ROWS:
        raise RuntimeError(
            f"Expanded HR old-target subset expected {EXPECTED_OLD_ROWS} rows; found {len(h2)}"
        )

    a = hr1[cols].copy().rename(
        columns={
            "HR_numeric_boundary_or_exact": "HR_old",
            "HR_relation": "relation_old",
            "HR_value_status": "status_old",
            "expression_z": "z_old",
        }
    )
    b = h2[cols].copy().rename(
        columns={
            "HR_numeric_boundary_or_exact": "HR_new",
            "HR_relation": "relation_new",
            "HR_value_status": "status_new",
            "expression_z": "z_new",
        }
    )

    c = a.merge(
        b,
        on=["canonical_target_id", "tissue_id"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    if not c["_merge"].eq("both").all():
        raise RuntimeError("Old HR coordinate set changed during expanded rebuild")

    c["abs_delta_z"] = (finite(c["z_old"]) - finite(c["z_new"])).abs()
    c["abs_delta_HR"] = (finite(c["HR_old"]) - finite(c["HR_new"])).abs()
    c["relation_match"] = c["relation_old"].astype(str).eq(c["relation_new"].astype(str))
    c["status_match"] = c["status_old"].astype(str).eq(c["status_new"].astype(str))

    c.to_csv(
        outdir / "HR_V1_VS_EXPANDED58_CROSSCHECK.csv",
        index=False,
    )

    max_z = float(c["abs_delta_z"].max())
    max_hr = float(c["abs_delta_HR"].max())
    relation_ok = bool(c["relation_match"].all())
    status_ok = bool(c["status_match"].all())

    log(
        f"Old-coordinate crosscheck: max |delta Z|={max_z:.3g}; "
        f"max |delta HR|={max_hr:.3g}; relation_match={relation_ok}; status_match={status_ok}"
    )

    if max_z > TOL or max_hr > TOL or not relation_ok or not status_ok:
        raise RuntimeError(
            "Expanded HR does not reproduce HR-v1 old coordinates within tolerance."
        )

    return {
        "coordinates": len(c),
        "max_abs_delta_expression_Z": max_z,
        "max_abs_delta_HR": max_hr,
        "relations_all_match": relation_ok,
        "statuses_all_match": status_ok,
    }


def build_coverage(hr: pd.DataFrame, activity: pd.DataFrame) -> pd.DataFrame:
    """Summarize target-level HR and expression coverage."""
    cov = (
        hr.groupby(
            ["canonical_target_id"],
            dropna=False,
        )
        .agg(
            tissue_count=("tissue_id", "nunique"),
            finite_HR_count=("HR_numeric_boundary_or_exact", lambda x: finite(x).notna().sum()),
            exact_HR_coordinate_count=("HR_value_status", lambda x: x.astype(str).str.startswith("EXACT").sum()),
            bounded_HR_coordinate_count=("HR_value_status", lambda x: x.astype(str).str.startswith("BOUNDED").sum()),
            min_expression_z=("expression_z", "min"),
            max_expression_z=("expression_z", "max"),
            min_HR_numeric=("HR_numeric_boundary_or_exact", "min"),
            max_HR_numeric=("HR_numeric_boundary_or_exact", "max"),
            expression_recovery_source=("expression_recovery_source", lambda x: " | ".join(sorted(set(map(str, x))))),
        )
        .reset_index()
    )

    keep = [
        c for c in [
            "canonical_target_id",
            "gene_symbol",
            "target_name",
            "final_activity_relation_class_v4",
            "final_activity_value_status_v4",
            "final_hr_input_status_v4",
            "final_selected_pActivity_v4",
            "species_provenance_tier_v3",
        ]
        if c in activity.columns
    ]
    cov = cov.merge(
        activity[keep].drop_duplicates("canonical_target_id"),
        on="canonical_target_id",
        how="left",
    )
    return cov


def build_wide(hr: pd.DataFrame):
    """Pivot long HR coordinates into stable numerical and status matrices."""
    idx = ["canonical_target_id", "gene_symbol"]

    numeric = hr.pivot_table(
        index=idx,
        columns="tissue_label",
        values="HR_numeric_boundary_or_exact",
        aggfunc="first",
    ).reset_index()
    numeric.columns.name = None

    relation = hr.pivot_table(
        index=idx,
        columns="tissue_label",
        values="HR_relation",
        aggfunc="first",
    ).reset_index()
    relation.columns.name = None

    status = hr.pivot_table(
        index=idx,
        columns="tissue_label",
        values="HR_value_status",
        aggfunc="first",
    ).reset_index()
    status.columns.name = None

    expr = hr.pivot_table(
        index=idx,
        columns="tissue_label",
        values="expression_z",
        aggfunc="first",
    ).reset_index()
    expr.columns.name = None

    return numeric, relation, status, expr


def main() -> int:
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    parser = argparse.ArgumentParser(
        description="Generate expanded 58-target pooled-parent-ketamine full-tissue HR."
    )
    parser.add_argument("--v4-dir", type=Path, required=True)
    parser.add_argument("--hr1-dir", type=Path, required=True)
    parser.add_argument("--recovery-dir", type=Path, required=True)
    args = parser.parse_args()

    v4_dir = args.v4_dir.resolve()
    hr1_dir = args.hr1_dir.resolve()
    recovery_dir = args.recovery_dir.resolve()

    outdir = hr1_dir / f"Expanded58_Full_Tissue_HR_v2_{stamp()}"
    outdir.mkdir(parents=True, exist_ok=False)
    log_path = outdir / "RUN.log"

    def log(msg):
        """Write one timestamped run-log message."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    try:
        log("=== POOLED PARENT KETAMINE EXPANDED58 FULL-TISSUE HR V2 START ===")
        log(f"V4 dir: {v4_dir}")
        log(f"HR-v1 dir: {hr1_dir}")
        log(f"Recovery dir: {recovery_dir}")
        log(f"Output: {outdir}")

        (
            activity,
            hr1,
            recovered,
            missing,
            activity_path,
            hr1_path,
            rec_path,
            missing_path,
        ) = load_inputs(v4_dir, hr1_dir, recovery_dir, log)

        old_expr = extract_old_expression(hr1, log)
        rec_expr = normalize_recovered_expression(recovered, log)
        unified_expr = build_unified_expression(old_expr, rec_expr, log)

        # Verify the 18 missing targets are exactly activity-selected targets absent
        # from unified expression.
        represented = set(unified_expr["canonical_target_id"].astype(str))
        activity_targets = set(activity["canonical_target_id"].astype(str))
        actual_missing = sorted(activity_targets - represented)

        missing_col = find_col(missing, ["canonical_target_id"])
        expected_missing = (
            sorted(set(missing[missing_col].astype(str)))
            if missing_col
            else actual_missing
        )

        if actual_missing != expected_missing:
            raise RuntimeError(
                "Unified expression missing-target set does not match recovery audit.\n"
                f"Actual: {actual_missing}\nAudit: {expected_missing}"
            )
        if len(actual_missing) != EXPECTED_MISSING_TARGETS:
            raise RuntimeError(
                f"Expected {EXPECTED_MISSING_TARGETS} missing targets; found {len(actual_missing)}"
            )

        hr2 = calculate_hr(activity, unified_expr, log)
        cross = crosscheck_old_coordinates(hr2, hr1, outdir, log)

        coverage = build_coverage(hr2, activity)
        numeric, relation, status, expr_matrix = build_wide(hr2)

        # Main outputs.
        hr_csv = outdir / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.csv"
        hr_pq = outdir / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.parquet"
        hr2.to_csv(hr_csv, index=False)
        hr2.to_parquet(hr_pq, index=False)

        unified_expr.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_EXPANDED58_EXPRESSION_LONG_V2.csv",
            index=False,
        )
        unified_expr.to_parquet(
            outdir / "POOLED_PARENT_KETAMINE_EXPANDED58_EXPRESSION_LONG_V2.parquet",
            index=False,
        )

        numeric.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_HR_NUMERIC_MATRIX_EXPANDED58_V2.csv",
            index=False,
        )
        relation.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_HR_RELATION_MATRIX_EXPANDED58_V2.csv",
            index=False,
        )
        status.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_HR_STATUS_MATRIX_EXPANDED58_V2.csv",
            index=False,
        )
        expr_matrix.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_EXPRESSION_MATRIX_EXPANDED58_V2.csv",
            index=False,
        )
        coverage.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_TARGET_HR_COVERAGE_EXPANDED58_V2.csv",
            index=False,
        )

        # Explicit missing-expression manifest copied/augmented from recovery audit.
        miss = activity[
            activity["canonical_target_id"].astype(str).isin(actual_missing)
        ].copy()
        if missing_col:
            audit_subset = missing.copy()
            audit_subset["canonical_target_id"] = audit_subset[missing_col].astype(str)
            miss = miss.merge(
                audit_subset,
                on="canonical_target_id",
                how="left",
                suffixes=("", "_recovery_audit"),
            )
        miss["expanded58_HR_status"] = "NO_AUTHORITATIVE_77TISSUE_EXPRESSION"
        miss.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_MISSING_EXPRESSION_TARGETS_EXPANDED58_V2.csv",
            index=False,
        )

        # Added-20-only HR rows.
        old_targets = set(hr1["canonical_target_id"].astype(str))
        added20 = hr2[
            ~hr2["canonical_target_id"].astype(str).isin(old_targets)
        ].copy()
        if len(added20) != EXPECTED_RECOVERED_TARGETS * EXPECTED_TISSUES:
            raise RuntimeError(
                f"Expected 1,540 newly added HR rows; found {len(added20)}"
            )
        added20.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_NEWLY_RECOVERED20_HR_ROWS_V2.csv",
            index=False,
        )

        # Sorted coordinate review table (not a fingerprint).
        ranked = hr2.copy()
        ranked["_abs_numeric_hr"] = ranked["HR_numeric_boundary_or_exact"].abs()
        ranked = ranked.sort_values(
            ["_abs_numeric_hr", "canonical_target_id", "tissue_label"],
            ascending=[False, True, True],
            kind="stable",
        ).drop(columns="_abs_numeric_hr")
        ranked.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_HR_COORDINATES_SORTED_BY_ABS_NUMERIC_EXPANDED58_V2.csv",
            index=False,
        )

        exact_targets = int(
            hr2[
                ["canonical_target_id", "final_activity_relation_class_v4"]
            ]
            .drop_duplicates()
            ["final_activity_relation_class_v4"]
            .eq("EXACT")
            .sum()
        )
        bounded_targets = int(
            hr2[
                ["canonical_target_id", "final_activity_relation_class_v4"]
            ]
            .drop_duplicates()
            ["final_activity_relation_class_v4"]
            .eq("GT_BOUND")
            .sum()
        )
        exact_coords = int(
            hr2["HR_value_status"].astype(str).str.startswith("EXACT").sum()
        )
        bounded_coords = int(
            hr2["HR_value_status"].astype(str).str.startswith("BOUNDED").sum()
        )

        summary = {
            "status": "PASS",
            "activity_targets_total": len(activity),
            "old_HR_targets": EXPECTED_OLD_HR_TARGETS,
            "newly_recovered_expression_targets": EXPECTED_RECOVERED_TARGETS,
            "final_HR_targets": hr2["canonical_target_id"].nunique(),
            "still_missing_expression_targets": len(actual_missing),
            "human_tissues": hr2["tissue_id"].nunique(),
            "old_HR_rows": len(hr1),
            "new_HR_rows_added": len(added20),
            "final_HR_rows": len(hr2),
            "activity_classes_among_58_HR_targets": {
                "exact_targets": exact_targets,
                "GT_bounded_targets": bounded_targets,
            },
            "HR_coordinate_classes": {
                "exact_coordinates": exact_coords,
                "bounded_coordinates": bounded_coords,
            },
            "old_coordinate_crosscheck": cross,
            "still_missing_target_ids": actual_missing,
            "formula": "HR = pActivity * expression_Z",
            "expression_profile": "HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1",
            "expression_ddof": 1,
            "GESD_or_fingerprint_calculated": False,
            "PCA_or_multivariate_calculated": False,
            "main_HR_table": str(hr_csv),
        }

        (outdir / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        lines = [
            "=== POOLED PARENT KETAMINE EXPANDED58 FULL-TISSUE HR V2 COMPLETE ===",
            "",
            "COVERAGE",
            f"Selected activity targets: {len(activity)}",
            f"Original HR-v1 targets: {EXPECTED_OLD_HR_TARGETS}",
            f"Newly recovered expression targets: {EXPECTED_RECOVERED_TARGETS}",
            f"FINAL HR TARGETS: {hr2['canonical_target_id'].nunique()}",
            f"Still missing expression targets: {len(actual_missing)}",
            f"Human tissues: {hr2['tissue_id'].nunique()}",
            "",
            "HR ROWS",
            f"Original HR-v1 rows: {len(hr1):,}",
            f"New HR rows added: {len(added20):,}",
            f"FINAL HR ROWS: {len(hr2):,}",
            "",
            "ACTIVITY TYPES AMONG THE 58 HR TARGETS",
            f"Exact activity targets: {exact_targets}",
            f"Bounded Ki >10,000 nM targets: {bounded_targets}",
            "",
            "HR COORDINATE TYPES",
            f"Exact HR coordinates: {exact_coords:,}",
            f"Bounded HR coordinates: {bounded_coords:,}",
            "",
            "OLD-COORDINATE REPRODUCTION",
            f"Coordinates crosschecked: {cross['coordinates']:,}",
            f"Max |delta expression_Z|: {cross['max_abs_delta_expression_Z']:.3g}",
            f"Max |delta HR|: {cross['max_abs_delta_HR']:.3g}",
            f"Relations all match: {cross['relations_all_match']}",
            f"Statuses all match: {cross['statuses_all_match']}",
            "",
            "STILL MISSING EXPRESSION",
            "  " + ", ".join(actual_missing),
            "",
            "No missing expression was zero-filled or imputed.",
            "NO GESD / FINGERPRINT WAS CALCULATED.",
            "NO PCA / CLUSTERING / MULTIVARIATE ANALYSIS WAS PERFORMED.",
            "",
            f"Main HR table: {hr_csv}",
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

        log(
            f"FINAL: targets={hr2['canonical_target_id'].nunique()}, "
            f"tissues={hr2['tissue_id'].nunique()}, rows={len(hr2)}"
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
