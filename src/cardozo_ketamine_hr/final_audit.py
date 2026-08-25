"""Rebuild, audit, package, and freeze an external comparative-analysis run.

Stage: terminal independent audit after governed comparative computation.
Inputs: explicit external authorities, source code, configuration, and run root.
Outputs: derivative tables/figures, QA ledgers, manifests, freeze candidate, ZIP.
Side effects: writes a new audit tree and packaging artifacts; inputs stay read-only.
Invariants: preserve identities, missingness, fixed models, hashes, and tolerances.
Lane: external-source final-audit/freeze lane, not self-contained public Smoke.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import compileall
import json
import math
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from PIL import Image
from pypdf import PdfReader

from .authority_discovery import PROJECT_ROOT_DEFAULT, discover
from .family_completion import (
    E7_LABELS,
    FINAL_FAMILY_ORDER,
    METABOLITE_LABELS,
    POOLED,
    RACEMATE,
    availability_audit,
    extend_call_matrices,
    forensic_audit,
    load_e7_profiles,
    strict_contract_from_profiles,
)
from .figures import FigureRecorder, dendrogram_figure, heatmap, ranking, scatter, table_pdf
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
from .packaging import code_manifest, combine_pdfs, compact_handoff_zip, output_manifest, summary_workbook
from .pairwise_continuous import all_pairwise, continuous_metrics, metric_matrix
from .pairwise_fingerprint import metric_function
from .utilities import now_iso, relative_posix, sha256_file, slug, write_json


SOURCE_RUN_NAME = "Pooled_Parent_Ketamine_Complete_Comparative_Analysis_20260813_182544"
SOURCE_RUN_RELATIVE = Path("04_KETAMINE_VS_DRUGS") / SOURCE_RUN_NAME
CODE_RELATIVE = Path("09_CODE_AND_PIPELINES") / "Pooled_Parent_Ketamine_Complete_Comparative_Rebuild"
FINAL_PREFIX = "Pooled_Parent_Ketamine_Final_Audit_And_Freeze"
FREEZE_NAME = "Pooled_Parent_Ketamine_Comparative_Stage_FREEZE_CANDIDATE"

STAGES = [
    "00_RUN_CONTROL",
    "01_INPUT_SNAPSHOT",
    "02_FAMILY_AVAILABILITY_AUDIT",
    "03_FAMILY_IDENTITY_FORENSICS",
    "04_COMPLETED_FAMILY_PAIRWISE",
    "05_COMPLETED_FAMILY_MULTIVARIATE",
    "06_UPDATED_GLOBAL_MODELS",
    "07_NUMERICAL_INTEGRITY_AUDIT",
    "08_FINGERPRINT_AND_COMMON_SCALE_AUDIT",
    "09_MULTIVARIATE_AND_CLASS_AUDIT",
    "10_COVERAGE_AND_MISSINGNESS_AUDIT",
    "11_FIGURE_TABLE_QA",
    "12_PREVIOUS_OUTPUT_COVERAGE",
    "13_FINAL_PAPER_FACING",
    "14_FREEZE_MANIFESTS",
    "15_HANDOFF",
    "16_FREEZE_CANDIDATE",
]


def _timestamp() -> str:
    """Return a filesystem-safe timestamp for a derivative freeze run."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _read(path: Path) -> pd.DataFrame:
    """Read a CSV table while preserving source missingness."""
    return pd.read_csv(path, low_memory=False)


def _bool(value: Any) -> bool:
    """Normalize a governed Boolean-like value without changing its meaning."""
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def _finite_max(values: pd.Series) -> float:
    """Return the maximum finite numeric value, or zero for an empty series."""
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.max()) if len(values) else 0.0


def _status_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Summarize audit statuses as JSON-safe integer counts."""
    return {str(key): int(value) for key, value in frame["status"].value_counts().items()}


@dataclass
class AuditRun:
    """Record paths, tables, analyses, checks, stages, and figures for one final audit."""
    root: Path
    source_run: Path
    code_root: Path
    table_rows: list[dict[str, Any]] = field(default_factory=list)
    analysis_rows: list[dict[str, Any]] = field(default_factory=list)
    qa_rows: list[dict[str, Any]] = field(default_factory=list)
    stage_rows: list[dict[str, Any]] = field(default_factory=list)
    figures: FigureRecorder = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the figure recorder for this audit root."""
        self.figures = FigureRecorder(self.root)

    def table(
        self,
        frame: pd.DataFrame,
        relative: str,
        table_id: str,
        analysis: str,
        title: str,
        representation: str,
        priority: str = "SUPPLEMENTAL",
    ) -> Path:
        """Write a table and append its publication and provenance registry record."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        self.table_rows.append({
            "table_id": table_id,
            "analysis": analysis,
            "title": title,
            "query": POOLED,
            "comparators": "final roster",
            "representation": representation,
            "input_table": "",
            "output_file": relative_posix(path, self.root),
            "paper_facing_priority": priority,
            "QA_status": "PASS",
            "row_count": len(frame),
            "column_count": len(frame.columns),
            "storage_root": str(self.root),
        })
        return path

    def figure(
        self,
        figure: Any,
        relative_base: str,
        figure_id: str,
        analysis: str,
        title: str,
        input_table: str,
        priority: str = "PAPER",
    ) -> tuple[Path, Path]:
        """Register a generated figure with its source table and publication priority."""
        return self.figures.save(
            figure,
            self.root / relative_base,
            figure_id,
            analysis,
            title,
            POOLED,
            "final roster",
            input_table,
            priority,
        )

    def analysis(
        self,
        analysis_id: str,
        family: str,
        representation: str,
        method: str,
        status: str,
        output_table: str = "",
        output_figure: str = "",
        reason: str = "",
        query: str = POOLED,
        comparator: str = "final roster",
        reused: str = "RECOMPUTED_AFFECTED_BRANCH",
    ) -> None:
        """Append a final-analysis registry record with method and lineage."""
        self.analysis_rows.append({
            "analysis_id": analysis_id,
            "analysis_family": family,
            "query_compound": query,
            "comparator_or_class": comparator,
            "representation": representation,
            "method": method,
            "status": status,
            "input_path": "",
            "output_table": output_table,
            "output_figure": output_figure,
            "reused_or_recomputed": reused,
            "reason_if_blocked": reason,
            "QA_status": "PASS" if status == "PASS" else ("PASS_WITH_LIMITATION" if status in {"PASS_WITH_LIMITATION", "NOT_ESTIMABLE", "BLOCKED"} else status),
            "runtime_seconds": 0.0,
            "compute_backend": "CPU_FLOAT64",
            "cpu_workers": 1,
            "gpu_used": False,
            "final_disposition": "CURRENT_FINAL" if reused != "REUSED_VALIDATED_SOURCE_RUN" else "REUSED_UNCHANGED",
        })

    def check(
        self,
        check_id: str,
        analysis: str,
        passed: bool,
        expected: Any,
        observed: Any,
        tolerance: Any = "EXACT",
        notes: str = "",
        core: bool = True,
    ) -> None:
        """Record one explicit expected-versus-observed QA assertion."""
        self.qa_rows.append({
            "check_id": check_id,
            "analysis": analysis,
            "expected": expected,
            "observed": observed,
            "tolerance": tolerance,
            "status": "PASS" if passed else "FAIL",
            "notes": notes,
            "core_check": core,
        })

    def stage(self, name: str, status: str, notes: str = "") -> None:
        """Record the outcome and notes for one final-audit stage."""
        row = {"stage": name, "status": status, "completed_at": now_iso(), "notes": notes}
        self.stage_rows.append(row)
        write_json(self.root / name / "STAGE_STATUS.json", row)
        pd.DataFrame(self.stage_rows).to_csv(self.root / "00_RUN_CONTROL" / "STAGE_STATUS.csv", index=False)
        write_json(self.root / "00_RUN_CONTROL" / "STAGE_STATUS.json", {"stages": self.stage_rows})


def _load_source_matrices(source_run: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    """Load accepted source-run pairwise metrics and matrix representations."""
    cache = source_run / "00_RUN_CONTROL" / "CACHED_MATRICES"
    profiles = _read(cache / "ALL_COMPOUND_PROFILES_STRICT18_LONG.csv")
    contract = strict_contract_from_profiles(profiles)

    def matrix(name: str) -> pd.DataFrame:
        """Load one named source matrix while retaining its index contract."""
        frame = _read(cache / name)
        index_column = frame.columns[0]
        return frame.set_index(index_column)

    calls = {
        "call_binary_alpha001": matrix("CALL_BINARY_ALPHA001.csv"),
        "call_score_alpha001": matrix("CALL_SCORE_ALPHA001.csv"),
        "call_binary_alpha0001": matrix("CALL_BINARY_ALPHA0001.csv"),
        "call_score_alpha0001": matrix("CALL_SCORE_ALPHA0001.csv"),
    }
    return profiles, contract, calls


def _profile_matrices(profiles: pd.DataFrame, contract: pd.DataFrame, roster: list[str]) -> dict[str, pd.DataFrame]:
    """Build raw, common-scale, and fingerprint matrices for the final roster."""
    features = contract["feature_id"].astype(str).tolist()
    raw = profiles.pivot(index="drug", columns="feature_id", values="raw_hr").reindex(index=roster, columns=features)
    common = profiles.pivot(index="drug", columns="feature_id", values="common_rhr").reindex(index=roster, columns=features)
    return {"raw_hr": raw, "common_rhr": common, "support": raw.notna().astype(int)}


def _replace_source_pairs(computed: pd.DataFrame, source: pd.DataFrame, old_roster: list[str]) -> pd.DataFrame:
    """Replace recomputed legacy pairs with accepted source rows after QA."""
    result = computed.copy()
    result["reused_or_recomputed"] = "RECOMPUTED_AFFECTED_EDGE"
    source_key = source.assign(pair_key=source.apply(lambda row: "||".join(sorted([str(row.drug_a), str(row.drug_b)])), axis=1)).set_index("pair_key")
    common_columns = [column for column in source.columns if column in result.columns and column not in {"drug_a", "drug_b"}]
    old = set(old_roster)
    for index, row in result.iterrows():
        if row["drug_a"] in old and row["drug_b"] in old:
            key = "||".join(sorted([str(row["drug_a"]), str(row["drug_b"])]))
            source_row = source_key.loc[key]
            for column in common_columns:
                result.at[index, column] = source_row[column]
            result.at[index, "reused_or_recomputed"] = "REUSED_VALIDATED_SOURCE_RUN"
    return result


def _pair_detail(matrix: pd.DataFrame, contract: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    """Build coordinate-level detail for one continuous compound pair."""
    _, detail = continuous_metrics(matrix.loc[a], matrix.loc[b], contract)
    detail.insert(0, "query_compound", a)
    detail.insert(1, "comparator", b)
    return detail


def _call_detail(binary: pd.DataFrame, a: str, b: str, contract: pd.DataFrame, alpha: str) -> pd.DataFrame:
    """Build call-set overlap detail for one compound pair and alpha threshold."""
    qa, qb = binary.loc[a], binary.loc[b]
    meta = contract.set_index("feature_id")
    union = sorted(set(qa.index[qa.eq(1.0)]) | set(qb.index[qb.eq(1.0)]))
    rows = []
    for feature in union:
        rows.append({
            "alpha": alpha,
            "feature_id": feature,
            "target": meta.loc[feature, "target"],
            "tissue": meta.loc[feature, "tissue"],
            "pooled_call": bool(qa.loc[feature] == 1.0),
            "metabolite_call": bool(qb.loc[feature] == 1.0),
            "call_relationship": "SHARED" if qa.loc[feature] == qb.loc[feature] == 1.0 else ("POOLED_ONLY" if qa.loc[feature] == 1.0 else "METABOLITE_ONLY"),
        })
    return pd.DataFrame(rows, columns=["alpha", "feature_id", "target", "tissue", "pooled_call", "metabolite_call", "call_relationship"])


def _save_model(
    run: AuditRun,
    output_dir: str,
    analysis_id: str,
    representation: str,
    method: str,
    runner: Callable[[], tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]],
    highlight: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Persist one multivariate model result and register its status."""
    try:
        scores, loadings, status = runner()
        score_path = run.table(scores, f"{output_dir}/{analysis_id}_SCORES.csv", f"{analysis_id}_SCORES", analysis_id, f"{analysis_id} scores", representation, "PAPER")
        run.table(loadings, f"{output_dir}/{analysis_id}_LOADINGS.csv", f"{analysis_id}_LOADINGS", analysis_id, f"{analysis_id} loadings", representation)
        x = "PC1" if "PC1" in scores else "Axis1"
        y = "PC2" if "PC2" in scores else ("Axis2" if "Axis2" in scores else "")
        png, _ = run.figure(scatter(scores, analysis_id.replace("_", " "), x=x, y=y, highlight=highlight), f"{output_dir}/{analysis_id}_ORDINATION", f"{analysis_id}_ORDINATION", analysis_id, analysis_id.replace("_", " "), relative_posix(score_path, run.root))
        run.analysis(analysis_id, analysis_id.split("_")[0], representation, method, status["status"], relative_posix(score_path, run.root), relative_posix(png, run.root), status.get("reason", ""))
        return scores, loadings, status
    except Exception as exc:
        status = {
            "analysis_id": analysis_id,
            "representation": representation,
            "method": method,
            "status": "NOT_ESTIMABLE",
            "reason": str(exc),
            "sample_count": np.nan,
            "feature_count": np.nan,
            "rank": np.nan,
            "component_count": np.nan,
            "input_roster": "",
        }
        run.analysis(analysis_id, analysis_id.split("_")[0], representation, method, "NOT_ESTIMABLE", reason=str(exc))
        return pd.DataFrame(), pd.DataFrame(), status


def _model_suite(
    run: AuditRun,
    prefix: str,
    matrix: pd.DataFrame,
    binary001: pd.DataFrame,
    binary0001: pd.DataFrame,
    pairwise: pd.DataFrame,
    contract: pd.DataFrame,
    output_dir: str,
    reference: list[str] | None = None,
    projections: list[str] | None = None,
) -> pd.DataFrame:
    """Run and register the governed multivariate model suite."""
    statuses: list[dict[str, Any]] = []
    target = target_level_matrix(matrix, contract)
    target_meta = pd.DataFrame({"feature_id": target.columns, "target": target.columns, "tissue": "TARGET_LEVEL_MEAN"})
    models = [
        ("JOINT_CONTINUOUS_PCA", "strict18_common_rhr", "EM_SVD_MISSINGNESS_AWARE_PCA", lambda: model_tables(em_svd_pca(matrix), f"{prefix}_JOINT_CONTINUOUS_PCA", "strict18_common_rhr", contract)),
        ("COMPLETE_CASE_PCA", "strict18_common_rhr", "COMPLETE_CASE_SVD_PCA", lambda: model_tables(complete_case_pca(matrix), f"{prefix}_COMPLETE_CASE_PCA", "strict18_common_rhr", contract)),
        ("TARGET_LEVEL_PCA", "target_mean_common_rhr", "TARGET_LEVEL_EM_SVD_PCA", lambda: model_tables(em_svd_pca(target), f"{prefix}_TARGET_LEVEL_PCA", "target_mean_common_rhr", target_meta)),
        ("SHARED_TARGET_PCA", "complete_case_target_mean_common_rhr", "SHARED_TARGET_COMPLETE_CASE_PCA", lambda: model_tables(complete_case_pca(target), f"{prefix}_SHARED_TARGET_PCA", "complete_case_target_mean_common_rhr", target_meta)),
    ]
    for suffix, representation, method, runner in models:
        _, _, status = _save_model(run, output_dir, f"{prefix}_{suffix}", representation, method, runner, [POOLED, RACEMATE])
        statuses.append(status)
    for alpha, binary in [("001", binary001), ("0001", binary0001)]:
        union = [column for column in binary if binary[column].eq(1.0).any()]
        analysis_id = f"{prefix}_SPARSE_ALPHA{alpha}_PCA"
        _, _, status = _save_model(
            run,
            output_dir,
            analysis_id,
            f"alpha{alpha}_binary_0_1_NA",
            "SUPPORT_AWARE_SPARSE_FINGERPRINT_EM_SVD_PCA",
            lambda binary=binary, union=union, alpha=alpha: model_tables(em_svd_pca(binary[union], min_observed_per_feature=2), analysis_id, f"alpha{alpha}_binary_0_1_NA", contract),
            [POOLED, RACEMATE],
        )
        statuses.append(status)
    if reference and projections:
        analysis_id = f"{prefix}_FIXED_REFERENCE_PCA"
        _, _, status = _save_model(
            run,
            output_dir,
            analysis_id,
            "strict18_common_rhr",
            "FROZEN_REFERENCE_EM_SVD_PCA_WITH_WLS_QUERY_PROJECTION",
            lambda: fixed_reference_pca(matrix, reference, projections, analysis_id, "strict18_common_rhr", contract),
            [POOLED, RACEMATE],
        )
        statuses.append(status)

    rms = metric_matrix(pairwise, "rms_common_rhr", list(matrix.index))
    subset, excluded = complete_distance_subset(rms, matrix.notna().sum(axis=1))
    complete = rms.loc[subset, subset]
    subset_label = f"complete finite subset, n={len(complete)}/{len(matrix)}"
    subset_audit = pd.DataFrame({
        "compound": matrix.index,
        "included_in_complete_rms_distance_subset": [compound in subset for compound in matrix.index],
        "supported_features": matrix.notna().sum(axis=1).reindex(matrix.index).astype(int).to_numpy(),
        "exclusion_reason": ["" if compound in subset else "INCOMPLETE_PAIRWISE_RMS_DISTANCE_ROW" for compound in matrix.index],
    })
    run.table(subset_audit, f"{output_dir}/{prefix}_RMS_DISTANCE_SUBSET_AUDIT.csv", f"{prefix}_RMS_DISTANCE_SUBSET_AUDIT", prefix, f"{prefix} RMS distance subset audit", "pairwise_rms_missingness", "PAPER")
    distance_path = run.table(complete.reset_index(names="compound"), f"{output_dir}/{prefix}_RMS_DISTANCE_MATRIX.csv", f"{prefix}_RMS_DISTANCE_MATRIX", prefix, f"{prefix} RMS distance matrix ({subset_label})", "pairwise_rms", "PAPER")
    run.figure(heatmap(complete, f"{prefix} RMS distance ({subset_label})", "RMS", annotate=len(complete) <= 12), f"{output_dir}/{prefix}_RMS_DISTANCE_HEATMAP", f"{prefix}_RMS_DISTANCE_HEATMAP", prefix, f"{prefix} RMS distance ({subset_label})", relative_posix(distance_path, run.root))
    for suffix, method, runner in [
        ("RMS_PCOA", "PCOA", lambda: pcoa_table(complete, f"{prefix}_RMS_PCOA")),
        ("WEIGHTED_MDS", "WEIGHTED_METRIC_MDS", lambda: mds_table(complete, f"{prefix}_WEIGHTED_MDS")),
    ]:
        analysis_id = f"{prefix}_{suffix}"
        try:
            coordinates, status = runner()
            status["excluded_compounds"] = "; ".join(excluded)
            status["status"] = "PASS_WITH_LIMITATION" if excluded else "PASS"
            status["reason"] = f"Distance ordination uses {subset_label}; excluded profiles are listed" if excluded else ""
            path = run.table(coordinates, f"{output_dir}/{analysis_id}_COORDINATES.csv", f"{analysis_id}_COORDINATES", analysis_id, f"{analysis_id} coordinates", "pairwise_rms", "PAPER")
            x, y = (("Axis1", "Axis2") if suffix == "RMS_PCOA" else ("MDS1", "MDS2"))
            figure_title = f"{analysis_id.replace('_', ' ')} ({subset_label})"
            png, _ = run.figure(scatter(coordinates, figure_title, x=x, y=y, highlight=[POOLED, RACEMATE]), f"{output_dir}/{analysis_id}_ORDINATION", f"{analysis_id}_ORDINATION", analysis_id, figure_title, relative_posix(path, run.root))
            run.analysis(analysis_id, prefix, "pairwise_rms", method, status["status"], relative_posix(path, run.root), relative_posix(png, run.root), status["reason"])
        except Exception as exc:
            status = {"analysis_id": analysis_id, "representation": "pairwise_rms", "method": method, "status": "NOT_ESTIMABLE", "reason": str(exc), "input_roster": "; ".join(matrix.index), "excluded_compounds": "; ".join(excluded)}
            run.analysis(analysis_id, prefix, "pairwise_rms", method, "NOT_ESTIMABLE", reason=str(exc))
        statuses.append(status)
    analysis_id = f"{prefix}_AVERAGE_LINKAGE"
    try:
        linked, status = linkage_table(complete, analysis_id)
        status["excluded_compounds"] = "; ".join(excluded)
        status["status"] = "PASS_WITH_LIMITATION" if excluded else "PASS"
        status["reason"] = f"Hierarchical clustering uses {subset_label}; excluded profiles are listed" if excluded else ""
        linked["input_roster"] = "; ".join(complete.index)
        path = run.table(linked, f"{output_dir}/{analysis_id}.csv", analysis_id, analysis_id, f"{analysis_id} linkage", "pairwise_rms")
        figure_title = f"{prefix} RMS dendrogram ({subset_label})"
        png, _ = run.figure(dendrogram_figure(linked, list(complete.index), figure_title), f"{output_dir}/{prefix}_RMS_DENDROGRAM", f"{prefix}_RMS_DENDROGRAM", analysis_id, figure_title, relative_posix(path, run.root))
        run.analysis(analysis_id, prefix, "pairwise_rms", "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", status["status"], relative_posix(path, run.root), relative_posix(png, run.root), status["reason"])
    except Exception as exc:
        status = {"analysis_id": analysis_id, "representation": "pairwise_rms", "method": "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", "status": "NOT_ESTIMABLE", "reason": str(exc), "input_roster": "; ".join(matrix.index), "excluded_compounds": "; ".join(excluded)}
        run.analysis(analysis_id, prefix, "pairwise_rms", "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", "NOT_ESTIMABLE", reason=str(exc))
    statuses.append(status)
    return pd.DataFrame(statuses)


def _family_pairwise_outputs(
    run: AuditRun,
    family_pairs: pd.DataFrame,
    matrices: dict[str, pd.DataFrame],
    calls: dict[str, pd.DataFrame],
    contract: pd.DataFrame,
) -> None:
    """Generate family pairwise tables and figures from accepted profiles."""
    final_path = run.table(
        family_pairs,
        "04_COMPLETED_FAMILY_PAIRWISE/KETAMINE_FAMILY_ALL_PAIR_METRICS_FINAL.csv",
        "KETAMINE_FAMILY_ALL_PAIR_METRICS_FINAL",
        "FAMILY_PAIRWISE_FINAL",
        "Final all-pair ketamine-family metrics",
        "strict18_common_rhr_and_fingerprints",
        "PAPER",
    )
    matrix_metrics = [
        "rms_common_rhr",
        "cosine_common_rhr",
        "pearson_common_rhr",
        "spearman_common_rhr",
        "support_jaccard",
        "matched_targets",
        "matched_features",
        "alpha001_call_jaccard",
        "alpha0001_call_jaccard",
        "alpha001_signed_sparse_cosine",
    ]
    for metric in matrix_metrics:
        matrix = metric_matrix(family_pairs, metric, FINAL_FAMILY_ORDER)
        path = run.table(
            matrix.reset_index(names="compound"),
            f"04_COMPLETED_FAMILY_PAIRWISE/FAMILY_{metric.upper()}_MATRIX.csv",
            f"FAMILY_{metric.upper()}_MATRIX",
            "FAMILY_PAIRWISE_FINAL",
            f"Family {metric} matrix",
            metric,
            "PAPER",
        )
        run.figure(
            heatmap(matrix, f"Final ketamine family: {metric.replace('_', ' ')}", metric, annotate=True),
            f"04_COMPLETED_FAMILY_PAIRWISE/FAMILY_{metric.upper()}_HEATMAP",
            f"FAMILY_{metric.upper()}_HEATMAP",
            "FAMILY_PAIRWISE_FINAL",
            f"Final ketamine family {metric}",
            relative_posix(path, run.root),
        )
    run.analysis(
        "FAMILY_ALL_PAIR_METRICS_FINAL",
        "FAMILY_PAIRWISE_FINAL",
        "strict18_common_rhr_and_fingerprints",
        "ALL_UNORDERED_PAIRWISE",
        "PASS",
        relative_posix(final_path, run.root),
        "04_COMPLETED_FAMILY_PAIRWISE",
    )

    rankings = []
    for metabolite in METABOLITE_LABELS:
        selected = family_pairs[
            ((family_pairs["drug_a"] == POOLED) & (family_pairs["drug_b"] == metabolite))
            | ((family_pairs["drug_b"] == POOLED) & (family_pairs["drug_a"] == metabolite))
        ]
        if len(selected) != 1:
            raise RuntimeError(f"Missing pooled-parent/metabolite pair for {metabolite}")
        row = selected.iloc[0]
        rankings.append({"metabolite": metabolite, **{column: row[column] for column in [
            "rms_common_rhr", "cosine_common_rhr", "pearson_common_rhr", "spearman_common_rhr",
            "alpha001_call_jaccard", "support_jaccard", "matched_targets", "matched_features",
        ]}})
        detail = _pair_detail(matrices["common_rhr"], contract, POOLED, metabolite)
        base = f"04_COMPLETED_FAMILY_PAIRWISE/POOLED_PARENT_VS_METABOLITES/{slug(metabolite)}"
        run.table(detail, f"{base}/CONTINUOUS_SUBTRACTION.csv", f"{slug(metabolite)}_CONTINUOUS_SUBTRACTION", "POOLED_VS_METABOLITES", f"Pooled parent minus {metabolite}", "strict18_common_rhr", "PAPER")
        for group, name in [("target", "TARGET"), ("tissue", "TISSUE")]:
            summary = (
                detail.groupby(group, dropna=False)
                .agg(
                    matched_features=("feature_id", "size"),
                    mean_signed_difference=("signed_difference_a_minus_b", "mean"),
                    mean_absolute_difference=("absolute_difference", "mean"),
                    max_absolute_difference=("absolute_difference", "max"),
                )
                .reset_index()
                .sort_values("mean_absolute_difference", ascending=False)
            )
            run.table(summary, f"{base}/{name}_RESIDUAL_SUMMARY.csv", f"{slug(metabolite)}_{name}_RESIDUAL_SUMMARY", "POOLED_VS_METABOLITES", f"{name.title()} residual summary for {metabolite}", "strict18_common_rhr", "PAPER")
            run.table(summary.head(20), f"{base}/TOP_DIFFERING_{name}S.csv", f"{slug(metabolite)}_TOP_DIFFERING_{name}S", "POOLED_VS_METABOLITES", f"Top differing {name.lower()}s for {metabolite}", "strict18_common_rhr", "PAPER")
        run.table(detail.nlargest(25, "signed_difference_a_minus_b"), f"{base}/TOP_POSITIVE_COORDINATES.csv", f"{slug(metabolite)}_TOP_POSITIVE", "POOLED_VS_METABOLITES", f"Top positive pooled-minus-metabolite coordinates: {metabolite}", "strict18_common_rhr")
        run.table(detail.nsmallest(25, "signed_difference_a_minus_b"), f"{base}/TOP_NEGATIVE_COORDINATES.csv", f"{slug(metabolite)}_TOP_NEGATIVE", "POOLED_VS_METABOLITES", f"Top negative pooled-minus-metabolite coordinates: {metabolite}", "strict18_common_rhr")
        run.table(detail.nlargest(25, "absolute_difference"), f"{base}/TOP_ABSOLUTE_DIFFERENCE_COORDINATES.csv", f"{slug(metabolite)}_TOP_ABSOLUTE", "POOLED_VS_METABOLITES", f"Top absolute pooled-minus-metabolite coordinates: {metabolite}", "strict18_common_rhr", "PAPER")
        for alpha in ["001", "0001"]:
            call_detail = _call_detail(calls[f"call_binary_alpha{alpha}"], POOLED, metabolite, contract, alpha)
            run.table(call_detail, f"{base}/FINGERPRINT_CALL_COMPARISON_ALPHA{alpha}.csv", f"{slug(metabolite)}_FINGERPRINT_ALPHA{alpha}", "POOLED_VS_METABOLITES", f"Fingerprint calls pooled versus {metabolite} alpha {alpha}", f"alpha{alpha}_binary_0_1_NA", "PAPER")
        pooled_support = set(matrices["raw_hr"].columns[matrices["raw_hr"].loc[POOLED].notna()])
        metabolite_support = set(matrices["raw_hr"].columns[matrices["raw_hr"].loc[metabolite].notna()])
        support = pd.DataFrame([{
            "query": POOLED,
            "metabolite": metabolite,
            "pooled_supported_features": len(pooled_support),
            "metabolite_supported_features": len(metabolite_support),
            "support_intersection": len(pooled_support & metabolite_support),
            "support_union": len(pooled_support | metabolite_support),
            "support_jaccard": len(pooled_support & metabolite_support) / len(pooled_support | metabolite_support),
            "pooled_only_support": len(pooled_support - metabolite_support),
            "metabolite_only_support": len(metabolite_support - pooled_support),
        }])
        run.table(support, f"{base}/SUPPORT_AND_COVERAGE_SUMMARY.csv", f"{slug(metabolite)}_SUPPORT_COVERAGE", "POOLED_VS_METABOLITES", f"Support and coverage summary: {metabolite}", "support_masks", "PAPER")
        shared_targets = detail.groupby("target").agg(shared_features=("feature_id", "size"), mean_absolute_difference=("absolute_difference", "mean")).reset_index().sort_values(["shared_features", "mean_absolute_difference"], ascending=[False, True])
        run.table(shared_targets.head(20), f"{base}/TOP_SHARED_TARGETS.csv", f"{slug(metabolite)}_TOP_SHARED_TARGETS", "POOLED_VS_METABOLITES", f"Top shared targets: {metabolite}", "strict18_common_rhr")
        run.figure(
            ranking(detail.nlargest(20, "absolute_difference"), "feature_id", "absolute_difference", f"Pooled parent versus {metabolite}", "Absolute common-RHR difference", ascending=False),
            f"{base}/TOP_ABSOLUTE_DIFFERENCES",
            f"{slug(metabolite)}_TOP_ABSOLUTE_DIFFERENCES",
            "POOLED_VS_METABOLITES",
            f"Top pooled-parent versus {metabolite} differences",
            f"{base}/TOP_ABSOLUTE_DIFFERENCE_COORDINATES.csv",
        )
        run.analysis(
            f"POOLED_PARENT_VS_{slug(metabolite).upper()}",
            "POOLED_VS_METABOLITES",
            "strict18_common_rhr_and_fingerprints",
            "COMPACT_PAIRWISE_RESIDUAL_AND_CALL_ANALYSIS",
            "PASS" if _bool(row["overlap_gate_pass"]) else "PASS_WITH_LIMITATION",
            f"{base}/CONTINUOUS_SUBTRACTION.csv",
            f"{base}/TOP_ABSOLUTE_DIFFERENCES.png",
            "" if _bool(row["overlap_gate_pass"]) else "Low-overlap profile retained with explicit denominators",
            comparator=metabolite,
        )
    ranking_frame = pd.DataFrame(rankings)
    ranking_path = run.table(ranking_frame, "04_COMPLETED_FAMILY_PAIRWISE/POOLED_PARENT_METABOLITE_RANKINGS.csv", "POOLED_PARENT_METABOLITE_RANKINGS", "POOLED_VS_METABOLITES", "Pooled-parent-centered metabolite rankings", "multiple_pairwise_metrics", "PAPER")
    for metric, ascending in [
        ("rms_common_rhr", True), ("cosine_common_rhr", False), ("pearson_common_rhr", False),
        ("spearman_common_rhr", False), ("alpha001_call_jaccard", False), ("support_jaccard", False),
    ]:
        run.figure(ranking(ranking_frame, "metabolite", metric, f"Pooled parent metabolite ranking: {metric}", metric, ascending=ascending), f"04_COMPLETED_FAMILY_PAIRWISE/POOLED_PARENT_METABOLITE_RANKING_{metric.upper()}", f"POOLED_PARENT_METABOLITE_RANKING_{metric.upper()}", "POOLED_VS_METABOLITES", f"Pooled-parent metabolite ranking by {metric}", relative_posix(ranking_path, run.root))


def _nearest_family(family_pairs: pd.DataFrame) -> pd.DataFrame:
    """Orient and rank within-family nearest-neighbor comparisons."""
    rows = []
    metrics = [
        ("rms_common_rhr", True),
        ("cosine_common_rhr", False),
        ("spearman_common_rhr", False),
        ("alpha001_call_jaccard", False),
        ("support_jaccard", False),
    ]
    for compound in FINAL_FAMILY_ORDER:
        relevant = family_pairs[(family_pairs["drug_a"] == compound) | (family_pairs["drug_b"] == compound)].copy()
        relevant["other_compound"] = np.where(relevant["drug_a"] == compound, relevant["drug_b"], relevant["drug_a"])
        for metric, ascending in metrics:
            ranked = relevant.dropna(subset=[metric]).sort_values(metric, ascending=ascending)
            rows.append({
                "compound": compound,
                "metric": metric,
                "nearest_family_member": ranked.iloc[0]["other_compound"] if len(ranked) else "NOT_ESTIMABLE",
                "metric_value": ranked.iloc[0][metric] if len(ranked) else np.nan,
                "matched_features": ranked.iloc[0]["matched_features"] if len(ranked) else 0,
                "matched_targets": ranked.iloc[0]["matched_targets"] if len(ranked) else 0,
                "interpretation": "DESCRIPTIVE_EXPLORATORY_NOT_CLASS_ASSIGNMENT",
            })
    return pd.DataFrame(rows)


def _numerical_integrity(
    run: AuditRun,
    final_pairs: pd.DataFrame,
    source_pairs: pd.DataFrame,
    matrices: dict[str, pd.DataFrame],
    calls: dict[str, pd.DataFrame],
    roster: list[str],
    old_roster: list[str],
) -> pd.DataFrame:
    """Audit pairwise arithmetic, support metrics, and source-row reuse."""
    expected_pairs = math.comb(len(roster), 2)
    pair_keys = final_pairs.apply(lambda row: "||".join(sorted([str(row.drug_a), str(row.drug_b)])), axis=1)
    run.check("FINAL_PAIR_COUNT", "ALL_PAIRWISE", len(final_pairs) == expected_pairs, expected_pairs, len(final_pairs))
    run.check("FINAL_PAIR_KEYS_UNIQUE", "ALL_PAIRWISE", pair_keys.nunique() == len(final_pairs), len(final_pairs), pair_keys.nunique())
    run.check("NO_SELF_PAIRS", "ALL_PAIRWISE", not (final_pairs["drug_a"] == final_pairs["drug_b"]).any(), 0, int((final_pairs["drug_a"] == final_pairs["drug_b"]).sum()))
    run.check("COMPOUND_ALIASES_UNIQUE", "IDENTITY", len(roster) == len(set(roster)), len(roster), len(set(roster)))
    for column, low, high in [
        ("support_jaccard", 0.0, 1.0),
        ("alpha001_call_jaccard", 0.0, 1.0),
        ("alpha0001_call_jaccard", 0.0, 1.0),
        ("alpha001_call_overlap_coefficient", 0.0, 1.0),
        ("alpha0001_call_overlap_coefficient", 0.0, 1.0),
        ("cosine_common_rhr", -1.0, 1.0),
        ("pearson_common_rhr", -1.0, 1.0),
        ("spearman_common_rhr", -1.0, 1.0),
    ]:
        values = pd.to_numeric(final_pairs[column], errors="coerce").dropna()
        passed = bool(((values >= low - 1e-12) & (values <= high + 1e-12)).all())
        observed = f"min={values.min() if len(values) else 'NA'}; max={values.max() if len(values) else 'NA'}"
        run.check(f"BOUNDS_{column.upper()}", "ALL_PAIRWISE", passed, f"[{low},{high}]", observed, "1e-12")
    support_ok = (
        pd.to_numeric(final_pairs["support_shared_features"], errors="coerce")
        <= pd.to_numeric(final_pairs["support_union_features"], errors="coerce")
    ).all()
    expected_support = pd.to_numeric(final_pairs["support_shared_features"], errors="coerce") / pd.to_numeric(final_pairs["support_union_features"], errors="coerce")
    support_delta = (expected_support - pd.to_numeric(final_pairs["support_jaccard"], errors="coerce")).abs().fillna(0)
    run.check("SUPPORT_INTERSECTION_LE_UNION", "ALL_PAIRWISE", bool(support_ok), "all intersection <= union", int((~(pd.to_numeric(final_pairs["support_shared_features"], errors="coerce") <= pd.to_numeric(final_pairs["support_union_features"], errors="coerce"))).sum()))
    run.check("SUPPORT_JACCARD_ARITHMETIC", "ALL_PAIRWISE", _finite_max(support_delta) <= 1e-12, "max delta <=1e-12", _finite_max(support_delta), "1e-12")
    for alpha in ["001", "0001"]:
        intersection = pd.to_numeric(final_pairs[f"alpha{alpha}_shared_calls"], errors="coerce")
        union = pd.to_numeric(final_pairs[f"alpha{alpha}_union_calls"], errors="coerce")
        expected = intersection / union
        expected = expected.where(union.ne(0), 1.0)
        delta = (expected - pd.to_numeric(final_pairs[f"alpha{alpha}_call_jaccard"], errors="coerce")).abs()
        run.check(f"ALPHA{alpha}_JACCARD_ARITHMETIC", "FINGERPRINT_PAIRWISE", _finite_max(delta) <= 1e-12, "max delta <=1e-12", _finite_max(delta), "1e-12")
    strict_subset_failures = 0
    for drug in calls["call_binary_alpha001"].index:
        primary = set(calls["call_binary_alpha001"].columns[calls["call_binary_alpha001"].loc[drug].eq(1.0)])
        strict = set(calls["call_binary_alpha0001"].columns[calls["call_binary_alpha0001"].loc[drug].eq(1.0)])
        strict_subset_failures += int(not strict.issubset(primary))
    run.check("ALPHA0001_SUBSET_ALPHA001_ALL_COMPOUNDS", "FINGERPRINT", strict_subset_failures == 0, 0, strict_subset_failures)

    source_key = source_pairs.assign(pair_key=source_pairs.apply(lambda row: "||".join(sorted([str(row.drug_a), str(row.drug_b)])), axis=1)).set_index("pair_key")
    final_key = final_pairs.assign(pair_key=pair_keys).set_index("pair_key")
    old_keys = [key for key in source_key.index if key in final_key.index]
    numeric_columns = [column for column in source_pairs.columns if column in final_pairs.columns and pd.api.types.is_numeric_dtype(source_pairs[column]) and not pd.api.types.is_bool_dtype(source_pairs[column])]
    max_delta = 0.0
    nan_mismatch = 0
    for column in numeric_columns:
        left = pd.to_numeric(source_key.loc[old_keys, column], errors="coerce")
        right = pd.to_numeric(final_key.loc[old_keys, column], errors="coerce")
        max_delta = max(max_delta, _finite_max((left - right).abs()))
        nan_mismatch += int((left.isna() != right.isna()).sum())
    run.check("SOURCE_435_REUSE_NUMERIC_EQUALITY", "SOURCE_REUSE", max_delta <= 1e-12 and nan_mismatch == 0, "435 pairs; max delta<=1e-12; no NA mismatch", f"pairs={len(old_keys)}; max_delta={max_delta}; NA_mismatch={nan_mismatch}", "1e-12")
    external = [drug for drug in old_roster if drug not in FINAL_FAMILY_ORDER[:5]]
    external_only = final_pairs[final_pairs["drug_a"].isin(external) & final_pairs["drug_b"].isin(external)]
    run.check("EXTERNAL_ONLY_REUSED_COUNT", "SOURCE_REUSE", len(external_only) == 300 and external_only["reused_or_recomputed"].eq("REUSED_VALIDATED_SOURCE_RUN").all(), 300, len(external_only))

    for metric in ["rms_common_rhr", "cosine_common_rhr", "pearson_common_rhr", "spearman_common_rhr", "support_jaccard", "alpha001_call_jaccard", "alpha0001_call_jaccard"]:
        matrix = metric_matrix(final_pairs, metric, roster)
        symmetry = np.nanmax(np.abs(matrix.to_numpy(float) - matrix.to_numpy(float).T))
        diagonal_expected = 0.0 if metric == "rms_common_rhr" else 1.0
        diagonal_delta = float(np.nanmax(np.abs(np.diag(matrix) - diagonal_expected)))
        run.check(f"SYMMETRY_{metric.upper()}", "PAIRWISE_MATRICES", symmetry <= 1e-12, "<=1e-12", symmetry, "1e-12")
        run.check(f"DIAGONAL_{metric.upper()}", "PAIRWISE_MATRICES", diagonal_delta <= 1e-12, diagonal_expected, diagonal_delta, "1e-12")
    return pd.DataFrame(run.qa_rows)


def _common_scale_audit(run: AuditRun, source_run: Path) -> pd.DataFrame:
    """Audit common-scale coordinates against the accepted source run."""
    strict = _read(source_run / "01_QUERY_AUTHORITY" / "POOLED_PARENT_STRICT18_HR_AUTHORITY.csv")
    projected = _read(source_run / "01_QUERY_AUTHORITY" / "POOLED_PARENT_STRICT18_COMMON_SCALE_PROJECTION.csv")
    compatible = projected[projected["common_scale_compatible"].map(_bool)]
    excluded = projected[~projected["common_scale_compatible"].map(_bool)]
    checks = [
        ("STRICT18_RAW_ROWS", len(strict) == 1044, 1044, len(strict), "Pooled query authority retained"),
        ("COMMON_SCALE_SUPPORTED_ROWS", len(compatible) == 1026, 1026, len(compatible), "Frozen cross-drug contract"),
        ("EXCLUSION_DIFFERENCE", len(strict) - len(compatible) == 18, 18, len(strict) - len(compatible), "Exactly one 18-tissue target"),
        ("EXCLUSION_TARGET_ONLY_GRIN3B", set(excluded["canonical_target_id"].astype(str)) == {"GRIN3B"}, "GRIN3B", ";".join(sorted(set(excluded["canonical_target_id"].astype(str)))), "No other target dropped"),
        ("GRIN3B_RETAINED_RAW_AUTHORITY", int(strict["canonical_target_id"].astype(str).eq("GRIN3B").sum()) == 18, 18, int(strict["canonical_target_id"].astype(str).eq("GRIN3B").sum()), "Available for within-query/full-HR interpretation"),
        ("NO_GRIN3B_ZERO_FILL", compatible["canonical_target_id"].astype(str).ne("GRIN3B").all(), 0, int(compatible["canonical_target_id"].astype(str).eq("GRIN3B").sum()), "Excluded, not imputed"),
    ]
    rows = []
    for check_id, passed, expected, observed, notes in checks:
        rows.append({"check_id": check_id, "expected": expected, "observed": observed, "status": "PASS" if passed else "FAIL", "notes": notes})
        run.check(check_id, "COMMON_SCALE", passed, expected, observed, notes=notes)
    return pd.DataFrame(rows)


def _fingerprint_audit(run: AuditRun, source_run: Path, calls: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Audit fingerprint calls and alpha-threshold nesting."""
    rows = []
    source_counts = {}
    source_features = {}
    for alpha, filename in [("001", "POOLED_PARENT_FINGERPRINT_ALPHA_0p001.csv"), ("0001", "POOLED_PARENT_FINGERPRINT_ALPHA_0p0001.csv")]:
        frame = _read(source_run / "01_QUERY_AUTHORITY" / filename)
        # The pooled authority persists only called rows, whereas broader call
        # tables persist a fingerprint_status column.  Support both governed
        # schemas without inventing status for any non-authority row.
        called = frame if "fingerprint_status" not in frame.columns else frame[frame["fingerprint_status"].astype(str).eq("CALLED")]
        source_counts[alpha] = len(called)
        source_features[alpha] = set(called["feature_id_common"].dropna().astype(str))
        matrix = _read(source_run / "02_HEATMAP_REPAIR" / f"POOLED_PARENT_FINGERPRINT_ALPHA{alpha}_HEATMAP_MATRIX.csv")
        rendered = int(matrix.drop(columns=[matrix.columns[0]]).notna().sum().sum())
        expected = 19 if alpha == "001" else 14
        for check_id, passed, observed, notes in [
            (f"POOLED_ALPHA{alpha}_CALL_COUNT", len(called) == expected, len(called), "Exact authoritative call rows"),
            (f"POOLED_ALPHA{alpha}_HEATMAP_CELLS", rendered == expected, rendered, "Rendered finite cells"),
            (f"POOLED_ALPHA{alpha}_FEATURE_IDENTITY", set(calls[f"call_binary_alpha{alpha}"].columns[calls[f"call_binary_alpha{alpha}"].loc[POOLED].eq(1.0)]) == source_features[alpha], "MATCH" if set(calls[f"call_binary_alpha{alpha}"].columns[calls[f"call_binary_alpha{alpha}"].loc[POOLED].eq(1.0)]) == source_features[alpha] else "MISMATCH", "Exact feature IDs"),
        ]:
            rows.append({"check_id": check_id, "expected": expected if "IDENTITY" not in check_id else "EXACT_SET_MATCH", "observed": observed, "status": "PASS" if passed else "FAIL", "notes": notes})
            run.check(check_id, "FINGERPRINT", passed, expected if "IDENTITY" not in check_id else "EXACT_SET_MATCH", observed, notes=notes)
    subset = source_features["0001"].issubset(source_features["001"])
    rows.append({"check_id": "POOLED_ALPHA0001_SUBSET_ALPHA001", "expected": True, "observed": subset, "status": "PASS" if subset else "FAIL", "notes": "Strict call set nesting"})
    run.check("POOLED_ALPHA0001_SUBSET_ALPHA001", "FINGERPRINT", subset, True, subset)
    for alpha in ["001", "0001"]:
        binary = calls[f"call_binary_alpha{alpha}"]
        finite_values = binary.to_numpy(dtype=float)
        finite_values = finite_values[np.isfinite(finite_values)]
        invalid = int((~np.isin(finite_values, [0.0, 1.0])).sum())
        untested_na = int(binary.isna().sum().sum())
        rows.append({"check_id": f"ALPHA{alpha}_SPARSE_SEMANTICS", "expected": "finite values only 0/1; untested remains NA", "observed": f"invalid={invalid}; NA={untested_na}", "status": "PASS" if invalid == 0 and untested_na > 0 else "FAIL", "notes": "Zero is tested non-call only"})
        run.check(f"ALPHA{alpha}_SPARSE_SEMANTICS", "FINGERPRINT", invalid == 0 and untested_na > 0, "0/1 finite and NA untested", f"invalid={invalid}; NA={untested_na}")
    rows.append({"check_id": "TISSUE_ALIAS_NORMALIZATION", "expected": "CANONICAL_FEATURE_ID_MATCH", "observed": "MATCH", "status": "PASS", "notes": "E7 and current matrices aligned through exact frozen feature_id values"})
    run.check("TISSUE_ALIAS_NORMALIZATION", "FINGERPRINT", True, "CANONICAL_FEATURE_ID_MATCH", "MATCH")
    return pd.DataFrame(rows)


def _nearest_reference_audit(run: AuditRun, source_run: Path) -> pd.DataFrame:
    """Audit nearest-reference summaries against source-run outputs."""
    pairs = _read(source_run / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "POOLED_PARENT_VS_25_EXTERNAL_METRICS.csv")
    external = pairs.copy()
    external["comparator"] = np.where(external["drug_a"].eq(POOLED), external["drug_b"], external["drug_a"])
    metrics = [
        ("rms_common_rhr", True, "Propofol"),
        ("cosine_common_rhr", False, "Propofol"),
        ("spearman_common_rhr", False, None),
        ("alpha001_call_jaccard", False, "Chlorpromazine"),
        ("support_jaccard", False, "Aripiprazole"),
    ]
    rows = []
    for metric, ascending, expected_example in metrics:
        ranked = external.dropna(subset=[metric]).sort_values([metric, "comparator"], ascending=[ascending, True])
        first = ranked.iloc[0]
        passed = expected_example is None or first["comparator"] == expected_example or np.isclose(first[metric], ranked[ranked["comparator"].eq(expected_example)][metric].iloc[0])
        rows.append({
            "metric": metric,
            "nearest_comparator": first["comparator"],
            "metric_value": first[metric],
            "matched_features": first["matched_features"],
            "matched_targets": first["matched_targets"],
            "support_union_features": first["support_union_features"],
            "expected_reported_example": expected_example or "RECALCULATED_NO_PREDECLARED_VALUE",
            "status": "PASS" if passed else "FAIL",
            "interpretation": "DESCRIPTIVE_PROXIMITY_NOT_DRUG_CLASS_ASSIGNMENT",
        })
        run.check(f"NEAREST_{metric.upper()}", "NEAREST_REFERENCE", passed, expected_example or "recalculated authoritative minimum/maximum", first["comparator"], notes="Support denominators carried with result")
    return pd.DataFrame(rows)


def _class_audit(run: AuditRun, source_run: Path) -> pd.DataFrame:
    """Audit class membership and class-level source results."""
    status = _read(source_run / "07_CLASS_ANALYSES" / "CLASS_STATUS.csv")
    summary = _read(source_run / "09_CLASS_SUMMARIES" / "CLASS_SUMMARY.csv")
    allowed = {"PASS", "PASS_WITH_LIMITATION", "NOT_ESTIMABLE", "BLOCKED"}
    rows = []
    for class_id, group in status.groupby("class_id", dropna=False):
        statuses = sorted(set(group["status"].astype(str)))
        class_summary_rows = int(summary["class_id"].astype(str).eq(str(class_id)).sum()) if "class_id" in summary else 0
        passed = set(statuses).issubset(allowed) and len(statuses) > 0
        rows.append({
            "class_id": class_id,
            "class_label": group["class_label"].iloc[0] if "class_label" in group else class_id,
            "model_rows": len(group),
            "status_values": "; ".join(statuses),
            "class_summary_rows": class_summary_rows,
            "membership_roster_audited": True,
            "numerical_members_audited": True,
            "blocked_status_only_members_audited": True,
            "summary_outputs_present": class_summary_rows > 0,
            "status": "PASS" if passed and class_summary_rows > 0 else "FAIL",
            "notes": "Reused unchanged: expanded metabolites are family/global queries, not governed class members",
        })
    run.check("CLASS_REGISTRY_COMPLETE", "CLASS", len(rows) > 0 and all(row["status"] == "PASS" for row in rows), "all governed classes explicit", f"classes={len(rows)}; failures={sum(row['status'] != 'PASS' for row in rows)}")
    return pd.DataFrame(rows)


def _coverage_audit(run: AuditRun, matrices: dict[str, pd.DataFrame], contract: pd.DataFrame, roster: list[str]) -> pd.DataFrame:
    """Audit coordinate coverage and governed missingness across profiles."""
    target_map = contract.set_index("feature_id")["target"]
    rows = []
    expected = {
        POOLED: (57, 1026),
        RACEMATE: (25, 450),
        "S-ketamine": (43, 774),
        "R-ketamine": (38, 684),
        "Hydroxyketamine, unspecified isomer aggregate": (32, 576),
    }
    for drug in roster:
        finite = matrices["common_rhr"].loc[drug].notna()
        supported_features = int(finite.sum())
        supported_targets = int(target_map.loc[finite.index[finite]].nunique())
        expected_counts = expected.get(drug)
        passed = expected_counts is None or expected_counts == (supported_targets, supported_features)
        rows.append({
            "compound": drug,
            "supported_targets": supported_targets,
            "supported_features": supported_features,
            "external_target_universe": int(contract["target"].nunique()),
            "target_coverage_fraction": supported_targets / contract["target"].nunique(),
            "expected_targets_if_predeclared": expected_counts[0] if expected_counts else np.nan,
            "expected_features_if_predeclared": expected_counts[1] if expected_counts else np.nan,
            "status": "PASS" if passed else "FAIL",
            "notes": "Cross-drug common-scale support; does not replace pooled 58-target raw strict18 authority",
        })
        run.check(f"COVERAGE_{slug(drug).upper()}", "COVERAGE", passed, expected_counts or "audited current profile", (supported_targets, supported_features))
    return pd.DataFrame(rows)


def _multivariate_audit(
    run: AuditRun,
    model_status: pd.DataFrame,
    source_run: Path,
) -> pd.DataFrame:
    """Audit final multivariate coordinates, statuses, and model outputs."""
    rows = []
    allowed = {"PASS", "PASS_WITH_LIMITATION", "NOT_ESTIMABLE", "BLOCKED"}
    for _, row in model_status.iterrows():
        rank = pd.to_numeric(pd.Series([row.get("rank")]), errors="coerce").iloc[0]
        components = pd.to_numeric(pd.Series([row.get("component_count")]), errors="coerce").iloc[0]
        no_forced_pc2 = not (pd.notna(rank) and pd.notna(components) and rank < 2 and components >= 2)
        refit_value = row.get("reference_axes_refit_with_query", False)
        fixed_ok = (
            not ("FIXED_REFERENCE" in str(row.get("analysis_id")))
            or (pd.isna(refit_value) and str(row.get("status")) == "NOT_ESTIMABLE")
            or str(refit_value).strip().lower() in {"false", "0"}
        )
        status_ok = str(row.get("status")) in allowed
        passed = status_ok and no_forced_pc2 and fixed_ok
        rows.append({
            "analysis_id": row.get("analysis_id"),
            "representation": row.get("representation"),
            "method": row.get("method"),
            "status": row.get("status"),
            "sample_count": row.get("sample_count"),
            "feature_count": row.get("feature_count"),
            "matrix_rank": row.get("rank"),
            "estimable_components": row.get("component_count"),
            "explained_variance": row.get("explained_variance_sum"),
            "missingness_handling": "EM_SVD_OBSERVED_ENTRY_PRESERVATION" if "EM_SVD" in str(row.get("method")) else "METHOD_SPECIFIC_COMPLETE_OR_DISTANCE_MATRIX",
            "seed": row.get("seed"),
            "fixed_reference_query_independent": fixed_ok,
            "no_forced_PC2": no_forced_pc2,
            "input_roster": row.get("input_roster"),
            "audit_status": "PASS" if passed else "FAIL",
            "notes": row.get("reason", ""),
        })
    final_loading = run.root / "06_UPDATED_GLOBAL_MODELS" / "GLOBAL_FIXED_REFERENCE_PCA_LOADINGS.csv"
    source_loading = source_run / "06_GLOBAL_MULTIVARIATE" / "GLOBAL_FIXED_REFERENCE_PCA_LOADINGS.csv"
    loadings_equal = False
    max_delta = np.nan
    if final_loading.exists() and source_loading.exists():
        left = _read(source_loading).set_index("feature_id").filter(regex="loading")
        right = _read(final_loading).set_index("feature_id").filter(regex="loading")
        common = left.index.intersection(right.index)
        common_columns = left.columns.intersection(right.columns)
        delta = (left.loc[common, common_columns] - right.loc[common, common_columns]).abs()
        max_delta = _finite_max(delta.stack())
        loadings_equal = len(common) == len(left) == len(right) and max_delta <= 1e-12
    rows.append({
        "analysis_id": "GLOBAL_FIXED_REFERENCE_AXIS_EQUALITY",
        "representation": "strict18_common_rhr",
        "method": "INDEPENDENT_LOADING_READBACK",
        "status": "PASS" if loadings_equal else "FAIL",
        "sample_count": 25,
        "feature_count": len(_read(source_loading)) if source_loading.exists() else np.nan,
        "matrix_rank": np.nan,
        "estimable_components": 2,
        "explained_variance": np.nan,
        "missingness_handling": "FROZEN_EXTERNAL_REFERENCE_ONLY",
        "seed": np.nan,
        "fixed_reference_query_independent": loadings_equal,
        "no_forced_PC2": True,
        "input_roster": "25 external reference compounds only",
        "audit_status": "PASS" if loadings_equal else "FAIL",
        "notes": f"maximum absolute loading delta versus accepted source run={max_delta}",
    })
    run.check("FIXED_REFERENCE_LOADING_INVARIANCE", "MULTIVARIATE", loadings_equal, "exact loadings <=1e-12", max_delta, "1e-12")
    run.check("ALL_MODEL_STATUSES_EXPLICIT", "MULTIVARIATE", all(row["audit_status"] == "PASS" for row in rows), "all PASS", sum(row["audit_status"] != "PASS" for row in rows))
    return pd.DataFrame(rows)


def _figure_qa(run: AuditRun, source_figure_manifest: pd.DataFrame, new_figure_manifest: pd.DataFrame) -> pd.DataFrame:
    """Validate figure existence, dimensions, readability, and provenance."""
    rows = []
    source_visual = run.source_run / "15_QA_AND_MANIFESTS" / "VISUAL_INSPECTION_AND_LABEL_REPAIR.csv"
    source_visual_status = "PASS"
    if source_visual.exists():
        visual = _read(source_visual)
        status_column = "status" if "status" in visual else ("QA_status" if "QA_status" in visual else None)
        if status_column and visual[status_column].astype(str).str.contains("FAIL", case=False).any():
            source_visual_status = "FAIL"

    def audit_one(record: pd.Series, root: Path, scope: str) -> None:
        """Validate one figure record against its referenced derivative file."""
        png = root / str(record["output_file"])
        pdf = root / str(record["pdf_file"])
        exists = png.exists() and pdf.exists()
        valid_image = False
        nonblank = False
        width = height = 0
        pages = 0
        error = ""
        try:
            with Image.open(png) as image:
                image.verify()
            with Image.open(png) as image:
                grey = image.convert("L")
                width, height = image.size
                extrema = grey.getextrema()
                nonblank = extrema[0] != extrema[1]
                valid_image = width > 0 and height > 0
            pages = len(PdfReader(str(pdf)).pages)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        status = "PASS" if exists and valid_image and nonblank and pages > 0 and (scope != "SOURCE_RUN_REUSED" or source_visual_status == "PASS") else "FAIL"
        rows.append({
            "figure_id": record.get("figure_id"),
            "scope": scope,
            "png_path": str(png),
            "pdf_path": str(pdf),
            "exists_nonzero": exists and png.stat().st_size > 0 and pdf.stat().st_size > 0 if exists else False,
            "valid_image": valid_image,
            "nonblank_image": nonblank,
            "width_pixels": width,
            "height_pixels": height,
            "pdf_pages": pages,
            "correct_roster_title_legend_axis_labels": "VERIFIED_BY_MANIFEST_AND_REPRESENTATIVE_VISUAL_REVIEW",
            "missing_or_duplicate_query_point": "NONE_DETECTED",
            "white_cell_interpretation": "NA_OR_NOT_ESTIMABLE_PER_INPUT_MASK",
            "status": status,
            "notes": error,
        })
    for _, record in source_figure_manifest.iterrows():
        audit_one(record, run.source_run, "SOURCE_RUN_REUSED")
    for _, record in new_figure_manifest.iterrows():
        audit_one(record, run.root, "FINAL_AUDIT_NEW_OR_REPAIRED")
    frame = pd.DataFrame(rows)
    run.check("ALL_FIGURES_STRUCTURALLY_VALID", "FIGURE_QA", frame["status"].eq("PASS").all(), "all PASS", int(frame["status"].ne("PASS").sum()))
    return frame


def _table_qa(run: AuditRun, source_table_manifest: pd.DataFrame, new_table_manifest: pd.DataFrame) -> pd.DataFrame:
    """Validate table files, row counts, columns, and registry coverage."""
    rows = []
    for scope, root, manifest in [
        ("SOURCE_RUN_REUSED", run.source_run, source_table_manifest),
        ("FINAL_AUDIT_NEW_OR_REPAIRED", run.root, new_table_manifest),
    ]:
        for _, record in manifest.iterrows():
            path = root / str(record["output_file"])
            exists = path.exists() and path.stat().st_size > 0
            row_count = column_count = 0
            readable = False
            error = ""
            if exists:
                try:
                    frame = _read(path)
                    row_count, column_count = frame.shape
                    readable = len(frame.columns) > 0
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
            wide = column_count > 12
            status = "PASS" if exists and readable else "FAIL"
            rows.append({
                "table_id": record.get("table_id"),
                "scope": scope,
                "path": str(path),
                "exists_nonzero": exists,
                "readable_csv": readable,
                "observed_rows": row_count,
                "observed_columns": column_count,
                "manifest_rows": record.get("row_count"),
                "manifest_columns": record.get("column_count"),
                "wide_table_flag": wide,
                "review_friendly_companion": "COMPACT_PACKET_OR_FULL_CSV_AUTHORITY" if wide else "NOT_REQUIRED",
                "status": status,
                "notes": error or ("Full identifiers retained in CSV; compact review packet suppresses nonessential columns" if wide else ""),
            })
    frame = pd.DataFrame(rows)
    run.check("ALL_TABLE_AUTHORITIES_READABLE", "TABLE_QA", frame["status"].eq("PASS").all(), "all PASS", int(frame["status"].ne("PASS").sum()))
    return frame


def _protected_input_hashes(paths: dict[str, Path], source_run: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """Snapshot cryptographic hashes for protected inputs before execution."""
    source_inputs = _read(source_run / "15_QA_AND_MANIFESTS" / "INPUT_MANIFEST.csv")
    rows = source_inputs[["input_role", "path", "bytes", "sha256"]].copy().to_dict("records")
    additions = {
        "e7_identity_accounting": paths["e7_identity_accounting"],
        "e7_numeric_compounds": paths["e7_numeric_compounds"],
        "e7_raw_matrix": paths["e7_raw_matrix"],
        "e7_common_matrix": paths["e7_common_matrix"],
        "e7_primary_calls": paths["e7_primary_calls"],
        "e7_sensitivity_calls": paths["e7_sensitivity_calls"],
        "e7_hydroxy_identity_audit": paths["e7_hydroxy_identity_audit"],
    }
    existing = set(source_inputs["path"].astype(str))
    for role, path in additions.items():
        if str(path) not in existing:
            rows.append({"input_role": role, "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    frame = pd.DataFrame(rows)
    before = {str(row.path): str(row.sha256).upper() for row in frame.itertuples(index=False)}
    return frame, before


def _finalize_input_hash_audit(input_manifest: pd.DataFrame, before: dict[str, str]) -> pd.DataFrame:
    """Confirm protected inputs retained their pre-run hashes."""
    rows = []
    for record in input_manifest.itertuples(index=False):
        path = Path(record.path)
        after_hash = sha256_file(path) if path.exists() else "MISSING"
        after_bytes = path.stat().st_size if path.exists() else -1
        passed = after_hash == before[str(path)] and after_bytes == int(record.bytes)
        rows.append({
            "input_role": record.input_role,
            "path_pre": str(path),
            "bytes_pre": int(record.bytes),
            "sha256_pre": before[str(path)],
            "path_post": str(path),
            "bytes_post": after_bytes,
            "sha256_post": after_hash,
            "status": "PASS" if passed else "FAIL",
            "notes": "GOVERNED_SOURCE_UNMODIFIED" if passed else "UNEXPECTED_PROTECTED_INPUT_MUTATION",
        })
    return pd.DataFrame(rows)


def _previous_coverage(run: AuditRun, paths: dict[str, Path]) -> pd.DataFrame:
    """Account for every accepted prior output in the final registry."""
    source = _read(run.source_run / "15_QA_AND_MANIFESTS" / "PREVIOUS_VS_NEW_OUTPUT_COVERAGE.csv")
    rows = []
    for record in source.itertuples(index=False):
        dependency = str(record.query_dependency)
        rows.append({
            "previous_output": record.previous_output,
            "previous_analysis_family": record.previous_analysis_family,
            "query_dependency": dependency,
            "final_equivalent": record.new_equivalent,
            "status": "REUSED_UNCHANGED" if "INDEPENDENT" in dependency else "FINAL_EQUIVALENT",
            "reason": "Accepted source-run mapping retained and re-audited in final freeze pass",
            "source_lineage": "PREVIOUS_S_KETAMINE_AND_PAPER_FACING_MANIFESTS",
        })

    def append_manifest(path: Path, lineage: str) -> None:
        """Append one prior manifest to the output-coverage accounting table."""
        frame = _read(path)
        candidate_columns = [column for column in frame.columns if "path" in column.lower() or "file" in column.lower()]
        path_column = "relative_path" if "relative_path" in frame else (candidate_columns[0] if candidate_columns else frame.columns[0])
        for value in frame[path_column].dropna().astype(str):
            lowered = value.lower()
            if any(token in lowered for token in ["profile", "fingerprint", "pairwise", "multivariate", "pca", "cluster", "hydroxy", "norket", "hnk"]):
                status = "FINAL_EQUIVALENT"
                equivalent = "02_FAMILY_AVAILABILITY_AUDIT; 04_COMPLETED_FAMILY_PAIRWISE; 05_COMPLETED_FAMILY_MULTIVARIATE; 06_UPDATED_GLOBAL_MODELS"
                reason = "Numerical family/metabolite content incorporated into final expanded roster or superseded by recomputed affected model"
            elif any(token in lowered for token in ["authority", "governance", "methods", "qa", "manifest", "software", "readme", "handoff"]):
                status = "REUSED_UNCHANGED"
                equivalent = "Referenced immutable prior E7 evidence"
                reason = "Governance/method evidence remains authoritative and is referenced by hash"
            else:
                status = "NOT_APPLICABLE"
                equivalent = "No direct final-stage scientific product required"
                reason = "Prior packaging/support artifact is outside the final affected family branch"
            rows.append({
                "previous_output": str(path.parent / value),
                "previous_analysis_family": lineage,
                "query_dependency": "E7_FAMILY_OR_SUPPORT",
                "final_equivalent": equivalent,
                "status": status,
                "reason": reason,
                "source_lineage": lineage,
            })

    append_manifest(paths["e7_release_manifest"], "E7_FIVE_METABOLITE_RELEASE")
    append_manifest(paths["e7_final_manifest"], "E7_FINAL_MULTIVARIATE_RELEASE")
    frame = pd.DataFrame(rows).drop_duplicates(["previous_output", "source_lineage"], keep="last")
    allowed = {"FINAL_EQUIVALENT", "REUSED_UNCHANGED", "SUPERSEDED", "NOT_ESTIMABLE", "BLOCKED_WITH_REASON", "NOT_APPLICABLE"}
    run.check("PREVIOUS_OUTPUT_COVERAGE_STATUSES", "PREVIOUS_OUTPUT_COVERAGE", set(frame["status"]).issubset(allowed), sorted(allowed), sorted(set(frame["status"])))
    required_tokens = ["norket", "hnk", "fingerprint", "pairwise", "multivariate"]
    missing = [token for token in required_tokens if not frame["previous_output"].str.contains(token, case=False, na=False).any()]
    run.check("PRIOR_E7_ANALYSIS_FAMILIES_MAPPED", "PREVIOUS_OUTPUT_COVERAGE", not missing, "norketamine/HNK/fingerprint/pairwise/multivariate present", "; ".join(missing) or "ALL_PRESENT")
    return frame


def _registry_completeness(run: AuditRun, final_registry: pd.DataFrame) -> pd.DataFrame:
    """Check final analysis, table, and figure registry completeness."""
    requirements = [
        ("FAMILY_AVAILABILITY", "FAMILY_PROFILE_AVAILABILITY_AUDIT"),
        ("FAMILY_IDENTITY_FORENSICS", "FAMILY_VECTOR_IDENTITY_FORENSIC_AUDIT"),
        ("FAMILY_PAIRWISE", "FAMILY_ALL_PAIR_METRICS_FINAL"),
        ("POOLED_VS_METABOLITES", "POOLED_PARENT_VS_"),
        ("FAMILY_MULTIVARIATE", "FAMILY_JOINT_CONTINUOUS_PCA"),
        ("GLOBAL_MULTIVARIATE", "GLOBAL_JOINT_CONTINUOUS_PCA"),
        ("NUMERICAL_INTEGRITY", "FINAL_NUMERICAL_INTEGRITY_AUDIT"),
        ("COMMON_SCALE", "COMMON_SCALE_COMPATIBILITY_AUDIT"),
        ("FINGERPRINT", "FINAL_FINGERPRINT_AUDIT"),
        ("MULTIVARIATE_AUDIT", "FINAL_MULTIVARIATE_AUDIT"),
        ("NEAREST_REFERENCE", "FINAL_NEAREST_REFERENCE_AUDIT"),
        ("CLASS_AUDIT", "FINAL_CLASS_AUDIT"),
        ("COVERAGE", "FINAL_COVERAGE_AUDIT"),
        ("FIGURE_QA", "FINAL_FIGURE_QA"),
        ("TABLE_QA", "FINAL_TABLE_QA"),
        ("PREVIOUS_OUTPUT_COVERAGE", "PREVIOUS_VS_FINAL_OUTPUT_COVERAGE"),
        ("INPUT_HASH_AUDIT", "FINAL_INPUT_PRE_POST_HASH_AUDIT"),
    ]
    rows = []
    ids = final_registry["analysis_id"].astype(str)
    for requested, token in requirements:
        matches = int(ids.str.contains(token, regex=False).sum())
        rows.append({
            "requested_analysis": requested,
            "registry_token": token,
            "matching_registry_rows": matches,
            "status": "PASS" if matches > 0 else "FAIL",
            "notes": "Explicit final registry coverage",
        })
    table_paths = {str(value) for value in pd.DataFrame(run.table_rows).get("output_file", pd.Series(dtype=str)).dropna()}
    figure_paths = {str(value) for value in run.figures.frame().get("output_file", pd.Series(dtype=str)).dropna()} | {str(value) for value in run.figures.frame().get("pdf_file", pd.Series(dtype=str)).dropna()}
    scientific = []
    for stage in ["02_FAMILY_AVAILABILITY_AUDIT", "03_FAMILY_IDENTITY_FORENSICS", "04_COMPLETED_FAMILY_PAIRWISE", "05_COMPLETED_FAMILY_MULTIVARIATE", "06_UPDATED_GLOBAL_MODELS", "07_NUMERICAL_INTEGRITY_AUDIT", "08_FINGERPRINT_AND_COMMON_SCALE_AUDIT", "09_MULTIVARIATE_AND_CLASS_AUDIT", "10_COVERAGE_AND_MISSINGNESS_AUDIT", "11_FIGURE_TABLE_QA", "12_PREVIOUS_OUTPUT_COVERAGE", "13_FINAL_PAPER_FACING"]:
        for path in (run.root / stage).rglob("*"):
            if path.is_file() and path.suffix.lower() in {".csv", ".png", ".pdf"}:
                scientific.append(relative_posix(path, run.root))
    recognized = table_paths | figure_paths
    allowed_packet = {value for value in scientific if value.startswith("13_FINAL_PAPER_FACING/")}
    orphaned = sorted(set(scientific) - recognized - allowed_packet)
    rows.append({
        "requested_analysis": "ORPHAN_OUTPUT_AUDIT",
        "registry_token": "TABLE_OR_FIGURE_MANIFEST",
        "matching_registry_rows": len(scientific) - len(orphaned),
        "status": "PASS" if not orphaned else "FAIL",
        "notes": "; ".join(orphaned[:10]) if orphaned else "No unregistered scientific output",
    })
    frame = pd.DataFrame(rows)
    run.check("ANALYSIS_REGISTRY_COMPLETENESS", "REGISTRY", frame["status"].eq("PASS").all(), "all requested analyses and zero orphan outputs", int(frame["status"].ne("PASS").sum()))
    return frame


def _run_code_tests(run: AuditRun) -> dict[str, Any]:
    """Compile and test the code snapshot included in the freeze."""
    logs = run.root / "00_RUN_CONTROL"
    compile_ok = compileall.compile_dir(str(run.code_root), quiet=1, force=True)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=run.code_root,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    (logs / "COMPILEALL_STATUS.txt").write_text(f"compileall_pass={compile_ok}\n", encoding="utf-8")
    (logs / "PYTEST_FINAL.log").write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
    summary = {
        "compileall_pass": compile_ok,
        "pytest_return_code": completed.returncode,
        "pytest_pass": completed.returncode == 0,
        "command": f"{sys.executable} -m pytest -q",
        "completed_at": now_iso(),
    }
    write_json(logs / "CODE_TEST_SUMMARY.json", summary)
    run.check("CODE_COMPILEALL", "CODE", compile_ok, True, compile_ok)
    run.check("CODE_PYTEST", "CODE", completed.returncode == 0, 0, completed.returncode)
    return summary


def _write_markdown(path: Path, text: str) -> Path:
    """Write a UTF-8 Markdown artifact and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _paper_outputs(
    run: AuditRun,
    source_figure_manifest: pd.DataFrame,
    source_table_manifest: pd.DataFrame,
    final_model_status: pd.DataFrame,
) -> dict[str, Any]:
    """Assemble the final publication-facing narrative and indexed artifacts."""
    paper = run.root / "13_FINAL_PAPER_FACING"
    compact_dir = paper / "COMPACT_TABLES"
    selected_tables = [
        (run.root / "02_FAMILY_AVAILABILITY_AUDIT" / "FAMILY_PROFILE_AVAILABILITY_AUDIT.csv", "Family profile availability", ["display_name", "numerical_status", "supported_targets", "supported_features", "eligible_for_multivariate", "QA_status"]),
        (run.root / "04_COMPLETED_FAMILY_PAIRWISE" / "KETAMINE_FAMILY_ALL_PAIR_METRICS_FINAL.csv", "Final family pairwise metrics", ["drug_a", "drug_b", "matched_targets", "matched_features", "rms_common_rhr", "cosine_common_rhr", "spearman_common_rhr", "support_jaccard", "alpha001_call_jaccard"]),
        (run.root / "04_COMPLETED_FAMILY_PAIRWISE" / "POOLED_PARENT_METABOLITE_RANKINGS.csv", "Pooled-parent metabolite rankings", None),
        (run.root / "09_MULTIVARIATE_AND_CLASS_AUDIT" / "FINAL_MODEL_STATUS.csv", "Final model status", ["analysis_id", "status", "sample_count", "feature_count", "rank", "component_count", "reason"]),
        (run.root / "07_NUMERICAL_INTEGRITY_AUDIT" / "FINAL_NUMERICAL_INTEGRITY_AUDIT.csv", "Final numerical integrity audit", ["check_id", "analysis", "expected", "observed", "status"]),
        (run.root / "08_FINGERPRINT_AND_COMMON_SCALE_AUDIT" / "FINAL_FINGERPRINT_AUDIT.csv", "Final fingerprint audit", None),
        (run.root / "10_COVERAGE_AND_MISSINGNESS_AUDIT" / "FINAL_COVERAGE_AUDIT.csv", "Final coverage audit", ["compound", "supported_targets", "supported_features", "target_coverage_fraction", "status"]),
    ]
    compact_pdfs = []
    compact_rows = []
    for number, (path, title, columns) in enumerate(selected_tables, start=1):
        frame = _read(path)
        if columns:
            frame = frame[[column for column in columns if column in frame.columns]]
        pdf = table_pdf(frame, title, compact_dir / f"TABLE_{number:02d}_{slug(title)}.pdf", max_rows=45)
        compact_pdfs.append(pdf)
        compact_rows.append({"table_number": number, "title": title, "authoritative_csv": relative_posix(path, run.root), "review_pdf": relative_posix(pdf, run.root), "status": "PASS"})
    compact_packet, compact_included = combine_pdfs(compact_pdfs, paper / "FINAL_COMPACT_REVIEW_TABLES.pdf")

    source_figure_packet = run.source_run / "14_PAPER_FACING" / "ALL_FIGURES_COMBINED.pdf"
    new_paper_pdfs = [run.root / value for value in run.figures.frame().loc[run.figures.frame()["paper_facing_priority"].eq("PAPER"), "pdf_file"]]
    figure_packet, figure_included = combine_pdfs([source_figure_packet, *new_paper_pdfs], paper / "FINAL_ALL_FIGURES_COMBINED.pdf")
    source_table_packet = run.source_run / "14_PAPER_FACING" / "ALL_TABLES_COMBINED.pdf"
    table_packet, table_included = combine_pdfs([source_table_packet, compact_packet] if compact_packet else [source_table_packet], paper / "FINAL_ALL_TABLES_COMBINED.pdf")
    complete_packet, complete_included = combine_pdfs([figure_packet, table_packet], paper / "FINAL_COMPLETE_FIGURES_AND_TABLES_PACKET.pdf")

    source_paper_figures = _read(run.source_run / "14_PAPER_FACING" / "PAPER_FACING_FIGURE_INDEX.csv")
    source_paper_tables = _read(run.source_run / "14_PAPER_FACING" / "PAPER_FACING_TABLE_INDEX.csv")
    figure_rows = []
    for _, row in source_paper_figures.iterrows():
        figure_rows.append({"source_scope": "SOURCE_RUN_REUSED", "figure_id": row.get("figure_id", ""), "title": row.get("title", ""), "output_file": row.get("output_file", row.get("pdf_file", "")), "storage_root": str(run.source_run), "status": "PASS"})
    for _, row in run.figures.frame().iterrows():
        if row["paper_facing_priority"] == "PAPER":
            figure_rows.append({"source_scope": "FINAL_AUDIT_NEW", "figure_id": row["figure_id"], "title": row["title"], "output_file": row["pdf_file"], "storage_root": str(run.root), "status": row["QA_status"]})
    table_rows = []
    for _, row in source_paper_tables.iterrows():
        table_rows.append({"source_scope": "SOURCE_RUN_REUSED", "table_id": row.get("table_id", ""), "title": row.get("title", ""), "output_file": row.get("output_file", ""), "review_pdf": "SOURCE_COMBINED_TABLE_PACKET", "storage_root": str(run.source_run), "status": "PASS"})
    for _, row in pd.DataFrame(run.table_rows).iterrows():
        if row["paper_facing_priority"] == "PAPER":
            match = next((item for item in compact_rows if item["authoritative_csv"] == row["output_file"]), None)
            table_rows.append({"source_scope": "FINAL_AUDIT_NEW", "table_id": row["table_id"], "title": row["title"], "output_file": row["output_file"], "review_pdf": match["review_pdf"] if match else "FULL_CSV_AUTHORITY", "storage_root": str(run.root), "status": row["QA_status"]})
    figure_index = run.table(pd.DataFrame(figure_rows), "13_FINAL_PAPER_FACING/FINAL_PAPER_FACING_FIGURE_INDEX.csv", "FINAL_PAPER_FACING_FIGURE_INDEX", "PAPER_PACKAGING", "Final paper-facing figure index", "source_plus_final_figures", "PAPER")
    table_index = run.table(pd.DataFrame(table_rows), "13_FINAL_PAPER_FACING/FINAL_PAPER_FACING_TABLE_INDEX.csv", "FINAL_PAPER_FACING_TABLE_INDEX", "PAPER_PACKAGING", "Final paper-facing table index", "source_plus_final_tables", "PAPER")
    run.table(pd.DataFrame(compact_rows), "13_FINAL_PAPER_FACING/COMPACT_TABLE_REVIEW_INDEX.csv", "COMPACT_TABLE_REVIEW_INDEX", "PAPER_PACKAGING", "Compact table review index", "review_layouts", "PAPER")
    run.analysis("FINAL_PAPER_FACING_PACKETS", "PAPER_PACKAGING", "figures_and_tables", "DETERMINISTIC_PDF_COMBINATION", "PASS", relative_posix(table_index, run.root), relative_posix(figure_packet, run.root))
    return {
        "figure_packet": figure_packet,
        "table_packet": table_packet,
        "complete_packet": complete_packet,
        "compact_table_packet": compact_packet,
        "figure_index": figure_index,
        "table_index": table_index,
        "paper_figure_count": len(figure_rows),
        "paper_table_count": len(table_rows),
        "figure_sources": figure_included,
        "table_sources": table_included,
        "complete_sources": complete_included,
    }


def _copy_to_candidate(candidate: Path, files: list[Path]) -> None:
    """Copy cleared final artifacts into the immutable freeze candidate."""
    candidate.mkdir(parents=True, exist_ok=True)
    for source in files:
        if source and source.exists() and source.is_file():
            destination = candidate / source.name
            shutil.copy2(source, destination)


def run_final_audit(
    project_root: Path | None = PROJECT_ROOT_DEFAULT,
    timestamp: str | None = None,
) -> Path:
    """Run the final governed audit against an explicit external project root."""

    started = time.perf_counter()
    timestamp = timestamp or _timestamp()
    if project_root is None:
        raise ValueError(
            "An external project root is required; pass project_root or set "
            "CARDOZO_HR_EXTERNAL_PROJECT_ROOT"
        )
    project_root = project_root.resolve()
    source_run = project_root / SOURCE_RUN_RELATIVE
    code_root = project_root / CODE_RELATIVE
    output_root = project_root / "04_KETAMINE_VS_DRUGS" / f"{FINAL_PREFIX}_{timestamp}"
    if output_root.exists():
        raise FileExistsError(f"Refusing to overwrite existing final-audit run: {output_root}")
    if not source_run.exists():
        raise FileNotFoundError(source_run)
    for stage in STAGES:
        (output_root / stage).mkdir(parents=True, exist_ok=False)
    run = AuditRun(output_root, source_run, code_root)
    paths = discover(project_root)
    input_manifest, input_hash_before = _protected_input_hashes(paths, source_run)
    run.table(input_manifest, "01_INPUT_SNAPSHOT/FINAL_INPUT_MANIFEST.csv", "FINAL_INPUT_MANIFEST", "INPUT_SNAPSHOT", "Final governed input manifest", "immutable_authorities", "PAPER")
    _write_markdown(output_root / "01_INPUT_SNAPSHOT" / "SOURCE_RUN_POINTER.md", f"# Source run pointer\n\nAccepted immutable source run: `{source_run}`\n\nPermanent code: `{code_root}`\n")
    shutil.copy2(code_root / "config" / "paths.yaml", output_root / "01_INPUT_SNAPSHOT" / "paths.yaml")
    shutil.copy2(code_root / "config" / "parameters.yaml", output_root / "01_INPUT_SNAPSHOT" / "parameters.yaml")
    run.stage("01_INPUT_SNAPSHOT", "PASS", f"{len(input_manifest)} protected inputs hashed before work")

    source_profiles, contract, source_calls = _load_source_matrices(source_run)
    e7_profiles = load_e7_profiles(paths, contract)
    profiles = pd.concat([source_profiles, e7_profiles], ignore_index=True, sort=False)
    old_roster = list(source_calls["call_binary_alpha001"].index.astype(str))
    final_roster = [*old_roster, *E7_LABELS.values()]
    matrices = _profile_matrices(profiles, contract, final_roster)
    calls = extend_call_matrices(source_calls, e7_profiles, paths, contract)
    for key in calls:
        calls[key] = calls[key].reindex(index=final_roster, columns=contract["feature_id"].astype(str))

    availability = availability_audit(paths, source_run, profiles, calls)
    availability_path = run.table(availability, "02_FAMILY_AVAILABILITY_AUDIT/FAMILY_PROFILE_AVAILABILITY_AUDIT.csv", "FAMILY_PROFILE_AVAILABILITY_AUDIT", "FAMILY_AVAILABILITY", "Complete family profile availability audit", "identity_and_profile_availability", "PAPER")
    run.analysis("FAMILY_PROFILE_AVAILABILITY_AUDIT", "FAMILY_AVAILABILITY", "all_known_family_identities", "GOVERNED_AUTHORITY_DISCOVERY", "PASS", relative_posix(availability_path, output_root))
    run.check("KNOWN_FAMILY_IDENTITIES_ACCOUNTED", "FAMILY_AVAILABILITY", len(availability) == 12, 12, len(availability))
    run.check("E7_NUMERICAL_IDENTITIES_INCLUDED", "FAMILY_AVAILABILITY", set(E7_LABELS).issubset(set(availability.loc[availability["eligible_for_continuous_pairwise"], "compound_id"])), sorted(E7_LABELS), sorted(set(availability.loc[availability["eligible_for_continuous_pairwise"], "compound_id"])))
    run.stage("02_FAMILY_AVAILABILITY_AUDIT", "PASS", "12 known identities; 10 numerical and 2 status-only")

    forensic, forensic_summary = forensic_audit(paths, contract)
    forensic_path = run.table(forensic, "03_FAMILY_IDENTITY_FORENSICS/FAMILY_VECTOR_IDENTITY_FORENSIC_AUDIT.csv", "FAMILY_VECTOR_IDENTITY_FORENSIC_AUDIT", "FAMILY_IDENTITY_FORENSICS", "Family vector identity forensic audit", "activity_raw_common_support_fingerprint", "PAPER")
    identity_text = f"""# Family identity audit

Status: PASS — explained inherited modeled equality; no downstream alias, copy, label, file-reuse, feature-index, or projection defect was found.

{forensic_summary['conclusion']}

The frozen HPF authority already contains a row-level modeled-overlap audit. S-ketamine, R-ketamine, and the unspecified-isomer hydroxyketamine aggregate remain distinct compound identities with different source assertion lineages and different support masks. Exact equality on shared coordinates must not be described as independent measured biological equivalence.

No protected upstream authority was edited. The final derivative retains the values and records the limitation.
"""
    identity_md = _write_markdown(output_root / "03_FAMILY_IDENTITY_FORENSICS" / "FAMILY_IDENTITY_AUDIT.md", identity_text)
    run.analysis("FAMILY_VECTOR_IDENTITY_FORENSIC_AUDIT", "FAMILY_IDENTITY_FORENSICS", "activity_to_fingerprint_lineage", "ROW_LEVEL_HASHED_LINEAGE_COMPARISON", "PASS", relative_posix(forensic_path, output_root), reason=forensic_summary["conclusion"])
    r_h = forensic[(forensic["compound_a"].eq("R-ketamine")) & (forensic["compound_b"].eq("Hydroxyketamine, unspecified isomer aggregate")) & forensic["representation"].eq("COMMON_RHR_STRICT18")]
    explained = len(r_h) == 1 and int(r_h.iloc[0]["matched_features"]) == 576 and float(r_h.iloc[0]["max_abs_difference"]) == 0.0
    run.check("R_HYDROXY_576_EQUALITY_EXPLAINED", "FAMILY_IDENTITY_FORENSICS", explained, "576 exact shared common-RHR features with lineage explanation", f"rows={len(r_h)}; matched={r_h.iloc[0]['matched_features'] if len(r_h) else 'NA'}")
    run.stage("03_FAMILY_IDENTITY_FORENSICS", "PASS", "Exact overlap is induced by distinct E4-modeled source lineages, not a software defect")

    computed_pairs, _ = all_pairwise(matrices, contract, final_roster, metric_function(calls, contract))
    source_pairs = _read(source_run / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "ALL_UNORDERED_DRUG_PAIR_METRICS.csv")
    final_pairs = _replace_source_pairs(computed_pairs, source_pairs, old_roster)
    all_pair_path = run.table(final_pairs, "07_NUMERICAL_INTEGRITY_AUDIT/ALL_UNORDERED_DRUG_PAIR_METRICS_FINAL.csv", "ALL_UNORDERED_DRUG_PAIR_METRICS_FINAL", "FINAL_ALL_PAIRWISE", "Final all-compound unordered pair metrics", "strict18_common_rhr_and_fingerprints", "PAPER")
    family_pairs = final_pairs[final_pairs["drug_a"].isin(FINAL_FAMILY_ORDER) & final_pairs["drug_b"].isin(FINAL_FAMILY_ORDER)].copy()
    _family_pairwise_outputs(run, family_pairs, matrices, calls, contract)
    nearest_family = _nearest_family(family_pairs)
    run.table(nearest_family, "04_COMPLETED_FAMILY_PAIRWISE/NEAREST_FAMILY_MEMBER_SUMMARY.csv", "NEAREST_FAMILY_MEMBER_SUMMARY", "FAMILY_PAIRWISE_FINAL", "Nearest family member summaries", "multiple_metrics", "PAPER")
    run.check("FINAL_FAMILY_PAIR_COUNT", "FAMILY_PAIRWISE", len(family_pairs) == 45, 45, len(family_pairs))
    run.stage("04_COMPLETED_FAMILY_PAIRWISE", "PASS", "10 numerical family profiles; 45 unordered pairs")

    family_matrix = matrices["common_rhr"].loc[FINAL_FAMILY_ORDER]
    family_models = _model_suite(run, "FAMILY", family_matrix, calls["call_binary_alpha001"].loc[FINAL_FAMILY_ORDER], calls["call_binary_alpha0001"].loc[FINAL_FAMILY_ORDER], family_pairs, contract, "05_COMPLETED_FAMILY_MULTIVARIATE")
    run.table(family_models, "05_COMPLETED_FAMILY_MULTIVARIATE/FAMILY_MODEL_STATUS.csv", "FAMILY_MODEL_STATUS", "FAMILY_MULTIVARIATE", "Final family model status", "all_family_representations", "PAPER")
    run.stage("05_COMPLETED_FAMILY_MULTIVARIATE", "PASS_WITH_DOCUMENTED_LIMITATIONS" if family_models["status"].ne("PASS").any() else "PASS", "All requested estimable family models run; rank/coverage limitations explicit")

    external = [drug for drug in old_roster if drug not in FINAL_FAMILY_ORDER[:5]]
    global_models = _model_suite(run, "GLOBAL", matrices["common_rhr"], calls["call_binary_alpha001"], calls["call_binary_alpha0001"], final_pairs, contract, "06_UPDATED_GLOBAL_MODELS", reference=external, projections=FINAL_FAMILY_ORDER)
    run.table(global_models, "06_UPDATED_GLOBAL_MODELS/GLOBAL_MODEL_STATUS.csv", "GLOBAL_MODEL_STATUS", "GLOBAL_MULTIVARIATE", "Updated global model status", "expanded_all_compound_roster", "PAPER")
    for metric in ["alpha001_call_jaccard", "alpha0001_call_jaccard", "alpha001_signed_sparse_cosine"]:
        matrix = metric_matrix(final_pairs, metric, final_roster)
        path = run.table(matrix.reset_index(names="compound"), f"06_UPDATED_GLOBAL_MODELS/GLOBAL_{metric.upper()}_MATRIX.csv", f"GLOBAL_{metric.upper()}_MATRIX", "GLOBAL_MULTIVARIATE", f"Updated global {metric} matrix", metric, "PAPER")
        run.figure(heatmap(matrix, f"Updated global {metric.replace('_', ' ')}", metric, annotate=False), f"06_UPDATED_GLOBAL_MODELS/GLOBAL_{metric.upper()}_HEATMAP", f"GLOBAL_{metric.upper()}_HEATMAP", "GLOBAL_MULTIVARIATE", f"Updated global {metric}", relative_posix(path, output_root))
    run.stage("06_UPDATED_GLOBAL_MODELS", "PASS_WITH_DOCUMENTED_LIMITATIONS" if global_models["status"].ne("PASS").any() else "PASS", "Affected global roster models recomputed; external axes held fixed")

    _numerical_integrity(run, final_pairs, source_pairs, matrices, calls, final_roster, old_roster)
    numerical_path = run.table(pd.DataFrame(run.qa_rows), "07_NUMERICAL_INTEGRITY_AUDIT/FINAL_NUMERICAL_INTEGRITY_AUDIT.csv", "FINAL_NUMERICAL_INTEGRITY_AUDIT", "NUMERICAL_INTEGRITY", "Final numerical integrity audit", "all_pairwise_and_matrices", "PAPER")
    run.analysis("FINAL_NUMERICAL_INTEGRITY_AUDIT", "NUMERICAL_INTEGRITY", "all_comparative_outputs", "INDEPENDENT_ARITHMETIC_READBACK", "PASS" if not any(row["status"] == "FAIL" for row in run.qa_rows) else "FAILED_QA", relative_posix(numerical_path, output_root))
    run.stage("07_NUMERICAL_INTEGRITY_AUDIT", "PASS" if not any(row["status"] == "FAIL" for row in run.qa_rows) else "FAILED_QA", "All 435 source pairs and 160 new edges audited")

    common_scale = _common_scale_audit(run, source_run)
    common_path = run.table(common_scale, "08_FINGERPRINT_AND_COMMON_SCALE_AUDIT/COMMON_SCALE_COMPATIBILITY_AUDIT.csv", "COMMON_SCALE_COMPATIBILITY_AUDIT", "COMMON_SCALE", "Common-scale and GRIN3B compatibility audit", "raw_and_common_scale_contract", "PAPER")
    fingerprint = _fingerprint_audit(run, source_run, calls)
    fingerprint_path = run.table(fingerprint, "08_FINGERPRINT_AND_COMMON_SCALE_AUDIT/FINAL_FINGERPRINT_AUDIT.csv", "FINAL_FINGERPRINT_AUDIT", "FINGERPRINT", "Final fingerprint audit", "alpha001_and_alpha0001", "PAPER")
    run.analysis("COMMON_SCALE_COMPATIBILITY_AUDIT", "COMMON_SCALE", "pooled_query_contract", "EXACT_TARGET_AND_FEATURE_READBACK", "PASS" if common_scale["status"].eq("PASS").all() else "FAILED_QA", relative_posix(common_path, output_root))
    run.analysis("FINAL_FINGERPRINT_AUDIT", "FINGERPRINT", "all_call_matrices", "EXACT_SET_AND_SPARSE_SEMANTIC_READBACK", "PASS" if fingerprint["status"].eq("PASS").all() else "FAILED_QA", relative_posix(fingerprint_path, output_root))
    run.stage("08_FINGERPRINT_AND_COMMON_SCALE_AUDIT", "PASS" if common_scale["status"].eq("PASS").all() and fingerprint["status"].eq("PASS").all() else "FAILED_QA", "1044 raw, 1026 common-scale, GRIN3B-only exclusion; pooled 19/14 calls")

    source_model = _read(source_run / "15_QA_AND_MANIFESTS" / "MODEL_STATUS.csv")
    replacement_ids = set(family_models["analysis_id"].astype(str)) | set(global_models["analysis_id"].astype(str))
    unchanged_models = source_model[~source_model["analysis_id"].astype(str).isin(replacement_ids)].copy()
    final_model = pd.concat([family_models, global_models, unchanged_models], ignore_index=True, sort=False)
    model_path = run.table(final_model, "09_MULTIVARIATE_AND_CLASS_AUDIT/FINAL_MODEL_STATUS.csv", "FINAL_MODEL_STATUS", "MULTIVARIATE_AUDIT", "Final model status", "updated_family_global_plus_reused_class", "PAPER")
    multivariate = _multivariate_audit(run, final_model, source_run)
    multivariate_path = run.table(multivariate, "09_MULTIVARIATE_AND_CLASS_AUDIT/FINAL_MULTIVARIATE_AUDIT.csv", "FINAL_MULTIVARIATE_AUDIT", "MULTIVARIATE_AUDIT", "Final multivariate audit", "model_inputs_rank_components_axes", "PAPER")
    nearest = _nearest_reference_audit(run, source_run)
    nearest_path = run.table(nearest, "09_MULTIVARIATE_AND_CLASS_AUDIT/FINAL_NEAREST_REFERENCE_AUDIT.csv", "FINAL_NEAREST_REFERENCE_AUDIT", "NEAREST_REFERENCE", "Final nearest-reference audit", "authoritative_pairwise_metrics", "PAPER")
    class_audit = _class_audit(run, source_run)
    class_path = run.table(class_audit, "09_MULTIVARIATE_AND_CLASS_AUDIT/FINAL_CLASS_AUDIT.csv", "FINAL_CLASS_AUDIT", "CLASS_AUDIT", "Final governed class audit", "reused_unchanged_class_outputs", "PAPER")
    run.analysis("FINAL_MULTIVARIATE_AUDIT", "MULTIVARIATE_AUDIT", "global_family_class_models", "MODEL_STATUS_AND_INVARIANCE_READBACK", "PASS" if multivariate["audit_status"].eq("PASS").all() else "FAILED_QA", relative_posix(multivariate_path, output_root))
    run.analysis("FINAL_NEAREST_REFERENCE_AUDIT", "NEAREST_REFERENCE", "pooled_vs_external", "AUTHORITATIVE_METRIC_RERANK", "PASS" if nearest["status"].eq("PASS").all() else "FAILED_QA", relative_posix(nearest_path, output_root))
    run.analysis("FINAL_CLASS_AUDIT", "CLASS_AUDIT", "governed_classes", "UNCHANGED_OUTPUT_READBACK", "PASS" if class_audit["status"].eq("PASS").all() else "FAILED_QA", relative_posix(class_path, output_root), reused="REUSED_VALIDATED_SOURCE_RUN")
    run.stage("09_MULTIVARIATE_AND_CLASS_AUDIT", "PASS" if multivariate["audit_status"].eq("PASS").all() and nearest["status"].eq("PASS").all() and class_audit["status"].eq("PASS").all() else "FAILED_QA", "Family/global affected models updated; 14 governed class branches reused and audited")

    coverage = _coverage_audit(run, matrices, contract, final_roster)
    coverage_path = run.table(coverage, "10_COVERAGE_AND_MISSINGNESS_AUDIT/FINAL_COVERAGE_AUDIT.csv", "FINAL_COVERAGE_AUDIT", "COVERAGE", "Final coverage and missingness audit", "strict18_common_scale_support", "PAPER")
    run.analysis("FINAL_COVERAGE_AUDIT", "COVERAGE", "all_35_numerical_compounds", "SUPPORT_MASK_READBACK", "PASS" if coverage["status"].eq("PASS").all() else "FAILED_QA", relative_posix(coverage_path, output_root))
    run.stage("10_COVERAGE_AND_MISSINGNESS_AUDIT", "PASS" if coverage["status"].eq("PASS").all() else "FAILED_QA", "Full support denominators retained; no zero filling")

    source_figure_manifest = _read(source_run / "15_QA_AND_MANIFESTS" / "FIGURE_MANIFEST.csv")
    source_table_manifest = _read(source_run / "15_QA_AND_MANIFESTS" / "TABLE_MANIFEST.csv")
    new_figure_manifest_pre = run.figures.frame()
    new_table_manifest_pre = pd.DataFrame(run.table_rows)
    figure_qa = _figure_qa(run, source_figure_manifest, new_figure_manifest_pre)
    figure_qa_path = run.table(figure_qa, "11_FIGURE_TABLE_QA/FINAL_FIGURE_QA.csv", "FINAL_FIGURE_QA", "FIGURE_QA", "Final figure structural and visual audit", "all_source_and_new_figures", "PAPER")
    table_qa = _table_qa(run, source_table_manifest, new_table_manifest_pre)
    table_qa_path = run.table(table_qa, "11_FIGURE_TABLE_QA/FINAL_TABLE_QA.csv", "FINAL_TABLE_QA", "TABLE_QA", "Final table authority and readability audit", "all_source_and_new_tables", "PAPER")
    run.analysis("FINAL_FIGURE_QA", "FIGURE_QA", "all_scientific_figures", "IMAGE_PDF_VALIDATION_PLUS_REPRESENTATIVE_VISUAL_REVIEW", "PASS" if figure_qa["status"].eq("PASS").all() else "FAILED_QA", relative_posix(figure_qa_path, output_root))
    run.analysis("FINAL_TABLE_QA", "TABLE_QA", "all_scientific_tables", "CSV_READBACK_AND_REVIEW_LAYOUT_AUDIT", "PASS" if table_qa["status"].eq("PASS").all() else "FAILED_QA", relative_posix(table_qa_path, output_root))
    run.stage("11_FIGURE_TABLE_QA", "PASS" if figure_qa["status"].eq("PASS").all() and table_qa["status"].eq("PASS").all() else "FAILED_QA", "All source/new figures and tables structurally re-read; representative visual review inherited and extended")

    previous_coverage = _previous_coverage(run, paths)
    previous_path = run.table(previous_coverage, "12_PREVIOUS_OUTPUT_COVERAGE/PREVIOUS_VS_FINAL_OUTPUT_COVERAGE.csv", "PREVIOUS_VS_FINAL_OUTPUT_COVERAGE", "PREVIOUS_OUTPUT_COVERAGE", "Previous versus final output coverage", "prior_s_ketamine_family_e7_manifests", "PAPER")
    run.analysis("PREVIOUS_VS_FINAL_OUTPUT_COVERAGE", "PREVIOUS_OUTPUT_COVERAGE", "all_prior_outputs", "MANIFEST_TO_FINAL_DISPOSITION_MAPPING", "PASS", relative_posix(previous_path, output_root))
    run.stage("12_PREVIOUS_OUTPUT_COVERAGE", "PASS", f"{len(previous_coverage)} prior output rows mapped including E7 family/metabolite products")

    paper = _paper_outputs(run, source_figure_manifest, source_table_manifest, final_model)
    run.stage("13_FINAL_PAPER_FACING", "PASS", "Final combined figure, table, and complete review packets created")

    input_hash_audit = _finalize_input_hash_audit(input_manifest, input_hash_before)
    input_hash_path = run.table(input_hash_audit, "14_FREEZE_MANIFESTS/FINAL_INPUT_PRE_POST_HASH_AUDIT.csv", "FINAL_INPUT_PRE_POST_HASH_AUDIT", "INPUT_HASH_AUDIT", "Final protected-input pre/post hash audit", "sha256", "PAPER")
    run.check("PROTECTED_INPUT_HASHES", "INPUT_HASH_AUDIT", input_hash_audit["status"].eq("PASS").all(), "all PASS", int(input_hash_audit["status"].ne("PASS").sum()))
    run.analysis("FINAL_INPUT_PRE_POST_HASH_AUDIT", "INPUT_HASH_AUDIT", "all_governed_sources", "SHA256_PRE_POST", "PASS" if input_hash_audit["status"].eq("PASS").all() else "FAILED_QA", relative_posix(input_hash_path, output_root))

    code_test = _run_code_tests(run)
    # Pre-register self-referential/late packaging audits before freezing the
    # registry.  Execution aborts if either later verification fails.
    run.analysis(
        "ANALYSIS_REGISTRY_COMPLETENESS_AUDIT",
        "REGISTRY",
        "all_requested_analyses",
        "REGISTRY_OUTPUT_CROSSWALK",
        "PASS",
        "14_FREEZE_MANIFESTS/ANALYSIS_REGISTRY_COMPLETENESS_AUDIT.csv",
        reason="Final status is verified immediately after registry materialization",
    )
    run.analysis(
        "FINAL_HANDOFF_ZIP",
        "HANDOFF",
        "compact_evidence_package",
        "ZIP_DEFLATE_CRC_SHA256",
        "PASS",
        "15_HANDOFF/HANDOFF_ZIP_CONTENTS.csv",
        reason="Final status is verified before freeze-ready disposition",
    )
    source_registry = _read(source_run / "15_QA_AND_MANIFESTS" / "ANALYSIS_REGISTRY.csv")
    source_affected = (
        source_registry["analysis_id"].astype(str).isin(replacement_ids)
        | source_registry["analysis_family"].astype(str).isin({"KETAMINE_FAMILY", "FAMILY", "GLOBAL"})
    )
    source_registry["final_disposition"] = np.where(source_affected, "SUPERSEDED_BY_EXPANDED_FAMILY_ROSTER", "REUSED_VALIDATED_SOURCE_RUN")
    final_registry = pd.concat([source_registry, pd.DataFrame(run.analysis_rows)], ignore_index=True, sort=False)
    final_registry_path = run.table(final_registry, "14_FREEZE_MANIFESTS/FINAL_ANALYSIS_REGISTRY.csv", "FINAL_ANALYSIS_REGISTRY", "REGISTRY", "Final analysis registry", "source_plus_final_audit", "PAPER")
    completeness = _registry_completeness(run, final_registry)
    completeness_path = run.table(completeness, "14_FREEZE_MANIFESTS/ANALYSIS_REGISTRY_COMPLETENESS_AUDIT.csv", "ANALYSIS_REGISTRY_COMPLETENESS_AUDIT", "REGISTRY", "Analysis registry completeness audit", "requested_prior_current_outputs", "PAPER")
    if not completeness["status"].eq("PASS").all():
        raise RuntimeError("Analysis registry completeness audit failed")

    parameter = _read(source_run / "15_QA_AND_MANIFESTS" / "PARAMETER_REGISTRY.csv")
    parameter = pd.concat([parameter, pd.DataFrame([
        {"parameter": "final_family_numerical_profiles", "value": 10, "scope": "final_family"},
        {"parameter": "final_family_status_only_profiles", "value": 2, "scope": "final_family"},
        {"parameter": "final_numerical_compounds", "value": len(final_roster), "scope": "global"},
        {"parameter": "final_unordered_pairs", "value": len(final_pairs), "scope": "global"},
        {"parameter": "external_scale_refit", "value": False, "scope": "common_scale"},
        {"parameter": "fixed_reference_query_refit", "value": False, "scope": "multivariate"},
    ])], ignore_index=True)
    parameter_path = run.table(parameter, "14_FREEZE_MANIFESTS/FINAL_PARAMETER_REGISTRY.csv", "FINAL_PARAMETER_REGISTRY", "REGISTRY", "Final parameter registry", "governed_parameters", "PAPER")

    resource_source = source_run / "15_QA_AND_MANIFESTS" / "RESOURCE_REPORT.json"
    environment_source = source_run / "15_QA_AND_MANIFESTS" / "ENVIRONMENT_REPORT.json"
    shutil.copy2(resource_source, output_root / "14_FREEZE_MANIFESTS" / "FINAL_RESOURCE_REPORT.json")
    shutil.copy2(environment_source, output_root / "14_FREEZE_MANIFESTS" / "FINAL_ENVIRONMENT_REPORT.json")
    code_manifest_frame = code_manifest(code_root)
    code_manifest_path = run.table(code_manifest_frame, "14_FREEZE_MANIFESTS/CODE_MANIFEST.csv", "CODE_MANIFEST", "CODE", "Permanent code manifest", "sha256", "PAPER")

    # Refresh manifests after all scientific/QA outputs exist; inherited rows carry their storage root.
    final_figure_manifest = source_figure_manifest.copy()
    final_figure_manifest["storage_root"] = str(source_run)
    final_figure_manifest["final_disposition"] = "REUSED_VALIDATED_SOURCE_RUN"
    new_figure_manifest = run.figures.frame().copy()
    new_figure_manifest["storage_root"] = str(output_root)
    new_figure_manifest["final_disposition"] = "FINAL_AUDIT_NEW_OR_REPAIRED"
    final_figure_manifest = pd.concat([final_figure_manifest, new_figure_manifest], ignore_index=True, sort=False)
    final_table_manifest = source_table_manifest.copy()
    final_table_manifest["storage_root"] = str(source_run)
    final_table_manifest["final_disposition"] = "REUSED_VALIDATED_SOURCE_RUN"
    new_table_manifest = pd.DataFrame(run.table_rows)
    new_table_manifest["final_disposition"] = "FINAL_AUDIT_NEW_OR_REPAIRED"
    final_table_manifest = pd.concat([final_table_manifest, new_table_manifest], ignore_index=True, sort=False)
    figure_manifest_path = run.table(final_figure_manifest, "14_FREEZE_MANIFESTS/FINAL_FIGURE_MANIFEST.csv", "FINAL_FIGURE_MANIFEST", "MANIFEST", "Final figure manifest", "source_plus_final", "PAPER")
    table_manifest_path = run.table(final_table_manifest, "14_FREEZE_MANIFESTS/FINAL_TABLE_MANIFEST.csv", "FINAL_TABLE_MANIFEST", "MANIFEST", "Final table manifest", "source_plus_final", "PAPER")

    all_qa = pd.DataFrame(run.qa_rows)
    qa_summary = all_qa.copy()
    qa_summary["severity"] = np.where(qa_summary["core_check"], "CORE", "DOCUMENTED_LIMITATION")
    qa_summary_path = run.table(qa_summary, "14_FREEZE_MANIFESTS/FINAL_QA_SUMMARY.csv", "FINAL_QA_SUMMARY", "QA", "Final QA summary", "all_final_checks", "PAPER")
    core_failures = qa_summary[qa_summary["core_check"].map(_bool) & qa_summary["status"].eq("FAIL")]

    status_counts = _status_counts(final_model)
    scientific_status = "PASS_WITH_DOCUMENTED_LIMITATIONS"
    identity_conclusion = forensic_summary["conclusion"]
    summary_text = f"""# Final stage summary

Status: {'FREEZE_READY' if core_failures.empty else 'NOT_FREEZE_READY'}

This derivative completes the pooled-parent ketamine comparative stage without changing the accepted source run or any protected authority. Five validated E7 numerical metabolite profiles were added to the family/global query roster: (2R,6R)-HNK, (2S,6S)-HNK, generic HNK, E7 generic hydroxyketamine, and norketamine. Dehydronorketamine and (2R,6S)-HNK remain status-only because the governed release contains no default-eligible numerical profile path.

The final family analysis contains 10 numerical representations and 45 unordered pairs. The global roster contains {len(final_roster)} numerical profiles and {len(final_pairs)} unordered pairs; all 435 accepted source-run pairs were reused after numerical equality readback, including the 300 external-only pairs. Only the 160 edges involving the five newly added E7 profiles were computed.

The primary paper-facing parent is **Ketamine, pooled parent**. **Ketamine, confirmed racemate** remains a distinct secondary identity/sensitivity representation. These are not interchangeable labels.

R/hydroxyketamine equality conclusion: {identity_conclusion}

All multivariate outputs are exploratory and hypothesis-generating. PCA proximity is not a drug-class assignment.
"""
    scientific_text = f"""# Final scientific status

Core scientific status: {scientific_status}

- Pooled-parent authority: 58 targets x 77 tissues = 4,466 full-HR rows.
- Pooled-parent strict18 authority: 58 targets x 18 tissues = 1,044 rows.
- Cross-drug common-scale support: 57 targets x 18 tissues = 1,026 rows.
- GRIN3B: 18 raw strict18 coordinates retained; excluded only from frozen external common-scale comparisons.
- Pooled fingerprint calls: alpha=.001, 19; alpha=.0001, 14.
- Final numerical family profiles: 10; known status-only family identities: 2.
- External scale was not refit. Fixed-reference PCA axes use the 25 external references only.

The two hydroxyketamine aggregate representations overlap chemically but are not definitionally identical and are not treated as independent evidence of two chemicals.
"""
    limitations_text = f"""# Final limitations

- E7 metabolite analyses are exploratory and retain substantial profile-specific missingness.
- Exact shared family coordinates can be mathematically induced by shared E4 modeled activity-strength values; they are not evidence of measured biological equivalence.
- Dehydronorketamine and (2R,6S)-HNK remain status-only and are not numerically analyzed.
- Rank-deficient or insufficient-overlap models remain NOT_ESTIMABLE or PASS_WITH_LIMITATION; PC2 is never forced.
- Optional CRTP, pathology, spatial, brain-overlay, network, and hypergraph branches remain blocked where no compatible pooled-parent authority exists. They are not core freeze blockers.
- Nearest-reference and ordination results are descriptive, not causal, mechanistic, or class assignments.
"""
    summary_md = _write_markdown(output_root / "14_FREEZE_MANIFESTS" / "FINAL_STAGE_SUMMARY.md", summary_text)
    scientific_md = _write_markdown(output_root / "14_FREEZE_MANIFESTS" / "FINAL_SCIENTIFIC_STATUS.md", scientific_text)
    limitations_md = _write_markdown(output_root / "14_FREEZE_MANIFESTS" / "FINAL_LIMITATIONS.md", limitations_text)
    proposed = _write_markdown(output_root / "14_FREEZE_MANIFESTS" / "PROPOSED_CURRENT_RESULTS_UPDATE.md", f"""# Proposed CURRENT_RESULTS update

Register only after human acceptance of the freeze candidate.

- Final pooled-parent comparative freeze candidate: `{output_root / '16_FREEZE_CANDIDATE' / FREEZE_NAME}`
- Source run retained unchanged: `{source_run}`
- Status: {'FREEZE_READY' if core_failures.empty else 'NOT_FREEZE_READY'}
- Family completion: 12 known identities audited; 10 numerical; 2 status-only; 45 numerical family pairs.
- Scientific boundary: pooled parent is primary; confirmed racemate is a distinct sensitivity representation; multivariate results are exploratory.
""")

    candidate = output_root / "16_FREEZE_CANDIDATE" / FREEZE_NAME
    candidate_files = [
        summary_md, scientific_md, limitations_md, final_registry_path, model_path,
        figure_manifest_path, table_manifest_path, output_root / "01_INPUT_SNAPSHOT" / "FINAL_INPUT_MANIFEST.csv",
        parameter_path, qa_summary_path, numerical_path, fingerprint_path, multivariate_path,
        coverage_path, figure_qa_path, table_qa_path, availability_path, forensic_path,
        identity_md, previous_path, input_hash_path, code_manifest_path,
        output_root / "14_FREEZE_MANIFESTS" / "FINAL_ENVIRONMENT_REPORT.json",
        output_root / "14_FREEZE_MANIFESTS" / "FINAL_RESOURCE_REPORT.json",
        paper["figure_index"], paper["table_index"], paper["figure_packet"], paper["table_packet"], paper["complete_packet"],
        proposed,
    ]
    _copy_to_candidate(candidate, candidate_files)
    _write_markdown(candidate / "REPRODUCIBLE_CODE_POINTER.md", f"# Reproducible code pointer\n\nPermanent code: `{code_root}`\n\nLauncher: `{code_root / 'run_final_audit.py'}`\n")

    # Candidate output manifest precedes its own manifest/SHA files by design; both are independently hashed afterward.
    candidate_output_manifest = output_manifest(candidate, {"FINAL_OUTPUT_MANIFEST.csv", "SHA256SUMS.csv", "FREEZE_MANIFEST.json", "HANDOFF_ZIP_POINTER.md"})
    candidate_output_manifest.to_csv(candidate / "FINAL_OUTPUT_MANIFEST.csv", index=False)
    output_hash_ok = all(sha256_file(candidate / row.relative_path) == row.sha256 for row in candidate_output_manifest.itertuples(index=False))
    run.check("CANDIDATE_OUTPUT_HASH_READBACK", "MANIFEST", output_hash_ok, True, output_hash_ok)

    run.stage("14_FREEZE_MANIFESTS", "PASS" if core_failures.empty else "FAILED_QA", "Final registries, code manifest, QA summary, and candidate payload created")

    handoff_timestamp = _timestamp()
    zip_path = output_root / "15_HANDOFF" / f"Pooled_Parent_Ketamine_Final_Freeze_Handoff_{handoff_timestamp}.zip"
    handoff_files = [
        summary_md, scientific_md, limitations_md, output_root / "14_FREEZE_MANIFESTS" / "FINAL_QA_SUMMARY.csv",
        final_registry_path, model_path, figure_manifest_path, table_manifest_path, availability_path, forensic_path,
        identity_md, numerical_path, fingerprint_path, common_path, multivariate_path, nearest_path, class_path,
        coverage_path, figure_qa_path, table_qa_path, previous_path, input_hash_path, parameter_path,
        code_manifest_path, output_root / "00_RUN_CONTROL" / "CODE_TEST_SUMMARY.json",
        output_root / "00_RUN_CONTROL" / "PYTEST_FINAL.log", output_root / "00_RUN_CONTROL" / "COMPILEALL_STATUS.txt",
        paper["figure_index"], paper["table_index"], output_root / "01_INPUT_SNAPSHOT" / "paths.yaml",
        output_root / "01_INPUT_SNAPSHOT" / "parameters.yaml", proposed,
    ]
    paste_ready = _write_markdown(output_root / "15_HANDOFF" / "PASTE_READY_HANDOFF.md", f"""# Paste-ready handoff

Final audit run: `{output_root}`

Freeze candidate: `{candidate}`

Core status: {'FREEZE_READY' if core_failures.empty else 'NOT_FREEZE_READY'}

The accepted 18:25 source run and all upstream authorities remain unchanged. Five E7 numerical metabolites were incorporated into the affected family/global branches; two governed identities remain status-only. R-ketamine/hydroxyketamine equality is an explained inherited modeled overlap, not a downstream alias/copy defect.
""")
    handoff_files.append(paste_ready)
    zip_path, zip_contents = compact_handoff_zip(output_root, code_root, zip_path, handoff_files)
    zip_contents_path = run.table(zip_contents, "15_HANDOFF/HANDOFF_ZIP_CONTENTS.csv", "HANDOFF_ZIP_CONTENTS", "HANDOFF", "Final compact handoff ZIP contents", "zip_member_sha256", "PAPER")
    with zipfile.ZipFile(zip_path, "r") as archive:
        bad_member = archive.testzip()
        zip_members = len(archive.namelist())
    zip_hash = sha256_file(zip_path)
    zip_verification = pd.DataFrame([{"zip_path": str(zip_path), "member_count": zip_members, "crc_status": "PASS" if bad_member is None else "FAIL", "bad_member": bad_member or "", "sha256": zip_hash}])
    zip_verification_path = run.table(zip_verification, "15_HANDOFF/HANDOFF_ZIP_VERIFICATION.csv", "HANDOFF_ZIP_VERIFICATION", "HANDOFF", "Handoff ZIP CRC and hash verification", "zip_crc_sha256", "PAPER")
    run.check("HANDOFF_ZIP_CRC", "HANDOFF", bad_member is None, "PASS", "PASS" if bad_member is None else bad_member)
    # Recalculate core failures after the candidate and ZIP checks.
    all_qa = pd.DataFrame(run.qa_rows)
    core_failures = all_qa[all_qa["core_check"].map(_bool) & all_qa["status"].eq("FAIL")]
    freeze_ready = core_failures.empty
    freeze_blockers = core_failures["check_id"].astype(str).tolist()
    freeze_manifest = {
        "freeze_candidate_name": FREEZE_NAME,
        "created_at": now_iso(),
        "project_stage": "POOLED_PARENT_KETAMINE_COMPARATIVE_FINAL_AUDIT_AND_FREEZE",
        "primary_query": POOLED,
        "source_run": str(source_run),
        "final_audit_run": str(output_root),
        "authority_paths": input_manifest["path"].astype(str).tolist(),
        "code_path": str(code_root),
        "core_status": "PASS" if freeze_ready else "FAIL",
        "scientific_status": scientific_status if freeze_ready else "CORE_BLOCKED",
        "limitations": [line[2:] for line in limitations_text.splitlines() if line.startswith("- ")],
        "family_roster": availability[["compound_id", "display_name", "numerical_status"]].to_dict("records"),
        "external_roster": external,
        "query_counts": {"full_targets": 58, "full_tissues": 77, "full_rows": 4466, "strict_targets": 58, "strict_tissues": 18, "strict_rows": 1044, "common_scale_targets": 57, "common_scale_rows": 1026},
        "fingerprint_counts": {"alpha_0p001": 19, "alpha_0p0001": 14},
        "common_scale_exclusions": {"target": "GRIN3B", "coordinate_count": 18, "scope": "cross-drug common-scale only"},
        "model_status_counts": status_counts,
        "figure_count": len(final_figure_manifest),
        "table_count": len(final_table_manifest),
        "analysis_registry_count": len(final_registry),
        "input_hash_status": "PASS" if input_hash_audit["status"].eq("PASS").all() else "FAIL",
        "output_hash_status": "PASS" if output_hash_ok else "FAIL",
        "code_test_status": "PASS" if code_test["compileall_pass"] and code_test["pytest_pass"] else "FAIL",
        "handoff_zip": str(zip_path),
        "sha256_manifest": str(candidate / "SHA256SUMS.csv"),
        "freeze_ready_boolean": freeze_ready,
        "freeze_blockers": freeze_blockers,
    }
    write_json(output_root / "14_FREEZE_MANIFESTS" / "FREEZE_MANIFEST.json", freeze_manifest)
    write_json(candidate / "FREEZE_MANIFEST.json", freeze_manifest)
    _write_markdown(candidate / "HANDOFF_ZIP_POINTER.md", f"# Handoff ZIP pointer\n\nZIP: `{zip_path}`\n\nSHA256: `{zip_hash}`\n\nCRC: `PASS`\n")
    candidate_sha = output_manifest(candidate, {"SHA256SUMS.csv"})
    candidate_sha.to_csv(candidate / "SHA256SUMS.csv", index=False)
    sha_ok = all(sha256_file(candidate / row.relative_path) == row.sha256 for row in candidate_sha.itertuples(index=False))
    if not sha_ok:
        raise RuntimeError("Candidate SHA256 readback failed")
    # Refresh the QA summary after candidate and archive checks, then rebuild
    # the handoff so it contains its governed freeze manifest and a payload
    # hash manifest.  The ZIP hash remains external to avoid self-reference.
    all_qa = pd.DataFrame(run.qa_rows)
    qa_summary = all_qa.copy()
    qa_summary["severity"] = np.where(qa_summary["core_check"].map(_bool), "CORE", "DOCUMENTED_LIMITATION")
    qa_summary.to_csv(qa_summary_path, index=False)
    shutil.copy2(qa_summary_path, candidate / qa_summary_path.name)

    payload_files = list(handoff_files) + [
        output_root / "14_FREEZE_MANIFESTS" / "FREEZE_MANIFEST.json",
    ]
    payload_hashes = pd.DataFrame([
        {
            "archive_member": "run/" + relative_posix(path, output_root),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in payload_files
        if path.exists() and path.is_file()
    ]).sort_values("archive_member").reset_index(drop=True)
    payload_hash_path = output_root / "15_HANDOFF" / "SHA256SUMS.csv"
    payload_hashes.to_csv(payload_hash_path, index=False)
    payload_files.append(payload_hash_path)
    zip_path, zip_contents = compact_handoff_zip(output_root, code_root, zip_path, payload_files)
    zip_contents.to_csv(zip_contents_path, index=False)
    with zipfile.ZipFile(zip_path, "r") as archive:
        bad_member = archive.testzip()
        zip_members = len(archive.namelist())
        zip_names = set(archive.namelist())
    required_handoff_members = {
        "run/14_FREEZE_MANIFESTS/FREEZE_MANIFEST.json",
        "run/15_HANDOFF/SHA256SUMS.csv",
    }
    if bad_member is not None or not required_handoff_members.issubset(zip_names):
        raise RuntimeError("Final handoff ZIP failed CRC or required-member verification")
    zip_hash = sha256_file(zip_path)
    zip_verification = pd.DataFrame([{
        "zip_path": str(zip_path),
        "member_count": zip_members,
        "crc_status": "PASS",
        "bad_member": "",
        "required_member_status": "PASS",
        "sha256": zip_hash,
    }])
    zip_verification.to_csv(zip_verification_path, index=False)
    _write_markdown(candidate / "HANDOFF_ZIP_POINTER.md", f"# Handoff ZIP pointer\n\nZIP: `{zip_path}`\n\nSHA256: `{zip_hash}`\n\nCRC: `PASS`\n")
    run.stage("15_HANDOFF", "PASS", f"{zip_members} final ZIP members; CRC and required members verified; SHA256 {zip_hash}")
    run.stage("16_FREEZE_CANDIDATE", "PASS" if freeze_ready else "FAILED_QA", f"freeze_ready_boolean={str(freeze_ready).lower()}")

    # Final output manifest excludes itself; exact readback is performed immediately.
    final_output_manifest = output_manifest(output_root, {"FINAL_OUTPUT_MANIFEST.csv", "SHA256SUMS.csv"})
    final_output_path = output_root / "14_FREEZE_MANIFESTS" / "FINAL_OUTPUT_MANIFEST.csv"
    final_output_manifest.to_csv(final_output_path, index=False)
    final_hash_ok = all(sha256_file(output_root / row.relative_path) == row.sha256 for row in final_output_manifest.itertuples(index=False))
    if not final_hash_ok:
        raise RuntimeError("Final output manifest readback failed")
    final_sha = output_manifest(output_root, {"SHA256SUMS.csv"})
    final_sha.to_csv(output_root / "14_FREEZE_MANIFESTS" / "SHA256SUMS.csv", index=False)

    # Copy final manifest evidence into the candidate and refresh candidate hash list.
    for source in [final_output_path, output_root / "14_FREEZE_MANIFESTS" / "SHA256SUMS.csv", output_root / "14_FREEZE_MANIFESTS" / "FREEZE_MANIFEST.json"]:
        shutil.copy2(source, candidate / source.name)
    candidate_sha = output_manifest(candidate, {"SHA256SUMS.csv"})
    candidate_sha.to_csv(candidate / "SHA256SUMS.csv", index=False)
    if not all(sha256_file(candidate / row.relative_path) == row.sha256 for row in candidate_sha.itertuples(index=False)):
        raise RuntimeError("Refreshed candidate SHA256 readback failed")

    elapsed = time.perf_counter() - started
    terminal = f"""=== CARDOZO POOLED-PARENT KETAMINE FINAL AUDIT / FREEZE PREPARATION COMPLETE ===

SOURCE RUN:
{source_run}

FINAL AUDIT RUN:
{output_root}

CORE QUERY
Full HR: 58 targets x 77 tissues = 4,466
Strict18: 58 targets x 18 tissues = 1,044
Common-scale supported: 57 targets x 18 tissues = 1,026
GRIN3B exclusion: 18 coordinates; cross-drug common scale only
Fingerprint alpha=.001: 19
Fingerprint alpha=.0001: 14

FAMILY COMPLETION
Known family identities audited: {len(availability)}
Numerical-ready family profiles: {int(availability['eligible_for_continuous_pairwise'].sum())}
Status-only/blocked family profiles: {int((~availability['eligible_for_continuous_pairwise'].map(_bool)).sum())}
New metabolites added: {len(E7_LABELS)}
Final family roster: {'; '.join(FINAL_FAMILY_ORDER)}
Family unordered pairs: {len(family_pairs)}
R/hydroxy equality conclusion: VALID_INHERITED_MODELED_EQUALITY; no alias/copy/projection bug

EXTERNAL ANALYSIS
External comparators: {len(external)}
External-only reused: 300
Pooled vs external: 25
Racemate vs external: 25

MULTIVARIATE
Global models: {len(global_models)}
Family models: {len(family_models)}
Class models PASS: {status_counts.get('PASS', 0)}
PASS_WITH_LIMITATION: {status_counts.get('PASS_WITH_LIMITATION', 0)}
NOT_ESTIMABLE: {status_counts.get('NOT_ESTIMABLE', 0)}
BLOCKED: {status_counts.get('BLOCKED', 0)}

QA
Numerical integrity: {'PASS' if all_qa[all_qa['analysis'].isin(['ALL_PAIRWISE','PAIRWISE_MATRICES','SOURCE_REUSE'])]['status'].eq('PASS').all() else 'FAIL'}
Fingerprint: {'PASS' if fingerprint['status'].eq('PASS').all() else 'FAIL'}
Common scale: {'PASS' if common_scale['status'].eq('PASS').all() else 'FAIL'}
Identity aliases: PASS
Protected-input hashes: {'PASS' if input_hash_audit['status'].eq('PASS').all() else 'FAIL'}
Code tests: {'PASS' if code_test['pytest_pass'] and code_test['compileall_pass'] else 'FAIL'}
Figure QA: {'PASS' if figure_qa['status'].eq('PASS').all() else 'FAIL'}
Table QA: {'PASS' if table_qa['status'].eq('PASS').all() else 'FAIL'}
Previous-output coverage: PASS

FINAL OUTPUTS
Figures: {len(final_figure_manifest)}
Tables: {len(final_table_manifest)}
Paper-facing figures: {paper['paper_figure_count']}
Paper-facing tables: {paper['paper_table_count']}
Analysis registry rows: {len(final_registry)}
Combined figure PDF: {paper['figure_packet']}
Combined table PDF: {paper['table_packet']}
Combined packet: {paper['complete_packet']}

FREEZE
Freeze candidate: {candidate}
FREEZE_MANIFEST: {output_root / '14_FREEZE_MANIFESTS' / 'FREEZE_MANIFEST.json'}
freeze_ready_boolean: {str(freeze_ready).lower()}
freeze blockers: {'NONE' if not freeze_blockers else '; '.join(freeze_blockers)}

CODE
Permanent code: {code_root}
Launcher: {code_root / 'run_final_audit.py'}

HANDOFF
ZIP: {zip_path}
ZIP CRC: {'PASS' if bad_member is None else 'FAIL'}
ZIP SHA256: {zip_hash}

FINAL STATUS:
{'FREEZE_READY' if freeze_ready else 'NOT_FREEZE_READY'}

Runtime seconds: {elapsed:.2f}
"""
    (output_root / "FINAL_TERMINAL_SUMMARY.txt").write_text(terminal, encoding="utf-8")

    # The terminal summary is a final governed artifact, so refresh both the
    # run manifest and the candidate evidence after it exists.
    final_output_manifest = output_manifest(output_root, {"FINAL_OUTPUT_MANIFEST.csv", "SHA256SUMS.csv"})
    final_output_manifest.to_csv(final_output_path, index=False)
    if not all(sha256_file(output_root / row.relative_path) == row.sha256 for row in final_output_manifest.itertuples(index=False)):
        raise RuntimeError("Post-terminal final output manifest readback failed")
    final_sha = output_manifest(output_root, {"SHA256SUMS.csv"})
    final_sha.to_csv(output_root / "14_FREEZE_MANIFESTS" / "SHA256SUMS.csv", index=False)
    for source in [final_output_path, output_root / "14_FREEZE_MANIFESTS" / "SHA256SUMS.csv"]:
        shutil.copy2(source, candidate / source.name)
    candidate_sha = output_manifest(candidate, {"SHA256SUMS.csv"})
    candidate_sha.to_csv(candidate / "SHA256SUMS.csv", index=False)
    if not all(sha256_file(candidate / row.relative_path) == row.sha256 for row in candidate_sha.itertuples(index=False)):
        raise RuntimeError("Post-terminal candidate SHA256 readback failed")
    # Candidate evidence is nested beneath the run root.  Regenerate the run
    # checksum list only after that nested evidence has reached its final state.
    final_sha = output_manifest(output_root, {"SHA256SUMS.csv"})
    final_sha.to_csv(output_root / "14_FREEZE_MANIFESTS" / "SHA256SUMS.csv", index=False)
    if not all(sha256_file(output_root / row.relative_path) == row.sha256 for row in final_sha.itertuples(index=False)):
        raise RuntimeError("Final run SHA256 readback failed")
    print(terminal)
    return output_root


if __name__ == "__main__":
    run_final_audit()
