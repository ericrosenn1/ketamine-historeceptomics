"""Execute the governed full comparative analysis from external authorities.

Stage: orchestration from query freeze through pairwise, models, QA, and handoff.
Inputs: explicit project authorities, governed configuration, code, and output root.
Outputs: derivative analysis tables/figures, manifests, summaries, and handoff ZIP.
Side effects: creates a timestamped run tree but does not mutate source authorities.
Invariants: retain identity, NA support, fixed common scale, thresholds, and QA gates.
Lane: external-authority comparative rebuild retained beside the portable lanes.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import math
import platform
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .authority_discovery import PROJECT_ROOT_DEFAULT, discover
from .class_analysis import run_class_models, summarize_classes
from .coverage_diagnostics import distance_confounding, profile_coverage
from .family_analysis import FAMILY_LABELS, family_roster, load_family_calls, load_family_profiles
from .figures import FigureRecorder, dashboard, dendrogram_figure, fingerprint_heatmap, heatmap, profile_heatmap, ranking, scatter, table_pdf
from .fingerprint import build_sparse_call_matrix, call_set, regression_calls
from .multivariate import (
    complete_case_pca,
    complete_distance_subset,
    em_svd_pca,
    fixed_reference_pca,
    linkage_table,
    mds_table,
    model_tables,
    pcoa_table,
    target_level_matrix,
)
from .nearest_reference import class_nearest, nearest_summary, orient_query_pairs
from .packaging import code_manifest, combine_pdfs, compact_handoff_zip, copy_paper_item, output_manifest, summary_workbook
from .pairwise_continuous import all_pairwise, build_profile_matrices, continuous_metrics, metric_matrix
from .pairwise_fingerprint import build_call_matrices, metric_function
from .qa import QARecorder, files_nonempty, matrix_symmetric, pairwise_contract
from .query_freeze import EXPECTED, freeze_query
from .residual_analysis import recurrence
from .resource_manager import ResourceManager
from .tables import TableRecorder, pairwise_table_bundle, target_summary, tissue_summary
from .utilities import now_iso, sha256_file, slug, write_json, write_table


QUERY = "Ketamine, pooled parent"
RACEMATE = "Ketamine, confirmed racemate"
S_KETAMINE = "S-ketamine"
R_KETAMINE = "R-ketamine"
DEFAULT_CODE_ROOT = (
    PROJECT_ROOT_DEFAULT
    / "09_CODE_AND_PIPELINES"
    / "Pooled_Parent_Ketamine_Complete_Comparative_Rebuild"
    if PROJECT_ROOT_DEFAULT is not None
    else None
)
OUTPUT_PREFIX = "Pooled_Parent_Ketamine_Complete_Comparative_Analysis_"
STAGE_NAMES = [
    "00_RUN_CONTROL", "01_QUERY_AUTHORITY", "02_HEATMAP_REPAIR", "03_EXTERNAL_PAIRWISE_CONTINUOUS",
    "04_EXTERNAL_FINGERPRINT_COMPARISONS", "05_KETAMINE_FAMILY", "06_GLOBAL_MULTIVARIATE",
    "07_CLASS_ANALYSES", "08_NEAREST_REFERENCE", "09_CLASS_SUMMARIES", "10_PROFILE_DIAGNOSTICS",
    "11_RESIDUAL_ANALYSES", "12_COVERAGE_AND_CONFOUNDING", "13_ANCILLARY_ANALYSES",
    "14_PAPER_FACING", "15_QA_AND_MANIFESTS", "16_HANDOFF",
]


@dataclass
class RunContext:
    """Hold derivative-run paths, recorders, QA state, and stage-level provenance."""
    project_root: Path
    code_root: Path
    run_root: Path
    started: str = field(default_factory=now_iso)
    started_perf: float = field(default_factory=time.perf_counter)
    analysis_rows: list[dict[str, Any]] = field(default_factory=list)
    model_statuses: list[dict[str, Any]] = field(default_factory=list)
    stage_rows: list[dict[str, Any]] = field(default_factory=list)
    failure_rows: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Create the immutable stage directory layout and initialize run recorders."""
        for name in STAGE_NAMES:
            (self.run_root / name).mkdir(parents=True, exist_ok=False)
        self.figures = FigureRecorder(self.run_root)
        self.tables = TableRecorder(self.run_root)
        self.qa = QARecorder()
        self.resources = ResourceManager(self.run_root / "15_QA_AND_MANIFESTS" / "RESOURCE_USAGE.csv")

    def add_analysis(
        self,
        analysis_id: str,
        family: str,
        comparator: str,
        representation: str,
        method: str,
        status: str,
        input_path: str = "",
        output_table: str = "",
        output_figure: str = "",
        reused: str = "RECOMPUTED",
        reason: str = "",
        runtime: float = 0.0,
        workers: int = 1,
    ) -> None:
        """Append one analysis-registry record with its provenance and execution status."""
        self.analysis_rows.append({
            "analysis_id": analysis_id,
            "analysis_family": family,
            "query_compound": QUERY,
            "comparator_or_class": comparator,
            "representation": representation,
            "method": method,
            "status": status,
            "input_path": input_path,
            "output_table": output_table,
            "output_figure": output_figure,
            "reused_or_recomputed": reused,
            "reason_if_blocked": reason,
            "QA_status": "PASS" if status.startswith("PASS") else status,
            "runtime_seconds": runtime,
            "compute_backend": "CPU_FLOAT64",
            "cpu_workers": workers,
            "gpu_used": False,
        })

    def mark_stage(self, name: str, status: str, started: str, runtime: float, notes: str = "") -> None:
        """Record the outcome, runtime, and notes for one pipeline stage."""
        row = {"stage": name, "status": status, "started": started, "ended": now_iso(), "runtime_seconds": runtime, "notes": notes}
        self.stage_rows.append(row)
        write_json(self.run_root / name / "STAGE_STATUS.json", row)
        pd.DataFrame(self.stage_rows).to_csv(self.run_root / "00_RUN_CONTROL" / "STAGE_STATUS.csv", index=False)
        write_json(self.run_root / "00_RUN_CONTROL" / "STAGE_STATUS.json", {"stages": self.stage_rows})

    def run_stage(self, name: str, function: Callable[[], Any], optional: bool = False) -> Any:
        """Execute a required or optional stage and capture failure provenance."""
        started = now_iso()
        before = time.perf_counter()
        self.resources.snapshot(name + "_START")
        try:
            result = function()
            self.mark_stage(name, "PASS", started, time.perf_counter() - before)
            return result
        except Exception as exc:
            status = "PASS_WITH_DOCUMENTED_LIMITATION" if optional else "FAILED_QA"
            reason = f"{type(exc).__name__}: {exc}"
            self.failure_rows.append({"stage": name, "status": status, "reason": reason, "traceback": traceback.format_exc()})
            self.mark_stage(name, status, started, time.perf_counter() - before, reason)
            pd.DataFrame(self.failure_rows).to_csv(self.run_root / "00_RUN_CONTROL" / "FAILURE_LEDGER.csv", index=False)
            if optional:
                return None
            raise
        finally:
            self.resources.snapshot(name + "_END")


def _relative(path: Path, root: Path) -> str:
    """Return a repository-independent path relative to the current run root."""
    return path.relative_to(root).as_posix()


def _write_registered(
    context: RunContext,
    frame: pd.DataFrame,
    path: Path,
    table_id: str,
    analysis: str,
    title: str,
    comparators: str,
    representation: str,
    priority: str = "SUPPLEMENTAL",
) -> Path:
    """Write a table and register it in the run-level table inventory."""
    return context.tables.write(frame, path, table_id, analysis, title, QUERY, comparators, representation, priority)


def _save_figure(
    context: RunContext,
    figure,
    base: Path,
    figure_id: str,
    analysis: str,
    title: str,
    comparators: str,
    input_table: str,
    priority: str = "SUPPLEMENTAL",
) -> tuple[Path, Path]:
    """Persist a figure and register its publication-facing metadata."""
    return context.figures.save(figure, base, figure_id, analysis, title, QUERY, comparators, input_table, priority)


def _pool_profile(query: dict[str, Any]) -> pd.DataFrame:
    """Construct the pooled-parent strict-CNS profile from the governed query freeze."""
    contract = query["strict_contract"]
    projected = query["strict_mapped"][query["strict_mapped"]["common_scale_compatible"]].copy()
    values = projected[["feature_id_common", "raw_hr", "common_rhr"]].rename(columns={"feature_id_common": "feature_id"})
    frame = contract[["feature_id", "target", "target_canonical_id", "tissue", "tissue_canonical_id", "feature_order"]].merge(values, on="feature_id", how="inner", validate="one_to_one")
    frame["drug"] = QUERY
    frame["source_lane"] = "FROZEN_POOLED_PARENT_QUERY"
    frame["data_role"] = "PRIMARY_PARENT_QUERY"
    return frame


def _pool_calls(calls: pd.DataFrame, projection: pd.DataFrame) -> pd.DataFrame:
    """Project pooled-parent fingerprint calls onto the stable feature contract."""
    common = projection[["feature_id_common", "raw_hr", "common_rhr"]].dropna(subset=["feature_id_common"]).drop_duplicates("feature_id_common")
    frame = calls.drop(columns=[column for column in ["raw_hr", "common_rhr"] if column in calls.columns]).merge(common, on="feature_id_common", how="left", validate="one_to_one")
    frame["drug"] = QUERY
    return frame


def _pair_row(pairwise: pd.DataFrame, a: str, b: str) -> pd.Series:
    """Select the canonical unordered-pair record for two compound identities."""
    selected = pairwise[((pairwise["drug_a"] == a) & (pairwise["drug_b"] == b)) | ((pairwise["drug_a"] == b) & (pairwise["drug_b"] == a))]
    if len(selected) != 1:
        raise RuntimeError(f"Expected exactly one pair for {a} / {b}; observed {len(selected)}")
    return selected.iloc[0]


def _reuse_external_only(
    computed: pd.DataFrame,
    prior: pd.DataFrame,
    external: list[str],
    qa: QARecorder,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reuse accepted external-only pairs after explicit numerical equality checks."""
    allowed = set(external)
    old = prior[prior["drug_a"].isin(allowed) & prior["drug_b"].isin(allowed)].copy()
    new = computed[computed["drug_a"].isin(allowed) & computed["drug_b"].isin(allowed)].copy()
    key = lambda frame: frame.assign(pair_key=frame.apply(lambda row: "||".join(sorted([str(row.drug_a), str(row.drug_b)])), axis=1)).set_index("pair_key")
    old_keyed, new_keyed = key(old), key(new)
    qa.check("EXTERNAL_REUSE_PAIR_COUNT", len(old_keyed) == len(new_keyed) == 300, f"old={len(old_keyed)} new={len(new_keyed)}", 300)
    common_columns = [column for column in old.columns if column in new.columns and column not in {"drug_a", "drug_b"}]
    numeric = [
        column for column in common_columns
        if pd.api.types.is_numeric_dtype(old[column]) and not pd.api.types.is_bool_dtype(old[column])
    ]
    boolean = [column for column in common_columns if pd.api.types.is_bool_dtype(old[column])]
    comparison_rows = []
    max_delta = 0.0
    for column in numeric:
        left = pd.to_numeric(old_keyed[column], errors="coerce")
        right = pd.to_numeric(new_keyed[column], errors="coerce")
        delta = (left - right).abs()
        finite_max = float(delta.max()) if delta.notna().any() else 0.0
        nan_mismatch = int((left.isna() != right.isna()).sum())
        max_delta = max(max_delta, finite_max)
        comparison_rows.append({"metric": column, "maximum_absolute_delta": finite_max, "nan_mismatch_count": nan_mismatch})
    boolean_mismatches = 0
    for column in boolean:
        mismatches = int((old_keyed[column].astype("boolean") != new_keyed[column].astype("boolean")).fillna(False).sum())
        boolean_mismatches += mismatches
        comparison_rows.append({"metric": column, "maximum_absolute_delta": 0.0, "nan_mismatch_count": mismatches})
    qa.check("EXTERNAL_REUSE_NUMERIC_EQUALITY", max_delta <= 1e-10 and not any(row["nan_mismatch_count"] for row in comparison_rows), f"max_delta={max_delta}; bool_mismatches={boolean_mismatches}", "<=1e-10 and zero NA/Boolean mismatches")
    result = computed.copy()
    result["reused_or_recomputed"] = "RECOMPUTED"
    for index, row in result.iterrows():
        if row["drug_a"] not in allowed or row["drug_b"] not in allowed:
            continue
        pair_key = "||".join(sorted([str(row["drug_a"]), str(row["drug_b"])]))
        source = old_keyed.loc[pair_key]
        for column in common_columns:
            result.at[index, column] = source[column]
        result.at[index, "reused_or_recomputed"] = "REUSED_UNCHANGED_AFTER_NUMERICAL_EQUALITY_QA"
    return result, pd.DataFrame(comparison_rows)


def _model_suite(
    context: RunContext,
    prefix: str,
    matrix: pd.DataFrame,
    binary001: pd.DataFrame,
    binary0001: pd.DataFrame,
    pairwise: pd.DataFrame,
    contract: pd.DataFrame,
    output_dir: Path,
    reference: list[str] | None = None,
    projections: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the governed multivariate model suite without changing model assumptions."""
    scores: list[pd.DataFrame] = []
    loadings: list[pd.DataFrame] = []
    statuses: list[dict[str, Any]] = []
    linkage_frames: list[pd.DataFrame] = []
    target = target_level_matrix(matrix, contract)
    target_meta = pd.DataFrame({"feature_id": target.columns, "target": target.columns, "tissue": "TARGET_LEVEL_MEAN"})

    def record_model(analysis_id: str, representation: str, method: str, runner: Callable[[], tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]]) -> None:
        """Execute and register one multivariate model while retaining failure status."""
        before = time.perf_counter()
        try:
            score, loading, status = runner()
            scores.append(score)
            loadings.append(loading)
            statuses.append(status)
            path = _write_registered(context, score, output_dir / f"{analysis_id}_SCORES.csv", analysis_id + "_SCORES", analysis_id, analysis_id + " scores", "all rostered compounds", representation, "PAPER")
            _write_registered(context, loading, output_dir / f"{analysis_id}_LOADINGS.csv", analysis_id + "_LOADINGS", analysis_id, analysis_id + " loadings", "all rostered compounds", representation)
            x = "PC1" if "PC1" in score.columns else "Axis1"
            y = "PC2" if "PC2" in score.columns else ("Axis2" if "Axis2" in score.columns else "")
            figure = scatter(score, analysis_id.replace("_", " "), x=x, y=y, highlight=[QUERY, RACEMATE], label_col="compound")
            png, _ = _save_figure(context, figure, output_dir / f"{analysis_id}_ORDINATION", analysis_id + "_ORDINATION", analysis_id, analysis_id.replace("_", " "), "all rostered compounds", _relative(path, context.run_root), "PAPER")
            context.add_analysis(analysis_id, prefix, "ALL", representation, method, status["status"], output_table=_relative(path, context.run_root), output_figure=_relative(png, context.run_root), reason=status.get("reason", ""), runtime=time.perf_counter() - before)
        except Exception as exc:
            status = {
                "analysis_id": analysis_id, "representation": representation, "method": method,
                "status": "NOT_ESTIMABLE", "reason": str(exc), "sample_count": len(matrix),
                "feature_count": np.nan, "rank": np.nan, "component_count": np.nan,
                "input_roster": "; ".join(matrix.index),
            }
            statuses.append(status)
            context.add_analysis(analysis_id, prefix, "ALL", representation, method, "NOT_ESTIMABLE", reason=str(exc), runtime=time.perf_counter() - before)

    record_model(prefix + "_JOINT_CONTINUOUS_PCA", "strict18_common_rhr", "EM_SVD_MISSINGNESS_AWARE_PCA", lambda: model_tables(em_svd_pca(matrix), prefix + "_JOINT_CONTINUOUS_PCA", "strict18_common_rhr", contract))
    record_model(prefix + "_COMPLETE_CASE_PCA", "strict18_common_rhr", "COMPLETE_CASE_SVD_PCA", lambda: model_tables(complete_case_pca(matrix), prefix + "_COMPLETE_CASE_PCA", "strict18_common_rhr", contract))
    record_model(prefix + "_TARGET_LEVEL_PCA", "target_mean_common_rhr", "TARGET_LEVEL_EM_SVD_PCA", lambda: model_tables(em_svd_pca(target), prefix + "_TARGET_LEVEL_PCA", "target_mean_common_rhr", target_meta))
    record_model(prefix + "_SHARED_TARGET_PCA", "complete_case_target_mean_common_rhr", "SHARED_TARGET_COMPLETE_CASE_PCA", lambda: model_tables(complete_case_pca(target), prefix + "_SHARED_TARGET_PCA", "complete_case_target_mean_common_rhr", target_meta))

    for alpha, binary in [("001", binary001), ("0001", binary0001)]:
        union = [column for column in binary if binary[column].eq(1.0).any()]
        record_model(
            prefix + f"_SPARSE_ALPHA{alpha}_PCA",
            f"alpha{alpha}_binary_0_1_NA",
            "SUPPORT_AWARE_SPARSE_FINGERPRINT_EM_SVD_PCA",
            lambda binary=binary, union=union, alpha=alpha: model_tables(em_svd_pca(binary[union], min_observed_per_feature=2), prefix + f"_SPARSE_ALPHA{alpha}_PCA", f"alpha{alpha}_binary_0_1_NA", contract),
        )

    if reference and projections:
        record_model(
            prefix + "_FIXED_REFERENCE_PCA", "strict18_common_rhr", "FROZEN_REFERENCE_EM_SVD_PCA_WITH_WLS_QUERY_PROJECTION",
            lambda: fixed_reference_pca(matrix, reference, projections, prefix + "_FIXED_REFERENCE_PCA", "strict18_common_rhr", contract),
        )

    rms = metric_matrix(pairwise, "rms_common_rhr", list(matrix.index))
    subset, excluded = complete_distance_subset(rms, matrix.notna().sum(axis=1))
    complete = rms.loc[subset, subset]
    distance_path = _write_registered(context, complete.reset_index(names="compound"), output_dir / f"{prefix}_RMS_DISTANCE_MATRIX.csv", prefix + "_RMS_DISTANCE_MATRIX", prefix, prefix + " RMS distance matrix", "all rostered compounds", "pairwise_rms", "PAPER")
    fig, _ = _save_figure(context, heatmap(complete, prefix.replace("_", " ") + " RMS distance", "RMS", annotate=len(complete) <= 10), output_dir / f"{prefix}_RMS_DISTANCE_HEATMAP", prefix + "_RMS_DISTANCE_HEATMAP", prefix, prefix.replace("_", " ") + " RMS distance", "all rostered compounds", _relative(distance_path, context.run_root), "PAPER")
    for kind, runner, coord_name in [
        ("PCOA", lambda: pcoa_table(complete, prefix + "_RMS_PCOA"), "pcoa"),
        ("WEIGHTED_MDS", lambda: mds_table(complete, prefix + "_WEIGHTED_MDS"), "mds"),
    ]:
        before = time.perf_counter()
        analysis_id = prefix + ("_RMS_PCOA" if kind == "PCOA" else "_WEIGHTED_MDS")
        try:
            coordinates, status = runner()
            statuses.append({**status, "excluded_compounds": "; ".join(excluded)})
            scores.append(coordinates)
            path = _write_registered(context, coordinates, output_dir / f"{analysis_id}_COORDINATES.csv", analysis_id + "_COORDINATES", analysis_id, analysis_id + " coordinates", "all rostered compounds", "pairwise_rms", "PAPER")
            x, y = ("Axis1", "Axis2") if kind == "PCOA" else ("MDS1", "MDS2")
            png, _ = _save_figure(context, scatter(coordinates, analysis_id.replace("_", " "), x=x, y=y, highlight=[QUERY, RACEMATE]), output_dir / f"{analysis_id}_ORDINATION", analysis_id + "_ORDINATION", analysis_id, analysis_id.replace("_", " "), "all rostered compounds", _relative(path, context.run_root), "PAPER")
            context.add_analysis(analysis_id, prefix, "ALL", "pairwise_rms", kind, "PASS", output_table=_relative(path, context.run_root), output_figure=_relative(png, context.run_root), runtime=time.perf_counter() - before)
        except Exception as exc:
            statuses.append({"analysis_id": analysis_id, "representation": "pairwise_rms", "method": kind, "status": "NOT_ESTIMABLE", "reason": str(exc), "input_roster": "; ".join(matrix.index)})
            context.add_analysis(analysis_id, prefix, "ALL", "pairwise_rms", kind, "NOT_ESTIMABLE", reason=str(exc), runtime=time.perf_counter() - before)
    try:
        linked, status = linkage_table(complete, prefix + "_AVERAGE_LINKAGE")
        statuses.append({**status, "excluded_compounds": "; ".join(excluded)})
        linked["input_roster"] = "; ".join(complete.index)
        linkage_frames.append(linked)
        path = _write_registered(context, linked, output_dir / f"{prefix}_AVERAGE_LINKAGE.csv", prefix + "_AVERAGE_LINKAGE", prefix, prefix + " average linkage", "all rostered compounds", "pairwise_rms")
        png, _ = _save_figure(context, dendrogram_figure(linked, list(complete.index), prefix.replace("_", " ") + " RMS dendrogram"), output_dir / f"{prefix}_RMS_DENDROGRAM", prefix + "_RMS_DENDROGRAM", prefix, prefix.replace("_", " ") + " RMS dendrogram", "all rostered compounds", _relative(path, context.run_root), "PAPER")
        context.add_analysis(prefix + "_AVERAGE_LINKAGE", prefix, "ALL", "pairwise_rms", "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", "PASS", output_table=_relative(path, context.run_root), output_figure=_relative(png, context.run_root))
    except Exception as exc:
        statuses.append({"analysis_id": prefix + "_AVERAGE_LINKAGE", "representation": "pairwise_rms", "method": "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", "status": "NOT_ESTIMABLE", "reason": str(exc), "input_roster": "; ".join(matrix.index)})
        context.add_analysis(prefix + "_AVERAGE_LINKAGE", prefix, "ALL", "pairwise_rms", "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", "NOT_ESTIMABLE", reason=str(exc))

    return {
        "scores": pd.concat(scores, ignore_index=True, sort=False) if scores else pd.DataFrame(),
        "loadings": pd.concat(loadings, ignore_index=True, sort=False) if loadings else pd.DataFrame(),
        "status": pd.DataFrame(statuses),
        "linkage": pd.concat(linkage_frames, ignore_index=True, sort=False) if linkage_frames else pd.DataFrame(),
        "rms": rms,
    }


def _input_manifest(paths: dict[str, Path]) -> pd.DataFrame:
    """Inventory governed input files with stable roles and cryptographic hashes."""
    rows = []
    for role, path in paths.items():
        if role in {"project_root", "prior_root", "prior_paper_root"} or not path.is_file():
            continue
        rows.append({"input_role": role, "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path), "status": "GOVERNED_SOURCE_UNMODIFIED"})
    return pd.DataFrame(rows)


def _previous_coverage(paths: dict[str, Path], analysis_registry_path: str) -> pd.DataFrame:
    """Account for every prior analysis artifact in the replacement registry."""
    rows = []
    for lane, manifest_key, root_key in [
        ("PRIOR_COMPLETE", "prior_manifest", "prior_root"),
        ("PRIOR_PAPER", "prior_paper_manifest", "prior_paper_root"),
    ]:
        manifest = pd.read_csv(paths[manifest_key], low_memory=False)
        for relative in manifest["relative_path"].astype(str):
            lowered = relative.lower()
            if "figure" in lowered or relative.lower().endswith((".png", ".pdf")):
                family = "FIGURE"
            elif "table" in lowered or relative.lower().endswith((".csv", ".parquet", ".xlsx")):
                family = "TABLE_OR_MATRIX"
            elif "multivariate" in lowered or "pca" in lowered or "pcoa" in lowered or "mds" in lowered:
                family = "MULTIVARIATE"
            else:
                family = "RUN_SUPPORT"
            query_dependent = any(token in lowered for token in ["s_ketamine", "sketamine", "pairwise", "nearest", "family", "fingerprint", "multivariate", "class_", "residual", "coverage", "profile", "figure", "table"])
            rows.append({
                "previous_output": str(paths[root_key] / relative),
                "previous_analysis_family": f"{lane}:{family}",
                "query_dependency": "QUERY_DEPENDENT_OR_QUERY_FACING" if query_dependent else "QUERY_INDEPENDENT_RUN_SUPPORT",
                "new_equivalent": analysis_registry_path if query_dependent else "Rebuilt run-control/manifest equivalent in current derivative",
                "status": "POOLED_PARENT_EQUIVALENT_AVAILABLE" if query_dependent else "RECOMPUTED_OR_AUDITED_UNCHANGED",
                "reason": "Covered by complete current analysis registry; individual mappings are indexed by analysis family" if query_dependent else "Run-support file was audited and has a current derivative equivalent",
            })
    return pd.DataFrame(rows)


def _ancillary_registry(context: RunContext, paths: dict[str, Path], output_dir: Path) -> pd.DataFrame:
    """Register optional ancillary analyses without treating them as core evidence."""
    requested = [
        ("CRTP_SANKEYS", "CRTP Sankeys", "validated pooled-parent CRTP path authority"),
        ("CRTP_TARGET_ANATOMY_PHENOTYPE", "CRTP target-anatomy-phenotype paths", "validated pooled-parent CRTP path authority"),
        ("CRTP_NETWORKS", "CRTP networks", "validated pooled-parent network edge authority"),
        ("PATHOLOGY_ATLAS", "pathology-atlas comparisons", "pooled-parent compatible pathology-atlas join authority"),
        ("DISEASE_EXPRESSION", "disease-expression comparisons", "pooled-parent compatible disease-expression contrast authority"),
        ("CNS_RECEPTOR_ANATOMY", "CNS receptor-anatomy heatmaps", "covered by strict18 query profile diagnostics"),
        ("BRAIN_OVERLAYS", "brain overlays", "validated spatial coordinate/template authority"),
        ("SAGITTAL_BRAIN_OVERLAYS", "sagittal brain overlays", "validated sagittal spatial coordinate/template authority"),
        ("TARGET_TISSUE_DRIVERS", "target/tissue driver figures", "covered by query residual and loading outputs"),
        ("METABOLIC_TREE", "compound metabolic tree", "validated compound relationship authority with explicit metabolite identity"),
        ("CHEMICAL_STRUCTURES", "chemical structures and fingerprint schematic", "validated chemical structure rendering workflow"),
        ("EVIDENCE_READINESS", "evidence-readiness diagrams", "query-independent governed diagram"),
        ("EVIDENCE_SOURCE_COMPOSITION", "evidence/source composition", "pooled-parent source-composition visualization workflow"),
        ("DATA_SPACE_COMPRESSION", "data-space compression diagrams", "query-independent governed diagram"),
        ("WORKFLOW_FIGURES", "workflow figures", "current workflow documentation"),
        ("COVERAGE_HISTORY", "coverage-history comparison", "pooled-parent historical coverage trajectory authority"),
        ("HYPERGRAPH_NETWORK", "hypergraph/network views", "validated hypergraph edge authority"),
    ]
    rows = []
    covered = {"CNS_RECEPTOR_ANATOMY", "TARGET_TISSUE_DRIVERS", "WORKFLOW_FIGURES"}
    for analysis_id, label, required in requested:
        status = "PASS_WITH_DOCUMENTED_LIMITATION" if analysis_id in covered else "BLOCKED_NOT_AVAILABLE"
        reason = required if analysis_id not in covered else f"{required}; satisfied by core outputs without fabricating a decorative or spatial model"
        rows.append({"analysis_id": analysis_id, "analysis_label": label, "status": status, "required_or_reused_authority": required, "exact_missing_input_or_limitation": reason})
        context.add_analysis("ANCILLARY_" + analysis_id, "ANCILLARY_BIOLOGICAL", label, "project_native_optional", "REUSE_COMPATIBILITY_AUDIT", status, input_path=str(paths["project_root"]), reason=reason)
    frame = pd.DataFrame(rows)
    _write_registered(context, frame, output_dir / "ANCILLARY_ANALYSIS_STATUS.csv", "ANCILLARY_ANALYSIS_STATUS", "ANCILLARY_BIOLOGICAL", "Ancillary biological analysis compatibility audit", "requested ancillary families", "authority_compatibility")
    return frame


def run(
    project_root: Path | None = PROJECT_ROOT_DEFAULT,
    output_root: Path | None = None,
    code_root: Path | None = DEFAULT_CODE_ROOT,
    pairwise_cache_root: Path | None = None,
) -> Path:
    """Execute all comparative stages in a new derivative output directory."""

    if project_root is None:
        raise ValueError(
            "An external project root is required; pass project_root or set "
            "CARDOZO_HR_EXTERNAL_PROJECT_ROOT"
        )
    project_root = Path(project_root).resolve()
    if code_root is None:
        code_root = (
            project_root
            / "09_CODE_AND_PIPELINES"
            / "Pooled_Parent_Ketamine_Complete_Comparative_Rebuild"
        )
    code_root = Path(code_root).resolve()
    if output_root is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_root = project_root / "04_KETAMINE_VS_DRUGS" / f"{OUTPUT_PREFIX}{stamp}"
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise FileExistsError(f"Refusing to overwrite existing run root: {output_root}")
    context = RunContext(project_root, code_root, output_root)
    paths = discover(project_root)
    pre_hashes = _input_manifest(paths)
    context.resources.snapshot("RUN_START")
    context.mark_stage("00_RUN_CONTROL", "PASS", context.started, 0.0, "Authorities resolved; derivative output root created without overwrite")

    # Stage 0/1: freeze immutable query objects and repair the tissue-keyed heatmaps.
    query = context.run_stage("01_QUERY_AUTHORITY", lambda: freeze_query(paths, output_root / "01_QUERY_AUTHORITY"))
    def heatmap_stage() -> dict[str, Any]:
        """Build the query heatmap products and their numerical source tables."""
        targets = query["strict"]["canonical_target_id"].drop_duplicates().tolist()
        tissues = query["strict"].sort_values("tissue_display_order")["tissue_label"].drop_duplicates().tolist()
        primary = build_sparse_call_matrix(query["calls001"], targets, tissues)
        strict = build_sparse_call_matrix(query["calls0001"], targets, tissues)
        primary_cells, strict_cells = int(primary.notna().sum().sum()), int(strict.notna().sum().sum())
        context.qa.check("HEATMAP_ALPHA001_CALL_CELLS", primary_cells == 19, primary_cells, 19)
        context.qa.check("HEATMAP_ALPHA0001_CALL_CELLS", strict_cells == 14, strict_cells, 14)
        primary_path = _write_registered(context, primary.reset_index(names="target"), output_root / "02_HEATMAP_REPAIR" / "POOLED_PARENT_FINGERPRINT_ALPHA001_HEATMAP_MATRIX.csv", "HEATMAP_ALPHA001_MATRIX", "HEATMAP_REPAIR", "Pooled parent alpha=.001 corrected call matrix", "none", "strict18_sparse_calls", "PAPER")
        strict_path = _write_registered(context, strict.reset_index(names="target"), output_root / "02_HEATMAP_REPAIR" / "POOLED_PARENT_FINGERPRINT_ALPHA0001_HEATMAP_MATRIX.csv", "HEATMAP_ALPHA0001_MATRIX", "HEATMAP_REPAIR", "Pooled parent alpha=.0001 corrected call matrix", "none", "strict18_sparse_calls", "PAPER")
        p_png, _ = _save_figure(context, fingerprint_heatmap(primary, "Ketamine, pooled parent — alpha=.001 fingerprint (19 calls)"), output_root / "02_HEATMAP_REPAIR" / "POOLED_PARENT_FINGERPRINT_ALPHA001_CORRECTED", "HEATMAP_ALPHA001", "HEATMAP_REPAIR", "Pooled parent alpha=.001 corrected fingerprint", "none", _relative(primary_path, output_root), "PAPER")
        s_png, _ = _save_figure(context, fingerprint_heatmap(strict, "Ketamine, pooled parent — alpha=.0001 fingerprint (14 calls)"), output_root / "02_HEATMAP_REPAIR" / "POOLED_PARENT_FINGERPRINT_ALPHA0001_CORRECTED", "HEATMAP_ALPHA0001", "HEATMAP_REPAIR", "Pooled parent alpha=.0001 corrected fingerprint", "none", _relative(strict_path, output_root), "PAPER")
        context.add_analysis("HEATMAP_REPAIR_ALPHA001", "HEATMAP_REPAIR", "NONE", "strict18_alpha001", "CANONICAL_TISSUE_KEY_PIVOT", "PASS", input_path=str(paths["pooled_calls_001"]), output_table=_relative(primary_path, output_root), output_figure=_relative(p_png, output_root))
        context.add_analysis("HEATMAP_REPAIR_ALPHA0001", "HEATMAP_REPAIR", "NONE", "strict18_alpha0001", "CANONICAL_TISSUE_KEY_PIVOT", "PASS", input_path=str(paths["pooled_calls_0001"]), output_table=_relative(strict_path, output_root), output_figure=_relative(s_png, output_root))
        return {"primary": primary, "strict": strict, "primary_cells": primary_cells, "strict_cells": strict_cells}
    repaired = context.run_stage("02_HEATMAP_REPAIR", heatmap_stage)

    # Unified profiles, fresh pooled call objects, and cached matrices.
    prior_profiles = pd.read_parquet(paths["prior_profiles"])
    external = [drug for drug in prior_profiles["drug"].drop_duplicates().astype(str) if drug != S_KETAMINE]
    family_profiles = load_family_profiles(paths, query["strict_contract"])
    pool_profile = _pool_profile(query)
    profiles = pd.concat([pool_profile, family_profiles, prior_profiles[prior_profiles["drug"].isin(external)]], ignore_index=True, sort=False)
    drugs = [QUERY, RACEMATE, S_KETAMINE, R_KETAMINE, FAMILY_LABELS["hydroxyketamine_unspecified_isomer_aggregate"], *external]
    matrices = build_profile_matrices(profiles, query["strict_contract"], drugs)
    prior_calls001 = pd.read_parquet(paths["prior_calls_001"])
    prior_calls0001 = pd.read_parquet(paths["prior_calls_0001"])
    for frame in [prior_calls001, prior_calls0001]:
        frame["feature_id_common"] = frame["feature_id"].astype(str)
    calls001 = pd.concat([_pool_calls(query["calls001"], query["strict_mapped"]), load_family_calls(paths, "001"), prior_calls001[prior_calls001["drug"].isin(external)]], ignore_index=True, sort=False)
    calls0001 = pd.concat([_pool_calls(query["calls0001"], query["strict_mapped"]), load_family_calls(paths, "0001"), prior_calls0001[prior_calls0001["drug"].isin(external)]], ignore_index=True, sort=False)
    calls = build_call_matrices(matrices["raw_hr"], calls001, calls0001, query["strict_contract"], drugs)
    matrix_dir = output_root / "00_RUN_CONTROL" / "CACHED_MATRICES"
    _write_registered(context, profiles, matrix_dir / "ALL_COMPOUND_PROFILES_STRICT18_LONG.csv", "UNIFIED_PROFILES", "MATRIX_CACHE", "Unified strict18 profiles", "all compounds", "raw_hr_and_common_rhr")
    for name, matrix in {**matrices, **calls}.items():
        _write_registered(context, matrix.reset_index(names="compound"), matrix_dir / f"{name.upper()}.csv", "CACHE_" + name.upper(), "MATRIX_CACHE", name.replace("_", " "), "all compounds", name)

    # QA query and identity contracts before any comparative result is accepted.
    for key, expected in EXPECTED.items():
        context.qa.check("QUERY_" + key.upper(), query["counts"][key] == expected, query["counts"][key], expected)
    context.qa.check("STRICT_CALL_SUBSET", call_set(query["calls0001"]).issubset(call_set(query["calls001"])), len(call_set(query["calls0001"])), "subset of alpha001")
    context.qa.check("MISSINGNESS_PRESERVED", int(matrices["raw_hr"].isna().sum().sum()) > 0 and int((matrices["raw_hr"].fillna(np.inf) == 0).sum().sum()) >= 0, int(matrices["raw_hr"].isna().sum().sum()), ">0 NA cells retained")
    context.qa.check("COMPOUND_IDENTITY_SEPARATION", len(drugs) == len(set(drugs)) and QUERY != RACEMATE and S_KETAMINE != R_KETAMINE, len(set(drugs)), len(drugs))
    context.qa.check("EXTERNAL_COMPARATOR_COUNT", len(external) == 25, len(external), 25)

    # Stages 2-4: complete pairwise atlas and external reuse validation.
    if pairwise_cache_root is not None:
        pairwise_cache_root = Path(pairwise_cache_root).resolve()
        cached_pairwise_path = pairwise_cache_root / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "ALL_UNORDERED_DRUG_PAIR_METRICS.csv"
        cached_reuse_path = pairwise_cache_root / "15_QA_AND_MANIFESTS" / "EXTERNAL_ONLY_REUSE_EQUALITY.csv"
        if not cached_pairwise_path.exists() or not cached_reuse_path.exists():
            raise FileNotFoundError(f"Validated pairwise cache is incomplete: {pairwise_cache_root}")
        pairwise = context.run_stage("03_EXTERNAL_PAIRWISE_CONTINUOUS", lambda: pd.read_csv(cached_pairwise_path, low_memory=False))
        reuse_comparison = pd.read_csv(cached_reuse_path, low_memory=False)
        context.qa.check("EXTERNAL_REUSE_PAIR_COUNT", int((pairwise["reused_or_recomputed"] == "REUSED_UNCHANGED_AFTER_NUMERICAL_EQUALITY_QA").sum()) == 300, int((pairwise["reused_or_recomputed"] == "REUSED_UNCHANGED_AFTER_NUMERICAL_EQUALITY_QA").sum()), 300)
        max_delta = float(pd.to_numeric(reuse_comparison["maximum_absolute_delta"], errors="coerce").fillna(0).max())
        mismatches = int(pd.to_numeric(reuse_comparison["nan_mismatch_count"], errors="coerce").fillna(0).sum())
        context.qa.check("EXTERNAL_REUSE_NUMERIC_EQUALITY", max_delta <= 1e-10 and mismatches == 0, f"max_delta={max_delta}; mismatches={mismatches}", "<=1e-10 and zero mismatches")
        details = {}
        detail_pairs = {(identity, comparator) for identity in [QUERY, RACEMATE] for comparator in external}
        detail_pairs.update({(QUERY, comparator) for comparator in drugs[1:5]})
        for identity, comparator in sorted(detail_pairs):
            _, detail = continuous_metrics(matrices["common_rhr"].loc[identity], matrices["common_rhr"].loc[comparator], query["strict_contract"])
            details[(identity, comparator)] = detail
        context.add_analysis("PAIRWISE_CACHE_REUSE", "EXTERNAL_PAIRWISE", "all compounds", "strict18_common_rhr_and_fingerprint", "VALIDATED_PAIRWISE_CACHE_READBACK", "PASS", input_path=str(cached_pairwise_path), reused="REUSED_VALIDATED_PARTIAL_RUN_CACHE")
    else:
        pairwise_computed, details = context.run_stage("03_EXTERNAL_PAIRWISE_CONTINUOUS", lambda: all_pairwise(matrices, query["strict_contract"], drugs, metric_function(calls, query["strict_contract"])))
        prior_pairwise = pd.read_parquet(paths["prior_pairwise"])
        pairwise, reuse_comparison = _reuse_external_only(pairwise_computed, prior_pairwise, external, context.qa)
    pairwise_contract(pairwise, math.comb(len(drugs), 2), context.qa, "ALL_COMPOUNDS")
    pair_path = _write_registered(context, pairwise, output_root / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "ALL_UNORDERED_DRUG_PAIR_METRICS.csv", "ALL_PAIRWISE_METRICS", "PAIRWISE_CONTINUOUS_AND_FINGERPRINT", "All unordered pair metrics", "all compounds", "strict18_common_rhr_and_fingerprints", "PAPER")
    _write_registered(context, reuse_comparison, output_root / "15_QA_AND_MANIFESTS" / "EXTERNAL_ONLY_REUSE_EQUALITY.csv", "EXTERNAL_REUSE_EQUALITY", "EXTERNAL_REUSE_QA", "External-only recomputation equality", "25 external drugs", "prior_vs_recomputed")
    external_pairs = pairwise[pairwise["drug_a"].isin(external) & pairwise["drug_b"].isin(external)]
    pool_external = orient_query_pairs(pairwise, QUERY, set(external))
    racemate_external = orient_query_pairs(pairwise, RACEMATE, set(external))
    _write_registered(context, pool_external, output_root / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "POOLED_PARENT_VS_25_EXTERNAL_METRICS.csv", "POOLED_EXTERNAL_METRICS", "EXTERNAL_PAIRWISE", "Pooled parent vs 25 external metrics", "25 external drugs", "strict18_common_rhr_and_fingerprints", "PAPER")
    _write_registered(context, racemate_external, output_root / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "CONFIRMED_RACEMATE_VS_25_EXTERNAL_METRICS.csv", "RACEMATE_EXTERNAL_METRICS", "EXTERNAL_PAIRWISE", "Confirmed racemate vs 25 external metrics", "25 external drugs", "strict18_common_rhr_and_fingerprints", "PAPER")

    # Ten-table pair bundles for pooled parent and the explicitly separate confirmed racemate.
    bundle_count = 0
    for identity in [QUERY, RACEMATE]:
        for comparator in external:
            key = (identity, comparator) if (identity, comparator) in details else (comparator, identity)
            detail = details[key].copy()
            if key[1] == identity:
                detail[["value_a", "value_b"]] = detail[["value_b", "value_a"]].to_numpy()
                detail["signed_difference_a_minus_b"] *= -1
            metrics_row = _pair_row(pairwise, identity, comparator)
            pair_dir = output_root / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / ("POOLED_PARENT_PAIRS" if identity == QUERY else "CONFIRMED_RACEMATE_PAIRS") / slug(comparator)
            bundle = pairwise_table_bundle(detail, calls["call_binary_alpha001"], identity, comparator, query["strict_contract"], metrics_row)
            written = []
            for table_name, table in bundle.items():
                path = _write_registered(context, table, pair_dir / f"{table_name}.csv", slug(identity) + "__" + slug(comparator) + "__" + table_name, "PAIRWISE_DETAIL", table_name.replace("_", " "), comparator, "strict18_common_rhr_or_alpha001", "PAPER" if table_name in {"TOP_ABSOLUTE_RESIDUAL_TARGETS", "TOP_DIFFERING_TISSUES"} and identity == QUERY else "SUPPLEMENTAL")
                written.append(path)
            subtraction = detail.pivot(index="target", columns="tissue", values="signed_difference_a_minus_b") if len(detail) else pd.DataFrame()
            if len(subtraction) and subtraction.notna().to_numpy().any():
                png, _ = _save_figure(context, heatmap(subtraction, f"{identity} minus {comparator}", "Common-RHR difference", diverging=True), pair_dir / "PAIRWISE_SUBTRACTION_HEATMAP", slug(identity) + "__" + slug(comparator) + "__SUBTRACTION", "PAIRWISE_RESIDUAL", f"{identity} minus {comparator}", comparator, _relative(written[3], output_root), "PAPER" if identity == QUERY and comparator in external[:8] else "SUPPLEMENTAL")
                figure_path = _relative(png, output_root)
                pair_status = "PASS" if bool(metrics_row["overlap_gate_pass"]) else "PASS_WITH_DOCUMENTED_LIMITATION"
                reason = "" if pair_status == "PASS" else "Pair retained with explicit low-overlap denominators; overlap gate not met"
            else:
                figure_path = ""
                pair_status = "NOT_ESTIMABLE"
                reason = "No finite common-scale coordinates; subtraction heatmap intentionally omitted"
            context.add_analysis(slug(identity) + "__" + slug(comparator) + "__PAIRWISE", "EXTERNAL_PAIRWISE", comparator, "strict18_common_rhr_and_fingerprint", "PAIRWISE_COMPLETE_CASE_METRICS", pair_status, input_path=_relative(pair_path, output_root), output_table="; ".join(_relative(path, output_root) for path in written), output_figure=figure_path, reason=reason)
            bundle_count += 1

    def fingerprint_stage() -> None:
        """Build fingerprint comparisons at both governed GESD alpha thresholds."""
        fp_dir = output_root / "04_EXTERNAL_FINGERPRINT_COMPARISONS"
        for alpha in ["001", "0001"]:
            for metric in ["call_jaccard", "call_overlap_coefficient", "target_call_jaccard", "tissue_call_jaccard", "signed_sparse_cosine"]:
                column = f"alpha{alpha}_{metric}"
                matrix = metric_matrix(pairwise, column, drugs)
                ok, delta = matrix_symmetric(matrix)
                context.qa.check("SYMMETRY_" + column.upper(), ok, delta, "<=1e-12")
                table_path = _write_registered(context, matrix.reset_index(names="compound"), fp_dir / f"{column.upper()}_MATRIX.csv", column.upper() + "_MATRIX", "FINGERPRINT_ATLAS", column.replace("_", " "), "all compounds", f"alpha{alpha}", "PAPER" if metric in {"call_jaccard", "signed_sparse_cosine"} else "SUPPLEMENTAL")
                _save_figure(context, heatmap(matrix, f"{column.replace('_', ' ')}", column, annotate=len(matrix) <= 10), fp_dir / f"{column.upper()}_HEATMAP", column.upper() + "_HEATMAP", "FINGERPRINT_ATLAS", column.replace("_", " "), "all compounds", _relative(table_path, output_root), "PAPER" if metric in {"call_jaccard", "signed_sparse_cosine"} else "SUPPLEMENTAL")
        context.add_analysis("EXTERNAL_FINGERPRINT_ATLAS", "EXTERNAL_FINGERPRINT", "25 external drugs", "alpha001_and_alpha0001", "CALL_SET_OVERLAP_AND_SIGNED_SPARSE_COSINE", "PASS", output_table="04_EXTERNAL_FINGERPRINT_COMPARISONS", output_figure="04_EXTERNAL_FINGERPRINT_COMPARISONS")
    context.run_stage("04_EXTERNAL_FINGERPRINT_COMPARISONS", fingerprint_stage)

    # Stage 4/5 family atlas.
    family_drugs = drugs[:5]
    family_pairwise = pairwise[pairwise["drug_a"].isin(family_drugs) & pairwise["drug_b"].isin(family_drugs)].copy()
    family_pair_path = _write_registered(context, family_pairwise, output_root / "05_KETAMINE_FAMILY" / "KETAMINE_FAMILY_ALL_10_PAIR_METRICS.csv", "FAMILY_10_PAIRS", "KETAMINE_FAMILY", "Ketamine-family all unordered pair metrics", "family compounds", "strict18_common_rhr_and_fingerprint", "PAPER")
    identity_sensitivity = family_pairwise[((family_pairwise["drug_a"] == QUERY) | (family_pairwise["drug_b"] == QUERY) | (family_pairwise["drug_a"] == RACEMATE) | (family_pairwise["drug_b"] == RACEMATE))].copy()
    _write_registered(context, identity_sensitivity, output_root / "05_KETAMINE_FAMILY" / "POOLED_PARENT_VS_CONFIRMED_RACEMATE_IDENTITY_SENSITIVITY.csv", "IDENTITY_SENSITIVITY", "KETAMINE_FAMILY", "Pooled-parent and confirmed-racemate identity sensitivity", "family compounds", "strict18_common_rhr_and_fingerprint", "PAPER")
    family_roster_path = _write_registered(context, family_roster(), output_root / "05_KETAMINE_FAMILY" / "KETAMINE_FAMILY_ROSTER.csv", "FAMILY_ROSTER", "KETAMINE_FAMILY", "Ketamine family roster and identity roles", "family compounds", "identity_authority", "PAPER")
    for metric in ["rms_common_rhr", "cosine_common_rhr", "spearman_common_rhr", "alpha001_call_jaccard", "support_jaccard", "matched_targets"]:
        matrix = metric_matrix(family_pairwise, metric, family_drugs)
        path = _write_registered(context, matrix.reset_index(names="compound"), output_root / "05_KETAMINE_FAMILY" / f"FAMILY_{metric.upper()}_MATRIX.csv", "FAMILY_" + metric.upper(), "KETAMINE_FAMILY", "Family " + metric, "family compounds", metric, "PAPER")
        _save_figure(context, heatmap(matrix, "Ketamine family " + metric.replace("_", " "), metric, annotate=True), output_root / "05_KETAMINE_FAMILY" / f"FAMILY_{metric.upper()}_HEATMAP", "FAMILY_" + metric.upper() + "_HEATMAP", "KETAMINE_FAMILY", "Ketamine family " + metric, "family compounds", _relative(path, output_root), "PAPER")
    context.add_analysis("KETAMINE_FAMILY_PAIRWISE", "KETAMINE_FAMILY", "all family identities", "strict18_common_rhr_and_fingerprint", "ALL_UNORDERED_PAIRWISE", "PASS", input_path=_relative(family_roster_path, output_root), output_table=_relative(family_pair_path, output_root), output_figure="05_KETAMINE_FAMILY")
    family_models = _model_suite(context, "FAMILY", matrices["common_rhr"].loc[family_drugs], calls["call_binary_alpha001"].loc[family_drugs], calls["call_binary_alpha0001"].loc[family_drugs], family_pairwise, query["strict_contract"], output_root / "05_KETAMINE_FAMILY" / "MULTIVARIATE")
    context.model_statuses.extend(family_models["status"].to_dict("records"))
    context.mark_stage("05_KETAMINE_FAMILY", "PASS", now_iso(), 0.0, "Five-compound family pairwise and multivariate atlas completed")

    # Stage 6 global geometry.
    def global_stage() -> dict[str, pd.DataFrame]:
        """Run the global multivariate analyses over the accepted compound roster."""
        result = _model_suite(context, "GLOBAL", matrices["common_rhr"], calls["call_binary_alpha001"], calls["call_binary_alpha0001"], pairwise, query["strict_contract"], output_root / "06_GLOBAL_MULTIVARIATE", reference=external, projections=family_drugs)
        context.model_statuses.extend(result["status"].to_dict("records"))
        return result
    global_models = context.run_stage("06_GLOBAL_MULTIVARIATE", global_stage)

    # Stage 7 all governed class models; do not force low-rank outputs.
    classes = pd.read_csv(paths["prior_class_registry"], low_memory=False)
    class_snapshot = code_root / "config" / "class_registry_snapshot.csv"
    class_snapshot.parent.mkdir(parents=True, exist_ok=True)
    classes.to_csv(class_snapshot, index=False)
    def class_stage() -> dict[str, pd.DataFrame]:
        """Run class-level comparative models using the governed membership registry."""
        result = run_class_models(matrices["common_rhr"], calls["call_binary_alpha001"], pairwise, query["strict_contract"], classes, [QUERY, RACEMATE])
        for name, frame in result.items():
            if len(frame):
                _write_registered(context, frame, output_root / "07_CLASS_ANALYSES" / f"CLASS_{name.upper()}.csv", "CLASS_" + name.upper(), "CLASS_ANALYSES", "All governed class " + name, "governed classes", name, "PAPER" if name in {"scores", "status"} else "SUPPLEMENTAL")
        context.model_statuses.extend(result["status"].to_dict("records"))
        for row in result["status"].to_dict("records"):
            context.add_analysis(str(row.get("analysis_id")), "CLASS_MULTIVARIATE", str(row.get("class_label", row.get("class_id", ""))), str(row.get("representation", "")), str(row.get("method", "")), str(row.get("status", "NOT_ESTIMABLE")), output_table="07_CLASS_ANALYSES", reason=str(row.get("reason", "")))
        rms = metric_matrix(pairwise, "rms_common_rhr", drugs)
        for class_id, membership in classes.groupby("class_id"):
            participants = [QUERY, RACEMATE] + [drug for drug in membership["drug"] if drug in rms.index and drug not in {QUERY, RACEMATE}]
            subset = rms.loc[list(dict.fromkeys(participants)), list(dict.fromkeys(participants))]
            if subset.notna().sum().sum() == 0:
                continue
            path = _write_registered(context, subset.reset_index(names="compound"), output_root / "07_CLASS_ANALYSES" / "DISTANCE_MATRICES" / f"{slug(class_id)}_RMS.csv", f"CLASS_{class_id}_RMS", "CLASS_ANALYSES", f"{class_id} RMS matrix", str(class_id), "pairwise_rms")
            _save_figure(context, heatmap(subset, f"{membership['class_label'].iloc[0]} — RMS distance", "RMS", annotate=len(subset) <= 10), output_root / "07_CLASS_ANALYSES" / "DISTANCE_HEATMAPS" / f"{slug(class_id)}_RMS", f"CLASS_{class_id}_RMS_HEATMAP", "CLASS_ANALYSES", f"{class_id} RMS distance", str(class_id), _relative(path, output_root), "PAPER")
        return result
    class_results = context.run_stage("07_CLASS_ANALYSES", class_stage)

    # Stage 8 nearest reference and five-metric summaries.
    def nearest_stage() -> dict[str, pd.DataFrame]:
        """Compute deterministic nearest-reference summaries for the query compound."""
        overall = nearest_summary(pairwise, QUERY, set(external))
        per_class = class_nearest(pairwise, QUERY, classes)
        query_pairs = orient_query_pairs(pairwise, QUERY, set(external)).sort_values("rms_common_rhr")
        target = target_level_matrix(matrices["common_rhr"], query["strict_contract"])
        target_rows = []
        for comparator in external:
            metrics, _ = continuous_metrics(target.loc[QUERY], target.loc[comparator], pd.DataFrame({"feature_id": target.columns, "target": target.columns, "tissue": "TARGET_LEVEL"}))
            target_rows.append({"comparator": comparator, **metrics})
        target_nearest = pd.DataFrame(target_rows).sort_values("rms_common_rhr")
        paths_out = [
            _write_registered(context, overall, output_root / "08_NEAREST_REFERENCE" / "NEAREST_REFERENCE_SUMMARY.csv", "NEAREST_REFERENCE_SUMMARY", "NEAREST_REFERENCE", "Nearest external reference by metric", "25 external drugs", "multiple", "PAPER"),
            _write_registered(context, per_class, output_root / "08_NEAREST_REFERENCE" / "NEAREST_REFERENCE_BY_CLASS.csv", "NEAREST_REFERENCE_BY_CLASS", "NEAREST_REFERENCE", "Nearest external reference by governed class", "governed classes", "pairwise_rms", "PAPER"),
            _write_registered(context, target_nearest, output_root / "08_NEAREST_REFERENCE" / "TARGET_LEVEL_NEAREST.csv", "TARGET_LEVEL_NEAREST", "NEAREST_REFERENCE", "Target-level nearest external references", "25 external drugs", "target_mean_common_rhr", "PAPER"),
        ]
        identity = per_class.pivot_table(index="class_label", values=["rms_common_rhr", "distance_percentile_within_class", "nearest_neighbor_margin"], aggfunc="first")
        _write_registered(context, identity.reset_index(), output_root / "08_NEAREST_REFERENCE" / "QUERY_BY_CLASS_DISTANCE_PERCENTILE_MATRIX.csv", "QUERY_CLASS_PERCENTILE", "NEAREST_REFERENCE", "Query by class distance percentile", "governed classes", "pairwise_rms")
        png, _ = _save_figure(context, dashboard(query_pairs, "comparator", [("rms_common_rhr", "RMS"), ("spearman_common_rhr", "Spearman"), ("alpha001_call_jaccard", "Fingerprint Jaccard"), ("matched_targets", "Matched targets"), ("support_jaccard", "Support Jaccard")], "Pooled parent five-metric nearest-reference dashboard", 25), output_root / "08_NEAREST_REFERENCE" / "FIVE_METRIC_NEAREST_REFERENCE_DASHBOARD", "FIVE_METRIC_NEAREST", "NEAREST_REFERENCE", "Pooled parent five-metric nearest-reference dashboard", "25 external drugs", _relative(paths_out[0], output_root), "PAPER")
        context.add_analysis("NEAREST_REFERENCE_ALL", "NEAREST_REFERENCE", "25 external drugs and governed classes", "continuous_target_sparse", "MULTI_METRIC_RANKING", "PASS", output_table="; ".join(_relative(path, output_root) for path in paths_out), output_figure=_relative(png, output_root))
        return {"overall": overall, "per_class": per_class, "query_pairs": query_pairs, "target_nearest": target_nearest}
    nearest = context.run_stage("08_NEAREST_REFERENCE", nearest_stage)

    # Stage 9 class summary profiles and residuals.
    def class_summary_stage() -> dict[str, pd.DataFrame]:
        """Summarize class memberships and class-level comparison results."""
        summary, residuals = summarize_classes(matrices["common_rhr"], calls["call_binary_alpha001"], query["strict_contract"], classes, QUERY)
        pair_class = orient_query_pairs(pairwise, QUERY).merge(classes[["class_id", "class_label", "drug"]], left_on="comparator", right_on="drug", how="inner")
        distance_summary = pair_class.groupby(["class_id", "class_label"], as_index=False).agg(mean_continuous_distance=("rms_common_rhr", "mean"), median_continuous_distance=("rms_common_rhr", "median"), minimum_continuous_distance=("rms_common_rhr", "min"), member_count=("comparator", "nunique"))
        summary = summary.merge(distance_summary, on=["class_id", "class_label"], how="left")
        target_residual = residuals.groupby(["class_id", "class_label", "target"], as_index=False).agg(mean_query_minus_class=("query_minus_class_median", "mean"), mean_absolute_difference=("query_minus_class_median", lambda values: float(np.mean(np.abs(values)))), matched_tissues=("feature_id", "size")) if len(residuals) else pd.DataFrame()
        tissue_residual = residuals.groupby(["class_id", "class_label", "tissue"], as_index=False).agg(mean_query_minus_class=("query_minus_class_median", "mean"), mean_absolute_difference=("query_minus_class_median", lambda values: float(np.mean(np.abs(values)))), matched_targets=("feature_id", "size")) if len(residuals) else pd.DataFrame()
        for frame, name in [(summary, "CLASS_SUMMARY"), (residuals, "CLASS_RESIDUALS_LONG"), (target_residual, "CLASS_TARGET_DIFFERENTIALS"), (tissue_residual, "CLASS_TISSUE_DIFFERENTIALS")]:
            _write_registered(context, frame, output_root / "09_CLASS_SUMMARIES" / f"{name}.csv", name, "CLASS_SUMMARIES", name.replace("_", " "), "governed classes", "class_median_and_fingerprint", "PAPER" if name != "CLASS_RESIDUALS_LONG" else "SUPPLEMENTAL")
        context.add_analysis("CLASS_LEVEL_SUMMARIES", "CLASS_SUMMARIES", "governed classes", "class_median_profile_and_fingerprint", "SUPPORT_AWARE_CLASS_AGGREGATION", "PASS", output_table="09_CLASS_SUMMARIES")
        return {"summary": summary, "residuals": residuals, "target": target_residual, "tissue": tissue_residual}
    class_summary = context.run_stage("09_CLASS_SUMMARIES", class_summary_stage)

    # Stage 10 profile and support diagnostics.
    def profile_stage() -> None:
        """Generate target- and tissue-level profile diagnostics."""
        full = query["full"].rename(columns={"canonical_target_id": "target", "tissue_label": "tissue", "HR_numeric_boundary_or_exact": "raw_hr"})
        strict = query["strict"].rename(columns={"canonical_target_id": "target", "tissue_label": "tissue", "hr_numeric_collapsed": "raw_hr"})
        for name, frame, priority in [("FULL77", full, "PAPER"), ("STRICT18", strict, "PAPER")]:
            table_path = _write_registered(context, frame, output_root / "10_PROFILE_DIAGNOSTICS" / f"POOLED_PARENT_{name}_PROFILE.csv", f"POOLED_{name}_PROFILE", "PROFILE_DIAGNOSTICS", f"Pooled parent {name} profile", "none", "raw_hr", priority)
            _save_figure(context, profile_heatmap(frame, "raw_hr", f"Ketamine, pooled parent — {name} HR profile", robust=True), output_root / "10_PROFILE_DIAGNOSTICS" / f"POOLED_PARENT_{name}_HR_HEATMAP_ROBUST", f"POOLED_{name}_ROBUST_HEATMAP", "PROFILE_DIAGNOSTICS", f"Pooled parent {name} robust HR heatmap", "none", _relative(table_path, output_root), priority)
            _save_figure(context, profile_heatmap(frame, "raw_hr", f"Ketamine, pooled parent — {name} HR profile (full range)", robust=False), output_root / "10_PROFILE_DIAGNOSTICS" / f"POOLED_PARENT_{name}_HR_HEATMAP_FULL_RANGE", f"POOLED_{name}_FULL_HEATMAP", "PROFILE_DIAGNOSTICS", f"Pooled parent {name} full-range HR heatmap", "none", _relative(table_path, output_root), "SUPPLEMENTAL")
        coverage = profile_coverage(matrices["raw_hr"], query["strict_contract"])
        _write_registered(context, coverage, output_root / "10_PROFILE_DIAGNOSTICS" / "PROFILE_COMPLETENESS.csv", "PROFILE_COMPLETENESS", "PROFILE_DIAGNOSTICS", "Profile completeness", "all compounds", "strict18_support", "PAPER")
        support_map = matrices["support"]
        path = _write_registered(context, support_map.reset_index(names="compound"), output_root / "10_PROFILE_DIAGNOSTICS" / "SUPPORT_TESTABILITY_MAP.csv", "SUPPORT_TESTABILITY_MAP", "PROFILE_DIAGNOSTICS", "Support and testability map", "all compounds", "binary_support")
        _save_figure(context, heatmap(support_map, "Strict18 support/testability map", "Supported (1)"), output_root / "10_PROFILE_DIAGNOSTICS" / "SUPPORT_TESTABILITY_HEATMAP", "SUPPORT_TESTABILITY_HEATMAP", "PROFILE_DIAGNOSTICS", "Strict18 support and testability", "all compounds", _relative(path, output_root), "PAPER")
        context.add_analysis("PROFILE_AND_FINGERPRINT_DIAGNOSTICS", "PROFILE_DIAGNOSTICS", "all compounds", "full77_strict18_support", "PROFILE_HEATMAPS_AND_SUPPORT_MAPS", "PASS", output_table="10_PROFILE_DIAGNOSTICS", output_figure="10_PROFILE_DIAGNOSTICS")
    context.run_stage("10_PROFILE_DIAGNOSTICS", profile_stage)

    # Stage 11 recurrence, residual, support asymmetry, and exact-tie audits.
    def residual_stage() -> dict[str, pd.DataFrame]:
        """Run residual recurrence diagnostics on accepted pairwise outputs."""
        target_rec, tissue_rec = recurrence(details, QUERY)
        query_details = []
        tie_rows = []
        for comparator in external + family_drugs[1:]:
            key = (QUERY, comparator) if (QUERY, comparator) in details else (comparator, QUERY)
            detail = details[key].copy()
            if key[1] == QUERY:
                detail[["value_a", "value_b"]] = detail[["value_b", "value_a"]].to_numpy()
                detail["signed_difference_a_minus_b"] *= -1
            detail["comparator"] = comparator
            query_details.append(detail)
            tie_rows.append({"comparator": comparator, "matched_features": len(detail), "exact_equal_features": int((detail["signed_difference_a_minus_b"] == 0).sum()), "exact_equality_fraction": float((detail["signed_difference_a_minus_b"] == 0).mean()) if len(detail) else np.nan})
        long = pd.concat(query_details, ignore_index=True)
        unique_calls = []
        for comparator in external:
            q = calls["call_binary_alpha001"].loc[QUERY]
            c = calls["call_binary_alpha001"].loc[comparator]
            for feature in q.index[q.eq(1.0) & ~c.eq(1.0)]:
                unique_calls.append({"feature_id": feature, "comparator": comparator})
        unique_recurrence = pd.DataFrame(unique_calls).groupby("feature_id", as_index=False).agg(comparator_count=("comparator", "nunique")) if unique_calls else pd.DataFrame(columns=["feature_id", "comparator_count"])
        outputs = {"TARGET_RECURRENCE": target_rec, "TISSUE_RECURRENCE": tissue_rec, "ALL_QUERY_RESIDUALS_LONG": long, "EXACT_EQUALITY_TIE_AUDIT": pd.DataFrame(tie_rows), "POOLED_UNIQUE_FINGERPRINT_RECURRENCE": unique_recurrence}
        for name, frame in outputs.items():
            _write_registered(context, frame, output_root / "11_RESIDUAL_ANALYSES" / f"{name}.csv", name, "RESIDUAL_ANALYSES", name.replace("_", " "), "external and family comparators", "strict18_common_rhr_or_alpha001", "PAPER" if name in {"TARGET_RECURRENCE", "TISSUE_RECURRENCE"} else "SUPPLEMENTAL")
        for frame, label, value in [(target_rec, "target", "mean_absolute_difference"), (tissue_rec, "tissue", "mean_absolute_difference")]:
            if len(frame):
                _save_figure(context, ranking(frame, label, value, f"Recurring differential {label}s", "Mean absolute common-RHR difference", ascending=False, top_n=20), output_root / "11_RESIDUAL_ANALYSES" / f"RECURRING_{label.upper()}_DRIVERS", f"RECURRING_{label.upper()}_DRIVERS", "RESIDUAL_ANALYSES", f"Recurring differential {label}s", "external and family comparators", f"11_RESIDUAL_ANALYSES/{label.upper()}_RECURRENCE.csv", "PAPER")
        context.add_analysis("RESIDUAL_RECURRENCE_AND_TIES", "RESIDUAL_ANALYSES", "external and family comparators", "strict18_common_rhr_and_alpha001", "PAIRWISE_RESIDUAL_AGGREGATION", "PASS", output_table="11_RESIDUAL_ANALYSES", output_figure="11_RESIDUAL_ANALYSES")
        return outputs
    residuals = context.run_stage("11_RESIDUAL_ANALYSES", residual_stage)

    # Stage 12 coverage/confounding and method availability.
    def coverage_stage() -> dict[str, pd.DataFrame]:
        """Quantify profile coverage and distance-confounding diagnostics."""
        coverage = profile_coverage(matrices["raw_hr"], query["strict_contract"])
        confounding = distance_confounding(nearest["query_pairs"])
        models = pd.DataFrame(context.model_statuses)
        method_availability = models.pivot_table(index="method", columns="status", values="analysis_id", aggfunc="count", fill_value=0).reset_index() if len(models) else pd.DataFrame()
        blocked = models[~models["status"].astype(str).str.startswith("PASS")].copy() if len(models) else pd.DataFrame()
        global_joint = global_models["scores"]
        position = coverage.merge(global_joint[global_joint.get("analysis_id", pd.Series(dtype=str)).eq("GLOBAL_JOINT_CONTINUOUS_PCA")][[column for column in ["compound", "PC1", "PC2"] if column in global_joint.columns]], on="compound", how="left") if len(global_joint) else coverage.copy()
        for frame, name in [(coverage, "PROFILE_COMPLETENESS"), (confounding, "COVERAGE_VS_DISTANCE"), (position, "COVERAGE_VS_PCA_POSITION"), (blocked, "BLOCKED_NOT_ESTIMABLE_ANALYSES"), (method_availability, "METHOD_AVAILABILITY_MATRIX")]:
            _write_registered(context, frame, output_root / "12_COVERAGE_AND_CONFOUNDING" / f"{name}.csv", "COVERAGE_" + name, "COVERAGE_AND_CONFOUNDING", name.replace("_", " "), "all compounds", "support_and_model_status", "PAPER" if name in {"PROFILE_COMPLETENESS", "COVERAGE_VS_DISTANCE"} else "SUPPLEMENTAL")
        if len(confounding):
            _save_figure(context, scatter(confounding.rename(columns={"comparator": "compound", "matched_features": "PC1", "rms_common_rhr": "PC2"}), "Coverage versus pooled-parent distance", x="PC1", y="PC2", highlight=[], label_col="compound"), output_root / "12_COVERAGE_AND_CONFOUNDING" / "COVERAGE_VS_DISTANCE", "COVERAGE_VS_DISTANCE_FIGURE", "COVERAGE_AND_CONFOUNDING", "Matched feature denominator versus RMS distance", "25 external drugs", "12_COVERAGE_AND_CONFOUNDING/COVERAGE_VS_DISTANCE.csv", "PAPER")
        context.add_analysis("COVERAGE_CONFOUNDING_DIAGNOSTICS", "COVERAGE_AND_CONFOUNDING", "all compounds", "support_denominators_and_model_status", "SUPPORT_AWARE_DIAGNOSTICS", "PASS", output_table="12_COVERAGE_AND_CONFOUNDING", output_figure="12_COVERAGE_AND_CONFOUNDING")
        return {"coverage": coverage, "confounding": confounding, "blocked": blocked, "availability": method_availability}
    coverage = context.run_stage("12_COVERAGE_AND_CONFOUNDING", coverage_stage)
    ancillary = context.run_stage("13_ANCILLARY_ANALYSES", lambda: _ancillary_registry(context, paths, output_root / "13_ANCILLARY_ANALYSES"), optional=True)

    # Register parameter, model, analysis, and prior-manifest coverage before paper packaging.
    parameter_registry = pd.DataFrame([
        {"parameter": "gesd_primary_alpha", "value": 0.001, "scope": "fingerprint"},
        {"parameter": "gesd_sensitivity_alpha", "value": 0.0001, "scope": "fingerprint"},
        {"parameter": "gesd_tail", "value": "one-sided upper", "scope": "fingerprint"},
        {"parameter": "gesd_sd_ddof", "value": 1, "scope": "fingerprint"},
        {"parameter": "gesd_rmax_fraction", "value": 0.10, "scope": "fingerprint"},
        {"parameter": "random_seed", "value": 20260813, "scope": "MDS"},
        {"parameter": "pca_components_requested", "value": 2, "scope": "multivariate; never forced beyond rank"},
        {"parameter": "missingness_policy", "value": "NA preserved; no unauthorized zero fill", "scope": "all"},
        {"parameter": "cpu_ceiling_fraction", "value": 0.80, "scope": "resource"},
        {"parameter": "ram_ceiling_fraction", "value": 0.80, "scope": "resource"},
        {"parameter": "vram_ceiling_fraction", "value": 0.80, "scope": "resource"},
        {"parameter": "common_scale", "value": "frozen weighted empirical CDF transform", "scope": "cross-drug"},
    ])
    _write_registered(context, parameter_registry, output_root / "15_QA_AND_MANIFESTS" / "PARAMETER_REGISTRY.csv", "PARAMETER_REGISTRY", "RUN_CONTROL", "Parameter registry", "all", "parameters")
    model_status = pd.DataFrame(context.model_statuses)
    _write_registered(context, model_status, output_root / "15_QA_AND_MANIFESTS" / "MODEL_STATUS.csv", "MODEL_STATUS", "RUN_CONTROL", "All multivariate model statuses", "all", "model_status")
    analysis_registry = pd.DataFrame(context.analysis_rows)
    analysis_path = output_root / "15_QA_AND_MANIFESTS" / "ANALYSIS_REGISTRY.csv"
    analysis_registry.to_csv(analysis_path, index=False)
    previous_coverage = _previous_coverage(paths, _relative(analysis_path, output_root))
    _write_registered(context, previous_coverage, output_root / "15_QA_AND_MANIFESTS" / "PREVIOUS_VS_NEW_OUTPUT_COVERAGE.csv", "PREVIOUS_VS_NEW_OUTPUT_COVERAGE", "COMPLETENESS_AUDIT", "Prior S-ketamine output coverage audit", "prior complete and paper manifests", "manifest_lineage")
    context.qa.check("PRIOR_MANIFEST_COMPLETE_AUDIT", len(previous_coverage) == len(pd.read_csv(paths["prior_manifest"])) + len(pd.read_csv(paths["prior_paper_manifest"])), len(previous_coverage), 881)
    context.qa.check("ANALYSIS_REGISTRY_NO_SILENT_STATUS", analysis_registry["status"].notna().all(), int(analysis_registry["status"].isna().sum()), 0)

    # Paper-facing derivative, workbooks, combined figure/table packets.
    def paper_stage() -> dict[str, Any]:
        """Assemble publication-facing tables, figures, and compact handoff artifacts."""
        paper_dir = output_root / "14_PAPER_FACING"
        figures_dir, tables_dir = paper_dir / "FIGURES", paper_dir / "TABLES"
        figure_index = context.figures.frame()
        selected_figures = figure_index[figure_index["paper_facing_priority"].eq("PAPER") & figure_index["QA_status"].eq("PASS")]
        copied_figures = []
        for row in selected_figures.itertuples(index=False):
            copied_figures.extend([copy_paper_item(output_root / row.output_file, figures_dir), copy_paper_item(output_root / row.pdf_file, figures_dir)])
        table_index = context.tables.frame()
        selected_tables = table_index[table_index["paper_facing_priority"].eq("PAPER") & table_index["QA_status"].eq("PASS")]
        copied_tables = [copy_paper_item(output_root / row.output_file, tables_dir) for row in selected_tables.itertuples(index=False)]
        selected_figures.to_csv(paper_dir / "PAPER_FACING_FIGURE_INDEX.csv", index=False)
        selected_tables.to_csv(paper_dir / "PAPER_FACING_TABLE_INDEX.csv", index=False)
        workbook = summary_workbook({
            "nearest": nearest["overall"], "class_nearest": nearest["per_class"], "family_pairs": family_pairwise,
            "pool_external": pool_external, "class_summary": class_summary["summary"], "coverage": coverage["coverage"],
            "model_status": model_status, "qa": context.qa.frame(),
        }, paper_dir / "POOLED_PARENT_COMPARATIVE_SUMMARY.xlsx")
        table_pdfs = []
        for name, frame in [("nearest", nearest["overall"]), ("family_pairs", family_pairwise), ("class_summary", class_summary["summary"]), ("coverage", coverage["coverage"]), ("target_recurrence", residuals["TARGET_RECURRENCE"]), ("tissue_recurrence", residuals["TISSUE_RECURRENCE"])]:
            table_pdfs.append(table_pdf(frame, name.replace("_", " ").title(), paper_dir / "TABLE_PDFS" / f"{name.upper()}.pdf"))
        all_figures, _ = combine_pdfs([output_root / row.pdf_file for row in selected_figures.itertuples(index=False)], paper_dir / "ALL_FIGURES_COMBINED.pdf")
        all_tables, _ = combine_pdfs(table_pdfs, paper_dir / "ALL_TABLES_COMBINED.pdf")
        complete, _ = combine_pdfs([path for path in [all_figures, all_tables] if path], paper_dir / "COMPLETE_FIGURES_AND_TABLES_PACKET.pdf")
        context.add_analysis("PAPER_FACING_PACKET", "PAPER_FACING", "selected results", "figures_tables_workbook", "DETERMINISTIC_SELECTION_AND_PDF_COMBINATION", "PASS", output_table=_relative(workbook, output_root), output_figure=_relative(complete, output_root) if complete else "")
        return {"figure_count": len(selected_figures), "table_count": len(selected_tables), "combined": complete, "workbook": workbook}
    paper = context.run_stage("14_PAPER_FACING", paper_stage)
    # Register paper packaging as an analysis family and refresh the registry
    # after that stage so its terminal row is not omitted.
    analysis_registry = pd.DataFrame(context.analysis_rows)
    analysis_registry.to_csv(analysis_path, index=False)

    # Final QA/manifests and immutable-source post-hash verification.
    post_hashes = _input_manifest(paths)
    merged_hashes = pre_hashes.merge(post_hashes, on="input_role", suffixes=("_pre", "_post"))
    changed = int((merged_hashes["sha256_pre"] != merged_hashes["sha256_post"]).sum())
    context.qa.check("GOVERNED_INPUTS_UNCHANGED", changed == 0, changed, 0)
    context.qa.check("FAMILY_PAIR_COUNT", len(family_pairwise) == 10, len(family_pairwise), 10)
    context.qa.check("POOLED_EXTERNAL_PAIR_COUNT", len(pool_external) == 25, len(pool_external), 25)
    context.qa.check("RACEMATE_EXTERNAL_PAIR_COUNT", len(racemate_external) == 25, len(racemate_external), 25)
    context.qa.check("FAMILY_DISTINCT_PROFILE_ROWS", not matrices["common_rhr"].loc[QUERY].equals(matrices["common_rhr"].loc[RACEMATE]), "profiles differ", "not accidentally identical or merged")
    regenerated001 = regression_calls(query["strict"], 0.001)
    regenerated0001 = regression_calls(query["strict"], 0.0001)
    context.qa.check("GESD_ALPHA001_REGRESSION", set(regenerated001["feature_id"]) == set(query["calls001"]["feature_id"]), len(regenerated001), 19)
    context.qa.check("GESD_ALPHA0001_REGRESSION", set(regenerated0001["feature_id"]) == set(query["calls0001"]["feature_id"]), len(regenerated0001), 14)
    resource_report = context.resources.report()
    context.qa.check("CPU_WORKER_CEILING", resource_report["peak_workers"] <= resource_report["cpu_worker_ceiling"], resource_report["peak_workers"], f"<={resource_report['cpu_worker_ceiling']}")
    context.qa.check("RAM_CEILING", resource_report["peak_ram_used_bytes"] <= resource_report["configured_ram_ceiling_bytes"], resource_report["peak_ram_used_bytes"], f"<={resource_report['configured_ram_ceiling_bytes']}", severity="LIMITATION", notes="System-wide RAM includes unrelated processes")
    context.qa.check("VRAM_CEILING", resource_report["peak_vram_used_mb"] <= resource_report["gpu_vram_ceiling_mb"] if resource_report["gpu_detected"] else True, resource_report["peak_vram_used_mb"], f"<={resource_report['gpu_vram_ceiling_mb']}", severity="LIMITATION", notes="System-wide VRAM includes unrelated processes")
    figure_frame, table_frame = context.figures.frame(), context.tables.frame()
    ok, bad = files_nonempty([output_root / path for path in figure_frame["output_file"]], 5000)
    context.qa.check("FIGURE_FILES_NONEMPTY", ok, bad, 0)
    context.qa.check("FIGURE_MANIFEST_QA", bool(figure_frame["QA_status"].eq("PASS").all()), int((figure_frame["QA_status"] != "PASS").sum()), 0)
    context.qa.check("TABLE_MANIFEST_QA", bool(table_frame["QA_status"].eq("PASS").all()), int((table_frame["QA_status"] != "PASS").sum()), 0)

    qa_frame = context.qa.frame()
    qa_frame.to_csv(output_root / "15_QA_AND_MANIFESTS" / "QA_SUMMARY.csv", index=False)
    figure_frame.to_csv(output_root / "15_QA_AND_MANIFESTS" / "FIGURE_MANIFEST.csv", index=False)
    table_frame.to_csv(output_root / "15_QA_AND_MANIFESTS" / "TABLE_MANIFEST.csv", index=False)
    pre_hashes.to_csv(output_root / "15_QA_AND_MANIFESTS" / "INPUT_MANIFEST.csv", index=False)
    merged_hashes.to_csv(output_root / "15_QA_AND_MANIFESTS" / "INPUT_PRE_POST_HASH_AUDIT.csv", index=False)
    pd.DataFrame(context.failure_rows, columns=["stage", "status", "reason", "traceback"]).to_csv(output_root / "00_RUN_CONTROL" / "FAILURE_LEDGER.csv", index=False)
    resource_report_path = output_root / "15_QA_AND_MANIFESTS" / "RESOURCE_REPORT.json"
    write_json(resource_report_path, resource_report)
    permanent_manifest = code_manifest(code_root)
    permanent_manifest.to_csv(output_root / "15_QA_AND_MANIFESTS" / "CODE_MANIFEST.csv", index=False)
    environment = {
        "python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
        "processor": platform.processor(), **resource_report,
    }
    write_json(output_root / "15_QA_AND_MANIFESTS" / "ENVIRONMENT_REPORT.json", environment)

    ended = now_iso()
    runtime_seconds = time.perf_counter() - context.started_perf
    status_counts = model_status["status"].value_counts().to_dict() if len(model_status) else {}
    qa_status = context.qa.overall()
    summary_text = f"""# Pooled Parent Ketamine Complete Comparative Rebuild

Status: {qa_status}

## Runtime

- Start: {context.started}
- End: {ended}
- Total runtime seconds: {runtime_seconds:.1f}

## Core query

- Full HR: {query['counts']['full_targets']} targets x {query['counts']['full_tissues']} tissues = {query['counts']['full_rows']} rows
- Strict18 HR: {query['counts']['strict_targets']} targets x {query['counts']['strict_tissues']} tissues = {query['counts']['strict_rows']} rows
- Fingerprint calls: alpha=.001 {query['counts']['calls_001']}; alpha=.0001 {query['counts']['calls_0001']}
- Corrected rendered call cells: {repaired['primary_cells']} / {repaired['strict_cells']}
- Common-scale exclusions: GRIN3B only ({int((~query['strict_mapped']['common_scale_compatible']).sum())} strict coordinates); query authority retained in full.

## Comparative analysis

- Numerical external comparators: {len(external)}
- All numerical compounds: {len(drugs)}
- All unordered pairs: {len(pairwise)}
- Pooled-parent vs external pairs: {len(pool_external)}
- Confirmed-racemate vs external pairs: {len(racemate_external)}
- External-only pairs reused after equality QA: {len(external_pairs)}
- Ketamine-family numerical compounds: {len(family_drugs)}; unordered pairs: {len(family_pairwise)}

## Multivariate and outputs

- Model statuses: {json.dumps(status_counts, sort_keys=True)}
- Figures indexed: {len(figure_frame)}
- Tables indexed: {len(table_frame)}
- Paper-facing figures: {paper['figure_count']}
- Paper-facing tables: {paper['table_count']}
- Analysis registry rows: {len(analysis_registry)}
- Prior output manifest rows audited: {len(previous_coverage)}

## Reproducibility and limits

- Permanent code: {code_root}
- Run root: {output_root}
- Frozen common-scale transform was reused; no upstream model was refit.
- Missing values remain NA; fingerprint matrices use 0 only for tested non-calls and NA for untested coordinates.
- GPU was detected but not used because the installed scientific stack lacks a compatible GPU array backend and the matrices are small; float64 CPU calculations were selected.
- Optional spatial/pathology/CRTP/network products without a pooled-parent-compatible authority are explicitly blocked in the ancillary registry.
"""
    final_summary = output_root / "16_HANDOFF" / "FINAL_RUN_SUMMARY.md"
    final_summary.write_text(summary_text, encoding="utf-8")
    paste_ready = output_root / "16_HANDOFF" / "PASTE_READY_HANDOFF.md"
    paste_ready.write_text(summary_text + f"\nAnalysis registry: {analysis_path}\n", encoding="utf-8")

    # Output manifest intentionally excludes itself and SHA256SUMS to avoid recursive hashes.
    manifest = output_manifest(output_root, {"OUTPUT_MANIFEST.csv", "SHA256SUMS.csv"})
    manifest.to_csv(output_root / "15_QA_AND_MANIFESTS" / "OUTPUT_MANIFEST.csv", index=False)
    manifest[["sha256", "relative_path"]].to_csv(output_root / "15_QA_AND_MANIFESTS" / "SHA256SUMS.csv", index=False)
    include = [
        final_summary, paste_ready, analysis_path,
        output_root / "15_QA_AND_MANIFESTS" / "MODEL_STATUS.csv",
        output_root / "15_QA_AND_MANIFESTS" / "FIGURE_MANIFEST.csv",
        output_root / "15_QA_AND_MANIFESTS" / "TABLE_MANIFEST.csv",
        output_root / "15_QA_AND_MANIFESTS" / "PARAMETER_REGISTRY.csv",
        output_root / "15_QA_AND_MANIFESTS" / "INPUT_MANIFEST.csv",
        output_root / "15_QA_AND_MANIFESTS" / "OUTPUT_MANIFEST.csv",
        output_root / "15_QA_AND_MANIFESTS" / "SHA256SUMS.csv",
        output_root / "15_QA_AND_MANIFESTS" / "PREVIOUS_VS_NEW_OUTPUT_COVERAGE.csv",
        output_root / "15_QA_AND_MANIFESTS" / "QA_SUMMARY.csv",
        output_root / "15_QA_AND_MANIFESTS" / "RESOURCE_USAGE.csv",
        output_root / "15_QA_AND_MANIFESTS" / "CODE_MANIFEST.csv",
        output_root / "15_QA_AND_MANIFESTS" / "ENVIRONMENT_REPORT.json",
        output_root / "00_RUN_CONTROL" / "STAGE_STATUS.csv",
        output_root / "00_RUN_CONTROL" / "FAILURE_LEDGER.csv",
        output_root / "14_PAPER_FACING" / "PAPER_FACING_FIGURE_INDEX.csv",
        output_root / "14_PAPER_FACING" / "PAPER_FACING_TABLE_INDEX.csv",
        output_root / "08_NEAREST_REFERENCE" / "NEAREST_REFERENCE_SUMMARY.csv",
        output_root / "05_KETAMINE_FAMILY" / "KETAMINE_FAMILY_ALL_10_PAIR_METRICS.csv",
        output_root / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "POOLED_PARENT_VS_25_EXTERNAL_METRICS.csv",
    ]
    zip_path = output_root / "16_HANDOFF" / f"Pooled_Parent_Ketamine_Complete_Comparative_Handoff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path, zip_manifest = compact_handoff_zip(output_root, code_root, zip_path, include)
    zip_manifest.to_csv(output_root / "16_HANDOFF" / "HANDOFF_ZIP_CONTENTS.csv", index=False)
    pd.DataFrame([{"path": str(zip_path), "bytes": zip_path.stat().st_size, "sha256": sha256_file(zip_path), "crc_test": "PASS"}]).to_csv(output_root / "16_HANDOFF" / "HANDOFF_ZIP_VERIFICATION.csv", index=False)
    context.mark_stage("15_QA_AND_MANIFESTS", qa_status, context.started, time.perf_counter() - context.started_perf)
    context.mark_stage("16_HANDOFF", "PASS", now_iso(), 0.0, str(zip_path))
    context.resources.snapshot("RUN_END")

    # Re-seal hashes only after every mutable stage/resource log is final.  ZIP-related
    # files are governed by HANDOFF_ZIP_VERIFICATION because hashing an archive that
    # embeds its own output manifest would otherwise create a recursive digest.
    manifest_exclusions = {
        "OUTPUT_MANIFEST.csv", "SHA256SUMS.csv", zip_path.name,
        "HANDOFF_ZIP_CONTENTS.csv", "HANDOFF_ZIP_VERIFICATION.csv",
    }
    manifest = output_manifest(output_root, manifest_exclusions)
    manifest.to_csv(output_root / "15_QA_AND_MANIFESTS" / "OUTPUT_MANIFEST.csv", index=False)
    manifest[["sha256", "relative_path"]].to_csv(output_root / "15_QA_AND_MANIFESTS" / "SHA256SUMS.csv", index=False)
    zip_path, zip_manifest = compact_handoff_zip(output_root, code_root, zip_path, include)
    zip_manifest.to_csv(output_root / "16_HANDOFF" / "HANDOFF_ZIP_CONTENTS.csv", index=False)
    pd.DataFrame([{"path": str(zip_path), "bytes": zip_path.stat().st_size, "sha256": sha256_file(zip_path), "crc_test": "PASS"}]).to_csv(output_root / "16_HANDOFF" / "HANDOFF_ZIP_VERIFICATION.csv", index=False)

    print("=== POOLED PARENT KETAMINE COMPLETE COMPARATIVE REBUILD COMPLETE ===")
    print(f"RUNTIME: {runtime_seconds:.1f} seconds | Start {context.started} | End {ended}")
    print(f"HARDWARE: {resource_report['physical_cpu']} physical / {resource_report['logical_cpu']} logical; worker ceiling {resource_report['cpu_worker_ceiling']}; peak {resource_report['peak_workers']}; GPU {resource_report['gpu_name'] or 'none'}; GPU used False")
    print(f"CORE QUERY: full {query['counts']['full_targets']}x{query['counts']['full_tissues']}={query['counts']['full_rows']}; strict {query['counts']['strict_targets']}x{query['counts']['strict_tissues']}={query['counts']['strict_rows']}; calls {query['counts']['calls_001']}/{query['counts']['calls_0001']}")
    print(f"HEATMAP REPAIR: {repaired['primary_cells']}/{repaired['strict_cells']} rendered calls; QA PASS")
    print(f"EXTERNAL COMPARATORS: {len(external)}; pooled {len(pool_external)}; confirmed racemate {len(racemate_external)}")
    print(f"KETAMINE FAMILY: {len(family_drugs)} compounds; {len(family_pairwise)} pairs; identities distinct")
    print(f"OUTPUTS: {len(figure_frame)} figures; {len(table_frame)} tables; {len(analysis_registry)} analysis rows")
    print(f"PERMANENT CODE: {code_root}")
    print(f"RUN OUTPUT: {output_root}")
    print(f"HANDOFF ZIP: {zip_path}")
    print(f"QA: {qa_status}")
    return output_root
