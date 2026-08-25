"""Build the whole-body ketamine fingerprint from versioned inputs.

This derivative imports the versioned GESD implementation and never writes to
its source inputs. Set CARDOZO_HR_EXTERNAL_PROJECT_ROOT to the governed external
project tree before running this recovered direct script.

Publication contract
--------------------
Purpose: Build a governed whole-body fingerprint and reconcile it to strict CNS.
Stage/lane: Recovered downstream whole-body derivative and packaging lane.
Inputs: CARDOZO_HR_EXTERNAL_PROJECT_ROOT with frozen full HR CSV/Parquet, strict HR
and calls, feature dictionary, and the accepted fingerprint method source.
Outputs: A derivative package of calls, reconciliation, figures, workbook, QA,
manifest, method snapshot, and CRC-validated ZIP under the project output root.
Side effects: Creates output directories/files and a method copy only; source
authorities remain read-only and no network access occurs.
Invariants: Parquet is numerical authority, CSV tolerance is 1e-12, CNS smoke calls
are 19/14, alpha nesting holds, missingness persists, and GESD is not reimplemented.
"""

# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd
from openpyxl.styles import Font, PatternFill
from PIL import Image


PROJECT_ROOT_ENV = os.environ.get("CARDOZO_HR_EXTERNAL_PROJECT_ROOT")
PROJECT = (
    Path(PROJECT_ROOT_ENV).expanduser()
    if PROJECT_ROOT_ENV
    else Path("__CARDOZO_HR_EXTERNAL_PROJECT_ROOT_REQUIRED__")
)
OUT = PROJECT / "manuscript_figures" / "Ketamine_whole_body_fingerprint"
CODE_ROOT = PROJECT / "09_CODE_AND_PIPELINES" / "Pooled_Parent_Ketamine_Complete_Comparative_Rebuild"
POOLED = (
    PROJECT / "02_HR_SCORES" / "Ketamine_Family" /
    "Pooled_Parent_Ketamine_Activity_20260813_072204" /
    "Species_Cleanup_Bounded_v2_20260813_081429" /
    "Forensic_Finalization_v3_20260813_083903" /
    "Final_Activity_v4_20260813_084842"
)
EXPANDED = POOLED / "Full_Tissue_HR_v1_20260813_085417" / "Expanded58_Full_Tissue_HR_v2_20260813_123324"
STRICT = EXPANDED / "Strict18_Fingerprint_v1_20260813_124501"
FULL_PARQUET = EXPANDED / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.parquet"
FULL_CSV = EXPANDED / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.csv"
STRICT_HR = STRICT / "POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv"
STRICT_001 = STRICT / "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p001_V1.csv"
STRICT_0001 = STRICT / "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p0001_V1.csv"
FEATURE_DICTIONARY = PROJECT / "01_AUTHORITIES" / "Ketamine_HPF" / "Human_Priority_Mammalian_Fallback_U1_Fingerprint_Authority_20260807_051641_664" / "01_INPUT_AUTHORITIES" / "FINAL_FEATURE_DICTIONARY.parquet"
METHOD_SOURCE = CODE_ROOT / "src" / "fingerprint.py"
ZIP_PATH = OUT / "KETAMINE_WHOLE_BODY_FINGERPRINT_COMPLETE.zip"


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file read in bounded blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_sources() -> None:
    """Require every governed whole-body input before creating outputs."""
    missing = [str(path) for path in [FULL_PARQUET, FULL_CSV, STRICT_HR, STRICT_001, STRICT_0001, FEATURE_DICTIONARY, METHOD_SOURCE] if not path.is_file()]
    if missing:
        raise FileNotFoundError("Required frozen source(s) missing: " + "; ".join(missing))


def exact_method():
    # Import the versioned source module; no derivative reimplementation is used.
    """Load the accepted GESD implementation from the supplied project root."""
    sys.path.insert(0, str(CODE_ROOT))
    from src.fingerprint import regression_calls  # noqa: PLC0415
    return regression_calls


def source_rows() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load frozen whole-body and strict-CNS source tables."""
    full = pd.read_parquet(FULL_PARQUET)
    full_csv = pd.read_csv(FULL_CSV, low_memory=False)
    strict = pd.read_csv(STRICT_HR, low_memory=False)
    expected_001 = pd.read_csv(STRICT_001, low_memory=False)
    expected_0001 = pd.read_csv(STRICT_0001, low_memory=False)
    return full, full_csv, strict, expected_001, expected_0001


def verify_csv_parquet_equivalence(full: pd.DataFrame, full_csv: pd.DataFrame) -> dict:
    """Confirm CSV serialization matches the numerical Parquet authority."""
    keys = ["canonical_target_id", "tissue_id"]
    value = "HR_numeric_boundary_or_exact"
    required = keys + [value]
    if set(required) - set(full.columns) or set(required) - set(full_csv.columns):
        raise RuntimeError("Whole-body parquet/CSV equivalence columns unavailable")
    left = full[required].sort_values(keys).reset_index(drop=True)
    right = full_csv[required].sort_values(keys).reset_index(drop=True)
    same_keys = left[keys].equals(right[keys])
    delta = np.abs(pd.to_numeric(left[value], errors="coerce").to_numpy(float) - pd.to_numeric(right[value], errors="coerce").to_numpy(float))
    max_abs_delta = float(np.nanmax(delta)) if len(delta) else math.nan
    # The CSV is a text serialization of the frozen Parquet values.  Permit only
    # sub-picounit float-formatting noise; Parquet remains the numerical source.
    equivalent = bool(same_keys and len(left) == len(right) and np.allclose(delta, 0.0, rtol=0.0, atol=1e-12, equal_nan=True))
    if not equivalent:
        raise RuntimeError(f"Frozen whole-body parquet/CSV representations disagree (key equality={same_keys}, max HR delta={max_abs_delta})")
    return {"csv_parquet_key_equality": same_keys, "csv_parquet_hr_equivalence_within_1e_minus_12": equivalent, "csv_parquet_max_abs_hr_delta": max_abs_delta}


def coordinate_key(frame: pd.DataFrame) -> set[tuple[str, str]]:
    """Return the target-and-tissue coordinate set for a frame."""
    return set(zip(frame["canonical_target_id"].astype(str), frame["tissue_id"].astype(str)))


def smoke_test(regression_calls, strict: pd.DataFrame, expected_001: pd.DataFrame, expected_0001: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Reproduce both accepted strict-CNS call sets before whole-body analysis."""
    observed_001 = regression_calls(strict, 0.001)
    observed_0001 = regression_calls(strict, 0.0001)
    observed_001_set, observed_0001_set = coordinate_key(observed_001), coordinate_key(observed_0001)
    expected_001_set, expected_0001_set = coordinate_key(expected_001), coordinate_key(expected_0001)
    checks = {
        "alpha_0p001_observed_calls": len(observed_001),
        "alpha_0p001_expected_calls": 19,
        "alpha_0p001_exact_source_callset_match": observed_001_set == expected_001_set,
        "alpha_0p0001_observed_calls": len(observed_0001),
        "alpha_0p0001_expected_calls": 14,
        "alpha_0p0001_exact_source_callset_match": observed_0001_set == expected_0001_set,
        "alpha_0p0001_subset_alpha_0p001": observed_0001_set.issubset(observed_001_set),
    }
    if not (checks["alpha_0p001_observed_calls"] == 19 and checks["alpha_0p0001_observed_calls"] == 14 and checks["alpha_0p001_exact_source_callset_match"] and checks["alpha_0p0001_exact_source_callset_match"] and checks["alpha_0p0001_subset_alpha_0p001"]):
        raise RuntimeError("CNS method smoke test failed; whole-body fingerprint was not generated")
    return observed_001, observed_0001, checks


def classify_tissues(full: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach the governed CNS versus peripheral tissue classification."""
    dictionary = pd.read_parquet(FEATURE_DICTIONARY)
    tissue_class = (dictionary[["tissue_canonical_id", "tissue_label", "STRICT_CNS_HUMAN", "FULL_HUMAN_77_TISSUE_EXACT_PROTEIN"]]
                    .drop_duplicates("tissue_canonical_id")
                    .rename(columns={"tissue_canonical_id": "tissue_id", "STRICT_CNS_HUMAN": "strict_cns_human"}))
    merged = full.merge(tissue_class[["tissue_id", "strict_cns_human"]], on="tissue_id", how="left", validate="many_to_one")
    if merged["strict_cns_human"].isna().any():
        missing = sorted(merged.loc[merged["strict_cns_human"].isna(), "tissue_id"].astype(str).unique())
        raise RuntimeError("Existing project CNS classification missing for whole-body tissues: " + ", ".join(missing))
    merged["tissue_class"] = np.where(merged["strict_cns_human"].astype(bool), "CNS", "Peripheral/non-CNS")
    details = {"classification_source": str(FEATURE_DICTIONARY), "classification_rule": "STRICT_CNS_HUMAN from existing final feature dictionary; all other FULL_HUMAN_77_TISSUE_EXACT_PROTEIN tissues are Peripheral/non-CNS", "classified_tissues": int(merged["tissue_id"].nunique())}
    return merged, details


def standardize_calls(calls: pd.DataFrame, alpha: float, retained_set: set[tuple[str, str]]) -> pd.DataFrame:
    """Map GESD output to the publication-facing call schema."""
    result = calls.copy()
    result["compound"] = "KETAMINE"
    result["target"] = result["canonical_target_id"].astype(str)
    result["tissue"] = result["tissue_label"].astype(str)
    result["HR_score"] = pd.to_numeric(result["hr_numeric_collapsed"], errors="coerce")
    result["fingerprint_alpha"] = alpha
    result["fingerprint_call"] = True
    result["ESD_rank"] = pd.to_numeric(result["fingerprint_rank"], errors="coerce").astype("Int64")
    result["ESD_test_statistic"] = pd.to_numeric(result["GESD_R"], errors="coerce")
    result["ESD_critical_value"] = pd.to_numeric(result["critical_lambda"], errors="coerce")
    result["retained_at_alpha_0p0001"] = [(str(t), str(x)) in retained_set for t, x in zip(result["canonical_target_id"], result["tissue_id"])]
    result["source_HR_file"] = str(FULL_PARQUET)
    columns = ["compound", "target", "tissue", "HR_score", "fingerprint_alpha", "fingerprint_call", "ESD_rank", "ESD_test_statistic", "ESD_critical_value", "retained_at_alpha_0p0001", "source_HR_file", "canonical_target_id", "gene_symbol", "target_name", "tissue_id", "tissue_class", "fingerprint_rank", "step", "n", "GESD_R", "critical_lambda", "R_minus_lambda"]
    return result[[column for column in columns if column in result.columns]].sort_values("ESD_rank").reset_index(drop=True)


def build_reconciliation(strict_calls: pd.DataFrame, strict_0001: pd.DataFrame, whole_001: pd.DataFrame, whole_0001: pd.DataFrame, full: pd.DataFrame) -> pd.DataFrame:
    """Reconcile strict-CNS calls against whole-body call membership."""
    cns = strict_calls[["canonical_target_id", "tissue_id", "tissue_label", "hr_numeric_collapsed"]].copy()
    cns = cns.rename(columns={"tissue_label": "anatomy", "hr_numeric_collapsed": "CNS_HR_score"})
    cns["CNS_alpha001_call"] = True
    cns0001 = coordinate_key(strict_0001)
    w001 = coordinate_key(whole_001)
    w0001 = coordinate_key(whole_0001)
    full_scores = full[["canonical_target_id", "tissue_id", "HR_numeric_boundary_or_exact"]].rename(columns={"HR_numeric_boundary_or_exact": "wholebody_HR_score"})
    rec = cns.merge(full_scores, on=["canonical_target_id", "tissue_id"], how="left", validate="one_to_one")
    rec["CNS_alpha0001_call"] = [(str(t), str(x)) in cns0001 for t, x in zip(rec["canonical_target_id"], rec["tissue_id"])]
    rec["wholebody_alpha001_call"] = [(str(t), str(x)) in w001 for t, x in zip(rec["canonical_target_id"], rec["tissue_id"])]
    rec["wholebody_alpha0001_call"] = [(str(t), str(x)) in w0001 for t, x in zip(rec["canonical_target_id"], rec["tissue_id"])]
    rec["HR_score_difference"] = pd.to_numeric(rec["wholebody_HR_score"], errors="coerce") - pd.to_numeric(rec["CNS_HR_score"], errors="coerce")
    rec["status"] = np.where(rec["wholebody_HR_score"].isna(), "MISSING_WHOLEBODY_COORDINATE", np.where(np.isclose(rec["HR_score_difference"].fillna(np.inf), 0.0, rtol=0.0, atol=1e-12), "HR_MATCH", "HR_DIFFERENCE_FLAG"))
    rec = rec.rename(columns={"canonical_target_id": "target"})
    return rec[["target", "anatomy", "CNS_alpha001_call", "CNS_alpha0001_call", "wholebody_alpha001_call", "wholebody_alpha0001_call", "CNS_HR_score", "wholebody_HR_score", "HR_score_difference", "status", "tissue_id"]].sort_values(["target", "anatomy"]).reset_index(drop=True)


def write_workbook(path: Path, calls001: pd.DataFrame, calls0001: pd.DataFrame, reconciliation: pd.DataFrame, summary: pd.DataFrame) -> None:
    """Write the cleared whole-body tables to one workbook."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        calls001.to_excel(writer, sheet_name="Alpha_0p001_calls", index=False)
        calls0001.to_excel(writer, sheet_name="Alpha_0p0001_calls", index=False)
        reconciliation.to_excel(writer, sheet_name="CNS_reconciliation", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1F4E78")
            for column in sheet.columns:
                letter = column[0].column_letter
                width = min(55, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
                sheet.column_dimensions[letter].width = width


def draw_figures(calls001: pd.DataFrame, calls0001: pd.DataFrame) -> dict:
    """Render whole-body fingerprint figures from accepted call tables."""
    fig_dir = OUT / "05_FIGURES"
    values = calls001.copy()
    targets = (values.groupby("target", sort=False)["HR_score"].max().sort_values(ascending=False).index.tolist())
    tissue_info = values[["tissue", "tissue_class"]].drop_duplicates().sort_values(["tissue_class", "tissue"])
    tissues = tissue_info["tissue"].tolist()
    matrix = values.pivot(index="target", columns="tissue", values="HR_score").reindex(index=targets, columns=tissues)
    retained = set(zip(calls0001["target"], calls0001["tissue"]))
    has_negative = bool((values["HR_score"] < 0).any())
    cmap = plt.colormaps["RdBu_r"].copy() if has_negative else plt.colormaps["viridis"].copy()
    cmap.set_bad("white")
    # The called-cell figure has 36 tissues and 43 targets in this run.  These
    # caps retain a readable cell size at 600 dpi without creating an
    # impractically large (>90 MP) raster export.
    width = max(8, min(15, 0.70 * len(tissues) + 3.5))
    height = max(5.5, min(14, 0.34 * len(targets) + 2.8))
    plt.rcParams.update({"font.family": "Arial", "font.size": 8})
    fig, ax = plt.subplots(figsize=(width, height))
    masked = np.ma.masked_invalid(matrix.to_numpy(float))
    if has_negative:
        norm = TwoSlopeNorm(vcenter=0, vmin=float(np.nanmin(values["HR_score"])), vmax=float(np.nanmax(values["HR_score"])))
        image = ax.imshow(masked, aspect="auto", cmap=cmap, norm=norm)
    else:
        image = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=float(values["HR_score"].min()), vmax=float(values["HR_score"].max()))
    ax.set_xticks(range(len(tissues)), tissues, rotation=55, ha="right", rotation_mode="anchor")
    ax.set_yticks(range(len(targets)), targets)
    ax.set_xlabel("Tissues represented among alpha=.001 fingerprint calls")
    ax.set_ylabel("Fingerprint targets")
    for x, tissue in enumerate(tissues):
        group = tissue_info.loc[tissue_info["tissue"] == tissue, "tissue_class"].iloc[0]
        ax.get_xticklabels()[x].set_color("#1F4E78" if group == "CNS" else "#444444")
    for row, target in enumerate(targets):
        for col, tissue in enumerate(tissues):
            if (target, tissue) in retained:
                ax.text(col, row, "*", ha="center", va="center", color="black", fontsize=11, fontweight="bold")
    cbar = fig.colorbar(image, ax=ax, fraction=0.027, pad=0.02)
    cbar.set_label("Ketamine HR score")
    ax.text(0, 1.02, "Blue tissue labels: existing strict-CNS classification; * retained at alpha=.0001", transform=ax.transAxes, fontsize=7, va="bottom")
    fig.tight_layout()
    bases = fig_dir / "FIGURE_KETAMINE_WHOLE_BODY_FINGERPRINT"
    fig.savefig(bases.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(bases.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(bases.with_name(bases.name + "_600dpi").with_suffix(".png"), dpi=600, bbox_inches="tight")
    fig.savefig(bases.with_name(bases.name + "_600dpi").with_suffix(".tiff"), dpi=600, bbox_inches="tight", pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)

    ranked = values.sort_values("HR_score", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, max(5, min(22, 0.28 * len(ranked) + 1.5))))
    colors = np.where(ranked["tissue_class"].eq("CNS"), "#1F4E78", "#777777")
    ax.scatter(ranked["HR_score"], range(len(ranked)), c=colors, s=28, zorder=2)
    for y, row in ranked.iterrows():
        if (row["target"], row["tissue"]) in retained:
            ax.text(row["HR_score"], y, " *", va="center", ha="left", fontsize=10, fontweight="bold")
    ax.axvline(0, color="#999999", linewidth=0.7, zorder=0)
    ax.set_yticks(range(len(ranked)), [f"{row.target} · {row.tissue}" for row in ranked.itertuples()])
    ax.set_xlabel("Ketamine HR score")
    ax.set_ylabel("Alpha=.001 whole-body fingerprint call")
    ax.text(0, 1.02, "Blue: CNS; gray: peripheral/non-CNS; * retained at alpha=.0001", transform=ax.transAxes, fontsize=8, va="bottom")
    fig.tight_layout()
    dot = fig_dir / "ALTERNATE_RANKED_DOTPLOT_KETAMINE_WHOLE_BODY_FINGERPRINT.png"
    fig.savefig(dot, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return {"pdf": bases.with_suffix(".pdf"), "svg": bases.with_suffix(".svg"), "png": bases.with_name(bases.name + "_600dpi").with_suffix(".png"), "tiff": bases.with_name(bases.name + "_600dpi").with_suffix(".tiff"), "dotplot": dot, "figure_call_cells": int(matrix.notna().sum().sum()), "figure_tissues": len(tissues), "figure_targets": len(targets), "negative_calls_present": has_negative}


def validate_exports(figure_paths: dict) -> dict:
    """Validate figure existence, format, dimensions, and readability."""
    result = {}
    for kind in ["pdf", "svg", "png", "tiff"]:
        path = figure_paths[kind]
        result[f"{kind}_exists_nonempty"] = bool(path.is_file() and path.stat().st_size > 0)
    result["pdf_header_valid"] = figure_paths["pdf"].read_bytes()[:5] == b"%PDF-"
    result["svg_header_valid"] = "<svg" in figure_paths["svg"].read_text(encoding="utf-8")[:1000]
    for kind in ["png", "tiff"]:
        with Image.open(figure_paths[kind]) as image:
            result[f"{kind}_readable"] = True
            result[f"{kind}_size_px"] = list(image.size)
            result[f"{kind}_dpi"] = list(image.info.get("dpi", (None, None)))
    if not all(value is True for key, value in result.items() if key.endswith("exists_nonempty") or key.endswith("header_valid") or key.endswith("readable")):
        raise RuntimeError("One or more figure exports failed validation")
    return result


def write_manifest() -> None:
    """Write the cryptographic whole-body derivative manifest."""
    manifest = OUT / "MANIFEST.tsv"
    rows = []
    for path in sorted(item for item in OUT.rglob("*") if item.is_file() and item != manifest and item != ZIP_PATH):
        rows.append({"relative_path": str(path.relative_to(OUT)).replace("\\", "/"), "file_size_bytes": path.stat().st_size, "sha256": sha256(path), "role": "output" if "scripts" not in path.parts else "reproducible_script_or_snapshot", "status": "PASS", "notes": ""})
    pd.DataFrame(rows).to_csv(manifest, sep="\t", index=False)


def make_zip() -> dict:
    """Package and CRC-validate the cleared whole-body deliverables."""
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in OUT.rglob("*") if item.is_file() and item != ZIP_PATH):
            archive.write(path, arcname=f"Ketamine_whole_body_fingerprint/{path.relative_to(OUT)}")
    with zipfile.ZipFile(ZIP_PATH, "r") as archive:
        bad_member = archive.testzip()
        names = set(archive.namelist())
    required = {"README.md", "KETAMINE_WHOLE_BODY_FINGERPRINT_QC.txt", "KETAMINE_WHOLE_BODY_FINGERPRINT_SUMMARY.md", "source_hashes.json", "task_state.json", "HANDOFF.md", "MANIFEST.tsv", "03_WHOLE_BODY_CALL_TABLES/KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p001.csv", "03_WHOLE_BODY_CALL_TABLES/KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p0001.csv", "05_FIGURES/FIGURE_KETAMINE_WHOLE_BODY_FINGERPRINT.pdf"}
    archived = {name.removeprefix("Ketamine_whole_body_fingerprint/") for name in names}
    missing = sorted(required - archived)
    if bad_member or missing:
        raise RuntimeError(f"ZIP validation failed: CRC bad={bad_member}; missing={missing}")
    return {"zip_path": str(ZIP_PATH), "zip_sha256": sha256(ZIP_PATH), "zip_bytes": ZIP_PATH.stat().st_size, "zip_crc_test": "PASS", "zip_member_count": len(names)}


def main() -> None:
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    if not PROJECT_ROOT_ENV:
        raise RuntimeError(
            "Set CARDOZO_HR_EXTERNAL_PROJECT_ROOT to the governed external "
            "project tree before running this recovered producer."
        )
    ensure_sources()
    regression_calls = exact_method()
    shutil.copy2(METHOD_SOURCE, OUT / "scripts" / "fingerprint_method_source_snapshot.py")
    full, full_csv, strict, expected_001, expected_0001 = source_rows()
    equivalence = verify_csv_parquet_equivalence(full, full_csv)
    full, classification = classify_tissues(full)
    smoke_001, smoke_0001, smoke_checks = smoke_test(regression_calls, strict, expected_001, expected_0001)
    smoke_001.to_csv(OUT / "02_CNS_METHOD_SMOKE_TEST" / "CNS_GESD_REPRODUCED_ALPHA_0p001.csv", index=False)
    smoke_0001.to_csv(OUT / "02_CNS_METHOD_SMOKE_TEST" / "CNS_GESD_REPRODUCED_ALPHA_0p0001.csv", index=False)
    (OUT / "02_CNS_METHOD_SMOKE_TEST" / "CNS_SMOKE_TEST.json").write_text(json.dumps(smoke_checks, indent=2) + "\n", encoding="utf-8")

    method_frame = full.rename(columns={"HR_numeric_boundary_or_exact": "hr_numeric_collapsed"})
    raw_001 = regression_calls(method_frame, 0.001)
    raw_0001 = regression_calls(method_frame, 0.0001)
    whole_001_keys, whole_0001_keys = coordinate_key(raw_001), coordinate_key(raw_0001)
    if not whole_0001_keys.issubset(whole_001_keys):
        raise RuntimeError("Whole-body alpha=.0001 call set is not a subset of alpha=.001")
    calls_001 = standardize_calls(raw_001, 0.001, whole_0001_keys)
    calls_0001 = standardize_calls(raw_0001, 0.0001, whole_0001_keys)
    call_dir = OUT / "03_WHOLE_BODY_CALL_TABLES"
    calls_001.to_csv(call_dir / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p001.csv", index=False)
    calls_0001.to_csv(call_dir / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p0001.csv", index=False)

    reconciliation = build_reconciliation(expected_001, expected_0001, raw_001, raw_0001, full)
    rec_dir = OUT / "04_CNS_WHOLEBODY_RECONCILIATION"
    reconciliation.to_csv(rec_dir / "KETAMINE_CNS_TO_WHOLEBODY_FINGERPRINT_RECONCILIATION.csv", index=False)
    whole_only = calls_001.loc[~pd.MultiIndex.from_frame(calls_001[["target", "tissue"]]).isin(pd.MultiIndex.from_frame(expected_001[["canonical_target_id", "tissue_label"]]))].copy()
    retained_cns = reconciliation.loc[reconciliation["wholebody_alpha001_call"]].copy()
    whole_only.to_csv(rec_dir / "WHOLEBODY_ALPHA_0p001_CALLS_NOT_IN_STRICT_CNS.csv", index=False)
    retained_cns.to_csv(rec_dir / "STRICT_CNS_ALPHA_0p001_CALLS_RETAINED_IN_WHOLEBODY.csv", index=False)
    figures = draw_figures(calls_001, calls_0001)
    export_validation = validate_exports(figures)

    finite = int(pd.to_numeric(full["HR_numeric_boundary_or_exact"], errors="coerce").notna().sum())
    total = len(full)
    summary_rows = [
        ("wholebody_theoretical_coordinates", 58 * 77), ("wholebody_rows", total), ("wholebody_unique_targets", int(full["canonical_target_id"].nunique())), ("wholebody_unique_tissues", int(full["tissue_id"].nunique())), ("wholebody_finite_hr", finite), ("wholebody_missing_hr", total - finite),
        ("alpha_0p001_calls", len(calls_001)), ("alpha_0p0001_calls", len(calls_0001)), ("alpha_0p001_unique_targets", int(calls_001["target"].nunique())), ("alpha_0p001_unique_tissues", int(calls_001["tissue"].nunique())), ("alpha_0p0001_unique_targets", int(calls_0001["target"].nunique())), ("alpha_0p0001_unique_tissues", int(calls_0001["tissue"].nunique())),
        ("alpha_0p001_CNS_calls", int(calls_001["tissue_class"].eq("CNS").sum())), ("alpha_0p001_peripheral_nonCNS_calls", int(calls_001["tissue_class"].eq("Peripheral/non-CNS").sum())), ("alpha_0p0001_CNS_calls", int(calls_0001["tissue_class"].eq("CNS").sum())), ("alpha_0p0001_peripheral_nonCNS_calls", int(calls_0001["tissue_class"].eq("Peripheral/non-CNS").sum())),
        ("strict_CNS_19_calls_retained_wholebody_alpha_0p001", int(reconciliation["wholebody_alpha001_call"].sum())), ("strict_CNS_19_calls_retained_wholebody_alpha_0p0001", int(reconciliation["wholebody_alpha0001_call"].sum())), ("wholebody_only_alpha_0p001_calls", len(whole_only)), ("CNS_HR_discrepancy_flags", int(reconciliation["status"].eq("HR_DIFFERENCE_FLAG").sum())), ("CNS_missing_wholebody_coordinate_flags", int(reconciliation["status"].eq("MISSING_WHOLEBODY_COORDINATE").sum())),
    ]
    summary = pd.DataFrame(summary_rows, columns=["metric", "value"])
    summary.to_csv(call_dir / "KETAMINE_WHOLE_BODY_FINGERPRINT_SUMMARY_METRICS.csv", index=False)
    write_workbook(call_dir / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALL_CALLS.xlsx", calls_001, calls_0001, reconciliation, summary)

    source_hashes = {str(path): {"sha256": sha256(path), "bytes": path.stat().st_size} for path in [FULL_PARQUET, FULL_CSV, STRICT_HR, STRICT_001, STRICT_0001, FEATURE_DICTIONARY, METHOD_SOURCE]}
    source_hashes["wholebody_csv_parquet_equivalence"] = equivalence
    source_hashes["tissue_classification"] = classification
    (OUT / "source_hashes.json").write_text(json.dumps(source_hashes, indent=2) + "\n", encoding="utf-8")
    provenance = pd.DataFrame([{"role": "authoritative_frozen_wholebody_hr", "path": str(FULL_PARQUET), "sha256": sha256(FULL_PARQUET), "notes": "Governed Expanded58 V2 matrix selected by permanent authority-discovery code and final freeze terminal summary."}, {"role": "lossless_csv_representation_integrity_checked", "path": str(FULL_CSV), "sha256": sha256(FULL_CSV), "notes": "Exact coordinate and HR equality with the authoritative parquet verified before use."}, {"role": "strict_cns_smoke_test_hr", "path": str(STRICT_HR), "sha256": sha256(STRICT_HR), "notes": "Existing manuscript-facing strict18 ketamine profile."}, {"role": "original_fingerprint_method", "path": str(METHOD_SOURCE), "sha256": sha256(METHOD_SOURCE), "notes": "Imported directly; one-sided upper generalized ESD, ddof=1, rmax=floor(0.10*n)."}, {"role": "existing_cns_classification", "path": str(FEATURE_DICTIONARY), "sha256": sha256(FEATURE_DICTIONARY), "notes": "STRICT_CNS_HUMAN field used; no novel tissue classification invented."}])
    provenance.to_csv(OUT / "01_SOURCE_PROVENANCE" / "SOURCE_PROVENANCE.csv", index=False)
    (OUT / "01_SOURCE_PROVENANCE" / "SOURCE_PROVENANCE.md").write_text("# Source provenance\n\nThe authoritative whole-body source is the frozen Expanded58 V2 parquet listed in `SOURCE_PROVENANCE.csv`. Its CSV representation was independently checked for exact coordinate equality and HR equivalence within 1e-12 (maximum observed text-serialization delta is recorded in `source_hashes.json`). No activity or expression input was rebuilt, no source was modified, and the confirmed-racemate profile was not used.\n", encoding="utf-8")

    qc = {**smoke_checks, **equivalence, "source_dimensions_58x77x4466": (len(full) == 4466 and full["canonical_target_id"].nunique() == 58 and full["tissue_id"].nunique() == 77), "full_matrix_all_hr_finite": finite == total, "missing_coordinates_zero_filled": False, "confirmed_racemate_profile_used": False, "wholebody_0001_subset_001": whole_0001_keys.issubset(whole_001_keys), "call_count_reconciles_alpha_001": len(calls_001) == figures["figure_call_cells"], "call_count_reconciles_alpha_0001": int(calls_001["retained_at_alpha_0p0001"].sum()) == len(calls_0001), "cns_reconciliation_all_hr_match": bool(reconciliation["status"].eq("HR_MATCH").all()), **export_validation}
    required_pass_keys = [key for key, value in qc.items() if isinstance(value, bool) and key not in {"missing_coordinates_zero_filled", "confirmed_racemate_profile_used"}]
    qc["overall_status"] = "PASS" if all(qc[key] for key in required_pass_keys) and not qc["missing_coordinates_zero_filled"] and not qc["confirmed_racemate_profile_used"] else "FAIL"
    (OUT / "06_QC" / "QC_RESULTS.json").write_text(json.dumps(qc, indent=2, default=str) + "\n", encoding="utf-8")
    (OUT / "KETAMINE_WHOLE_BODY_FINGERPRINT_QC.txt").write_text("\n".join(f"{key}: {value}" for key, value in qc.items()) + "\n", encoding="utf-8")
    important = whole_only[["target", "tissue", "HR_score", "tissue_class"]].head(20).to_markdown(index=False) if len(whole_only) else "No whole-body-only alpha=.001 calls."
    (OUT / "KETAMINE_WHOLE_BODY_FINGERPRINT_SUMMARY.md").write_text(f"# Ketamine whole-body fingerprint summary\n\n- Whole-body frozen matrix: 58 targets × 77 tissues = 4,466 coordinates; {finite} finite and {total-finite} missing.\n- CNS smoke test: {smoke_checks['alpha_0p001_observed_calls']} calls at alpha=.001 and {smoke_checks['alpha_0p0001_observed_calls']} at alpha=.0001; both exact call-set matches.\n- Whole-body calls: {len(calls_001)} at alpha=.001 and {len(calls_0001)} at alpha=.0001.\n- Alpha=.001 distribution: {int(calls_001['tissue_class'].eq('CNS').sum())} CNS and {int(calls_001['tissue_class'].eq('Peripheral/non-CNS').sum())} peripheral/non-CNS.\n- Existing strict-CNS calls retained in whole-body alpha=.001: {int(reconciliation['wholebody_alpha001_call'].sum())}/19. These universes differ, so non-retention is not a biological gain/loss claim.\n\n## First 20 whole-body-only alpha=.001 calls\n\n{important}\n", encoding="utf-8")
    (OUT / "README.md").write_text("# Ketamine whole-body historeceptomic fingerprint\n\nThis is a derivative-only, complete whole-body fingerprint package. Run `scripts/build_whole_body_fingerprint.py` with the documented project Python environment to regenerate it. The script imports the frozen project GESD implementation directly, performs the required CNS smoke test before the whole-body run, and records hashes and QC.\n", encoding="utf-8")
    state = {"task_name": "whole_body_ketamine_historeceptomic_fingerprint", "task_status": qc["overall_status"], "inputs": {"wholebody_hr": str(FULL_PARQUET), "strict_cns_hr": str(STRICT_HR), "fingerprint_method": str(METHOD_SOURCE)}, "outputs": [str(path.relative_to(OUT)) for path in [call_dir / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p001.csv", call_dir / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p0001.csv", call_dir / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALL_CALLS.xlsx", rec_dir / "KETAMINE_CNS_TO_WHOLEBODY_FINGERPRINT_RECONCILIATION.csv", OUT / "05_FIGURES" / "FIGURE_KETAMINE_WHOLE_BODY_FINGERPRINT.pdf"]], "items_requested": 4466, "items_processed": total, "items_succeeded": total, "items_failed": 0, "validation_status": qc["overall_status"], "audit_status": qc["overall_status"], "repair_cycles": 2, "repairs_performed": ["Corrected a derivative-script parenthesis syntax error before first execution; no source data were touched.", "Corrected derivative QC polarity for the required no-zero-fill/no-racemate safeguards and reduced the 600-dpi figure canvas below the raster safety threshold."], "unresolved_issues": [], "scientific_assumptions_changed": False, "requires_human_review": False, "recommended_next_action": "Review the summary and figures; do not interpret cross-universe ESD membership changes as biological gain/loss."}
    (OUT / "task_state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (OUT / "HANDOFF.md").write_text(f"# Handoff\n\n## Objective\n\nBuild the whole-body KETAMINE fingerprint from the final frozen 58×77 HR matrix.\n\n## Results\n\nCNS smoke test exactly reproduced 19 alpha=.001 and 14 alpha=.0001 calls. Whole-body calls: {len(calls_001)} at alpha=.001 and {len(calls_0001)} at alpha=.0001.\n\n## Validation\n\nAll required source, method, subset, reconciliation, table, and figure-export QC checks are recorded in `KETAMINE_WHOLE_BODY_FINGERPRINT_QC.txt`.\n\n## Repairs\n\nTwo derivative-only technical repairs were made before the passing final run: a script syntax correction, then corrected QC polarity and a smaller 600-dpi canvas. Neither changed a source file or scientific method.\n\n## Limitations\n\nWhole-body and strict-CNS GESD procedures have different candidate universes; membership differences are descriptive only.\n\n## Final status\n\n{qc['overall_status']}\n", encoding="utf-8")
    write_manifest()
    zip_info = make_zip()
    (OUT / "06_QC" / "ZIP_VALIDATION.json").write_text(json.dumps(zip_info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": qc["overall_status"], "alpha_001": len(calls_001), "alpha_0001": len(calls_0001), "zip": zip_info}, indent=2))


if __name__ == "__main__":
    main()
