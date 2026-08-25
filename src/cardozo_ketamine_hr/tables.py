# SPDX-License-Identifier: MIT
"""Build pairwise summary tables and record persisted CSV artifacts.

Stage
-----
Table construction follows pairwise detail computation and precedes
paper-facing table rendering and packaging.

Inputs
------
Functions consume governed feature-level differences, fingerprint matrices,
feature contracts, and pairwise metric rows.

Outputs
-------
Summary helpers return pandas tables; ``TableRecorder`` persists CSV files and
accumulates their manifest metadata.

Side Effects
------------
Only ``TableRecorder.write`` creates directories and writes files.

Invariants
----------
Signed differences retain query-minus-comparator orientation, missing call
states are not converted to calls, and output rankings derive from supplied
persisted metrics without recomputation.

Lane
----
Portable pairwise reporting and publication-table lane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .utilities import slug


@dataclass
class TableRecorder:
    """Persist CSV tables and accumulate manifest rows.

    Attributes
    ----------
    run_root : pathlib.Path
        Root used to store portable relative output paths.
    rows : list of dict
        Table metadata accumulated in write order.
    """

    run_root: Path
    rows: list[dict[str, Any]] = field(default_factory=list)

    def write(self, frame: pd.DataFrame, path: Path, table_id: str, analysis: str, title: str, query: str, comparators: str, representation: str, priority: str = "SUPPLEMENTAL") -> Path:
        """Write one CSV table and append its manifest metadata.

        Parameters
        ----------
        frame : pandas.DataFrame
            Table to persist without an index column.
        path : pathlib.Path
            CSV destination beneath ``run_root``.
        table_id : str
            Stable table identifier.
        analysis, title, query, comparators, representation : str
            Publication and provenance metadata.
        priority : str, default="SUPPLEMENTAL"
            Paper-facing priority label.

        Returns
        -------
        pathlib.Path
            Written CSV path.

        Side Effects
        ------------
        Creates the parent directory, writes the CSV, and appends a manifest
        row with basic size QA.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        self.rows.append({
            "table_id": table_id,
            "analysis": analysis,
            "title": title,
            "query": query,
            "comparators": comparators,
            "representation": representation,
            "input_table": "",
            "output_file": path.relative_to(self.run_root).as_posix(),
            "paper_facing_priority": priority,
            "QA_status": "PASS" if path.stat().st_size > 20 else "FAILED_QA",
            "row_count": len(frame),
            "column_count": len(frame.columns),
        })
        return path

    def frame(self) -> pd.DataFrame:
        """Return accumulated table metadata as a new table.

        Returns
        -------
        pandas.DataFrame
            One row for each table written by this recorder.
        """
        return pd.DataFrame(self.rows)


def target_summary(detail: pd.DataFrame) -> pd.DataFrame:
    """Aggregate feature-level pair differences by target.

    Parameters
    ----------
    detail : pandas.DataFrame
        Matched feature-level pair details oriented as query versus comparator.

    Returns
    -------
    pandas.DataFrame
        Target-level support, means, and signed/absolute residual statistics.
    """
    if detail.empty:
        return pd.DataFrame(columns=["target", "matched_feature_count", "query_mean", "comparator_mean", "mean_difference", "mean_absolute_difference", "max_absolute_difference"])
    result = detail.groupby("target", as_index=False).agg(
        matched_feature_count=("feature_id", "size"),
        query_mean=("value_a", "mean"),
        comparator_mean=("value_b", "mean"),
        mean_difference=("signed_difference_a_minus_b", "mean"),
        mean_absolute_difference=("absolute_difference", "mean"),
        max_absolute_difference=("absolute_difference", "max"),
    )
    return result


def tissue_summary(detail: pd.DataFrame) -> pd.DataFrame:
    """Aggregate feature-level pair differences by tissue.

    Parameters
    ----------
    detail : pandas.DataFrame
        Matched feature-level pair details oriented as query versus comparator.

    Returns
    -------
    pandas.DataFrame
        Tissue-level support, means, and signed/absolute residual statistics.
    """
    if detail.empty:
        return pd.DataFrame(columns=["tissue", "matched_feature_count", "query_mean", "comparator_mean", "mean_difference", "mean_absolute_difference", "max_absolute_difference"])
    return detail.groupby("tissue", as_index=False).agg(
        matched_feature_count=("feature_id", "size"),
        query_mean=("value_a", "mean"),
        comparator_mean=("value_b", "mean"),
        mean_difference=("signed_difference_a_minus_b", "mean"),
        mean_absolute_difference=("absolute_difference", "mean"),
        max_absolute_difference=("absolute_difference", "max"),
    )


def call_detail(binary: pd.DataFrame, query: str, comparator: str, contract: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Partition fingerprint calls into query-only, comparator-only, and shared.

    Parameters
    ----------
    binary : pandas.DataFrame
        Compound-by-feature call matrix in which calls equal ``1.0``.
    query, comparator : str
        Compound row labels.
    contract : pandas.DataFrame
        Feature metadata containing target and tissue fields.

    Returns
    -------
    dict of str to pandas.DataFrame
        Metadata tables for the three disjoint call-status sets.
    """
    metadata = contract.set_index("feature_id")
    query_calls = set(binary.columns[binary.loc[query].eq(1.0)])
    comparator_calls = set(binary.columns[binary.loc[comparator].eq(1.0)])

    def rows(features: set[str], status: str) -> pd.DataFrame:
        """Attach contract metadata and one status to a feature set.

        Parameters
        ----------
        features : set of str
            Feature identifiers in one call partition.
        status : str
            Call-status label assigned to all rows.

        Returns
        -------
        pandas.DataFrame
            Sorted feature metadata with ``call_status``.
        """
        if not features:
            return pd.DataFrame(columns=["feature_id", "target", "tissue", "call_status"])
        frame = metadata.reindex(sorted(features)).reset_index()[["feature_id", "target", "tissue"]]
        frame["call_status"] = status
        return frame

    return {
        "query_only": rows(query_calls - comparator_calls, "QUERY_ONLY"),
        "comparator_only": rows(comparator_calls - query_calls, "COMPARATOR_ONLY"),
        "shared": rows(query_calls & comparator_calls, "SHARED"),
    }


def pairwise_table_bundle(detail: pd.DataFrame, binary: pd.DataFrame, query: str, comparator: str, contract: pd.DataFrame, pair_metrics: pd.Series) -> dict[str, pd.DataFrame]:
    """Build the standard publication-table bundle for one query pair.

    Parameters
    ----------
    detail : pandas.DataFrame
        Feature-level continuous pair detail.
    binary : pandas.DataFrame
        Fingerprint call matrix.
    query, comparator : str
        Oriented compound labels.
    contract : pandas.DataFrame
        Frozen feature metadata.
    pair_metrics : pandas.Series
        Persisted pair-level coverage and similarity metrics.

    Returns
    -------
    dict of str to pandas.DataFrame
        Named target, tissue, coordinate, call, and coverage tables.
    """
    targets = target_summary(detail)
    tissues = tissue_summary(detail)
    calls = call_detail(binary, query, comparator, contract)
    # Shared strength uses the weaker absolute member of each target pair so a
    # large value from only one compound cannot dominate the shared ranking.
    top_shared = targets.assign(shared_strength=np.minimum(targets["query_mean"].abs(), targets["comparator_mean"].abs())).sort_values("shared_strength", ascending=False).head(20)
    query_higher = targets.sort_values("mean_difference", ascending=False).head(20)
    comparator_higher = targets.sort_values("mean_difference", ascending=True).head(20)
    absolute = targets.sort_values("mean_absolute_difference", ascending=False).head(20)
    coordinates = detail.sort_values("absolute_difference", ascending=False).head(30)
    coverage_columns = [column for column in pair_metrics.index if column in {
        "matched_features", "matched_targets", "support_shared_features", "support_union_features", "support_jaccard",
        "rms_common_rhr", "cosine_common_rhr", "pearson_common_rhr", "spearman_common_rhr",
        "alpha001_call_jaccard", "alpha0001_call_jaccard",
    }]
    coverage = pd.DataFrame([{column: pair_metrics[column] for column in coverage_columns}])
    return {
        "TOP_SHARED_TARGETS": top_shared,
        "TOP_KETAMINE_HIGHER_TARGETS": query_higher,
        "TOP_DRUG_HIGHER_TARGETS": comparator_higher,
        "TOP_ABSOLUTE_RESIDUAL_TARGETS": absolute,
        "TOP_SHARED_TARGET_TISSUE_COORDINATES": coordinates,
        "TOP_KETAMINE_ONLY_FINGERPRINT_CALLS": calls["query_only"],
        "TOP_DRUG_ONLY_FINGERPRINT_CALLS": calls["comparator_only"],
        "SHARED_FINGERPRINT_CALLS": calls["shared"],
        "TOP_DIFFERING_TISSUES": tissues.sort_values("mean_absolute_difference", ascending=False).head(20),
        "COVERAGE_AND_SUPPORT_SUMMARY": coverage,
    }
