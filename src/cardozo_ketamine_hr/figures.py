# SPDX-License-Identifier: MIT
"""Render deterministic analysis figures and record their publication metadata.

Stage
-----
Figure rendering consumes persisted analysis tables after numerical stages and
before paper-facing packet assembly.

Inputs
------
Functions accept pandas matrices or long-form tables whose coordinates,
identities, and ordering were fixed upstream.

Outputs
-------
Rendering helpers return Matplotlib figures; ``FigureRecorder`` and
``table_pdf`` persist derivative PNG/PDF artifacts and manifest metadata.

Side Effects
------------
The module selects Matplotlib's noninteractive ``Agg`` backend and installs
project-wide rendering defaults at import time. Recorder methods write files.

Invariants
----------
Rendering never refits a model, moves ordination coordinates, fills missing
scientific values, or changes compound identity labels.

Lane
----
Portable derivative visualization and publication-packaging lane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from scipy.cluster.hierarchy import dendrogram

from .utilities import sha256_file, slug


plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "figure.dpi": 120,
    "savefig.dpi": 220,
    "savefig.bbox": "tight",
})


@dataclass
class FigureRecorder:
    """Persist figures and accumulate their manifest rows.

    Attributes
    ----------
    run_root : pathlib.Path
        Root used to express output paths portably in the manifest.
    rows : list of dict
        In-memory figure metadata accumulated in save order.
    """

    run_root: Path
    rows: list[dict[str, Any]] = field(default_factory=list)

    def save(self, figure: plt.Figure, base: Path, figure_id: str, analysis: str, title: str, query: str, comparators: str, input_table: str, priority: str = "SUPPLEMENTAL") -> tuple[Path, Path]:
        """Save one figure as PNG and PDF and record basic artifact QA.

        Parameters
        ----------
        figure : matplotlib.figure.Figure
            Completed figure to persist and close.
        base : pathlib.Path
            Output path without an extension.
        figure_id : str
            Stable manifest identifier.
        analysis : str
            Analysis family or stage label.
        title : str
            Publication-facing figure title.
        query : str
            Query identity represented by the figure.
        comparators : str
            Comparator description recorded in the manifest.
        input_table : str
            Persisted numerical table used for rendering.
        priority : str, default="SUPPLEMENTAL"
            Paper-facing priority label.

        Returns
        -------
        png, pdf : tuple of pathlib.Path
            Paths to the two rendered artifacts.

        Side Effects
        ------------
        Creates parent directories, writes PNG/PDF files, closes ``figure``,
        and appends a manifest row.
        """
        base.parent.mkdir(parents=True, exist_ok=True)
        png = base.with_suffix(".png")
        pdf = base.with_suffix(".pdf")
        figure.savefig(png)
        figure.savefig(pdf)
        plt.close(figure)
        ok = png.stat().st_size > 5000 and pdf.stat().st_size > 1000
        self.rows.append({
            "figure_id": figure_id,
            "analysis": analysis,
            "title": title,
            "query": query,
            "comparators": comparators,
            "input_table": input_table,
            "output_file": png.relative_to(self.run_root).as_posix(),
            "pdf_file": pdf.relative_to(self.run_root).as_posix(),
            "paper_facing_priority": priority,
            "QA_status": "PASS" if ok else "FAILED_QA",
            "png_bytes": png.stat().st_size,
            "pdf_bytes": pdf.stat().st_size,
        })
        return png, pdf

    def frame(self) -> pd.DataFrame:
        """Return accumulated figure metadata as a new table.

        Returns
        -------
        pandas.DataFrame
            One row for each figure saved by this recorder.
        """
        return pd.DataFrame(self.rows)


def heatmap(matrix: pd.DataFrame, title: str, colorbar_label: str, diverging: bool = False, figsize: tuple[float, float] | None = None, annotate: bool = False) -> plt.Figure:
    """Render a general matrix heatmap while retaining missing cells.

    Parameters
    ----------
    matrix : pandas.DataFrame
        Labeled numerical matrix.
    title : str
        Figure title.
    colorbar_label : str
        Colorbar description.
    diverging : bool, default=False
        Center the color scale around zero when true.
    figsize : tuple of float, optional
        Explicit figure dimensions; otherwise dimensions follow matrix size.
    annotate : bool, default=False
        Add cell values only for matrices of at most 400 cells.

    Returns
    -------
    matplotlib.figure.Figure
        Unsaved heatmap figure.

    Raises
    ------
    ValueError
        If the matrix contains no finite value.
    """
    height = max(5.5, min(14, 0.32 * len(matrix.index) + 2))
    width = max(8.0, min(18, 0.34 * len(matrix.columns) + 3))
    fig, ax = plt.subplots(figsize=figsize or (width, height))
    values = matrix.to_numpy(float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("Cannot render a NaN-only matrix")
    if diverging:
        # A robust symmetric bound prevents isolated extremes from obscuring
        # the signed structure without altering the plotted values.
        bound = float(np.nanquantile(np.abs(finite), 0.99)) or 1.0
        image = ax.imshow(values, aspect="auto", interpolation="nearest", cmap="coolwarm", vmin=-bound, vmax=bound)
    else:
        image = ax.imshow(values, aspect="auto", interpolation="nearest", cmap="viridis")
    ax.set_xticks(np.arange(len(matrix.columns)), labels=matrix.columns, rotation=45, ha="right")
    ax.set_yticks(np.arange(len(matrix.index)), labels=matrix.index)
    ax.set_title(title)
    colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
    colorbar.set_label(colorbar_label)
    if annotate and values.size <= 400:
        for row in range(values.shape[0]):
            for column in range(values.shape[1]):
                if np.isfinite(values[row, column]):
                    ax.text(column, row, f"{values[row, column]:.2f}", ha="center", va="center", fontsize=6, color="white" if abs(values[row, column]) > np.nanmedian(abs(finite)) else "black")
    fig.tight_layout()
    return fig


def profile_heatmap(long_frame: pd.DataFrame, value_col: str, title: str, target_col: str = "target", tissue_col: str = "tissue", robust: bool = True) -> plt.Figure:
    """Render a target-by-tissue heatmap from a long-form profile.

    Parameters
    ----------
    long_frame : pandas.DataFrame
        Long profile with unique target/tissue coordinates.
    value_col : str
        Numerical value to plot.
    title : str
        Figure title.
    target_col : str, default="target"
        Column supplying heatmap rows.
    tissue_col : str, default="tissue"
        Column supplying heatmap columns.
    robust : bool, default=True
        Use the 99th absolute percentile rather than the full maximum.

    Returns
    -------
    matplotlib.figure.Figure
        Unsaved diverging profile heatmap.

    Raises
    ------
    ValueError
        If no finite profile cells are available.
    """
    matrix = long_frame.pivot(index=target_col, columns=tissue_col, values=value_col)
    values = matrix.to_numpy(float)
    finite = values[np.isfinite(values)]
    if not finite.size:
        raise ValueError("Profile contains no finite cells")
    bound = float(np.nanquantile(np.abs(finite), 0.99 if robust else 1.0)) or 1.0
    fig, ax = plt.subplots(figsize=(14, max(7, 0.22 * len(matrix))))
    image = ax.imshow(values, aspect="auto", cmap="coolwarm", vmin=-bound, vmax=bound, interpolation="nearest")
    ax.set_xticks(np.arange(len(matrix.columns)), labels=matrix.columns, rotation=45, ha="right")
    ax.set_yticks(np.arange(len(matrix.index)), labels=matrix.index)
    ax.set_title(title)
    fig.colorbar(image, ax=ax, label=value_col, shrink=0.8)
    fig.tight_layout()
    return fig


def fingerprint_heatmap(matrix: pd.DataFrame, title: str) -> plt.Figure:
    """Render fingerprint membership from non-missing call cells.

    Parameters
    ----------
    matrix : pandas.DataFrame
        Target-by-tissue call matrix whose non-missing cells are calls.
    title : str
        Figure title.

    Returns
    -------
    matplotlib.figure.Figure
        Unsaved binary membership heatmap.

    Notes
    -----
    Values are not thresholded here; membership is defined upstream and
    represented by non-missing cells.
    """
    mask = matrix.notna().to_numpy(int)
    fig, ax = plt.subplots(figsize=(14, max(7, 0.23 * len(matrix))))
    image = ax.imshow(mask, aspect="auto", cmap=ListedColormap(["#f7f7f7", "#8b1a1a"]), vmin=0, vmax=1, interpolation="nearest")
    ax.set_xticks(np.arange(len(matrix.columns)), labels=matrix.columns, rotation=45, ha="right")
    ax.set_yticks(np.arange(len(matrix.index)), labels=matrix.index)
    ax.set_title(title)
    ax.set_xlabel(f"Rendered call cells: {int(mask.sum())}")
    fig.tight_layout()
    return fig


def scatter(scores: pd.DataFrame, title: str, x: str = "PC1", y: str = "PC2", highlight: list[str] | None = None, label_col: str = "compound") -> plt.Figure:
    """Render persisted ordination scores with numbered direct labels.

    Parameters
    ----------
    scores : pandas.DataFrame
        Persisted coordinate table.
    title : str
        Figure title.
    x, y : str
        Coordinate columns. If ``y`` is unavailable, a one-dimensional strip
        is rendered at zero without random jitter.
    highlight : list of str, optional
        Labels rendered with the query highlight color.
    label_col : str, default="compound"
        Column used for the numbered external key.

    Returns
    -------
    matplotlib.figure.Figure
        Unsaved ordination figure.

    Notes
    -----
    Coordinates are plotted exactly as supplied; numbering affects labels only.
    """
    highlight = highlight or []
    count = len(scores)
    fig, ax = plt.subplots(figsize=(14 if count > 12 else 11, 7))
    legend_handles = []
    if y in scores.columns and scores[y].notna().any():
        for number, row in enumerate(scores.itertuples(index=False), start=1):
            label = str(getattr(row, label_col))
            color = "#b22222" if label in highlight else "#336699"
            size = 90 if label in highlight else 60
            ax.scatter(getattr(row, x), getattr(row, y), color=color, s=size, alpha=0.9)
            ax.annotate(str(number), (getattr(row, x), getattr(row, y)), ha="center", va="center", fontsize=6, color="white", fontweight="bold")
            legend_handles.append(Line2D([0], [0], marker="o", color="none", markerfacecolor=color, markeredgecolor=color, label=f"{number}. {label}", markersize=6))
        ax.set_ylabel(y)
    else:
        # The one-dimensional fallback uses deterministic zeros, never jitter,
        # so the supplied coordinate geometry remains unchanged.
        jitter = np.zeros(len(scores))
        ax.scatter(scores[x], jitter, color=["#b22222" if value in highlight else "#336699" for value in scores[label_col]], s=55)
        for number, ((_, row), yy) in enumerate(zip(scores.iterrows(), jitter), start=1):
            label = str(row[label_col])
            color = "#b22222" if label in highlight else "#336699"
            ax.annotate(str(number), (row[x], yy), ha="center", va="center", fontsize=6, color="white", fontweight="bold")
            legend_handles.append(Line2D([0], [0], marker="o", color="none", markerfacecolor=color, markeredgecolor=color, label=f"{number}. {label}", markersize=6))
        ax.set_yticks([])
    ax.axhline(0, color="0.85", linewidth=0.8)
    ax.axvline(0, color="0.85", linewidth=0.8)
    ax.set_xlabel(x)
    ax.set_title(title)
    legend_columns = 2 if count > 18 else 1
    ax.legend(handles=legend_handles, title="Compound key", loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=7, title_fontsize=8, ncol=legend_columns, columnspacing=1.0, handletextpad=0.4)
    fig.tight_layout(rect=(0, 0, 0.72 if legend_columns == 2 else 0.78, 1))
    return fig


def ranking(frame: pd.DataFrame, label_col: str, value_col: str, title: str, xlabel: str, ascending: bool = True, top_n: int | None = None) -> plt.Figure:
    """Render a sorted horizontal ranking chart.

    Parameters
    ----------
    frame : pandas.DataFrame
        Source ranking table.
    label_col, value_col : str
        Label and numerical columns to render.
    title, xlabel : str
        Figure title and horizontal-axis label.
    ascending : bool, default=True
        Sort direction before selection.
    top_n : int, optional
        Maximum number of sorted rows to retain.

    Returns
    -------
    matplotlib.figure.Figure
        Unsaved ranking figure.
    """
    data = frame[[label_col, value_col]].dropna().sort_values(value_col, ascending=ascending)
    if top_n:
        data = data.head(top_n)
    fig, ax = plt.subplots(figsize=(10, max(5, 0.35 * len(data) + 1.5)))
    ax.barh(data[label_col], data[value_col], color="#456b8e")
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    fig.tight_layout()
    return fig


def dashboard(frame: pd.DataFrame, label_col: str, metrics: list[tuple[str, str]], title: str, top_n: int = 25) -> plt.Figure:
    """Render aligned metric panels for a shared ordered roster.

    Parameters
    ----------
    frame : pandas.DataFrame
        Already ordered source rows.
    label_col : str
        Shared y-axis label column.
    metrics : list of tuple of str
        ``(column, axis_label)`` pairs for each panel.
    title : str
        Figure title.
    top_n : int, default=25
        Number of leading source rows to display.

    Returns
    -------
    matplotlib.figure.Figure
        Unsaved multi-panel dashboard.
    """
    data = frame.head(top_n).copy()
    fig, axes = plt.subplots(1, len(metrics), figsize=(3.3 * len(metrics), max(7, 0.32 * len(data) + 2)), sharey=True)
    if len(metrics) == 1:
        axes = [axes]
    for ax, (column, label) in zip(axes, metrics):
        ax.scatter(data[column], np.arange(len(data)), s=30, color="#4b6f91")
        ax.set_xlabel(label)
        ax.grid(axis="x", alpha=0.25)
    axes[0].set_yticks(np.arange(len(data)), labels=data[label_col])
    axes[0].invert_yaxis()
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def dendrogram_figure(linkage_matrix: pd.DataFrame, labels: list[str], title: str) -> plt.Figure:
    """Render a dendrogram from a persisted linkage table.

    Parameters
    ----------
    linkage_matrix : pandas.DataFrame
        SciPy-compatible linkage columns.
    labels : list of str
        Leaf labels in the linkage input order.
    title : str
        Figure title.

    Returns
    -------
    matplotlib.figure.Figure
        Unsaved dendrogram figure.
    """
    values = linkage_matrix[["left_cluster", "right_cluster", "distance", "member_count"]].to_numpy(float)
    fig, ax = plt.subplots(figsize=(max(10, 0.42 * len(labels)), 7))
    dendrogram(values, labels=labels, leaf_rotation=65, leaf_font_size=8, ax=ax)
    ax.set_ylabel("Average-linkage RMS distance")
    ax.set_title(title)
    fig.tight_layout()
    return fig


def table_pdf(frame: pd.DataFrame, title: str, path: Path, max_rows: int = 30) -> Path:
    """Render the leading rows of a table to a compact PDF.

    Parameters
    ----------
    frame : pandas.DataFrame
        Source table.
    title : str
        PDF title.
    path : pathlib.Path
        Destination PDF path.
    max_rows : int, default=30
        Maximum number of leading rows rendered.

    Returns
    -------
    pathlib.Path
        Written PDF path.

    Side Effects
    ------------
    Creates the destination directory, writes the PDF, and closes the figure.
    """
    data = frame.head(max_rows).copy()
    for column in data.columns:
        if pd.api.types.is_float_dtype(data[column]):
            data[column] = data[column].map(lambda value: "" if pd.isna(value) else f"{value:.4g}")
    fig, ax = plt.subplots(figsize=(max(8.5, 1.2 * len(data.columns)), max(3.5, 0.3 * len(data) + 1.8)))
    ax.axis("off")
    ax.set_title(title, pad=14)
    table = ax.table(cellText=data.astype(str).values, colLabels=data.columns, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(6.5)
    table.scale(1, 1.25)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path
