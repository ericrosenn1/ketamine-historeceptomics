#!/usr/bin/env python3
r"""
POOLED PARENT KETAMINE — STRICT18 CNS FINGERPRINT v1
====================================================

PURPOSE
-------
Generate the strict-CNS sparse historeceptomic fingerprint from the completed
Expanded58 full-tissue pooled-parent-ketamine HR profile.

FINGERPRINT INPUT INVARIANT
-----------------------------
The upstream activity pipeline has already collapsed censored/bounded activity to
a numerical value according to the established rule. Therefore this fingerprint
step DOES NOT distinguish exact versus bounded activity.

For statistical fingerprinting, every represented HR coordinate enters as one
numeric HR score. No stratification, weighting, exclusion, or annotation based on
exact/bounded status is used.

STATISTICAL UNIVERSE
--------------------
Use the current ketamine-project strict-CNS analysis universe:

18 human CNS tissues:
    Whole brain
    Pons
    Amygdala
    Subthalamic nucleus
    Cerebellum peduncles
    Globus pallidus
    Medulla oblongata
    Prefrontal Cortex
    Occipital Lobe
    Hypothalamus
    Spinal cord
    Cerebellum
    Caudate nucleus
    Cingulate Cortex
    Parietal Lobe
    Temporal Lobe
    Thalamus
    Olfactory Bulb

Expected represented universe:
    58 targets x 18 tissues = 1,044 finite HR coordinates

FINGERPRINT METHOD
------------------
For the 1,044 finite numeric HR scores:

    one-sided upper-tail Rosner generalized ESD (GESD)
    sample SD ddof = 1
    rmax = floor(0.10 * n_finite)

Run:
    alpha = 0.001   PRIMARY fingerprint
    alpha = 0.0001  STRICT sensitivity fingerprint

The final call set is the largest valid prefix of iteratively removed upper-tail
candidates through the last step satisfying R > critical lambda.

No fixed score cutoff is imposed.
No calls are forced.
Negative and low positive HR scores remain in the background distribution.

QA
--
A second independent implementation of one-sided upper-tail GESD must agree on:
    selected feature IDs
    step order
    candidate scores
    R statistics
    critical lambdas
within numerical tolerance.

NO DOWNSTREAM MULTIVARIATE ANALYSIS
-----------------------------------
This script does NOT run:
    PCA
    PCoA
    clustering
    external-drug comparisons
    phenotype mapping
    manuscript edits

OUTPUT
------
A timestamped folder inside the Expanded58 HR-v2 folder:

    Strict18_Fingerprint_v1_YYYYMMDD_HHMMSS

Main outputs:
    POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv
    POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p001_V1.csv
    POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p0001_V1.csv
    POOLED_PARENT_KETAMINE_FINGERPRINT_COMBINED_V1.csv
    GESD_STEPS_ALPHA_0p001_V1.csv
    GESD_STEPS_ALPHA_0p0001_V1.csv
    STRICT18_NUMERIC_HR_MATRIX_V1.csv
    FINGERPRINT_MATRIX_ALPHA_0p001_V1.csv
    FINGERPRINT_MATRIX_ALPHA_0p0001_V1.csv
    fingerprint_alpha_0p001_heatmap.png
    fingerprint_alpha_0p0001_heatmap.png
    gesd_diagnostic_alpha_0p001.png
    gesd_diagnostic_alpha_0p0001.png
    SUMMARY.txt
    SUMMARY.json
    RUN.log
    OUTPUT_SHA256SUMS.csv

Publication contract
--------------------
Purpose: Derive both governed strict-CNS pooled-parent GESD fingerprints.
Stage/lane: Recovered Strict18 fingerprint v1, after Expanded58 HR.
Inputs: Explicit Final Activity v4 and Expanded58 directories containing the long HR.
Outputs: A new timestamped Strict18 directory with numeric inputs, call/step tables,
matrices, figures, summaries, hashes, and run log.
Side effects: Writes derivative fingerprint files only; it does not edit HR inputs
or run downstream multivariate/comparator analyses.
Invariants: The 58-by-18 finite universe, one-sided upper GESD, ddof=1, rmax=10%,
alphas 0.001/0.0001, deterministic ties, and no forced calls remain fixed.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = None
V4_DIR = None
HR1_DIR = None
DEFAULT_EXPANDED58_DIR = None

MAIN_HR_FILENAME = "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.csv"

STRICT18 = [
    "Whole brain",
    "Pons",
    "Amygdala",
    "Subthalamic nucleus",
    "Cerebellum peduncles",
    "Globus pallidus",
    "Medulla oblongata",
    "Prefrontal Cortex",
    "Occipital Lobe",
    "Hypothalamus",
    "Spinal cord",
    "Cerebellum",
    "Caudate nucleus",
    "Cingulate Cortex",
    "Parietal Lobe",
    "Temporal Lobe",
    "Thalamus",
    "Olfactory Bulb",
]

EXPECTED_TARGETS = 58
EXPECTED_TISSUES = 18
EXPECTED_ROWS = EXPECTED_TARGETS * EXPECTED_TISSUES  # 1044
QA_TOL = 1e-10


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


def norm_tissue(v) -> str:
    """Normalize a tissue label for exact strict-CNS matching."""
    return "".join(ch.lower() for ch in s(v) if ch.isalnum())


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file read in bounded blocks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


@dataclass
class GESDResult:
    """Store call identifiers, ordered GESD steps, and the retained outlier count."""
    call_indices: List[int]
    steps: pd.DataFrame


def critical_lambda_one_sided(n_i: int, alpha: float) -> float:
    """Compute the one-sided Rosner critical value for one GESD step."""
    p = 1.0 - alpha / n_i
    tcrit = float(student_t.ppf(p, df=n_i - 2))
    lam = ((n_i - 1) * tcrit) / math.sqrt(
        n_i * (n_i - 2 + tcrit * tcrit)
    )
    return float(lam)


def choose_max_with_tie(values: np.ndarray, feature_ids: np.ndarray) -> int:
    """Choose the maximal residual with deterministic feature-ID tie breaking."""
    vmax = np.max(values)
    positions = np.flatnonzero(values == vmax)
    if len(positions) == 1:
        return int(positions[0])
    tied_ids = feature_ids[positions].astype(str)
    order = np.argsort(tied_ids, kind="stable")
    return int(positions[int(order[0])])


def gesd_upper_primary(
    values: np.ndarray,
    feature_ids: np.ndarray,
    alpha: float,
    rmax: int,
) -> GESDResult:
    """Run the primary upper-tail generalized ESD implementation."""
    x = np.asarray(values, dtype=float)
    ids = np.asarray(feature_ids, dtype=object)

    if x.ndim != 1 or len(x) != len(ids):
        raise ValueError("GESD input shape mismatch")
    if not np.all(np.isfinite(x)):
        raise ValueError("GESD requires finite numeric values")

    n = len(x)
    if n < 8:
        return GESDResult([], pd.DataFrame())

    rmax = min(int(rmax), n - 3)
    if rmax < 1:
        return GESDResult([], pd.DataFrame())

    remaining = np.arange(n, dtype=int)
    removed = []
    rows = []

    for step in range(1, rmax + 1):
        vals = x[remaining]
        fids = ids[remaining]
        n_i = len(vals)

        mean = float(np.mean(vals))
        sd = float(np.std(vals, ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            break

        local = choose_max_with_tie(vals, fids)
        original_index = int(remaining[local])
        candidate = float(vals[local])
        R = float((candidate - mean) / sd)
        lam = critical_lambda_one_sided(n_i, alpha)

        rows.append(
            {
                "step": step,
                "n_remaining": n_i,
                "candidate_original_index": original_index,
                "candidate_feature_id": str(ids[original_index]),
                "candidate_hr": candidate,
                "mean": mean,
                "sd_ddof1": sd,
                "R": R,
                "critical_lambda": lam,
                "R_minus_lambda": R - lam,
                "R_gt_lambda": bool(R > lam),
                "alpha": alpha,
            }
        )

        removed.append(original_index)
        remaining = np.delete(remaining, local)

    steps = pd.DataFrame(rows)
    if steps.empty:
        return GESDResult([], steps)

    sig = np.flatnonzero(steps["R_gt_lambda"].to_numpy(dtype=bool))
    k = int(sig.max() + 1) if len(sig) else 0
    return GESDResult(removed[:k], steps)


def gesd_upper_independent(
    values: np.ndarray,
    feature_ids: np.ndarray,
    alpha: float,
    rmax: int,
) -> GESDResult:
    """
    Independent list/dictionary implementation for QA.
    """
    records = [
        {
            "idx": i,
            "id": str(feature_ids[i]),
            "value": float(values[i]),
        }
        for i in range(len(values))
    ]

    removed = []
    rows = []

    for step in range(1, min(rmax, len(records) - 3) + 1):
        vals = np.array([r["value"] for r in records], dtype=float)
        n_i = len(vals)
        mean = float(vals.mean())
        sd = float(vals.std(ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            break

        maxval = max(r["value"] for r in records)
        tied = [r for r in records if r["value"] == maxval]
        chosen = sorted(tied, key=lambda r: r["id"])[0]

        R = float((chosen["value"] - mean) / sd)

        p = 1.0 - alpha / n_i
        tc = float(student_t.ppf(p, n_i - 2))
        lam = float(
            ((n_i - 1) * tc)
            / math.sqrt(n_i * (n_i - 2 + tc * tc))
        )

        rows.append(
            {
                "step": step,
                "n_remaining": n_i,
                "candidate_original_index": int(chosen["idx"]),
                "candidate_feature_id": chosen["id"],
                "candidate_hr": float(chosen["value"]),
                "mean": mean,
                "sd_ddof1": sd,
                "R": R,
                "critical_lambda": lam,
                "R_minus_lambda": R - lam,
                "R_gt_lambda": bool(R > lam),
                "alpha": alpha,
            }
        )
        removed.append(int(chosen["idx"]))
        records = [r for r in records if r["idx"] != chosen["idx"]]

    steps = pd.DataFrame(rows)
    if steps.empty:
        return GESDResult([], steps)

    sig_steps = [
        i for i, row in steps.iterrows()
        if bool(row["R_gt_lambda"])
    ]
    k = max(sig_steps) + 1 if sig_steps else 0
    return GESDResult(removed[:k], steps)


def qa_compare(a: GESDResult, b: GESDResult, alpha: float):
    """Compare both GESD implementations within fixed numerical tolerance."""
    if a.call_indices != b.call_indices:
        raise RuntimeError(
            f"Independent GESD call-set disagreement at alpha={alpha}"
        )

    if len(a.steps) != len(b.steps):
        raise RuntimeError(
            f"Independent GESD step-count disagreement at alpha={alpha}"
        )

    if len(a.steps):
        for c in [
            "candidate_original_index",
            "candidate_feature_id",
            "step",
            "n_remaining",
        ]:
            if not a.steps[c].astype(str).equals(b.steps[c].astype(str)):
                raise RuntimeError(
                    f"Independent GESD discrete-step disagreement for {c} "
                    f"at alpha={alpha}"
                )

        for c in [
            "candidate_hr",
            "mean",
            "sd_ddof1",
            "R",
            "critical_lambda",
            "R_minus_lambda",
        ]:
            delta = np.max(
                np.abs(
                    pd.to_numeric(a.steps[c], errors="coerce").to_numpy()
                    - pd.to_numeric(b.steps[c], errors="coerce").to_numpy()
                )
            )
            if delta > QA_TOL:
                raise RuntimeError(
                    f"Independent GESD numerical disagreement for {c}: "
                    f"max delta={delta} at alpha={alpha}"
                )


def locate_expanded58(v4_dir: Path, preferred: Path) -> Path:
    """Resolve the explicit or uniquely timestamped Expanded58 input directory."""
    if preferred.is_dir():
        return preferred

    hr1 = v4_dir / "Full_Tissue_HR_v1_20260813_085417"
    hits = [
        p for p in hr1.glob("Expanded58_Full_Tissue_HR_v2_*")
        if p.is_dir()
    ]
    if not hits:
        raise FileNotFoundError(
            f"Could not locate Expanded58_Full_Tissue_HR_v2 under {hr1}"
        )
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0]


def make_fingerprint_table(
    strict: pd.DataFrame,
    result: GESDResult,
    alpha: float,
) -> pd.DataFrame:
    """Build the governed fingerprint call table from accepted GESD steps."""
    if not result.call_indices:
        return pd.DataFrame(
            columns=[
                "fingerprint_rank",
                "canonical_target_id",
                "gene_symbol",
                "target_name",
                "tissue_id",
                "tissue_label",
                "hr_numeric_collapsed",
                "expression_z",
                "GESD_R",
                "critical_lambda",
                "R_minus_lambda",
                "alpha",
            ]
        )

    step_lookup = (
        result.steps
        .set_index("candidate_original_index")
        .to_dict("index")
    )

    rows = []
    for rank, idx in enumerate(result.call_indices, start=1):
        r = strict.iloc[idx]
        st = step_lookup[idx]
        rows.append(
            {
                "fingerprint_rank": rank,
                "canonical_target_id": s(r["canonical_target_id"]),
                "gene_symbol": s(r["gene_symbol"]),
                "target_name": s(r.get("target_name")),
                "tissue_id": s(r["tissue_id"]),
                "tissue_label": s(r["tissue_label"]),
                "feature_id": s(r["feature_id"]),
                "hr_numeric_collapsed": float(r["hr_numeric_collapsed"]),
                "expression_z": float(r["expression_z"]),
                "GESD_step": int(st["step"]),
                "GESD_R": float(st["R"]),
                "critical_lambda": float(st["critical_lambda"]),
                "R_minus_lambda": float(st["R_minus_lambda"]),
                "alpha": alpha,
            }
        )
    return pd.DataFrame(rows)


def build_matrix(
    strict: pd.DataFrame,
    value_col: str,
) -> pd.DataFrame:
    """Pivot strict-CNS HR coordinates into a stable target-by-tissue matrix."""
    x = strict.pivot(
        index=["canonical_target_id", "gene_symbol"],
        columns="tissue_display_order",
        values=value_col,
    )
    x = x.reindex(columns=STRICT18)
    x = x.reset_index()
    x.columns.name = None
    return x


def sparse_matrix(strict: pd.DataFrame, calls: pd.DataFrame) -> pd.DataFrame:
    """Build a sparse matrix containing only GESD call coordinates."""
    d = strict.copy()
    called = set(calls["feature_id"].astype(str)) if len(calls) else set()
    d["fingerprint_hr"] = np.where(
        d["feature_id"].astype(str).isin(called),
        d["hr_numeric_collapsed"],
        np.nan,
    )
    return build_matrix(d, "fingerprint_hr")


def plot_sparse_heatmap(
    strict: pd.DataFrame,
    calls: pd.DataFrame,
    title: str,
    output: Path,
):
    """Render a sparse fingerprint heatmap from the call matrix."""
    targets = (
        strict[["canonical_target_id", "gene_symbol"]]
        .drop_duplicates()
        .sort_values(["gene_symbol", "canonical_target_id"])
        .reset_index(drop=True)
    )
    target_keys = targets["canonical_target_id"].astype(str).tolist()
    target_labels = targets["gene_symbol"].astype(str).tolist()

    row_index = {k: i for i, k in enumerate(target_keys)}
    col_index = {t: j for j, t in enumerate(STRICT18)}

    arr = np.full((len(target_keys), len(STRICT18)), np.nan)
    for _, r in calls.iterrows():
        i = row_index.get(str(r["canonical_target_id"]))
        j = col_index.get(str(r["tissue_label"]))
        if i is not None and j is not None:
            arr[i, j] = float(r["hr_numeric_collapsed"])

    finite = arr[np.isfinite(arr)]
    vmax = float(np.max(np.abs(finite))) if len(finite) else 1.0
    vmin = -vmax

    # Only show rows with calls for a compact fingerprint figure.
    called_rows = np.flatnonzero(np.isfinite(arr).any(axis=1))
    if len(called_rows):
        arr_show = arr[called_rows]
        labels_show = [target_labels[i] for i in called_rows]
    else:
        arr_show = np.full((1, len(STRICT18)), np.nan)
        labels_show = ["No calls"]

    fig_h = max(4, 0.45 * len(labels_show) + 2)
    fig, ax = plt.subplots(figsize=(14, fig_h))
    masked = np.ma.masked_invalid(arr_show)
    im = ax.imshow(
        masked,
        aspect="auto",
        interpolation="nearest",
        cmap="coolwarm",
        vmin=vmin,
        vmax=vmax,
    )
    ax.set_xticks(np.arange(len(STRICT18)))
    ax.set_xticklabels(STRICT18, rotation=55, ha="right")
    ax.set_yticks(np.arange(len(labels_show)))
    ax.set_yticklabels(labels_show)
    ax.set_title(title)
    ax.set_xlabel("Strict18 CNS tissue")
    ax.set_ylabel("Target")
    fig.colorbar(im, ax=ax, label="Collapsed numeric HR")
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_gesd_diagnostic(
    strict: pd.DataFrame,
    calls: pd.DataFrame,
    title: str,
    output: Path,
):
    """Render the ordered-score GESD diagnostic without changing calls."""
    vals = np.sort(strict["hr_numeric_collapsed"].to_numpy(dtype=float))
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(np.arange(1, len(vals) + 1), vals, linewidth=1)
    if len(calls):
        call_values = calls["hr_numeric_collapsed"].to_numpy(dtype=float)
        for v in call_values:
            pos = np.searchsorted(vals, v, side="left") + 1
            ax.scatter([pos], [v], s=22)
    ax.set_title(title)
    ax.set_xlabel("Ordered strict18 HR coordinate")
    ax.set_ylabel("Collapsed numeric HR")
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def main() -> int:
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    parser = argparse.ArgumentParser(
        description="Generate pooled-parent-ketamine strict18 GESD fingerprint."
    )
    parser.add_argument("--v4-dir", type=Path, required=True)
    parser.add_argument(
        "--expanded58-dir",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    v4_dir = args.v4_dir.resolve()
    expanded58_dir = locate_expanded58(
        v4_dir,
        args.expanded58_dir.resolve(),
    )
    input_path = expanded58_dir / MAIN_HR_FILENAME

    outdir = expanded58_dir / f"Strict18_Fingerprint_v1_{stamp()}"
    outdir.mkdir(parents=True, exist_ok=False)
    log_path = outdir / "RUN.log"

    def log(msg):
        """Write one timestamped run-log message."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    try:
        log("=== POOLED PARENT KETAMINE STRICT18 FINGERPRINT V1 START ===")
        log(f"Expanded58 folder: {expanded58_dir}")
        log(f"Input: {input_path}")
        log(f"Output: {outdir}")

        if not input_path.is_file():
            raise FileNotFoundError(input_path)

        d = pd.read_csv(input_path, low_memory=False)
        log(
            f"Loaded expanded HR: rows={len(d):,}; "
            f"targets={d['canonical_target_id'].nunique()}; "
            f"tissues={d['tissue_id'].nunique()}"
        )

        required = [
            "canonical_target_id",
            "gene_symbol",
            "tissue_id",
            "tissue_label",
            "HR_numeric_boundary_or_exact",
            "expression_z",
        ]
        missing = [c for c in required if c not in d.columns]
        if missing:
            raise RuntimeError(f"Input missing required columns: {missing}")

        # ------------------------------------------------------------------
        # Strict18 extraction.
        # ------------------------------------------------------------------
        tissue_map = {norm_tissue(t): t for t in STRICT18}
        d["_tissue_norm"] = d["tissue_label"].map(norm_tissue)
        strict = d[d["_tissue_norm"].isin(tissue_map)].copy()
        strict["tissue_display_order"] = strict["_tissue_norm"].map(tissue_map)

        strict["hr_numeric_collapsed"] = pd.to_numeric(
            strict["HR_numeric_boundary_or_exact"],
            errors="coerce",
        )
        strict["expression_z"] = pd.to_numeric(
            strict["expression_z"],
            errors="coerce",
        )

        # Explicitly remove exact/bounded distinction from the analysis table.
        keep_cols = [
            c for c in [
                "canonical_target_id",
                "gene_symbol",
                "target_name",
                "tissue_id",
                "tissue_label",
                "tissue_display_order",
                "hr_numeric_collapsed",
                "expression_z",
                "expression_recovery_source",
                "expression_recovery_mapping_method",
            ]
            if c in strict.columns
        ]
        strict = strict[keep_cols].copy()

        strict["feature_id"] = (
            strict["canonical_target_id"].astype(str)
            + "||"
            + strict["tissue_display_order"].astype(str)
        )

        if strict["feature_id"].duplicated().any():
            bad = strict.loc[
                strict["feature_id"].duplicated(keep=False),
                ["feature_id", "canonical_target_id", "tissue_display_order"],
            ]
            raise RuntimeError(
                "Duplicate strict18 feature IDs:\n"
                + bad.head(30).to_string(index=False)
            )

        if strict["hr_numeric_collapsed"].isna().any():
            raise RuntimeError("Strict18 input contains nonfinite numeric HR values")

        target_counts = strict.groupby(
            "canonical_target_id"
        )["tissue_display_order"].nunique()

        if len(target_counts) != EXPECTED_TARGETS:
            raise RuntimeError(
                f"Expected {EXPECTED_TARGETS} strict18 targets; found {len(target_counts)}"
            )
        if not target_counts.eq(EXPECTED_TISSUES).all():
            bad = target_counts[~target_counts.eq(EXPECTED_TISSUES)]
            raise RuntimeError(
                "One or more targets do not have all 18 strict CNS tissues:\n"
                + bad.to_string()
            )
        if len(strict) != EXPECTED_ROWS:
            raise RuntimeError(
                f"Expected {EXPECTED_ROWS} strict18 rows; found {len(strict)}"
            )

        observed_tissues = set(strict["tissue_display_order"])
        if observed_tissues != set(STRICT18):
            raise RuntimeError(
                "Strict18 tissue set mismatch.\n"
                f"Missing: {sorted(set(STRICT18) - observed_tissues)}\n"
                f"Unexpected: {sorted(observed_tissues - set(STRICT18))}"
            )

        # Deterministic feature ordering.
        strict = strict.sort_values(
            ["canonical_target_id", "tissue_display_order", "feature_id"],
            kind="stable",
        ).reset_index(drop=True)

        strict.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv",
            index=False,
        )

        log("Strict18 universe PASS: 58 targets x 18 tissues = 1,044 numeric HR coordinates")
        log("Exact/bounded activity distinction is NOT used in fingerprint selection.")

        values = strict["hr_numeric_collapsed"].to_numpy(dtype=float)
        ids = strict["feature_id"].to_numpy(dtype=object)
        n = len(values)
        rmax = int(math.floor(0.10 * n))
        rmax = min(max(1, rmax), n - 3)
        log(f"GESD n={n}; rmax={rmax}; ddof=1")

        results = {}
        calls = {}

        for alpha, label in [
            (0.001, "0p001"),
            (0.0001, "0p0001"),
        ]:
            primary = gesd_upper_primary(values, ids, alpha, rmax)
            independent = gesd_upper_independent(values, ids, alpha, rmax)
            qa_compare(primary, independent, alpha)

            table = make_fingerprint_table(strict, primary, alpha)

            primary.steps.to_csv(
                outdir / f"GESD_STEPS_ALPHA_{label}_V1.csv",
                index=False,
            )
            table.to_csv(
                outdir / f"POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_{label}_V1.csv",
                index=False,
            )

            results[label] = primary
            calls[label] = table

            log(
                f"alpha={alpha}: calls={len(table)}; "
                f"independent implementation agreement=PASS"
            )

        # Combined call table.
        c001 = calls["0p001"].copy()
        strict_ids = set(calls["0p0001"]["feature_id"].astype(str))
        if len(c001):
            c001["retained_at_alpha_0p0001"] = (
                c001["feature_id"].astype(str).isin(strict_ids)
            )
        else:
            c001["retained_at_alpha_0p0001"] = pd.Series(dtype=bool)

        c001.to_csv(
            outdir / "POOLED_PARENT_KETAMINE_FINGERPRINT_COMBINED_V1.csv",
            index=False,
        )

        # Matrices.
        full_matrix = build_matrix(strict, "hr_numeric_collapsed")
        full_matrix.to_csv(
            outdir / "STRICT18_NUMERIC_HR_MATRIX_V1.csv",
            index=False,
        )

        sparse001 = sparse_matrix(strict, calls["0p001"])
        sparse0001 = sparse_matrix(strict, calls["0p0001"])
        sparse001.to_csv(
            outdir / "FINGERPRINT_MATRIX_ALPHA_0p001_V1.csv",
            index=False,
        )
        sparse0001.to_csv(
            outdir / "FINGERPRINT_MATRIX_ALPHA_0p0001_V1.csv",
            index=False,
        )

        # Figures.
        plot_sparse_heatmap(
            strict,
            calls["0p001"],
            "Pooled parent ketamine strict18 fingerprint (GESD alpha=0.001)",
            outdir / "fingerprint_alpha_0p001_heatmap.png",
        )
        plot_sparse_heatmap(
            strict,
            calls["0p0001"],
            "Pooled parent ketamine strict18 fingerprint (GESD alpha=0.0001)",
            outdir / "fingerprint_alpha_0p0001_heatmap.png",
        )
        plot_gesd_diagnostic(
            strict,
            calls["0p001"],
            "Strict18 numeric HR ordered distribution — GESD alpha=0.001",
            outdir / "gesd_diagnostic_alpha_0p001.png",
        )
        plot_gesd_diagnostic(
            strict,
            calls["0p0001"],
            "Strict18 numeric HR ordered distribution — GESD alpha=0.0001",
            outdir / "gesd_diagnostic_alpha_0p0001.png",
        )

        n001 = len(calls["0p001"])
        n0001 = len(calls["0p0001"])
        targets001 = (
            calls["0p001"]["canonical_target_id"].nunique()
            if n001 else 0
        )
        tissues001 = (
            calls["0p001"]["tissue_label"].nunique()
            if n001 else 0
        )

        # Strict calls must be subset of primary calls.
        if not set(calls["0p0001"]["feature_id"].astype(str)).issubset(
            set(calls["0p001"]["feature_id"].astype(str))
        ):
            raise RuntimeError(
                "Safety stop: alpha=.0001 calls are not a subset of alpha=.001 calls."
            )

        summary = {
            "status": "PASS",
            "input": str(input_path),
            "input_sha256": sha256(input_path),
            "analysis_compound": "POOLED_PARENT_KETAMINE",
            "analysis_universe": "STRICT18_CNS",
            "targets": EXPECTED_TARGETS,
            "tissues": EXPECTED_TISSUES,
            "finite_numeric_HR_coordinates": EXPECTED_ROWS,
            "bounded_exact_distinction_used": False,
            "HR_value_for_GESD": "collapsed numeric HR",
            "GESD": {
                "tail": "one-sided upper",
                "ddof": 1,
                "rmax_fraction": 0.10,
                "rmax": rmax,
                "primary_alpha": 0.001,
                "strict_alpha": 0.0001,
                "primary_calls": n001,
                "strict_calls": n0001,
                "primary_unique_targets": targets001,
                "primary_unique_tissues": tissues001,
                "independent_implementation_QA": "PASS",
            },
            "fingerprint_calculated": True,
            "PCA_or_multivariate_calculated": False,
        }

        (outdir / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        top_lines = []
        if n001:
            for _, r in calls["0p001"].head(20).iterrows():
                top_lines.append(
                    f"  {int(r['fingerprint_rank']):>2}. "
                    f"{r['gene_symbol']} — {r['tissue_label']} "
                    f"(HR={r['hr_numeric_collapsed']:.6g}, "
                    f"R-lambda={r['R_minus_lambda']:.6g}, "
                    f"strict={bool(r['feature_id'] in strict_ids)})"
                )
        else:
            top_lines.append("  NONE")

        lines = [
            "=== POOLED PARENT KETAMINE STRICT18 FINGERPRINT V1 COMPLETE ===",
            "",
            "ANALYSIS UNIVERSE",
            "Targets: 58",
            "Strict-CNS tissues: 18",
            "Finite numeric HR coordinates: 1,044",
            "",
            "IMPORTANT INPUT RULE",
            "Exact versus bounded activity is NOT distinguished in this fingerprint step.",
            "All upstream-collapsed numerical HR scores enter the same GESD distribution.",
            "",
            "GESD",
            "Tail: one-sided upper",
            "Sample SD: ddof=1",
            f"rmax: {rmax} (= floor(0.10 x 1,044))",
            f"Primary alpha=0.001 calls: {n001}",
            f"Strict alpha=0.0001 calls: {n0001}",
            f"Primary fingerprint unique targets: {targets001}",
            f"Primary fingerprint unique tissues: {tissues001}",
            "Independent implementation QA: PASS",
            "",
            "PRIMARY ALPHA=0.001 CALLS",
            *top_lines,
            "",
            "NO PCA / CLUSTERING / MULTIVARIATE ANALYSIS WAS PERFORMED.",
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
            f"FINAL fingerprint: alpha=.001 calls={n001}; "
            f"alpha=.0001 calls={n0001}"
        )
        log("QA: PASS")
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
