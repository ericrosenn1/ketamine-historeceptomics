#!/usr/bin/env python3
r"""
Pooled Parent Ketamine — Targeted Source-Record Finalization v3
=======================================================

PURPOSE
-------
This is a targeted pre-HR source-record audit and finalization step for the
pooled-parent-ketamine activity table.

It is designed to answer the remaining questions without launching another broad
project reconstruction:

1. For each target, quickly check whether there is at least one ACTUAL RAW PDSP
   ketamine measurement whose Species field explicitly says human.
   - If raw PDSP support is not found, accept the existing receptor-level unanimous
     species mapping as usable, but clearly distinguish it from direct/raw support.
   - Also recognize existing non-PDSP rows whose species was already explicit.

2. Audit the large 10,000 nM / pActivity=5 pile-up.
   - Inspect the raw PDSP Ki workbook.
   - Determine whether raw "Ki Value" cells contain explicit < or > markers.
   - Quantify whether 10,000 nM is a database maximum/ceiling or simply a common value.
   - Inspect the original source-record CSV for selected 10,000-nM records.
   - DO NOT infer a bound merely because 10,000 nM is common.

3. Recover bound direction for the currently SELECTED unknown-direction bounded
   values wherever an explicit operator exists in an upstream source row or raw
   PDSP value cell.

4. Produce a revised 81-target target-activity summary with:
   - explicit-human-support status
   - species provenance tier
   - 10,000-nM source-record status
   - recovered relation/operator when supported
   - HR-input-readiness flag

5. NO HR is calculated.
6. NO source input or prior output is modified.

IMPORTANT SCIENTIFIC RULES
--------------------------
- Receptor-level unanimous species mapping is accepted as usable for this exploratory
  pooled profile, but it is labeled separately from direct/raw row-level species.
- Human-priority / mammalian-fallback selection from v2 is preserved unless the audit
  directly establishes that its selected-row relation/operator was misclassified.
- A numeric 10,000 nM value is NOT automatically converted to a bound.
- If the raw source says ">10000", "<10000", ">=", "<=", that operator is preserved.
- If the raw source simply contains numeric 10000 and has no relation metadata, it
  remains numeric-as-reported and is flagged "NO_BOUND_MARKER_FOUND".
- Unknown-direction bounded selected rows remain REVIEW_REQUIRED if the operator cannot
  be recovered.
- Zero or negative bounds are never used.

EXPECTED V2 INPUT FOLDER
------------------------
Supply the governed v2 directory explicitly with --v2-dir.

EXPECTED V2 FILES
-----------------
POOLED_PARENT_KETAMINE_ACTIVITY_TABLE_SPECIES_CLEANED.csv
POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY.csv

EXPECTED RAW PDSP WORKBOOK
--------------------------
Supply the governed workbook explicitly with --pdsp.

If not found there, it performs only a targeted filename search.

OUTPUT
------
A new timestamped folder inside the v2 output folder:
Forensic_Finalization_v3_YYYYMMDD_HHMMSS

Main output:
POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FORENSIC_V3.csv

Publication contract
--------------------
Purpose: Resolve source-record species and relation evidence before final activity.
Stage/lane: Recovered forensic v3, after cleanup v2 and before Final Activity v4.
Inputs: Explicit project root, v2 directory, and governed PDSP workbook.
Outputs: A new timestamped forensic directory containing the revised target summary,
source audits, summaries, hashes, and run log.
Side effects: Writes derivative audit/finalization files only; no input is modified
and no HR score is calculated.
Invariants: Human-priority selection persists, relation operators require source
evidence, a 10,000-nM pile-up is not itself a bound, and invalid bounds stay excluded.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# =============================================================================
# Defaults
# =============================================================================

PROJECT_ROOT = None
POOLED_PARENT_ROOT = None
DEFAULT_V2_DIR = None
DEFAULT_CLEANED = None
DEFAULT_TARGET = None
DEFAULT_PDSP = None


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


def inum(v) -> Optional[int]:
    """Return the rounded integer value or None when it is not finite."""
    x = fnum(v)
    return None if math.isnan(x) else int(round(x))


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file read in bounded blocks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def uniq_join(values: Iterable, sep: str = " | ") -> str:
    """Join unique nonblank values in stable encounter order."""
    out = []
    seen = set()
    for v in values:
        x = s(v)
        if not x or x.lower() == "nan":
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return sep.join(out)


def norm(value) -> str:
    """Normalize a scalar for conservative text comparison."""
    return re.sub(r"[^A-Z0-9]+", "", up(value))


def parse_source_rows(v) -> List[int]:
    """Parse governed source-row identifiers into integers."""
    x = s(v)
    if not x:
        return []
    result = []
    for token in re.split(r"[|,; ]+", x):
        if not token:
            continue
        try:
            result.append(int(float(token)))
        except Exception:
            pass
    return result


EXACT = {"=", "EXACT", "EQ", "EQUAL", "EQUALS"}
GT = {">", ">=", "GT", "GE", "GTE"}
LT = {"<", "<=", "LT", "LE", "LTE"}


def relation_class(v) -> str:
    """Normalize a censored relation to the governed relation class."""
    x = up(v)
    if x in EXACT:
        return "EXACT"
    if x in GT:
        return "GT_BOUND"
    if x in LT:
        return "LT_BOUND"
    if x == "BOUNDED":
        return "BOUNDED_DIRECTION_UNKNOWN"
    return "UNKNOWN"


def detect_relation_in_text(value) -> str:
    """
    Detect an explicit relation marker only when visibly present in source text.
    """
    x = s(value)
    if not x:
        return ""
    # Prefer two-character markers.
    if re.search(r">\s*=", x):
        return ">="
    if re.search(r"<\s*=", x):
        return "<="
    if re.search(r"(^|[^A-Za-z])>\s*[0-9.]", x):
        return ">"
    if re.search(r"(^|[^A-Za-z])<\s*[0-9.]", x):
        return "<"
    return ""


def parse_numeric_from_raw(value) -> float:
    """Parse a finite numeric value from a raw source field."""
    x = s(value)
    if not x:
        return math.nan
    x = x.replace(",", "")
    m = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", x)
    if not m:
        return math.nan
    try:
        y = float(m.group(0))
        return y if math.isfinite(y) else math.nan
    except Exception:
        return math.nan


def find_col(columns, names: Sequence[str]) -> Optional[str]:
    """Return the first case-insensitive matching column name."""
    lut = {str(c).strip().lower(): c for c in columns}
    for name in names:
        if name.lower() in lut:
            return lut[name.lower()]
    return None


# =============================================================================
# Raw PDSP
# =============================================================================

def find_pdsp(project_root: Path, preferred: Path, log) -> Optional[Path]:
    """Resolve the explicitly supplied or uniquely governed PDSP workbook."""
    if preferred.is_file():
        return preferred

    roots = [
        project_root / "09_CODE_AND_PIPELINES" / "Historical_Project_Trees",
        project_root / "12_QA_AUDITS_AND_PROVENANCE",
        project_root / "98_DEPRECATED",
    ]

    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for pat in ("KiDatabase*.xlsx", "*PDSP*Ki*.xlsx", "KiDatabase*.xls"):
            try:
                candidates.extend([p for p in root.rglob(pat) if p.is_file()])
            except Exception:
                pass

    if not candidates:
        return None

    candidates = sorted(
        set(candidates),
        key=lambda p: (
            0 if p.name.lower().startswith("kidatabase") else 1,
            len(str(p)),
            str(p).lower(),
        ),
    )
    log(f"PDSP fallback candidates: {len(candidates)}")
    return candidates[0]


def load_pdsp(path: Path, log):
    """Load PDSP records without modifying their source grain."""
    log(f"Loading raw PDSP workbook: {path}")
    d = pd.read_excel(path, dtype=object)

    ki_id = find_col(d.columns, ["Ki ID", "KiID", "Ki_ID", "ID"])
    species = find_col(d.columns, ["Species", "Organism"])
    receptor = find_col(d.columns, ["Receptor", "Target"])
    ligand = find_col(d.columns, ["Test Ligands", "Test Ligand", "Ligand", "Compound"])
    value = find_col(d.columns, ["Ki Value", "Ki", "Value"])

    if not species or not receptor or not ligand or not value:
        raise RuntimeError(
            "Raw PDSP workbook is missing one or more required columns. "
            f"Found columns: {list(d.columns)}"
        )

    # Relation-like / comment-like fields if any.
    relation_cols = [
        c for c in d.columns
        if any(
            token in str(c).lower()
            for token in ("relation", "operator", "qualifier", "comment", "note")
        )
    ]

    d["_raw_species"] = d[species].map(s)
    d["_raw_receptor"] = d[receptor].map(s)
    d["_raw_ligand"] = d[ligand].map(s)
    d["_raw_value_text"] = d[value].map(s)
    d["_raw_value_numeric"] = d[value].map(parse_numeric_from_raw)
    d["_raw_value_relation"] = d[value].map(detect_relation_in_text)
    d["_receptor_norm"] = d["_raw_receptor"].map(norm)
    d["_ligand_low"] = d["_raw_ligand"].str.lower()

    # Explicit relation markers in any relation/comment columns.
    rel_markers = []
    for _, row in d.iterrows():
        marks = []
        if s(row["_raw_value_relation"]):
            marks.append(s(row["_raw_value_relation"]))
        for c in relation_cols:
            m = detect_relation_in_text(row.get(c))
            if m:
                marks.append(m)
            else:
                raw = up(row.get(c))
                if raw in EXACT | GT | LT:
                    marks.append(raw)
        classes = {relation_class(x) for x in marks if relation_class(x) != "UNKNOWN"}
        if len(classes) == 1 and marks:
            # Prefer a literal symbol where possible.
            sym = None
            for candidate in (">=", "<=", ">", "<", "="):
                if any(candidate in x for x in marks):
                    sym = candidate
                    break
            rel_markers.append(sym or marks[0])
        elif len(classes) > 1:
            rel_markers.append("CONFLICT")
        else:
            rel_markers.append("")
    d["_explicit_relation_marker"] = rel_markers

    audit = {
        "path": str(path),
        "sha256": sha256(path),
        "rows": len(d),
        "ki_id_column": str(ki_id or ""),
        "species_column": str(species),
        "receptor_column": str(receptor),
        "ligand_column": str(ligand),
        "value_column": str(value),
        "relation_comment_columns": [str(c) for c in relation_cols],
    }

    return d, audit


def raw_pdsp_target_matches(pdsp: pd.DataFrame, cleaned: pd.DataFrame):
    """
    Create target -> raw PDSP rows using receptor aliases already present in the
    pooled PDSP-derived records for that target. This avoids inventing new
    pharmacological target-name mappings.
    """
    target_aliases = defaultdict(set)

    pdsp_clean = cleaned[
        cleaned["source_database"].astype(str).str.contains("PDSP", case=False, na=False)
    ]

    for target, g in pdsp_clean.groupby("canonical_target_id", dropna=False):
        target = s(target)
        if not target:
            continue
        for col in ("original_target_name", "target_name", "gene_symbol", "canonical_target_id"):
            if col in g.columns:
                for value in g[col]:
                    k = norm(value)
                    if k:
                        target_aliases[target].add(k)

    matches = {}
    for target, aliases in target_aliases.items():
        mask = pdsp["_receptor_norm"].isin(aliases)
        # Include only ketamine-like raw ligand rows; do not include
        # explicit esketamine/arketamine-only raw rows.
        ligand = pdsp["_ligand_low"].fillna("")
        ket = ligand.str.contains("ketamine", na=False)
        explicit_enantiomer = ligand.str.contains(
            r"\besketamine\b|\barketamine\b|s[- ]?ketamine|r[- ]?ketamine",
            regex=True,
            na=False,
        )
        m = pdsp[mask & ket & ~explicit_enantiomer].copy()
        matches[target] = m

    return matches


# =============================================================================
# Original source-record CSV audit
# =============================================================================

def resolve_legacy_source_path(source_path: str, project_root: Path) -> Optional[Path]:
    """Resolve a legacy path only within the supplied project root."""
    raw = Path(source_path)
    if raw.is_file():
        return raw

    # Main reorganization transform.
    marker = r"\Ketamine project\ketamine_hr_analysis\\"
    txt = str(source_path)
    idx = txt.lower().find(marker.lower())
    if idx >= 0:
        rel = txt[idx + len(marker):]
        candidate = (
            project_root
            / "09_CODE_AND_PIPELINES"
            / "Historical_Project_Trees"
            / "ketamine_hr_analysis"
            / Path(rel)
        )
        if candidate.is_file():
            return candidate

    # Targeted basename fallback.
    basename = Path(source_path).name
    roots = [
        project_root / "09_CODE_AND_PIPELINES" / "Historical_Project_Trees",
        project_root / "12_QA_AUDITS_AND_PROVENANCE",
        project_root / "98_DEPRECATED",
    ]
    for root in roots:
        if not root.exists():
            continue
        try:
            hits = list(root.rglob(basename))
        except Exception:
            hits = []
        hits = [p for p in hits if p.is_file()]
        if hits:
            hits.sort(key=lambda p: (len(str(p)), str(p).lower()))
            return hits[0]

    return None


def read_selected_csv_records(path: Path, requested_rows: Sequence[int], log):
    """
    Read only requested logical CSV records (+/- one neighboring record) in one
    sequential pass. This avoids loading the approximately 100 MB source CSV into RAM.

    The source-row index may be 0- or 1-based. For each requested number,
    retain row-1, row, and row+1 for downstream target/value matching.
    """
    wanted = set()
    for r in requested_rows:
        if r < 0:
            continue
        for x in (r - 1, r, r + 1):
            if x >= 0:
                wanted.add(x)

    if not wanted:
        return {}

    maxwanted = max(wanted)
    result = {}

    log(
        f"Reading selected source rows from {path.name}: "
        f"{len(wanted):,} candidate record indices through ~{maxwanted:,}"
    )

    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        # data_index starts at 1 for first data record, which is the most common
        # convention for stored source_rows. Neighboring indices are also captured.
        for data_index, rec in enumerate(reader, start=1):
            if data_index in wanted:
                result[data_index] = rec
            if data_index > maxwanted:
                break

    return result


def relation_from_source_record(rec: dict) -> Tuple[str, str]:
    """
    Recover an explicit relation from relation-like fields first, then from value
    text. No inference from numeric magnitude.
    """
    if not rec:
        return "", ""

    for key, value in rec.items():
        kl = str(key).lower()
        if any(tok in kl for tok in ("relation", "operator", "qualifier")):
            raw = s(value)
            rc = relation_class(raw)
            if rc in {"EXACT", "GT_BOUND", "LT_BOUND"}:
                return raw, f"SOURCE_FIELD:{key}"
            marker = detect_relation_in_text(raw)
            if marker:
                return marker, f"SOURCE_FIELD_TEXT:{key}"

    for key, value in rec.items():
        kl = str(key).lower()
        if any(tok in kl for tok in ("value", "activity", "affinity", "ki")):
            marker = detect_relation_in_text(value)
            if marker:
                return marker, f"SOURCE_VALUE_TEXT:{key}"

    return "", ""


def record_match_score(rec: dict, target: str, expected_value: float, source_database: str):
    """Score a source record for deterministic forensic matching."""
    if not rec:
        return -999

    text = " | ".join(s(v) for v in rec.values()).upper()
    score = 0

    if target and target.upper() in text:
        score += 5

    if source_database and "PDSP" in source_database.upper() and "PDSP" in text:
        score += 3

    if not math.isnan(expected_value):
        ev = f"{expected_value:g}"
        if ev in text:
            score += 3

    return score


# =============================================================================
# Main audit
# =============================================================================

def main():
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    parser = argparse.ArgumentParser(
        description="Targeted source-record finalization of pooled-parent-ketamine activity before HR."
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--v2-dir", type=Path, required=True)
    parser.add_argument("--pdsp", type=Path, required=True)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    v2_dir = args.v2_dir.resolve()
    cleaned_path = v2_dir / "POOLED_PARENT_KETAMINE_ACTIVITY_TABLE_SPECIES_CLEANED.csv"
    target_path = v2_dir / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY.csv"
    output = v2_dir / f"Forensic_Finalization_v3_{stamp()}"
    output.mkdir(parents=True, exist_ok=False)

    log_path = output / "RUN.log"

    def log(msg):
        """Write one timestamped run-log message."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    try:
        log("=== POOLED PARENT KETAMINE FORENSIC FINALIZATION V3 START ===")
        log(f"V2 dir: {v2_dir}")
        log(f"Output: {output}")

        for p in (cleaned_path, target_path):
            if not p.is_file():
                raise FileNotFoundError(f"Required v2 file not found: {p}")

        cleaned = pd.read_csv(cleaned_path, low_memory=False)
        target = pd.read_csv(target_path, low_memory=False)

        log(f"Loaded cleaned activity rows: {len(cleaned):,}")
        log(f"Loaded target summary rows: {len(target):,}")

        if len(target) != 81:
            log(f"WARNING: expected 81 target rows, found {len(target)}")

        pdsp_path = find_pdsp(project_root, args.pdsp.resolve(), log)
        if not pdsp_path:
            raise FileNotFoundError("Raw PDSP Ki workbook could not be located")

        pdsp, pdsp_audit = load_pdsp(pdsp_path, log)
        matches = raw_pdsp_target_matches(pdsp, cleaned)

        # ---------------------------------------------------------------------
        # 1. Explicit human support audit by target.
        # ---------------------------------------------------------------------
        support_rows = []

        for _, tr in target.iterrows():
            tid = s(tr.get("canonical_target_id"))
            raw = matches.get(tid, pdsp.iloc[0:0])

            raw_human = raw[
                raw["_raw_species"].str.contains(
                    r"\bhuman\b|homo sapiens",
                    case=False,
                    regex=True,
                    na=False,
                )
            ]

            # Explicit human rows already present in cleaned table from any source.
            cg = cleaned[cleaned["canonical_target_id"].astype(str).eq(tid)].copy()
            explicit_human = cg[
                cg["species_class_clean"].eq("HUMAN")
                & cg["species_resolution_method"].isin(
                    ["POOLED_TABLE_EXPLICIT", "AUDIT_SOURCE_ASSERTION"]
                )
                & cg["activity_lane_clean"].eq("MEASURED_NUMERICAL")
            ]

            explicit_nonpdsp_human = explicit_human[
                ~explicit_human["source_database"].astype(str).str.contains(
                    "PDSP", case=False, na=False
                )
            ]

            raw_vals = pd.to_numeric(raw_human["_raw_value_numeric"], errors="coerce")
            raw_vals = raw_vals[raw_vals > 0]

            raw_relation_markers = raw_human["_explicit_relation_marker"].replace("", np.nan).dropna()

            consensus_selected = (
                s(tr.get("proposed_selected_activity_species")).upper() in {"HUMAN", "HOMO SAPIENS"}
                or s(tr.get("proposed_species_basis")) == "HUMAN_PRIORITY"
            )

            if len(raw_human):
                support_status = "RAW_PDSP_EXPLICIT_HUMAN_SUPPORT"
            elif len(explicit_nonpdsp_human):
                support_status = "OTHER_SOURCE_EXPLICIT_HUMAN_SUPPORT"
            elif consensus_selected:
                support_status = "RECEPTOR_UNANIMOUS_OR_OTHER_CONSENSUS_HUMAN_ONLY"
            else:
                support_status = "NO_EXPLICIT_HUMAN_SUPPORT_FOUND_QUICK_AUDIT"

            support_rows.append({
                "canonical_target_id": tid,
                "gene_symbol": s(tr.get("gene_symbol")),
                "proposed_species_basis_v2": s(tr.get("proposed_species_basis")),
                "proposed_selected_species_v2": s(tr.get("proposed_selected_activity_species")),
                "explicit_human_support_status": support_status,
                "n_raw_pdsp_ketamine_rows_matched": len(raw),
                "n_raw_pdsp_explicit_human_rows": len(raw_human),
                "raw_pdsp_human_min_positive_Ki_numeric": (
                    float(raw_vals.min()) if len(raw_vals) else np.nan
                ),
                "raw_pdsp_human_max_positive_Ki_numeric": (
                    float(raw_vals.max()) if len(raw_vals) else np.nan
                ),
                "raw_pdsp_human_Ki_IDs": uniq_join(
                    raw_human[
                        find_col(raw_human.columns, ["Ki ID", "KiID", "Ki_ID", "ID"])
                    ].tolist()
                    if len(raw_human) and find_col(raw_human.columns, ["Ki ID", "KiID", "Ki_ID", "ID"])
                    else []
                ),
                "raw_pdsp_explicit_relation_markers": uniq_join(raw_relation_markers),
                "n_other_source_explicit_human_measured_rows": len(explicit_nonpdsp_human),
                "other_source_explicit_human_databases": uniq_join(
                    explicit_nonpdsp_human["source_database"]
                ),
            })

        support = pd.DataFrame(support_rows)
        support.to_csv(output / "TARGET_EXPLICIT_HUMAN_SUPPORT_AUDIT.csv", index=False)
        log(
            "Explicit raw PDSP human support found for "
            f"{int(support['n_raw_pdsp_explicit_human_rows'].gt(0).sum())}/{len(support)} targets"
        )

        # ---------------------------------------------------------------------
        # 2. 10,000-nM semantics audit.
        # ---------------------------------------------------------------------
        pdsp_numeric = pd.to_numeric(pdsp["_raw_value_numeric"], errors="coerce")
        pdsp_numeric = pdsp_numeric[pdsp_numeric > 0]

        ket_mask = (
            pdsp["_ligand_low"].str.contains("ketamine", na=False)
            & ~pdsp["_ligand_low"].str.contains(
                r"\besketamine\b|\barketamine\b|s[- ]?ketamine|r[- ]?ketamine",
                regex=True,
                na=False,
            )
        )
        pdsp_k = pdsp[ket_mask].copy()
        k_numeric = pd.to_numeric(pdsp_k["_raw_value_numeric"], errors="coerce")
        k_numeric = k_numeric[k_numeric > 0]

        selected_p5 = target[
            target["proposed_selected_pActivity"].fillna(-999).eq(5.0)
            & target["proposed_selected_source_database"].astype(str).str.contains(
                "PDSP", case=False, na=False
            )
        ].copy()

        p5_targets = set(selected_p5["canonical_target_id"].astype(str))
        p5_raw_rows = []
        for tid in sorted(p5_targets):
            raw = matches.get(tid, pdsp.iloc[0:0])
            z = raw[
                pd.to_numeric(raw["_raw_value_numeric"], errors="coerce").eq(10000)
            ].copy()
            if z.empty:
                continue
            z["canonical_target_id_matched"] = tid
            p5_raw_rows.append(z)

        if p5_raw_rows:
            p5_raw = pd.concat(p5_raw_rows, ignore_index=True)
        else:
            p5_raw = pd.DataFrame()

        raw_export_cols = [
            c for c in [
                "canonical_target_id_matched",
                find_col(pdsp.columns, ["Ki ID", "KiID", "Ki_ID", "ID"]),
                find_col(pdsp.columns, ["Species", "Organism"]),
                find_col(pdsp.columns, ["Receptor", "Target"]),
                find_col(pdsp.columns, ["Test Ligands", "Test Ligand", "Ligand", "Compound"]),
                find_col(pdsp.columns, ["Ki Value", "Ki", "Value"]),
                "_raw_value_text",
                "_raw_value_numeric",
                "_explicit_relation_marker",
            ]
            if c is not None and c in p5_raw.columns
        ]
        if not p5_raw.empty:
            p5_raw[raw_export_cols].to_csv(
                output / "PDSP_10000_FORENSIC_ROWS.csv",
                index=False,
            )
        else:
            pd.DataFrame(columns=raw_export_cols).to_csv(
                output / "PDSP_10000_FORENSIC_ROWS.csv",
                index=False,
            )

        n_all_10000 = int((pdsp_numeric == 10000).sum())
        n_all_gt10000 = int((pdsp_numeric > 10000).sum())
        n_k_10000 = int((k_numeric == 10000).sum())
        n_k_gt10000 = int((k_numeric > 10000).sum())

        raw_10000_bound_markers = (
            int(
                p5_raw["_explicit_relation_marker"]
                .astype(str)
                .isin([">", ">=", "<", "<="])
                .sum()
            )
            if not p5_raw.empty else 0
        )

        max_all = float(pdsp_numeric.max()) if len(pdsp_numeric) else np.nan
        max_k = float(k_numeric.max()) if len(k_numeric) else np.nan
        mode_k = (
            float(k_numeric.mode().iloc[0])
            if len(k_numeric) and not k_numeric.mode().empty else np.nan
        )

        if n_k_gt10000 > 0:
            ceiling_status = "RAW_PDSP_CONTAINS_KETAMINE_VALUES_ABOVE_10000_NOT_A_HARD_DATABASE_MAX"
        elif len(k_numeric) and max_k == 10000 and n_k_10000 > 0:
            ceiling_status = "10000_IS_MAXIMUM_KETAMINE_VALUE_POSSIBLE_CEILING_REVIEW"
        else:
            ceiling_status = "NO_SIMPLE_10000_CEILING_PATTERN"

        semantics_lines = [
            "=== PDSP 10,000 nM SEMANTICS AUDIT ===",
            "",
            f"Raw PDSP workbook: {pdsp_path}",
            f"All positive numeric PDSP Ki rows: {len(pdsp_numeric):,}",
            f"All PDSP rows exactly 10,000: {n_all_10000:,}",
            f"All PDSP rows > 10,000: {n_all_gt10000:,}",
            f"All-PDSP maximum numeric Ki: {max_all:g}" if not math.isnan(max_all) else "All-PDSP maximum numeric Ki: NA",
            "",
            f"Parent-ketamine-like raw PDSP rows: {len(pdsp_k):,}",
            f"Parent-ketamine positive numeric Ki rows: {len(k_numeric):,}",
            f"Parent-ketamine rows exactly 10,000: {n_k_10000:,}",
            f"Parent-ketamine rows > 10,000: {n_k_gt10000:,}",
            f"Parent-ketamine maximum numeric Ki: {max_k:g}" if not math.isnan(max_k) else "Parent-ketamine maximum numeric Ki: NA",
            f"Parent-ketamine modal numeric Ki: {mode_k:g}" if not math.isnan(mode_k) else "Parent-ketamine modal numeric Ki: NA",
            "",
            f"Selected PDSP pActivity=5 targets: {len(selected_p5):,}",
            f"Matched raw 10,000 rows for those targets: {len(p5_raw):,}",
            f"Matched raw 10,000 rows with explicit < or > marker: {raw_10000_bound_markers:,}",
            "",
            f"Ceiling diagnostic: {ceiling_status}",
            "",
            "Interpretation rule:",
            "- An explicit raw < or > marker is authoritative for censoring direction.",
            "- A plain numeric 10000 without a bound marker is NOT automatically converted to a bound.",
            "- Frequency/pile-up diagnostics are flags for review, not proof of censoring.",
        ]
        (output / "PDSP_10000_SEMANTICS_REPORT.txt").write_text(
            "\n".join(semantics_lines) + "\n",
            encoding="utf-8",
        )

        # ---------------------------------------------------------------------
        # 3. Upstream source-row audit for selected PDSP p=5 + selected unknown
        #    bounded rows.
        # ---------------------------------------------------------------------
        selected_unknown = target[
            target["proposed_selection_status"]
            .astype(str)
            .str.contains("BOUNDED_DIRECTION_UNKNOWN", na=False)
        ].copy()

        selected_forensic = pd.concat(
            [selected_p5, selected_unknown],
            ignore_index=True,
        ).drop_duplicates("proposed_selected_source_assertion_id")

        source_groups = defaultdict(list)
        for _, tr in selected_forensic.iterrows():
            sid = s(tr.get("proposed_selected_source_assertion_id"))
            if not sid:
                continue
            cg = cleaned[cleaned["source_assertion_id"].astype(str).eq(sid)]
            if cg.empty:
                continue
            cr = cg.iloc[0]
            spath = s(cr.get("source_file"))
            rows = parse_source_rows(cr.get("source_rows"))
            if not spath or not rows:
                continue
            source_groups[spath].append({
                "target": s(tr.get("canonical_target_id")),
                "source_assertion_id": sid,
                "expected_value": fnum(tr.get("proposed_selected_activity_value_original")),
                "source_database": s(tr.get("proposed_selected_source_database")),
                "source_rows": rows,
            })

        source_forensic_rows = []
        recovered_by_sid = {}

        for source_path, items in source_groups.items():
            resolved = resolve_legacy_source_path(source_path, project_root)
            if not resolved:
                for item in items:
                    source_forensic_rows.append({
                        **item,
                        "resolved_source_file": "",
                        "source_row_status": "SOURCE_FILE_NOT_FOUND",
                    })
                continue

            requested = sorted({r for item in items for r in item["source_rows"]})
            records = read_selected_csv_records(resolved, requested, log)

            for item in items:
                candidates = []
                for stored in item["source_rows"]:
                    for idx in (stored - 1, stored, stored + 1):
                        rec = records.get(idx)
                        if rec is None:
                            continue
                        score = record_match_score(
                            rec,
                            item["target"],
                            item["expected_value"],
                            item["source_database"],
                        )
                        candidates.append((score, idx, rec))

                if candidates:
                    candidates.sort(key=lambda x: (-x[0], abs(x[1] - item["source_rows"][0])))
                    score, idx, best = candidates[0]
                    op, opsrc = relation_from_source_record(best)
                    recovered_by_sid[item["source_assertion_id"]] = {
                        "operator": op,
                        "operator_source": opsrc,
                        "matched_record_index": idx,
                        "match_score": score,
                    }

                    interesting = {
                        k: v for k, v in best.items()
                        if any(
                            tok in str(k).lower()
                            for tok in (
                                "compound", "target", "gene", "activity", "affinity",
                                "value", "unit", "relation", "operator", "species",
                                "organism", "source", "database", "evidence", "status",
                                "comment", "note",
                            )
                        )
                    }

                    source_forensic_rows.append({
                        "canonical_target_id": item["target"],
                        "source_assertion_id": item["source_assertion_id"],
                        "legacy_source_file": source_path,
                        "resolved_source_file": str(resolved),
                        "stored_source_rows": uniq_join(item["source_rows"]),
                        "matched_record_index": idx,
                        "record_match_score": score,
                        "recovered_relation_operator": op,
                        "recovered_relation_source": opsrc,
                        "source_record_selected_fields_json": json.dumps(
                            interesting,
                            ensure_ascii=False,
                            default=str,
                        ),
                        "source_row_status": "MATCHED_NEAREST_RECORD",
                    })
                else:
                    source_forensic_rows.append({
                        "canonical_target_id": item["target"],
                        "source_assertion_id": item["source_assertion_id"],
                        "legacy_source_file": source_path,
                        "resolved_source_file": str(resolved),
                        "stored_source_rows": uniq_join(item["source_rows"]),
                        "source_row_status": "NO_RECORD_RECOVERED",
                    })

        source_forensic = pd.DataFrame(source_forensic_rows)
        source_forensic.to_csv(
            output / "SELECTED_SOURCE_ROW_FORENSIC.csv",
            index=False,
        )

        # ---------------------------------------------------------------------
        # 4. Revised 81-target summary.
        # ---------------------------------------------------------------------
        final = target.merge(
            support,
            on=["canonical_target_id", "gene_symbol"],
            how="left",
            validate="one_to_one",
        )

        final["v3_relation_operator"] = final[
            "proposed_selected_relation_operator_clean"
        ].fillna("").astype(str)
        final["v3_relation_class"] = final[
            "proposed_selected_relation_class"
        ].fillna("").astype(str)
        final["v3_relation_evidence_source"] = "V2"
        final["v3_relation_changed_from_v2"] = False

        for idx, row in final.iterrows():
            sid = s(row.get("proposed_selected_source_assertion_id"))
            rec = recovered_by_sid.get(sid)
            if not rec:
                continue
            op = s(rec.get("operator"))
            rc = relation_class(op)
            if rc in {"EXACT", "GT_BOUND", "LT_BOUND"}:
                old = s(row.get("v3_relation_class"))
                final.at[idx, "v3_relation_operator"] = op
                final.at[idx, "v3_relation_class"] = rc
                final.at[idx, "v3_relation_evidence_source"] = rec.get(
                    "operator_source", ""
                )
                final.at[idx, "v3_relation_changed_from_v2"] = rc != old

        # Raw-PDSP selected-target source-record status.
        p5_raw_by_target = {}
        if not p5_raw.empty:
            for tid, g in p5_raw.groupby("canonical_target_id_matched"):
                markers = set(
                    x for x in g["_explicit_relation_marker"].map(s)
                    if x
                )
                if len(markers) == 1:
                    marker = next(iter(markers))
                    stat = f"RAW_PDSP_10000_WITH_EXPLICIT_RELATION_{marker}"
                elif len(markers) > 1:
                    stat = "RAW_PDSP_10000_RELATION_CONFLICT"
                else:
                    stat = "RAW_PDSP_10000_NO_BOUND_MARKER_FOUND"
                p5_raw_by_target[str(tid)] = stat

        final["pdsp_10000_forensic_status"] = ""
        for idx, row in final.iterrows():
            if (
                s(row.get("proposed_selected_source_database")).lower().startswith("pdsp")
                and fnum(row.get("proposed_selected_pActivity")) == 5.0
            ):
                final.at[idx, "pdsp_10000_forensic_status"] = p5_raw_by_target.get(
                    s(row.get("canonical_target_id")),
                    "NO_MATCHED_RAW_PDSP_10000_ROW_FOUND",
                )

        # Species provenance tier.
        def provenance_tier(row):
            """Assign the governed provenance tier to a finalized record."""
            status = s(row.get("explicit_human_support_status"))
            basis = s(row.get("proposed_species_basis"))
            if basis == "HUMAN_PRIORITY":
                if status == "RAW_PDSP_EXPLICIT_HUMAN_SUPPORT":
                    return "HUMAN_RAW_PDSP_EXPLICIT_SUPPORT"
                if status == "OTHER_SOURCE_EXPLICIT_HUMAN_SUPPORT":
                    return "HUMAN_OTHER_SOURCE_EXPLICIT_SUPPORT"
                return "HUMAN_RECEPTOR_CONSENSUS_SUPPORT"
            if basis == "MAMMALIAN_FALLBACK":
                return "MAMMALIAN_FALLBACK"
            return "NO_PRINCIPAL_SPECIES_SELECTION"

        final["species_provenance_tier_v3"] = final.apply(
            provenance_tier,
            axis=1,
        )

        # A plain numeric 10000 is not blocked solely because it is common.
        readiness = []
        rationale = []
        for _, row in final.iterrows():
            p = fnum(row.get("proposed_selected_pActivity"))
            rc = s(row.get("v3_relation_class"))
            sel_status = s(row.get("proposed_selection_status"))
            p5stat = s(row.get("pdsp_10000_forensic_status"))

            if math.isnan(p):
                readiness.append("NOT_READY_NO_SELECTED_ACTIVITY")
                rationale.append("No selected human/mammalian numerical activity.")
            elif rc in {"GT_BOUND", "LT_BOUND"}:
                readiness.append("READY_BOUNDED_RELATION_PRESERVED")
                rationale.append("Numerical boundary available with explicit relation direction.")
            elif rc == "BOUNDED_DIRECTION_UNKNOWN":
                readiness.append("REVIEW_UNKNOWN_BOUND_DIRECTION")
                rationale.append("Selected numerical boundary exists but < or > direction remains unresolved.")
            elif rc == "EXACT":
                readiness.append("READY_EXACT_NUMERIC_AS_REPORTED")
                if "10000" in p5stat:
                    rationale.append(
                        "Raw PDSP value is numeric as reported; 10,000-nM pile-up is documented. "
                        "No bound is inferred without an explicit source marker."
                    )
                else:
                    rationale.append("Exact measured numerical activity selected under v2 policy.")
            else:
                readiness.append("REVIEW_RELATION_UNRESOLVED")
                rationale.append("Selected numerical activity exists but relation classification is unresolved.")

        final["HR_INPUT_READINESS_V3"] = readiness
        final["HR_INPUT_READINESS_RATIONALE"] = rationale

        # Save.
        final_path = output / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FORENSIC_V3.csv"
        final.to_csv(final_path, index=False)

        # Small review subset.
        review = final[
            final["HR_INPUT_READINESS_V3"].astype(str).str.startswith(
                ("REVIEW", "NOT_READY")
            )
            | final["pdsp_10000_forensic_status"].astype(str).ne("")
        ].copy()
        review.to_csv(
            output / "TARGETS_REQUIRING_OR_DESERVING_REVIEW_V3.csv",
            index=False,
        )

        # ---------------------------------------------------------------------
        # Summary
        # ---------------------------------------------------------------------
        raw_human_targets = int(
            support["n_raw_pdsp_explicit_human_rows"].gt(0).sum()
        )
        other_explicit_targets = int(
            (
                support["n_raw_pdsp_explicit_human_rows"].eq(0)
                & support["n_other_source_explicit_human_measured_rows"].gt(0)
            ).sum()
        )
        consensus_only_targets = int(
            support["explicit_human_support_status"]
            .eq("RECEPTOR_UNANIMOUS_OR_OTHER_CONSENSUS_HUMAN_ONLY")
            .sum()
        )

        changed_rel = int(final["v3_relation_changed_from_v2"].sum())
        ready_exact = int(
            final["HR_INPUT_READINESS_V3"].eq("READY_EXACT_NUMERIC_AS_REPORTED").sum()
        )
        ready_bound = int(
            final["HR_INPUT_READINESS_V3"].eq("READY_BOUNDED_RELATION_PRESERVED").sum()
        )
        review_n = int(
            final["HR_INPUT_READINESS_V3"].str.startswith("REVIEW").sum()
        )
        no_value_n = int(
            final["HR_INPUT_READINESS_V3"].str.startswith("NOT_READY").sum()
        )

        summary = {
            "status": "PASS",
            "v2_dir": str(v2_dir),
            "output_dir": str(output),
            "cleaned_rows": len(cleaned),
            "target_rows": len(final),
            "raw_pdsp": pdsp_audit,
            "targets_with_raw_pdsp_explicit_human_support": raw_human_targets,
            "additional_targets_with_other_source_explicit_human_support": other_explicit_targets,
            "targets_with_human_consensus_only": consensus_only_targets,
            "selected_pdsp_pActivity_5_targets": len(selected_p5),
            "pdsp_10000_raw_rows_matched": len(p5_raw),
            "pdsp_10000_raw_rows_with_explicit_bound_marker": raw_10000_bound_markers,
            "pdsp_10000_ceiling_diagnostic": ceiling_status,
            "selected_unknown_bound_targets_v2": len(selected_unknown),
            "selected_relations_changed_by_direct_source_forensics": changed_rel,
            "ready_exact_targets": ready_exact,
            "ready_bounded_targets": ready_bound,
            "review_targets": review_n,
            "no_selected_value_targets": no_value_n,
            "no_hr_calculated": True,
        }

        (output / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )

        lines = [
            "=== POOLED PARENT KETAMINE FORENSIC FINALIZATION V3 COMPLETE ===",
            "",
            f"Targets: {len(final)}",
            "",
            "EXPLICIT HUMAN SUPPORT",
            f"Targets with raw PDSP ketamine row(s) explicitly labeled human: {raw_human_targets}",
            f"Additional targets with explicit human support from other source rows: {other_explicit_targets}",
            f"Targets relying on human receptor/source consensus only: {consensus_only_targets}",
            "",
            "PDSP 10,000 nM",
            f"Selected PDSP pActivity=5 targets audited: {len(selected_p5)}",
            f"Matched raw PDSP 10,000 rows: {len(p5_raw)}",
            f"Raw 10,000 rows with explicit < or > marker: {raw_10000_bound_markers}",
            f"Ceiling diagnostic: {ceiling_status}",
            "",
            "BOUNDED RELATIONS",
            f"Selected unknown-direction bounded targets entering audit: {len(selected_unknown)}",
            f"Selected relations changed by explicit upstream source evidence: {changed_rel}",
            "",
            "PRE-HR READINESS",
            f"Ready exact numeric targets: {ready_exact}",
            f"Ready bounded targets with relation preserved: {ready_bound}",
            f"Review targets: {review_n}",
            f"No selected activity targets: {no_value_n}",
            "",
            "Key policy:",
            "- Receptor-level unanimous species mapping remains acceptable for this exploratory pooled profile.",
            "- Raw row-level explicit-human support is reported separately when found.",
            "- Numeric 10,000 nM is not converted to a bound without an explicit source marker.",
            "- Unknown-direction bounds remain review-required.",
            "",
            "NO HR WAS CALCULATED.",
            f"Main output: {final_path}",
            f"Output folder: {output}",
            "QA: PASS",
        ]
        (output / "SUMMARY.txt").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        # Hash outputs.
        hashes = []
        for p in sorted(output.iterdir()):
            if p.is_file() and p.name != "OUTPUT_SHA256SUMS.csv":
                hashes.append({
                    "filename": p.name,
                    "bytes": p.stat().st_size,
                    "sha256": sha256(p),
                })
        pd.DataFrame(hashes).to_csv(
            output / "OUTPUT_SHA256SUMS.csv",
            index=False,
        )

        log("QA: PASS")
        log("NO HR CALCULATED")
        print()
        print("\n".join(lines))
        return 0

    except Exception as exc:
        tb = traceback.format_exc()
        log("=== FAILED ===")
        log(repr(exc))
        log(tb)
        (output / "FAILURE.json").write_text(
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
