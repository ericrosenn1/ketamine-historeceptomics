#!/usr/bin/env python3
r"""
Pooled Parent Ketamine Activity Cleanup v2
==========================================

Censored-value pre-HR cleanup for the Cardozo ketamine historeceptomics project.

This script:
  1. Loads the existing pooled-parent-ketamine activity table.
  2. Resolves UNRESOLVED activity species only from deterministic source/project
     metadata, with special handling for PDSP Ki records.
  3. Does NOT infer species from gene/target identity alone.
  4. Separates measured numerical activity from assigned/modelled/imputed rows.
  5. Recovers original relation operators where possible.
  6. Retains non-zero bounded/censored numerical values at the REPORTED BOUNDARY
     while preserving the relation operator.
  7. Builds a target-level pre-HR summary with all independent observations and
     one proposed selected activity value per target.
  8. DOES NOT calculate HR.

Key bounded-data rule
---------------------
A bounded observation is not discarded just because it is not "=".

Examples:
    Ki > 10,000 nM  -> retain 10,000 nM as the numerical boundary, relation ">"
    Ki < 10 nM      -> retain 10 nM as the numerical boundary, relation "<"

Zero and negative boundaries are never converted to pActivity.

For multiple bounded observations in the selected species/endpoint stratum:
  * ">" or ">=" : use the largest non-zero concentration boundary
                  (tightest lower bound on concentration).
  * "<" or "<=" : use the smallest non-zero concentration boundary
                  (tightest upper bound on concentration).
  * if direction cannot be recovered, retain the boundary records for review;
    only use an unknown-direction boundary as a provisional selected value when
    no exact or direction-known bounded value exists, and flag it clearly.

Species-selection hierarchy
---------------------------
For each exact mapped target:
  1. HUMAN if any usable measured human numerical activity exists.
  2. Else MAMMALIAN_NONHUMAN fallback.
  3. Non-mammalian and unresolved-species data remain in the audit but are not
     selected for the proposed principal target value.

Within the selected species basis:
  1. exact measured numerical activity
  2. if no exact value exists, bounded measured numerical activity

Endpoint priority:
  1. BINDING_KI
  2. BINDING_KD
  3. INHIBITION_IC50
  4. ACTIVATION_EC50 / FUNCTIONAL_AC50
  5. OTHER_QUANTITATIVE_POTENCY when numerically standardized

For exact values, the strongest affinity/potency is proposed (maximum pActivity,
equivalent to minimum molar concentration), matching the historical Cardozo
"smallest affinity value" convention.

This is intentionally only a pre-HR activity selection. It does not modify any
source input and it does not calculate tissue scores.

Input routing
-------------
Supply --project-root and --input explicitly. The public repository does not
include or infer the governed external project tree.

Publication contract
--------------------
Purpose: Normalize species and censored activity before any HR calculation.
Stage/lane: Recovered activity-cleanup v2, upstream of forensic finalization.
Inputs: An explicit pooled activity CSV and governed external project root.
Outputs: A new timestamped cleanup directory with row/target tables, audits,
summaries, provenance hashes, and a run log.
Side effects: Writes derivative outputs only; it neither edits sources nor computes
tissue HR values.
Invariants: Exact target grain, human-priority hierarchy, endpoint ordering,
measured/modelled separation, nonzero boundary values, operators, and NA persist.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# =============================================================================
# Paths
# =============================================================================

# The recovered producer is fail-closed: no external scientific input is
# inferred from the executing user's filesystem.
DEFAULT_PROJECT_ROOT = None
DEFAULT_INPUT = None
IDENTITY_AUDIT_MASTER = None


# =============================================================================
# Species normalization
# =============================================================================

HUMAN_TAXON = 9606

MAMMAL_TAXA = {
    9606, 9598, 9544, 9534, 9615, 9685, 9823, 9913, 9925, 9940,
    9796, 9986, 10036, 10090, 10116, 10141,
}

NAME_TO_TAXON = {
    "human": 9606,
    "homo sapiens": 9606,
    "man": 9606,
    "mouse": 10090,
    "mus musculus": 10090,
    "rat": 10116,
    "rattus norvegicus": 10116,
    "pig": 9823,
    "swine": 9823,
    "sus scrofa": 9823,
    "dog": 9615,
    "canis lupus familiaris": 9615,
    "cat": 9685,
    "felis catus": 9685,
    "rabbit": 9986,
    "oryctolagus cuniculus": 9986,
    "guinea pig": 10141,
    "cavia porcellus": 10141,
    "cow": 9913,
    "cattle": 9913,
    "bos taurus": 9913,
    "sheep": 9940,
    "ovis aries": 9940,
    "goat": 9925,
    "capra hircus": 9925,
    "horse": 9796,
    "equus caballus": 9796,
    "rhesus": 9544,
    "rhesus macaque": 9544,
    "macaca mulatta": 9544,
    "chimpanzee": 9598,
    "pan troglodytes": 9598,
    "electric eel": 8005,
    "electrophorus electricus": 8005,
    "torpedo californica": 7787,
    "chicken": 9031,
    "gallus gallus": 9031,
    "zebrafish": 7955,
    "danio rerio": 7955,
    "xenopus laevis": 8355,
}

MAMMAL_TOKENS = (
    "human", "homo sapiens", "mouse", "mus musculus", "rat", "rattus",
    "pig", "swine", "sus scrofa", "dog", "canis", "cat", "felis",
    "rabbit", "oryctolagus", "guinea pig", "cavia", "cow", "cattle",
    "bos taurus", "sheep", "ovis", "goat", "capra", "horse", "equus",
    "macaque", "macaca", "chimpanzee", "pan troglodytes", "hamster",
)

NONMAMMAL_TOKENS = (
    "eel", "electrophorus", "torpedo", "ray", "chicken", "gallus",
    "zebrafish", "danio", "xenopus", "frog", "fish", "drosophila",
    "insect", "yeast", "bacteria", "bacterial", "e. coli", "escherichia",
)


# =============================================================================
# Activity handling
# =============================================================================

ENDPOINT_PRIORITY = {
    "BINDING_KI": 1,
    "BINDING_KD": 2,
    "INHIBITION_IC50": 3,
    "ACTIVATION_EC50": 4,
    "FUNCTIONAL_AC50": 4,
    "OTHER_QUANTITATIVE_POTENCY": 5,
}

EXACT_RELATIONS = {"EXACT", "=", "EQ", "EQUAL", "EQUALS"}
GT_RELATIONS = {">", ">=", "GT", "GE", "GTE"}
LT_RELATIONS = {"<", "<=", "LT", "LE", "LTE"}

UNIT_TO_M = {
    "M": 1.0,
    "MM": 1e-3,
    "UM": 1e-6,
    "NM": 1e-9,
    "PM": 1e-12,
}


# =============================================================================
# General utilities
# =============================================================================

def stamp() -> str:
    """Return a filesystem-safe local timestamp for a derivative run."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def s(value) -> str:
    """Normalize a nullable scalar to a stripped string."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def upper(value) -> str:
    """Return a normalized string in uppercase form."""
    return s(value).upper()


def fnum(value) -> float:
    """Return a finite float or NaN when the value is not numeric."""
    try:
        x = float(value)
        return x if math.isfinite(x) else math.nan
    except Exception:
        return math.nan


def inum(value) -> Optional[int]:
    """Return the rounded integer value or None when it is not finite."""
    x = fnum(value)
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
    for value in values:
        x = s(value)
        if not x or x.lower() == "nan":
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return sep.join(out)


def first_nonblank(values: Iterable) -> str:
    """Return the first normalized nonblank value."""
    for value in values:
        x = s(value)
        if x and x.upper() not in {"NAN", "NONE", "NA", "N/A", "UNKNOWN", "UNRESOLVED"}:
            return x
    return ""


def split_ids(value) -> List[str]:
    """Split a compound identifier field into normalized identifiers."""
    x = s(value)
    if not x:
        return []
    return [z.strip() for z in x.split("|") if z.strip()]


def normalize_unit(value) -> str:
    """Normalize an activity-unit label to the supported vocabulary."""
    x = s(value).replace("μ", "u").replace("µ", "u").upper().replace(" ", "")
    aliases = {
        "MOLAR": "M",
        "MOL/L": "M",
        "MMOLAR": "MM",
        "UMOLAR": "UM",
        "NMOLAR": "NM",
        "PMOLAR": "PM",
    }
    return aliases.get(x, x)


def pactivity_from_value(value, unit) -> float:
    """Convert a positive supported activity value to pActivity."""
    x = fnum(value)
    u = normalize_unit(unit)
    if math.isnan(x) or x <= 0 or u not in UNIT_TO_M:
        return math.nan
    molar = x * UNIT_TO_M[u]
    if molar <= 0:
        return math.nan
    return -math.log10(molar)


def relation_class(value) -> str:
    """Normalize a censored relation to the governed relation class."""
    x = upper(value)
    if x in EXACT_RELATIONS:
        return "EXACT"
    if x in GT_RELATIONS:
        return "GT_BOUND"
    if x in LT_RELATIONS:
        return "LT_BOUND"
    if x == "BOUNDED":
        return "BOUNDED_DIRECTION_UNKNOWN"
    return "UNKNOWN"


def classify_species(name="", taxon=None) -> Tuple[str, Optional[int], str]:
    """Classify a species name or taxon without inventing an identity."""
    raw = s(name)
    low = raw.lower()
    tx = inum(taxon)

    if tx == HUMAN_TAXON:
        return "Homo sapiens", tx, "HUMAN"

    if tx in MAMMAL_TAXA:
        return raw or f"taxon:{tx}", tx, "MAMMALIAN_NONHUMAN"

    if low in NAME_TO_TAXON:
        tx2 = NAME_TO_TAXON[low]
        if tx2 == HUMAN_TAXON:
            return "Homo sapiens", tx2, "HUMAN"
        if tx2 in MAMMAL_TAXA:
            return raw, tx2, "MAMMALIAN_NONHUMAN"
        return raw, tx2, "NON_MAMMALIAN"

    if any(t in low for t in MAMMAL_TOKENS):
        if "human" in low or "homo sapiens" in low:
            return "Homo sapiens", HUMAN_TAXON, "HUMAN"
        return raw, tx, "MAMMALIAN_NONHUMAN"

    if any(t in low for t in NONMAMMAL_TOKENS):
        return raw, tx, "NON_MAMMALIAN"

    return "UNRESOLVED", tx, "UNRESOLVED"


def norm_target_text(value) -> str:
    """Normalize target text for conservative identity comparison."""
    x = upper(value)
    x = re.sub(r"[^A-Z0-9]+", "", x)
    return x


# =============================================================================
# Audit-master metadata
# =============================================================================

def load_identity_audit_master(project_root: Path, log):
    """Load the governed ketamine identity-audit authority."""
    path = (
        project_root
        / "12_QA_AUDITS_AND_PROVENANCE"
        / "Audit_Reports"
        / "Racemic_Ketamine_Identity_Coverage_Audit_20260805_165431_492"
        / "02_SOURCE_RECORD_INVENTORY"
        / "KETAMINE_SOURCE_ASSERTION_MASTER.parquet"
    )

    if not path.is_file():
        log(f"WARNING: identity audit master not found: {path}")
        return None, {}, {}

    a = pd.read_parquet(path)
    log(f"Loaded identity audit master: {len(a):,} rows")

    if "source_assertion_id" not in a.columns:
        log("WARNING: audit master has no source_assertion_id")
        return a, {}, {}

    rowmap = {}
    for row in a.to_dict("records"):
        aid = s(row.get("source_assertion_id"))
        if aid:
            rowmap[aid] = row

    # Duplicate-group metadata can also hydrate rows that are alternative database
    # representations of the same source experiment.
    dup_species = {}
    if "duplicate_group_id" in a.columns:
        for gid, g in a.groupby("duplicate_group_id", dropna=False):
            gid = s(gid)
            if not gid:
                continue

            resolved = []
            for _, r in g.iterrows():
                names = [
                    r.get("organism", ""),
                    r.get("target_organism", ""),
                    r.get("assay_organism", ""),
                    r.get("species", ""),
                ]
                taxons = [
                    r.get("taxon_id", None),
                    r.get("target_taxon_id", None),
                    r.get("assay_taxon_id", None),
                ]

                got = None
                for nm in names:
                    sp, tx, cls = classify_species(nm, None)
                    if cls != "UNRESOLVED":
                        got = (sp, tx, cls)
                        break
                if got is None:
                    for tx0 in taxons:
                        sp, tx, cls = classify_species("", tx0)
                        if cls != "UNRESOLVED":
                            got = (sp, tx, cls)
                            break
                if got:
                    resolved.append(got)

            keys = {(x[0], x[1], x[2]) for x in resolved}
            if len(keys) == 1:
                dup_species[gid] = next(iter(keys))

    return a, rowmap, dup_species


def resolve_from_audit_ids(row, audit_rowmap):
    """Resolve species evidence from governed source-row identifiers."""
    ids = []
    ids.extend(split_ids(row.get("source_assertion_id")))
    ids.extend(split_ids(row.get("all_source_assertion_ids")))
    ids = list(dict.fromkeys(ids))

    candidates = []

    for aid in ids:
        rec = audit_rowmap.get(aid)
        if not rec:
            continue

        names = [
            rec.get("organism", ""),
            rec.get("target_organism", ""),
            rec.get("assay_organism", ""),
            rec.get("species", ""),
        ]
        taxons = [
            rec.get("taxon_id"),
            rec.get("target_taxon_id"),
            rec.get("assay_taxon_id"),
        ]

        found = None
        for nm in names:
            sp, tx, cls = classify_species(nm, None)
            if cls != "UNRESOLVED":
                found = (sp, tx, cls, aid)
                break

        if found is None:
            for tx0 in taxons:
                sp, tx, cls = classify_species("", tx0)
                if cls != "UNRESOLVED":
                    found = (sp, tx, cls, aid)
                    break

        if found:
            candidates.append(found)

    keys = {(x[0], x[1], x[2]) for x in candidates}
    if len(keys) == 1:
        sp, tx, cls = next(iter(keys))
        return sp, tx, cls, uniq_join([x[3] for x in candidates])

    return "UNRESOLVED", None, "UNRESOLVED", ""


def recover_relation_from_audit(row, audit_rowmap):
    """
    Recover the original comparison operator from source assertion metadata.

    Return:
      operator, source
    """
    if relation_class(row.get("activity_relation")) == "EXACT":
        return "=", "POOLED_TABLE_EXACT"

    ids = []
    ids.extend(split_ids(row.get("source_assertion_id")))
    ids.extend(split_ids(row.get("all_source_assertion_ids")))
    ids = list(dict.fromkeys(ids))

    operators = []
    for aid in ids:
        rec = audit_rowmap.get(aid)
        if not rec:
            continue
        for col in (
            "relation_operator", "activity_relation", "relation",
            "standard_relation", "activity_relation_operator"
        ):
            op = s(rec.get(col))
            if op:
                rc = relation_class(op)
                if rc in {"EXACT", "GT_BOUND", "LT_BOUND"}:
                    operators.append(op)
                    break

    classes = {relation_class(x) for x in operators}
    if len(classes) == 1 and operators:
        # Keep a literal operator where possible.
        preferred = sorted(set(operators), key=lambda x: (len(x), x))[0]
        return preferred, "IDENTITY_AUDIT_SOURCE_ASSERTION"

    if upper(row.get("activity_relation")) == "BOUNDED":
        return "BOUNDED", "POOLED_TABLE_DIRECTION_UNKNOWN"

    return s(row.get("activity_relation")), "POOLED_TABLE"


# =============================================================================
# PDSP resolution
# =============================================================================

def find_pdsp_workbooks(project_root: Path) -> List[Path]:
    """
    Targeted filename search that does not load broad project tables.
    """
    candidates = []

    # Fast likely roots first.
    likely_roots = [
        project_root / "02_HR_SCORES",
        project_root / "01_AUTHORITIES",
        project_root / "12_QA_AUDITS_AND_PROVENANCE",
        project_root / "90_ARCHIVES",
    ]

    seen = set()
    patterns = (
        "KiDatabase*.xlsx",
        "*PDSP*Ki*.xlsx",
        "KiDatabase*.xls",
    )

    for root in likely_roots:
        if not root.exists():
            continue
        for pat in patterns:
            try:
                for p in root.rglob(pat):
                    if p.is_file():
                        key = str(p).lower()
                        if key not in seen:
                            seen.add(key)
                            candidates.append(p)
            except Exception:
                pass

    # If not found, one bounded whole-project filename search.
    if not candidates:
        for dirpath, dirnames, filenames in os.walk(project_root):
            # Prune directories that are very unlikely to contain raw PDSP activity.
            low = dirpath.lower()
            if any(token in low for token in (
                "\\08_graphics_and_figures",
                "\\10_manuscript_and_literature",
                "\\05_phenotype_atlas",
                "\\06_pathology_atlas",
                "\\07_crtp",
                "\\99_unclassified_review",
            )):
                dirnames[:] = []
                continue
            for fn in filenames:
                lfn = fn.lower()
                if (lfn.startswith("kidatabase") and lfn.endswith((".xlsx", ".xls"))) or (
                    "pdsp" in lfn and "ki" in lfn and lfn.endswith((".xlsx", ".xls"))
                ):
                    p = Path(dirpath) / fn
                    key = str(p).lower()
                    if key not in seen:
                        seen.add(key)
                        candidates.append(p)

    return candidates


def detect_col(columns, alternatives):
    """Return the first available column from a list of aliases."""
    lut = {str(c).strip().lower(): c for c in columns}
    for alt in alternatives:
        if alt.lower() in lut:
            return lut[alt.lower()]
    return None


def load_pdsp_raw(project_root: Path, log):
    """Load and normalize governed PDSP records for source reconciliation."""
    candidates = find_pdsp_workbooks(project_root)
    if not candidates:
        log("WARNING: no raw PDSP Ki workbook found")
        return None, {}, {}

    scored = []
    for p in candidates:
        score = 0
        low = str(p).lower()
        if p.name.lower().startswith("kidatabase"):
            score += 10
        if "pdsp" in low:
            score += 5
        if "raw" in low:
            score += 3
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        scored.append((score, size, p))

    scored.sort(key=lambda x: (-x[0], -x[1], str(x[2]).lower()))

    for _, _, path in scored[:20]:
        try:
            # Inspect first.
            probe = pd.read_excel(path, nrows=5)
            ki_col = detect_col(probe.columns, ["Ki ID", "KiID", "Ki_ID", "ID"])
            species_col = detect_col(probe.columns, ["Species", "Organism"])
            if not ki_col or not species_col:
                continue

            d = pd.read_excel(path)
            receptor_col = detect_col(d.columns, ["Receptor", "Target", "Gene"])
            ligand_col = detect_col(d.columns, ["Test Ligands", "Test Ligand", "Ligand", "Compound"])
            value_col = detect_col(d.columns, ["Ki Value", "Ki", "Value"])
            relation_col = detect_col(d.columns, ["Relation", "Operator", "Qualifier"])
            unit_col = detect_col(d.columns, ["Units", "Unit"])

            idmap = {}
            target_species = defaultdict(list)

            for _, r in d.iterrows():
                kid = s(r.get(ki_col))
                try:
                    kf = float(kid)
                    if math.isfinite(kf) and abs(kf - round(kf)) < 1e-9:
                        kid = str(int(round(kf)))
                except Exception:
                    pass
                if not kid:
                    continue

                raw_species = s(r.get(species_col))
                sp, tx, cls = classify_species(raw_species)
                if cls == "UNRESOLVED":
                    continue

                ligand = s(r.get(ligand_col)) if ligand_col else ""
                receptor = s(r.get(receptor_col)) if receptor_col else ""
                value = r.get(value_col) if value_col else np.nan
                relation = s(r.get(relation_col)) if relation_col else ""
                unit = s(r.get(unit_col)) if unit_col else ""

                rec = {
                    "ki_id": kid,
                    "species": sp,
                    "taxon": tx,
                    "species_class": cls,
                    "raw_species": raw_species,
                    "receptor": receptor,
                    "ligand": ligand,
                    "value": value,
                    "relation": relation,
                    "unit": unit,
                    "source_path": str(path),
                }

                if kid not in idmap:
                    idmap[kid] = rec
                else:
                    old = idmap[kid]
                    if (
                        old["species_class"], old["taxon"], upper(old["species"])
                    ) != (
                        rec["species_class"], rec["taxon"], upper(rec["species"])
                    ):
                        idmap[kid] = None

                if receptor:
                    target_species[norm_target_text(receptor)].append(rec)

            idmap = {k: v for k, v in idmap.items() if v is not None}

            # Build conservative target-name consensus, used only when all
            # explicit PDSP ketamine rows matching the same receptor name agree on
            # one species. It is source-derived, not inferred from the target biology.
            targetmap = {}
            for key, records in target_species.items():
                ket_records = []
                for rec in records:
                    lig = rec["ligand"].lower()
                    if not lig or "ketamine" in lig:
                        ket_records.append(rec)

                if not ket_records:
                    continue

                keys = {
                    (x["species_class"], x["taxon"], upper(x["species"]))
                    for x in ket_records
                }
                if len(keys) == 1:
                    targetmap[key] = ket_records[0]

            log(
                f"Loaded raw PDSP workbook {path.name}: "
                f"{len(d):,} rows; {len(idmap):,} nonconflicting Ki IDs; "
                f"{len(targetmap):,} unanimous receptor-name species mappings"
            )

            audit = {
                "path": str(path),
                "sha256": sha256(path),
                "rows": len(d),
                "ki_id_column": str(ki_col),
                "species_column": str(species_col),
                "receptor_column": str(receptor_col or ""),
                "ligand_column": str(ligand_col or ""),
                "value_column": str(value_col or ""),
                "relation_column": str(relation_col or ""),
                "unit_column": str(unit_col or ""),
            }
            return audit, idmap, targetmap

        except Exception as exc:
            log(f"WARNING: could not use PDSP candidate {path}: {exc}")

    log("WARNING: no PDSP workbook with explicit Ki ID + Species columns could be loaded")
    return None, {}, {}


PDSP_ID_RE = re.compile(r"(?i)PDSP\s*Ki[_\s:-]*([0-9]+(?:\.0+)?)")


def pdsp_id_from_assay(value) -> Optional[str]:
    """Extract the stable PDSP record identifier from an assay label."""
    m = PDSP_ID_RE.search(s(value))
    if not m:
        return None
    try:
        return str(int(round(float(m.group(1)))))
    except Exception:
        return m.group(1)


# =============================================================================
# Working numerical activity
# =============================================================================

def working_pactivity(row):
    """
    Return:
      pActivity_working
      numerical_value_M
      numerical_origin
      zero_or_invalid_boundary
    """
    p = fnum(row.get("pActivity_if_available"))
    std = fnum(row.get("standardized_activity_value"))
    std_unit = normalize_unit(row.get("standardized_activity_unit"))

    if not math.isnan(std) and std > 0 and std_unit == "M":
        calc = -math.log10(std)
        return (
            p if not math.isnan(p) else calc,
            std,
            "SUPPLIED_PACTIVITY_AND_STANDARDIZED_M" if not math.isnan(p)
            else "RECOMPUTED_FROM_STANDARDIZED_M",
            False,
        )

    original = fnum(row.get("activity_value_original"))
    original_unit = normalize_unit(row.get("activity_unit_original"))

    if not math.isnan(original) and original > 0 and original_unit in UNIT_TO_M:
        molar = original * UNIT_TO_M[original_unit]
        calc = -math.log10(molar)
        return (
            p if not math.isnan(p) else calc,
            molar,
            "SUPPLIED_PACTIVITY_AND_ORIGINAL_VALUE" if not math.isnan(p)
            else "RECOMPUTED_FROM_ORIGINAL_VALUE",
            False,
        )

    if not math.isnan(p):
        # A pActivity already calculated upstream can still be retained, including a
        # censored/bounded boundary pActivity. Convert it back to molar for selection.
        molar = 10 ** (-p)
        return p, molar, "SUPPLIED_PACTIVITY_ONLY", False

    zero_invalid = (not math.isnan(std) and std <= 0) or (
        not math.isnan(original) and original <= 0
    )
    return math.nan, math.nan, "NO_NUMERICAL_ACTIVITY", bool(zero_invalid)


def activity_lane(row):
    """Classify the row as measured, modeled, or nonnumeric activity."""
    atype = upper(row.get("activity_type"))
    origin = upper(row.get("activity_origin"))
    p = fnum(row.get("pActivity_working"))

    if any(t in atype for t in ("ASSIGNED", "SCENARIO")):
        return "ASSIGNED_SCENARIO"

    if origin in {"MODELED_OR_IMPUTED", "MODELED", "MODELLED", "IMPUTED"}:
        return "MODELED_OR_IMPUTED"

    if origin == "MEASURED":
        if not math.isnan(p):
            return "MEASURED_NUMERICAL"
        return "MEASURED_NONNUMERICAL"

    return "OTHER"


# =============================================================================
# Target selection
# =============================================================================

def is_exact_target(row) -> bool:
    """Return whether a record exactly matches its governed target identity."""
    status = upper(row.get("activity_table_status"))
    grain = upper(row.get("target_grain"))
    target = s(row.get("canonical_target_id"))

    if not target:
        return False
    if "UNRESOLVED" in status or "UNRESOLVED" in grain:
        return False
    if "FAMILY" in grain or "GENERIC" in grain:
        return False
    return status in {"MAPPED_EXACT_TARGET", "EXACT_TARGET"} or "EXACT" in grain


def endpoint_priority(row):
    """Return the fixed endpoint ordering used for record selection."""
    return ENDPOINT_PRIORITY.get(upper(row.get("activity_type")))


def choose_exact(g):
    """Choose an exact measured record using the fixed hierarchy."""
    g = g.copy()
    g["endpoint_priority"] = g.apply(endpoint_priority, axis=1)
    g = g[g["endpoint_priority"].notna()]
    if g.empty:
        return None

    best_ep = g["endpoint_priority"].min()
    g = g[g["endpoint_priority"].eq(best_ep)].copy()
    g["p"] = pd.to_numeric(g["pActivity_working"], errors="coerce")
    g = g[g["p"].notna()]
    if g.empty:
        return None

    # Historical Cardozo-style strongest affinity within the selected endpoint.
    g = g.sort_values(
        ["p", "source_assertion_id"],
        ascending=[False, True],
        kind="stable",
    )
    return g.iloc[0]


def choose_bounded(g):
    """
    Bounded selection preserving direction.

    Priority:
      1. direction-known bounded rows
      2. unknown-direction bounded rows only if no known-direction row exists

    Endpoint priority is applied before boundary selection.
    """
    g = g.copy()
    g["endpoint_priority"] = g.apply(endpoint_priority, axis=1)
    g = g[g["endpoint_priority"].notna()]
    if g.empty:
        return None, "NO_ELIGIBLE_BOUNDED_ENDPOINT"

    best_ep = g["endpoint_priority"].min()
    g = g[g["endpoint_priority"].eq(best_ep)].copy()

    g["molar"] = pd.to_numeric(g["activity_value_M_working"], errors="coerce")
    g["p"] = pd.to_numeric(g["pActivity_working"], errors="coerce")
    g = g[(g["molar"] > 0) & g["molar"].notna() & g["p"].notna()]
    if g.empty:
        return None, "NO_NONZERO_NUMERICAL_BOUNDARY"

    gt = g[g["relation_class_clean"].eq("GT_BOUND")]
    lt = g[g["relation_class_clean"].eq("LT_BOUND")]

    if not gt.empty and not lt.empty:
        # Mixed censoring directions in the same target/species/endpoint stratum are
        # not silently collapsed into a single exact-like value.
        return None, "MIXED_BOUND_DIRECTIONS_REVIEW_REQUIRED"

    if not gt.empty:
        # Tightest lower bound on concentration: largest reported concentration.
        gt = gt.sort_values(
            ["molar", "source_assertion_id"],
            ascending=[False, True],
            kind="stable",
        )
        return gt.iloc[0], "GT_TIGHTEST_LOWER_CONCENTRATION_BOUND"

    if not lt.empty:
        # Tightest upper bound on concentration: smallest reported concentration.
        lt = lt.sort_values(
            ["molar", "source_assertion_id"],
            ascending=[True, True],
            kind="stable",
        )
        return lt.iloc[0], "LT_TIGHTEST_UPPER_CONCENTRATION_BOUND"

    unknown = g[g["relation_class_clean"].eq("BOUNDED_DIRECTION_UNKNOWN")]
    if not unknown.empty:
        # Preserve unknown-direction censored observations rather than dropping them. Because direction
        # is unknown, choose the strongest non-zero numerical boundary provisionally,
        # and flag it for review.
        unknown = unknown.sort_values(
            ["p", "source_assertion_id"],
            ascending=[False, True],
            kind="stable",
        )
        return unknown.iloc[0], "UNKNOWN_DIRECTION_PROVISIONAL_STRONGEST_BOUNDARY"

    return None, "NO_RECOGNIZED_BOUNDED_DIRECTION"


def build_target_summary(d, log):
    """Build one selected activity record per governed target."""
    rows = []

    mapped = d[d.apply(is_exact_target, axis=1)].copy()

    for target, g in mapped.groupby("canonical_target_id", dropna=False):
        gene = first_nonblank(g["gene_symbol"]) if "gene_symbol" in g else ""
        tname = first_nonblank(g["target_name"]) if "target_name" in g else ""

        measured = g[g["activity_lane_clean"].eq("MEASURED_NUMERICAL")].copy()
        measured = measured[
            pd.to_numeric(measured["pActivity_working"], errors="coerce").notna()
        ]

        human = measured[measured["species_class_clean"].eq("HUMAN")]
        mammal = measured[measured["species_class_clean"].eq("MAMMALIAN_NONHUMAN")]
        nonmammal = measured[measured["species_class_clean"].eq("NON_MAMMALIAN")]
        unresolved = measured[measured["species_class_clean"].eq("UNRESOLVED")]

        # Species priority is applied before exact/bounded priority.
        if not human.empty:
            species_pool = human
            species_basis = "HUMAN_PRIORITY"
        elif not mammal.empty:
            species_pool = mammal
            species_basis = "MAMMALIAN_FALLBACK"
        else:
            species_pool = measured.iloc[0:0]
            species_basis = ""

        exact = species_pool[species_pool["relation_class_clean"].eq("EXACT")]
        bounded = species_pool[
            species_pool["relation_class_clean"].isin(
                ["GT_BOUND", "LT_BOUND", "BOUNDED_DIRECTION_UNKNOWN"]
            )
        ]

        selected = None
        selection_kind = ""
        bound_rule = ""

        if not exact.empty:
            selected = choose_exact(exact)
            if selected is not None:
                selection_kind = "EXACT_MEASURED"
        elif not bounded.empty:
            selected, bound_rule = choose_bounded(bounded)
            if selected is not None:
                selection_kind = "BOUNDED_MEASURED_BOUNDARY"

        def stats(x):
            """Summarize numeric values and unique relation labels for one group."""
            vals = pd.to_numeric(x["pActivity_working"], errors="coerce").dropna()
            if vals.empty:
                return (math.nan, math.nan, math.nan, math.nan)
            return (
                float(vals.min()),
                float(vals.median()),
                float(vals.max()),
                float(vals.mean()),
            )

        all_min, all_med, all_max, all_mean = stats(measured)
        h_min, h_med, h_max, h_mean = stats(human)
        m_min, m_med, m_max, m_mean = stats(mammal)

        rec = {
            "analysis_compound": "POOLED_PARENT_KETAMINE",
            "canonical_target_id": s(target),
            "gene_symbol": gene,
            "target_name": tname,

            "n_all_independent_observations": len(g),
            "n_measured_numerical": len(measured),
            "n_human_measured": len(human),
            "n_mammalian_nonhuman_measured": len(mammal),
            "n_nonmammalian_measured": len(nonmammal),
            "n_unresolved_species_measured": len(unresolved),

            "n_exact_measured_selected_species": int(
                species_pool["relation_class_clean"].eq("EXACT").sum()
            ),
            "n_gt_bounded_selected_species": int(
                species_pool["relation_class_clean"].eq("GT_BOUND").sum()
            ),
            "n_lt_bounded_selected_species": int(
                species_pool["relation_class_clean"].eq("LT_BOUND").sum()
            ),
            "n_unknown_direction_bounded_selected_species": int(
                species_pool["relation_class_clean"].eq(
                    "BOUNDED_DIRECTION_UNKNOWN"
                ).sum()
            ),

            "measured_activity_types": uniq_join(measured["activity_type"]),
            "measured_species": uniq_join(measured["activity_species_clean"]),
            "measured_sources": uniq_join(measured["source_database"]),
            "measured_identity_categories": uniq_join(
                measured["adjudicated_identity_category"]
            ),

            "measured_pActivity_min": all_min,
            "measured_pActivity_median": all_med,
            "measured_pActivity_max": all_max,
            "human_pActivity_min": h_min,
            "human_pActivity_median": h_med,
            "human_pActivity_max": h_max,
            "mammalian_pActivity_min": m_min,
            "mammalian_pActivity_median": m_med,
            "mammalian_pActivity_max": m_max,

            "proposed_species_basis": species_basis,
            "proposed_selection_kind": selection_kind,
            "proposed_bound_selection_rule": bound_rule,
            "proposed_selected_source_assertion_id": "",
            "proposed_selected_independence_key": "",
            "proposed_selected_activity_type": "",
            "proposed_selected_relation_original": "",
            "proposed_selected_relation_operator_clean": "",
            "proposed_selected_relation_class": "",
            "proposed_selected_is_bounded": False,
            "proposed_selected_boundary_direction_known": False,
            "proposed_selected_activity_species": "",
            "proposed_selected_activity_taxon_id": np.nan,
            "proposed_selected_pActivity": np.nan,
            "proposed_selected_activity_value_M": np.nan,
            "proposed_selected_activity_value_original": np.nan,
            "proposed_selected_activity_unit_original": "",
            "proposed_selected_source_database": "",
            "proposed_selected_publication": "",
            "proposed_selected_DOI": "",
            "proposed_selected_PMID": "",
            "proposed_selected_identity_category": "",
            "proposed_selection_status": "",
        }

        if selected is not None:
            rc = s(selected.get("relation_class_clean"))
            rec.update({
                "proposed_selected_source_assertion_id": s(
                    selected.get("source_assertion_id")
                ),
                "proposed_selected_independence_key": s(
                    selected.get("independence_key")
                ),
                "proposed_selected_activity_type": s(
                    selected.get("activity_type")
                ),
                "proposed_selected_relation_original": s(
                    selected.get("activity_relation")
                ),
                "proposed_selected_relation_operator_clean": s(
                    selected.get("relation_operator_clean")
                ),
                "proposed_selected_relation_class": rc,
                "proposed_selected_is_bounded": rc != "EXACT",
                "proposed_selected_boundary_direction_known": rc in {
                    "GT_BOUND", "LT_BOUND"
                },
                "proposed_selected_activity_species": s(
                    selected.get("activity_species_clean")
                ),
                "proposed_selected_activity_taxon_id": selected.get(
                    "activity_taxon_id_clean", np.nan
                ),
                "proposed_selected_pActivity": selected.get(
                    "pActivity_working", np.nan
                ),
                "proposed_selected_activity_value_M": selected.get(
                    "activity_value_M_working", np.nan
                ),
                "proposed_selected_activity_value_original": selected.get(
                    "activity_value_original", np.nan
                ),
                "proposed_selected_activity_unit_original": s(
                    selected.get("activity_unit_original")
                ),
                "proposed_selected_source_database": s(
                    selected.get("source_database")
                ),
                "proposed_selected_publication": s(
                    selected.get("publication")
                ),
                "proposed_selected_DOI": s(selected.get("DOI")),
                "proposed_selected_PMID": s(selected.get("PMID")),
                "proposed_selected_identity_category": s(
                    selected.get("adjudicated_identity_category")
                ),
            })

            if rc == "EXACT":
                rec["proposed_selection_status"] = "SELECTED_EXACT_MEASURED"
            elif rc in {"GT_BOUND", "LT_BOUND"}:
                rec["proposed_selection_status"] = (
                    "SELECTED_BOUNDED_MEASURED_DIRECTION_PRESERVED"
                )
            else:
                rec["proposed_selection_status"] = (
                    "SELECTED_BOUNDED_DIRECTION_UNKNOWN_REVIEW_REQUIRED"
                )
        else:
            if measured.empty:
                rec["proposed_selection_status"] = (
                    "NO_HUMAN_OR_MAMMALIAN_MEASURED_NUMERICAL_ACTIVITY"
                )
            elif species_pool.empty:
                rec["proposed_selection_status"] = (
                    "ONLY_NONMAMMALIAN_OR_UNRESOLVED_SPECIES_MEASURED_ACTIVITY"
                )
            elif bound_rule:
                rec["proposed_selection_status"] = bound_rule
            else:
                rec["proposed_selection_status"] = (
                    "NO_SELECTABLE_EXACT_OR_BOUNDED_ACTIVITY"
                )

        rows.append(rec)

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(
            [
                "proposed_selection_status",
                "canonical_target_id",
            ],
            kind="stable",
        ).reset_index(drop=True)

    log(
        f"Target summary: {len(out):,} targets; "
        f"{int(out['proposed_selected_pActivity'].notna().sum()) if not out.empty else 0:,} "
        "with a proposed selected numerical activity"
    )
    return out


# =============================================================================
# Main species-resolution process
# =============================================================================

def resolve_species_and_relations(d, project_root, audit_rowmap, audit_dup_species, log):
    """Reconcile species and relation evidence against governed sources."""
    d = d.copy()

    d["species_before"] = d["activity_species"].fillna("").astype(str)
    d["species_class_before"] = d["species_class"].fillna("").astype(str)
    d["taxon_before"] = d["activity_taxon_id"]

    d["activity_species_clean"] = "UNRESOLVED"
    d["activity_taxon_id_clean"] = np.nan
    d["species_class_clean"] = "UNRESOLVED"
    d["species_resolution_method"] = ""
    d["species_resolution_detail"] = ""

    # A. Current explicit row metadata.
    for idx, row in d.iterrows():
        candidates = [
            (row.get("activity_species"), row.get("activity_taxon_id")),
            (row.get("target_organism_reported"), None),
            (row.get("assay_organism_reported"), None),
        ]

        got = None
        for nm, tx in candidates:
            sp, tax, cls = classify_species(nm, tx)
            if cls != "UNRESOLVED":
                got = (sp, tax, cls)
                break

        if got:
            sp, tax, cls = got
            d.at[idx, "activity_species_clean"] = sp
            d.at[idx, "activity_taxon_id_clean"] = (
                tax if tax is not None else np.nan
            )
            d.at[idx, "species_class_clean"] = cls
            d.at[idx, "species_resolution_method"] = "POOLED_TABLE_EXPLICIT"
            d.at[idx, "species_resolution_detail"] = "Existing explicit species/taxon"

    before_extra = int((d["species_class_clean"] != "UNRESOLVED").sum())
    log(f"Initially resolved from pooled table: {before_extra:,}/{len(d):,}")

    # B. Source-assertion audit metadata.
    for idx, row in d[d["species_class_clean"].eq("UNRESOLVED")].iterrows():
        sp, tax, cls, ids = resolve_from_audit_ids(row, audit_rowmap)
        if cls != "UNRESOLVED":
            d.at[idx, "activity_species_clean"] = sp
            d.at[idx, "activity_taxon_id_clean"] = (
                tax if tax is not None else np.nan
            )
            d.at[idx, "species_class_clean"] = cls
            d.at[idx, "species_resolution_method"] = "AUDIT_SOURCE_ASSERTION"
            d.at[idx, "species_resolution_detail"] = f"Resolved source IDs: {ids}"

    after_audit = int((d["species_class_clean"] != "UNRESOLVED").sum())
    log(f"After audit-source metadata: {after_audit:,}/{len(d):,}")

    # C. Duplicate-group metadata from audit master.
    if "duplicate_group_id" in d.columns:
        for idx, row in d[d["species_class_clean"].eq("UNRESOLVED")].iterrows():
            gid = s(row.get("duplicate_group_id"))
            if gid and gid in audit_dup_species:
                sp, tax, cls = audit_dup_species[gid]
                d.at[idx, "activity_species_clean"] = sp
                d.at[idx, "activity_taxon_id_clean"] = (
                    tax if tax is not None else np.nan
                )
                d.at[idx, "species_class_clean"] = cls
                d.at[idx, "species_resolution_method"] = "AUDIT_DUPLICATE_GROUP"
                d.at[idx, "species_resolution_detail"] = (
                    f"Unanimous explicit species in audit duplicate_group_id={gid}"
                )

    after_dup = int((d["species_class_clean"] != "UNRESOLVED").sum())
    log(f"After audit duplicate-group metadata: {after_dup:,}/{len(d):,}")

    # D. PDSP raw source.
    pdsp_audit, pdsp_idmap, pdsp_targetmap = load_pdsp_raw(project_root, log)

    if pdsp_idmap:
        pdsp_mask = (
            d["species_class_clean"].eq("UNRESOLVED")
            & d["source_database"].astype(str).str.contains("PDSP", case=False, na=False)
        )

        # Direct Ki ID.
        n_direct = 0
        for idx, row in d[pdsp_mask].iterrows():
            kid = pdsp_id_from_assay(row.get("assay_id"))
            if not kid or kid not in pdsp_idmap:
                continue

            rec = pdsp_idmap[kid]
            lig = s(rec.get("ligand")).lower()
            if lig and "ketamine" not in lig:
                continue

            d.at[idx, "activity_species_clean"] = rec["species"]
            d.at[idx, "activity_taxon_id_clean"] = (
                rec["taxon"] if rec["taxon"] is not None else np.nan
            )
            d.at[idx, "species_class_clean"] = rec["species_class"]
            d.at[idx, "species_resolution_method"] = "PDSP_RAW_KI_ID"
            d.at[idx, "species_resolution_detail"] = (
                f"PDSP Ki ID={kid}; raw species={rec['raw_species']}; "
                f"receptor={rec['receptor']}"
            )
            n_direct += 1

        log(f"PDSP direct Ki-ID resolutions: {n_direct:,}")

        # Propagate unanimous species within pooled-table duplicate groups after the
        # direct raw PDSP IDs have resolved some representatives.
        n_prop = 0
        if "duplicate_group_id" in d.columns:
            for gid, g in d.groupby("duplicate_group_id", dropna=False):
                gid = s(gid)
                if not gid:
                    continue
                rg = g[g["species_class_clean"] != "UNRESOLVED"]
                if rg.empty:
                    continue
                keys = {
                    (
                        s(r.activity_species_clean),
                        inum(r.activity_taxon_id_clean),
                        s(r.species_class_clean),
                    )
                    for r in rg.itertuples()
                }
                if len(keys) != 1:
                    continue
                sp, tax, cls = next(iter(keys))
                for idx in g.index[g["species_class_clean"].eq("UNRESOLVED")]:
                    d.at[idx, "activity_species_clean"] = sp
                    d.at[idx, "activity_taxon_id_clean"] = (
                        tax if tax is not None else np.nan
                    )
                    d.at[idx, "species_class_clean"] = cls
                    d.at[idx, "species_resolution_method"] = (
                        "POOLED_DUPLICATE_GROUP_UNANIMOUS"
                    )
                    d.at[idx, "species_resolution_detail"] = (
                        f"Unanimous resolved species within duplicate_group_id={gid}"
                    )
                    n_prop += 1

        log(f"Species propagated within pooled duplicate groups: {n_prop:,}")

        # Conservative receptor-name mapping only when the raw PDSP records for that
        # normalized receptor name are explicitly unanimous.
        n_target = 0
        pdsp_mask = (
            d["species_class_clean"].eq("UNRESOLVED")
            & d["source_database"].astype(str).str.contains("PDSP", case=False, na=False)
        )
        for idx, row in d[pdsp_mask].iterrows():
            keys = [
                norm_target_text(row.get("original_target_name")),
                norm_target_text(row.get("target_name")),
                norm_target_text(row.get("gene_symbol")),
                norm_target_text(row.get("canonical_target_id")),
            ]
            recs = [pdsp_targetmap[k] for k in keys if k and k in pdsp_targetmap]
            if not recs:
                continue

            species_keys = {
                (
                    r["species_class"],
                    r["taxon"],
                    upper(r["species"]),
                )
                for r in recs
            }
            if len(species_keys) != 1:
                continue

            rec = recs[0]
            d.at[idx, "activity_species_clean"] = rec["species"]
            d.at[idx, "activity_taxon_id_clean"] = (
                rec["taxon"] if rec["taxon"] is not None else np.nan
            )
            d.at[idx, "species_class_clean"] = rec["species_class"]
            d.at[idx, "species_resolution_method"] = (
                "PDSP_RAW_RECEPTOR_UNANIMOUS"
            )
            d.at[idx, "species_resolution_detail"] = (
                "All explicit raw PDSP ketamine rows matching this receptor name "
                f"have species={rec['raw_species']}"
            )
            n_target += 1

        log(f"PDSP unanimous receptor-name resolutions: {n_target:,}")

    # Relation recovery.
    ops = []
    op_sources = []
    op_classes = []
    for _, row in d.iterrows():
        op, src = recover_relation_from_audit(row, audit_rowmap)
        ops.append(op)
        op_sources.append(src)
        op_classes.append(relation_class(op))

    d["relation_operator_clean"] = ops
    d["relation_recovery_source"] = op_sources
    d["relation_class_clean"] = op_classes

    # Numerical values.
    pvals = []
    molars = []
    origins = []
    invalids = []

    for _, row in d.iterrows():
        p, m, origin, invalid = working_pactivity(row)
        pvals.append(p)
        molars.append(m)
        origins.append(origin)
        invalids.append(invalid)

    d["pActivity_working"] = pvals
    d["activity_value_M_working"] = molars
    d["numerical_activity_origin"] = origins
    d["zero_or_invalid_boundary"] = invalids
    d["activity_lane_clean"] = d.apply(activity_lane, axis=1)

    d["species_newly_resolved"] = (
        d["species_class_before"].astype(str).str.upper().eq("UNRESOLVED")
        & ~d["species_class_clean"].eq("UNRESOLVED")
    )

    return d, pdsp_audit


# =============================================================================
# Main
# =============================================================================

def main():
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    parser = argparse.ArgumentParser(
        description=(
            "Resolve pooled-parent-ketamine species, preserve bounded activity "
            "boundaries, separate measured/modelled lanes, and build a target-level "
            "pre-HR activity summary."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument(
        "--output-parent",
        type=Path,
        default=None,
        help="Default: same directory as input CSV",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    project_root = args.project_root.resolve()
    output_parent = (
        args.output_parent.resolve() if args.output_parent else input_path.parent
    )
    output_dir = output_parent / f"Species_Cleanup_Bounded_v2_{stamp()}"
    output_dir.mkdir(parents=True, exist_ok=False)

    log_path = output_dir / "RUN.log"

    def log(msg):
        """Write one timestamped run-log message."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    try:
        log("=== POOLED PARENT KETAMINE ACTIVITY CLEANUP V2 START ===")
        log(f"Input: {input_path}")
        log(f"Project root: {project_root}")
        log(f"Output: {output_dir}")

        if not input_path.is_file():
            raise FileNotFoundError(f"Input CSV not found: {input_path}")
        if not project_root.is_dir():
            raise FileNotFoundError(f"Project root not found: {project_root}")

        input_hash = sha256(input_path)
        d = pd.read_csv(input_path, low_memory=False)
        log(f"Input rows: {len(d):,}; columns: {len(d.columns):,}")
        log(f"Input SHA256: {input_hash}")

        required = [
            "source_assertion_id",
            "source_database",
            "canonical_target_id",
            "gene_symbol",
            "activity_type",
            "activity_relation",
            "activity_origin",
            "activity_species",
            "activity_taxon_id",
            "species_class",
        ]
        missing = [c for c in required if c not in d.columns]
        if missing:
            raise RuntimeError(f"Missing required input columns: {missing}")

        if "independence_key" in d.columns:
            dup_ind = int(d["independence_key"].astype(str).duplicated().sum())
        else:
            dup_ind = -1
        log(f"Duplicate independence_key rows in input: {dup_ind:,}")

        audit_master, audit_rowmap, audit_dup_species = load_identity_audit_master(
            project_root, log
        )

        cleaned, pdsp_audit = resolve_species_and_relations(
            d,
            project_root,
            audit_rowmap,
            audit_dup_species,
            log,
        )

        target_summary = build_target_summary(cleaned, log)

        # Lane outputs.
        measured = cleaned[
            cleaned["activity_lane_clean"].eq("MEASURED_NUMERICAL")
        ].copy()

        modeled = cleaned[
            cleaned["activity_lane_clean"].isin(
                ["MODELED_OR_IMPUTED", "ASSIGNED_SCENARIO"]
            )
        ].copy()

        unresolved_species = cleaned[
            cleaned["species_class_clean"].eq("UNRESOLVED")
        ].copy()

        bounded = cleaned[
            cleaned["relation_class_clean"].isin(
                ["GT_BOUND", "LT_BOUND", "BOUNDED_DIRECTION_UNKNOWN"]
            )
        ].copy()

        # Output.
        paths = {
            "cleaned": output_dir
            / "POOLED_PARENT_KETAMINE_ACTIVITY_TABLE_SPECIES_CLEANED.csv",
            "measured": output_dir
            / "POOLED_PARENT_KETAMINE_MEASURED_NUMERICAL.csv",
            "modeled": output_dir
            / "POOLED_PARENT_KETAMINE_MODELED_ASSIGNED.csv",
            "target": output_dir
            / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY.csv",
            "species_audit": output_dir
            / "POOLED_PARENT_KETAMINE_SPECIES_RESOLUTION_AUDIT.csv",
            "bounded_audit": output_dir
            / "POOLED_PARENT_KETAMINE_BOUNDED_ACTIVITY_AUDIT.csv",
            "unresolved_species": output_dir
            / "POOLED_PARENT_KETAMINE_UNRESOLVED_SPECIES_REMAINDER.csv",
        }

        cleaned.to_csv(paths["cleaned"], index=False)
        measured.to_csv(paths["measured"], index=False)
        modeled.to_csv(paths["modeled"], index=False)
        target_summary.to_csv(paths["target"], index=False)

        species_cols = [
            c for c in [
                "source_assertion_id",
                "all_source_assertion_ids",
                "duplicate_group_id",
                "source_database",
                "assay_id",
                "canonical_target_id",
                "gene_symbol",
                "activity_type",
                "activity_relation",
                "species_before",
                "species_class_before",
                "taxon_before",
                "activity_species_clean",
                "activity_taxon_id_clean",
                "species_class_clean",
                "species_resolution_method",
                "species_resolution_detail",
                "species_newly_resolved",
            ] if c in cleaned.columns
        ]
        cleaned[species_cols].to_csv(paths["species_audit"], index=False)

        bounded_cols = [
            c for c in [
                "source_assertion_id",
                "independence_key",
                "duplicate_group_id",
                "source_database",
                "canonical_target_id",
                "gene_symbol",
                "activity_type",
                "activity_relation",
                "relation_operator_clean",
                "relation_class_clean",
                "relation_recovery_source",
                "activity_value_original",
                "activity_unit_original",
                "standardized_activity_value",
                "standardized_activity_unit",
                "pActivity_if_available",
                "pActivity_working",
                "activity_value_M_working",
                "zero_or_invalid_boundary",
                "activity_species_clean",
                "species_class_clean",
                "activity_origin",
                "activity_lane_clean",
            ] if c in bounded.columns
        ]
        bounded[bounded_cols].to_csv(paths["bounded_audit"], index=False)
        unresolved_species.to_csv(paths["unresolved_species"], index=False)

        species_before = cleaned["species_class_before"].value_counts(
            dropna=False
        ).to_dict()
        species_after = cleaned["species_class_clean"].value_counts(
            dropna=False
        ).to_dict()

        rel_counts = cleaned["relation_class_clean"].value_counts(
            dropna=False
        ).to_dict()

        sel_counts = (
            target_summary["proposed_selection_status"].value_counts(
                dropna=False
            ).to_dict()
            if not target_summary.empty else {}
        )

        pdsp_mask = cleaned["source_database"].astype(str).str.contains(
            "PDSP", case=False, na=False
        )
        pdsp_unresolved_before = int(
            (
                pdsp_mask
                & cleaned["species_class_before"]
                .astype(str)
                .str.upper()
                .eq("UNRESOLVED")
            ).sum()
        )
        pdsp_unresolved_after = int(
            (pdsp_mask & cleaned["species_class_clean"].eq("UNRESOLVED")).sum()
        )

        summary = {
            "status": "PASS",
            "input": str(input_path),
            "input_sha256": input_hash,
            "output_dir": str(output_dir),
            "input_rows": len(cleaned),
            "duplicate_independence_key_rows": dup_ind,
            "species_before": species_before,
            "species_after": species_after,
            "new_species_resolutions": int(
                cleaned["species_newly_resolved"].sum()
            ),
            "pdsp_rows": int(pdsp_mask.sum()),
            "pdsp_unresolved_before": pdsp_unresolved_before,
            "pdsp_unresolved_after": pdsp_unresolved_after,
            "pdsp_newly_resolved": (
                pdsp_unresolved_before - pdsp_unresolved_after
            ),
            "relation_class_counts": rel_counts,
            "measured_numerical_rows": len(measured),
            "modeled_or_assigned_rows": len(modeled),
            "bounded_rows": len(bounded),
            "zero_or_invalid_boundaries": int(
                cleaned["zero_or_invalid_boundary"].sum()
            ),
            "target_rows": len(target_summary),
            "targets_with_selected_value": int(
                target_summary["proposed_selected_pActivity"].notna().sum()
            ) if not target_summary.empty else 0,
            "selection_status_counts": sel_counts,
            "pdsp_raw_source_audit": pdsp_audit,
            "no_hr_calculated": True,
        }

        (output_dir / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )

        text = [
            "=== POOLED PARENT KETAMINE ACTIVITY CLEANUP V2 COMPLETE ===",
            "",
            f"Input rows: {len(cleaned):,}",
            f"Duplicate independence_key rows: {dup_ind:,}",
            "",
            "SPECIES",
            f"New species resolutions: {summary['new_species_resolutions']:,}",
            f"Human rows: {int(species_after.get('HUMAN', 0)):,}",
            f"Mammalian nonhuman rows: {int(species_after.get('MAMMALIAN_NONHUMAN', 0)):,}",
            f"Non-mammalian rows: {int(species_after.get('NON_MAMMALIAN', 0)):,}",
            f"Still unresolved rows: {int(species_after.get('UNRESOLVED', 0)):,}",
            "",
            "PDSP",
            f"PDSP rows: {summary['pdsp_rows']:,}",
            f"PDSP unresolved before: {pdsp_unresolved_before:,}",
            f"PDSP newly resolved: {summary['pdsp_newly_resolved']:,}",
            f"PDSP unresolved after: {pdsp_unresolved_after:,}",
            "",
            "ACTIVITY LANES",
            f"Measured numerical rows: {len(measured):,}",
            f"Modeled/assigned rows: {len(modeled):,}",
            "",
            "BOUNDED DATA",
            f"Bounded rows retained: {len(bounded):,}",
            f"GT-bound rows: {int(rel_counts.get('GT_BOUND', 0)):,}",
            f"LT-bound rows: {int(rel_counts.get('LT_BOUND', 0)):,}",
            f"Unknown-direction bounded rows: {int(rel_counts.get('BOUNDED_DIRECTION_UNKNOWN', 0)):,}",
            f"Zero/invalid boundaries excluded from numerical selection: {summary['zero_or_invalid_boundaries']:,}",
            "",
            "TARGET SUMMARY",
            f"Targets summarized: {len(target_summary):,}",
            f"Targets with proposed selected numerical value: {summary['targets_with_selected_value']:,}",
            "",
            "SELECTION POLICY",
            "Human priority -> mammalian fallback.",
            "Within selected species: exact measured first; if none, bounded measured.",
            "Endpoint priority: Ki > Kd > IC50 > EC50/AC50 > standardized other potency.",
            "Exact: strongest activity (max pActivity / minimum molar concentration).",
            "Bounded: retain non-zero reported boundary and preserve relation.",
            "  > / >= : largest concentration boundary (tightest lower concentration bound).",
            "  < / <= : smallest concentration boundary (tightest upper concentration bound).",
            "  unknown direction: provisional strongest non-zero boundary, flagged for review.",
            "",
            "NO HR WAS CALCULATED.",
            f"Output folder: {output_dir}",
            "QA: PASS",
        ]
        (output_dir / "SUMMARY.txt").write_text(
            "\n".join(text) + "\n",
            encoding="utf-8",
        )

        # Hash outputs after completion.
        hash_rows = []
        for p in sorted(output_dir.iterdir()):
            if p.is_file() and p.name != "OUTPUT_SHA256SUMS.csv":
                hash_rows.append({
                    "filename": p.name,
                    "bytes": p.stat().st_size,
                    "sha256": sha256(p),
                })
        pd.DataFrame(hash_rows).to_csv(
            output_dir / "OUTPUT_SHA256SUMS.csv",
            index=False,
        )

        log("QA: PASS")
        log("NO HR CALCULATED")
        print()
        print("\n".join(text))
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
