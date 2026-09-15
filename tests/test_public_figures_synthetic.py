# SPDX-License-Identifier: MIT
"""Validate derivative-only figure rendering and label repair on synthetic coordinates."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from pypdf import PdfWriter

from cardozo_ketamine_hr.figure_repair import repair_ordination_labels
from cardozo_ketamine_hr.figures import (
    FigureRecorder,
    dashboard,
    dendrogram_figure,
    fingerprint_heatmap,
    heatmap,
    profile_heatmap,
    ranking,
    scatter,
    table_pdf,
)


def test_heatmap_variants_preserve_values_and_reject_empty_profiles() -> None:
    matrix = pd.DataFrame([[1.0, np.nan], [-2.0, 0.0]], index=["T1", "T2"], columns=["brain", "cortex"])
    ordinary = heatmap(matrix, "ordinary", "value", annotate=True)
    diverging = heatmap(matrix, "diverging", "value", diverging=True)
    assert ordinary.axes[0].get_title() == "ordinary"
    assert diverging.axes[0].images[0].get_array().shape == (2, 2)
    plt.close(ordinary)
    plt.close(diverging)
    with pytest.raises(ValueError, match="NaN-only"):
        heatmap(pd.DataFrame([[np.nan]]), "empty", "value")

    long = pd.DataFrame({"target": ["T1", "T1", "T2"], "tissue": ["brain", "cortex", "brain"], "score": [1.0, -2.0, 0.5]})
    for robust in (True, False):
        figure = profile_heatmap(long, "score", "profile", robust=robust)
        assert figure.axes[0].images[0].get_array().shape == (2, 2)
        plt.close(figure)
    with pytest.raises(ValueError, match="no finite"):
        profile_heatmap(pd.DataFrame({"target": ["T"], "tissue": ["B"], "score": [np.nan]}), "score", "empty")


def test_fingerprint_scatter_ranking_dashboard_and_dendrogram() -> None:
    fingerprint = fingerprint_heatmap(pd.DataFrame([[1.0, np.nan], [np.nan, 1.0]], index=["T1", "T2"], columns=["B", "C"]), "calls")
    assert "2" in fingerprint.axes[0].get_xlabel()
    plt.close(fingerprint)

    scores_2d = pd.DataFrame({"compound": ["Q", "A", "B"], "PC1": [1.0, 0.0, -1.0], "PC2": [0.0, 1.0, -1.0]})
    plotted = scatter(scores_2d, "ordination", highlight=["Q"])
    assert plotted.axes[0].get_ylabel() == "PC2"
    plt.close(plotted)
    scores_1d = scores_2d.drop(columns="PC2")
    strip = scatter(scores_1d, "rank-one", highlight=["Q"])
    assert strip.axes[0].get_yticks().size == 0
    plt.close(strip)

    ranks = ranking(pd.DataFrame({"label": ["a", "b", "c"], "value": [3.0, np.nan, 1.0]}), "label", "value", "rank", "metric", top_n=1)
    assert len(ranks.axes[0].patches) == 1
    plt.close(ranks)
    panels = dashboard(pd.DataFrame({"label": ["a", "b"], "x": [1, 2], "y": [2, 1]}), "label", [("x", "X"), ("y", "Y")], "dashboard")
    assert len(panels.axes) == 2
    plt.close(panels)
    one_panel = dashboard(pd.DataFrame({"label": ["a"], "x": [1]}), "label", [("x", "X")], "one")
    assert len(one_panel.axes) == 1
    plt.close(one_panel)

    linkage = pd.DataFrame({"left_cluster": [0.0, 2.0], "right_cluster": [1.0, 3.0], "distance": [1.0, 2.0], "member_count": [2.0, 3.0]})
    tree = dendrogram_figure(linkage, ["A", "B", "C"], "tree")
    assert tree.axes[0].get_title() == "tree"
    plt.close(tree)


def test_figure_recorder_and_table_pdf_persist_derivatives(tmp_path: Path) -> None:
    recorder = FigureRecorder(tmp_path)
    figure = heatmap(pd.DataFrame([[1.0, 2.0], [3.0, 4.0]]), "saved", "value")
    png, pdf = recorder.save(figure, tmp_path / "figures" / "heatmap", "F1", "synthetic", "Saved", "Q", "A", "table.csv")
    assert png.stat().st_size > 5000 and pdf.stat().st_size > 1000
    assert recorder.frame().iloc[0]["QA_status"] == "PASS"
    table_path = table_pdf(pd.DataFrame({"label": ["a", "b"], "value": [1.23456, np.nan]}), "table", tmp_path / "tables" / "table.pdf")
    assert table_path.stat().st_size > 1000


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def test_ordination_label_repair_reuses_persisted_coordinates(tmp_path: Path) -> None:
    qa = tmp_path / "15_QA_AND_MANIFESTS"
    paper = tmp_path / "14_PAPER_FACING"
    figures = paper / "FIGURES"
    source = tmp_path / "scores.csv"
    qa.mkdir(parents=True)
    figures.mkdir(parents=True)
    scores = pd.DataFrame({"compound": ["Ketamine, pooled parent", "Reference"], "Axis1": [1.25, -0.5], "Axis2": [0.0, 2.0]})
    scores.to_csv(source, index=False)
    output_png = tmp_path / "plots" / "SYNTHETIC_ORDINATION.png"
    output_pdf = tmp_path / "plots" / "SYNTHETIC_ORDINATION.pdf"
    output_png.parent.mkdir()
    output_png.write_bytes(b"old")
    _blank_pdf(output_pdf)
    (figures / output_png.name).write_bytes(b"old paper")
    _blank_pdf(figures / output_pdf.name)
    manifest = pd.DataFrame(
        [{"figure_id": "ORD1", "title": "Synthetic ordination", "output_file": output_png.relative_to(tmp_path).as_posix(), "pdf_file": output_pdf.relative_to(tmp_path).as_posix(), "input_table": source.relative_to(tmp_path).as_posix(), "png_bytes": 3, "pdf_bytes": output_pdf.stat().st_size, "QA_status": "OLD"}]
    )
    manifest.to_csv(qa / "FIGURE_MANIFEST.csv", index=False)
    manifest.to_csv(paper / "PAPER_FACING_FIGURE_INDEX.csv", index=False)
    _blank_pdf(paper / "ALL_TABLES_COMBINED.pdf")
    result = repair_ordination_labels(tmp_path)
    assert result["status"].tolist() == ["PASS_AFTER_LABEL_REPAIR"]
    refreshed = pd.read_csv(qa / "FIGURE_MANIFEST.csv")
    assert refreshed.loc[0, "QA_status"] == "PASS"
    assert output_png.stat().st_size > 5000
    assert (paper / "COMPLETE_FIGURES_AND_TABLES_PACKET.pdf").exists()


@pytest.mark.xfail(
    strict=True,
    reason="Pre-existing defect: missing ordination input passes None into combine_pdfs before the intended RuntimeError",
)
def test_ordination_label_repair_fails_closed_on_missing_input(tmp_path: Path) -> None:
    qa = tmp_path / "15_QA_AND_MANIFESTS"
    paper = tmp_path / "14_PAPER_FACING"
    qa.mkdir(parents=True)
    paper.mkdir(parents=True)
    manifest = pd.DataFrame(
        [{"figure_id": "ORD2", "title": "Missing", "output_file": "plots/MISSING_ORDINATION.png", "pdf_file": "plots/MISSING_ORDINATION.pdf", "input_table": "missing.csv", "png_bytes": 0, "pdf_bytes": 0, "QA_status": "OLD"}]
    )
    manifest.to_csv(qa / "FIGURE_MANIFEST.csv", index=False)
    manifest.to_csv(paper / "PAPER_FACING_FIGURE_INDEX.csv", index=False)
    with pytest.raises(RuntimeError, match="could not be repaired"):
        repair_ordination_labels(tmp_path)
    audit = pd.read_csv(qa / "VISUAL_INSPECTION_AND_LABEL_REPAIR.csv")
    assert audit.loc[0, "status"] == "BLOCKED_INPUT_NOT_FOUND"
