"""Render a small gallery from hash-verified public reference tables.

Stage: public scientific presentation after accepted analysis, without refitting.
Inputs: retained v0.1.1 whole-body calls, family metrics, and Figure 4 assets.
Outputs: two PNG table views and a JSON provenance record under docs/figures/.
Side effects: writes only gallery assets, never results/reference/.
Invariants: validates frozen source hashes and counts, uses stored HR and Jaccard
values directly, preserves separate profile identities, and infers no non-calls.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SOURCE_HASHES = {
    "results/reference/whole_body/KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p001.csv":
        "abb2aa0bc6e3343e0eeda91cca9b0699356c770542b9b7b1ff9976f86eeb9a0e",
    "results/reference/family/KETAMINE_FAMILY_ALL_PAIR_METRICS_FINAL.csv":
        "ff279f96cb5b8c7fbf64370add496e91e45dbce69268d2c1c156ece10dda142a",
    "results/reference/figure4/final/FINAL_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND_600dpi.png":
        "0acb17dce9b984fd2db0c9144e472dd8828bc2523688bbf0dd812cfd7f3105f8",
    "results/reference/figure4/source_data/VALIDATED_FIGURE4_SOURCE_COORDINATES.csv":
        "8a369b7ddd2201e3ebc5a9ba227d67997b2e154b8982238588bf95a4894ed4aa",
    "results/reference/global/GLOBAL_MODEL_STATUS.csv":
        "a32606c98f49603fcc3ae027fda20efb6b54c3a9a69b4ed1ff23550b02e1a12d",
}


def sha256(path: Path) -> str:
    """Return the byte-level source or rendered-asset SHA-256 digest."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_whole_body(root: Path, destination: Path) -> dict:
    """Plot stored HR values for the first 12 accepted whole-body GESD ranks."""

    source = next(path for path in SOURCE_HASHES if "/whole_body/" in path)
    calls = pd.read_csv(root / source)
    if len(calls) != 59 or calls.duplicated(["canonical_target_id", "tissue_id"]).any():
        raise ValueError("Expected exactly 59 unique accepted whole-body calls")
    if not calls["fingerprint_alpha"].eq(0.001).all() or not calls["fingerprint_call"].eq(True).all():
        raise ValueError("Whole-body table is not the accepted primary call set")
    shown = calls.sort_values("fingerprint_rank", kind="stable").head(12)
    if shown["fingerprint_rank"].tolist() != list(range(1, 13)):
        raise ValueError("Expected consecutive stored GESD ranks 1 through 12")
    labels = [f"{row.canonical_target_id} · {row.tissue}" for row in shown.itertuples()]
    colors = ["#237a95" if value == "CNS" else "#ab6235" for value in shown["tissue_class"]]
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}):
        fig, ax = plt.subplots(figsize=(10, 5.3), layout="constrained")
        positions = np.arange(len(shown))
        ax.barh(positions, shown["HR_score"], color=colors, height=0.65)
        ax.set_yticks(positions, labels)
        ax.invert_yaxis()
        ax.set(xlabel="Stored HR score")
        ax.set_title("Whole-body ketamine fingerprint · highest-ranked 12 calls\n"
                     "Primary GESD α = 0.001 · 59 calls among 4,466 candidate coordinates",
                     fontsize=10, loc="left", pad=12)
        ax.grid(axis="x", color="#e6e6e6", linewidth=0.7)
        ax.set_axisbelow(True)
        ax.set_xlim(0, float(shown["HR_score"].max()) * 1.15)
        for position, value in zip(positions, shown["HR_score"]):
            ax.text(value + 0.35, position, f"{value:.2f}", va="center", fontsize=9)
        fig.savefig(destination, dpi=170, metadata={"Software": "Ketamine Historeceptomics gallery"})
        plt.close(fig)
    return {
        "source": source, "selection": "stored fingerprint_rank 1 through 12 of 59; no new calls",
        "scope": "whole_body_58_targets_77_tissues", "gesd_alpha": 0.001,
        "fields_plotted": ["canonical_target_id", "tissue", "HR_score", "tissue_class"],
        "records_plotted": len(shown), "source_records": len(calls),
        "display_colors": {"CNS": "#237a95", "Peripheral/non-CNS": "#ab6235"},
    }


def render_family(root: Path, destination: Path) -> dict:
    """Display all 45 stored family Jaccard metrics without recomputing them."""

    source = next(path for path in SOURCE_HASHES if "/family/" in path)
    pairs = pd.read_csv(root / source)
    roster = list(dict.fromkeys(pairs["drug_a"].tolist() + pairs["drug_b"].tolist()))
    if len(roster) != 10 or len(pairs) != 45:
        raise ValueError("Expected the accepted 10-profile, 45-pair family table")
    seen = set()
    matrix = np.full((10, 10), np.nan)
    empty_union = np.zeros((10, 10), dtype=bool)
    for row in pairs.itertuples():
        key = tuple(sorted((row.drug_a, row.drug_b)))
        if row.drug_a == row.drug_b or key in seen:
            raise ValueError("Duplicate or self-comparison in accepted family table")
        seen.add(key)
        value = float(row.alpha001_call_jaccard)
        if not np.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Invalid stored primary Jaccard value")
        a, b = sorted((roster.index(row.drug_a), roster.index(row.drug_b)))
        matrix[a, b] = value
        empty_union[a, b] = row.alpha001_union_calls == 0
    with plt.rc_context({"font.size": 10}):
        fig = plt.figure(figsize=(11.5, 6.0), layout="constrained")
        grid = fig.add_gridspec(1, 2, width_ratios=[1.3, 1.0])
        ax, legend = fig.add_subplot(grid[0]), fig.add_subplot(grid[1])
        cmap = plt.get_cmap("YlGnBu").copy()
        cmap.set_bad("#f3f5f6")
        image = ax.imshow(matrix, vmin=0, vmax=1, cmap=cmap)
        numbers = list(range(1, 11))
        ax.set_xticks(range(10), numbers)
        ax.set_yticks(range(10), numbers)
        ax.set(xlabel="Profile number", ylabel="Profile number")
        for i, j in zip(*np.where(np.isfinite(matrix))):
            value = matrix[i, j]
            label = f"{value:.2f}" + ("*" if empty_union[i, j] else "")
            ax.text(j, i, label, ha="center", va="center",
                    fontsize=9, color="white" if value > 0.58 else "#17202a")
        fig.colorbar(image, ax=ax, shrink=0.7, label="Stored call Jaccard")
        legend.axis("off")
        y = 1.0
        for number, label in zip(numbers, roster):
            wrapped = textwrap.fill(f"{number:2}. {label}", width=39, subsequent_indent="    ")
            legend.text(0, y, wrapped, transform=legend.transAxes, va="top", fontsize=10)
            y -= 0.082 + 0.025 * wrapped.count("\n")
        fig.suptitle("Ketamine-family fingerprints · all 45 unordered pairs", fontsize=14)
        fig.supxlabel("Strict-CNS · primary GESD α = 0.001 · diagonal omitted\n"
                      "* Both call sets empty: stored Jaccard = 1 by convention; no shared calls", fontsize=9)
        fig.savefig(destination, dpi=170, metadata={"Software": "Ketamine Historeceptomics gallery"})
        plt.close(fig)
    return {
        "source": source, "scope": "strict_CNS_10_family_profiles_45_unordered_pairs",
        "gesd_alpha": 0.001, "field_plotted": "alpha001_call_jaccard",
        "records_plotted": 45, "roster": roster,
        "display": "upper triangle only; diagonal/lower triangle omitted, not zero",
        "empty_union_pairs": int(empty_union.sum()),
        "empty_union_convention": "stored Jaccard = 1 for both empty call sets; marked with an asterisk",
    }


def main() -> None:
    """Verify source bytes, render table views, and record source/asset lineage."""

    root = Path(__file__).resolve().parents[1]
    for relative, expected in SOURCE_HASHES.items():
        if sha256(root / relative) != expected:
            raise ValueError(f"Frozen public v0.1.1 source hash mismatch: {relative}")
    figures = root / "docs/figures"
    figures.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for filename, renderer in (
        ("gallery_whole_body.png", render_whole_body),
        ("gallery_family_jaccard.png", render_family),
    ):
        path = figures / filename
        outputs[path.relative_to(root).as_posix()] = {**renderer(root, path), "sha256": sha256(path)}
    original = next(path for path in SOURCE_HASHES if path.endswith(".png"))
    outputs[original] = {
        "sha256": SOURCE_HASHES[original], "transformation": "none; original accepted Figure 4",
        "scope": "exploratory continuous strict-CNS common-RHR fixed-reference PCA; 25 reference drugs plus pooled-parent query",
        "gesd_alpha": None, "limitation": "Inherited EM-SVD reference fit did not converge in 300 iterations; retained point estimate",
    }
    provenance = {
        "reference_release": "v0.1.1", "source_hashes": SOURCE_HASHES,
        "scientific_recalculation": False,
        "rendering": "Two direct views of accepted tables plus unchanged accepted Figure 4; no HR, GESD, pair metric, or PCA refit",
        "data_license": "CC-BY-SA-4.0; DATA_LICENSE.md and third-party qualifications apply",
        "outputs": outputs,
    }
    (figures / "gallery_provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print("PASS: 5 frozen source hashes; 12 stored HR values and all 45 family metrics rendered; accepted Figure 4 unchanged")


if __name__ == "__main__":
    main()
