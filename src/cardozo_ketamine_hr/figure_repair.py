# SPDX-License-Identifier: MIT
"""Repair persisted ordination labels without changing coordinates.

Stage
-----
The repair runs after figure and table manifests have been produced and before
the final paper-facing PDF packet is frozen.

Inputs
------
The run root supplies persisted score tables, figure manifests, rendered
figures, and paper-facing indexes.

Outputs
-------
Ordination PNG/PDF files, manifest byte counts, combined PDF packets, and a
visual-repair audit table are refreshed in place under the derivative run.

Side Effects
------------
Writes derivative figures and manifests, copies repaired figures into the
paper-facing folder, and rebuilds combined PDFs.

Invariants
----------
Persisted coordinates and compound identities are reused exactly; only labels
and their external key are regenerated.

Lane
----
Derivative-only visual repair and publication-packaging lane.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from .figures import scatter
from .packaging import combine_pdfs


def repair_ordination_labels(run_root: Path) -> pd.DataFrame:
    """Regenerate persisted ordinations with numbered points and an external key.

    Parameters
    ----------
    run_root : pathlib.Path
        Completed derivative run containing figure manifests and score tables.

    Returns
    -------
    pandas.DataFrame
        One status row per ordination considered for repair.

    Raises
    ------
    RuntimeError
        If any identified ordination lacks a supported input or schema.

    Side Effects
    ------------
    Rewrites derivative ordination images, manifest/index CSVs, combined PDF
    packets, and the label-repair audit CSV beneath ``run_root``.
    """
    run_root = Path(run_root)
    manifest_path = run_root / "15_QA_AND_MANIFESTS" / "FIGURE_MANIFEST.csv"
    manifest = pd.read_csv(manifest_path, low_memory=False)
    paper_figures = run_root / "14_PAPER_FACING" / "FIGURES"
    rows = []
    for index, record in manifest.iterrows():
        png_path = run_root / str(record["output_file"])
        if "ORDINATION" not in png_path.stem:
            continue
        input_path = run_root / str(record["input_table"])
        if not input_path.exists():
            rows.append({"figure_id": record["figure_id"], "status": "BLOCKED_INPUT_NOT_FOUND", "path": str(png_path), "reason": str(input_path)})
            continue
        scores = pd.read_csv(input_path, low_memory=False)
        x, y = None, None
        # Coordinate column names differ by the already-selected method, but
        # the values are loaded rather than recomputed.
        for candidate in [("PC1", "PC2"), ("Axis1", "Axis2"), ("MDS1", "MDS2")]:
            if candidate[0] in scores.columns:
                x, y = candidate
                break
        if x is None or "compound" not in scores.columns:
            rows.append({"figure_id": record["figure_id"], "status": "BLOCKED_SCHEMA", "path": str(png_path), "reason": "No supported coordinates or compound label"})
            continue
        figure = scatter(scores, str(record["title"]), x=x, y=y or "", highlight=["Ketamine, pooled parent", "Ketamine, confirmed racemate"], label_col="compound")
        pdf_path = run_root / str(record["pdf_file"])
        figure.savefig(png_path)
        figure.savefig(pdf_path)
        import matplotlib.pyplot as plt
        plt.close(figure)
        manifest.at[index, "png_bytes"] = png_path.stat().st_size
        manifest.at[index, "pdf_bytes"] = pdf_path.stat().st_size
        manifest.at[index, "QA_status"] = "PASS" if png_path.stat().st_size > 5000 and pdf_path.stat().st_size > 1000 else "FAILED_QA"
        for source in [png_path, pdf_path]:
            paper_copy = paper_figures / source.name
            if paper_copy.exists():
                shutil.copy2(source, paper_copy)
        rows.append({"figure_id": record["figure_id"], "status": "PASS_AFTER_LABEL_REPAIR", "path": str(png_path), "reason": "Numbered points and deterministic external compound key"})
    manifest.to_csv(manifest_path, index=False)

    paper_index_path = run_root / "14_PAPER_FACING" / "PAPER_FACING_FIGURE_INDEX.csv"
    paper_index = pd.read_csv(paper_index_path, low_memory=False)
    refreshed = manifest.set_index("figure_id")
    for index, row in paper_index.iterrows():
        if row["figure_id"] in refreshed.index:
            for column in ["png_bytes", "pdf_bytes", "QA_status"]:
                paper_index.at[index, column] = refreshed.at[row["figure_id"], column]
    paper_index.to_csv(paper_index_path, index=False)
    figure_pdfs = [run_root / path for path in paper_index["pdf_file"]]
    all_figures, _ = combine_pdfs(figure_pdfs, run_root / "14_PAPER_FACING" / "ALL_FIGURES_COMBINED.pdf")
    all_tables = run_root / "14_PAPER_FACING" / "ALL_TABLES_COMBINED.pdf"
    combine_pdfs([all_figures, all_tables], run_root / "14_PAPER_FACING" / "COMPLETE_FIGURES_AND_TABLES_PACKET.pdf")
    result = pd.DataFrame(rows)
    result.to_csv(run_root / "15_QA_AND_MANIFESTS" / "VISUAL_INSPECTION_AND_LABEL_REPAIR.csv", index=False)
    if len(result) and not result["status"].eq("PASS_AFTER_LABEL_REPAIR").all():
        raise RuntimeError("One or more ordination panels could not be repaired")
    return result
