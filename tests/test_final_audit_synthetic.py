# SPDX-License-Identifier: MIT
"""Exercise terminal audit logic with derivative-only synthetic authorities."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from cardozo_ketamine_hr.final_audit import (
    POOLED,
    RACEMATE,
    AuditRun,
    _read,
    _timestamp,
    _bool,
    _call_detail,
    _class_audit,
    _common_scale_audit,
    _coverage_audit,
    _figure_qa,
    _finalize_input_hash_audit,
    _fingerprint_audit,
    _family_pairwise_outputs,
    _finite_max,
    _multivariate_audit,
    _model_suite,
    _nearest_family,
    _nearest_reference_audit,
    _numerical_integrity,
    _pair_detail,
    _profile_matrices,
    _protected_input_hashes,
    _registry_completeness,
    _replace_source_pairs,
    _save_model,
    _status_counts,
    _table_qa,
)
from cardozo_ketamine_hr.figures import scatter
from cardozo_ketamine_hr.family_completion import FINAL_FAMILY_ORDER
from cardozo_ketamine_hr.pairwise_continuous import all_pairwise
from cardozo_ketamine_hr.pairwise_fingerprint import metric_function


def _run(tmp_path: Path) -> AuditRun:
    root = tmp_path / "audit"
    source = tmp_path / "source"
    code = tmp_path / "code"
    for path in (root, source, code):
        path.mkdir()
    for stage in ("00_RUN_CONTROL", "01_INPUT_SNAPSHOT", "06_UPDATED_GLOBAL_MODELS"):
        (root / stage).mkdir()
    return AuditRun(root, source, code)


def _matrix_inputs() -> tuple[list[str], pd.DataFrame, dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    roster = [POOLED, RACEMATE, "S-ketamine", "R-ketamine", "Hydroxyketamine, unspecified isomer aggregate"]
    features = [f"f{i}" for i in range(1, 7)]
    contract = pd.DataFrame(
        {
            "feature_id": features,
            "target": ["T1", "T1", "T2", "T2", "T3", "T3"],
            "tissue": ["B1", "B2", "B1", "B2", "B1", "B2"],
            "feature_order": range(6),
        }
    )
    common = pd.DataFrame(
        [[1, 2, 3, 4, 5, 6], [1.1, 2.2, 3.1, 4.1, 5.2, 6.1], [-1, -2, -3, -4, -5, -6], [2, 1, 2, 1, 2, 1], [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]],
        index=roster,
        columns=features,
        dtype=float,
    )
    common.loc[roster[-1], "f6"] = np.nan
    raw = common * 2
    matrices = {"raw_hr": raw, "common_rhr": common, "support": raw.notna().astype(int)}
    binary = (common > 2).astype(float).mask(common.isna())
    strict = (common > 4).astype(float).mask(common.isna())
    calls = {
        "call_binary_alpha001": binary,
        "call_score_alpha001": binary * common,
        "call_binary_alpha0001": strict,
        "call_score_alpha0001": strict * common,
    }
    return roster, contract, matrices, calls


def test_scalar_profile_pair_and_call_helpers_preserve_semantics() -> None:
    assert len(_timestamp()) == 15
    assert [_bool(value) for value in [True, np.bool_(False), " yes ", "0"]] == [True, False, True, False]
    assert _finite_max(pd.Series(["bad", np.nan])) == 0.0
    assert _finite_max(pd.Series([1, "3"])) == 3.0
    assert _status_counts(pd.DataFrame({"status": ["PASS", "PASS", "FAIL"]})) == {"PASS": 2, "FAIL": 1}
    roster, contract, matrices, calls = _matrix_inputs()
    profiles = matrices["raw_hr"].stack().rename("raw_hr").reset_index()
    profiles.columns = ["drug", "feature_id", "raw_hr"]
    profiles["common_rhr"] = profiles["raw_hr"] / 2
    rebuilt = _profile_matrices(profiles, contract, roster)
    assert rebuilt["raw_hr"].equals(matrices["raw_hr"])
    detail = _pair_detail(matrices["common_rhr"], contract, roster[0], roster[1])
    assert detail.columns[:2].tolist() == ["query_compound", "comparator"] and len(detail) == 6
    call_detail = _call_detail(calls["call_binary_alpha001"], roster[0], roster[1], contract, "001")
    assert set(call_detail["call_relationship"]).issubset({"SHARED", "POOLED_ONLY", "METABOLITE_ONLY"})


def test_audit_csv_reader_preserves_missing_values(tmp_path: Path) -> None:
    path = tmp_path / "values.csv"
    path.write_text("name,value\nA,\nB,2\n", encoding="utf-8")
    frame = _read(path)
    assert pd.isna(frame.loc[0, "value"]) and frame.loc[1, "value"] == 2


def test_audit_run_registers_real_derivative_tables_figures_checks_and_stages(tmp_path: Path) -> None:
    run = _run(tmp_path)
    table = run.table(pd.DataFrame({"x": [1, 2]}), "tables/a.csv", "T1", "A1", "Synthetic", "unit-test")
    figure = scatter(pd.DataFrame({"compound": [POOLED, "A"], "PC1": [0, 1], "PC2": [1, 0]}), "Synthetic", "PC1", "PC2")
    png, pdf = run.figure(figure, "figures/a", "F1", "A1", "Synthetic", "tables/a.csv")
    run.analysis("A1", "family", "unit-test", "SYNTHETIC", "PASS", str(table), str(png))
    run.check("C1", "A1", True, 2, 2)
    run.stage("01_INPUT_SNAPSHOT", "PASS", "synthetic derivative")
    assert table.exists() and png.exists() and pdf.exists()
    assert run.analysis_rows[0]["final_disposition"] == "CURRENT_FINAL"
    assert run.qa_rows[0]["status"] == "PASS"
    assert (run.root / "00_RUN_CONTROL" / "STAGE_STATUS.json").exists()


def test_replace_source_pairs_reuses_only_legacy_edges() -> None:
    source = pd.DataFrame({"drug_a": ["A"], "drug_b": ["B"], "metric": [1.25], "label": ["accepted"]})
    computed = pd.DataFrame({"drug_a": ["A", "A"], "drug_b": ["B", "NEW"], "metric": [9.0, 2.0], "label": ["new", "new"]})
    result = _replace_source_pairs(computed, source, ["A", "B"])
    assert result.loc[0, "metric"] == 1.25 and result.loc[0, "reused_or_recomputed"] == "REUSED_VALIDATED_SOURCE_RUN"
    assert result.loc[1, "metric"] == 2.0 and result.loc[1, "reused_or_recomputed"] == "RECOMPUTED_AFFECTED_EDGE"


def test_model_persistence_records_not_estimable_without_false_outputs(tmp_path: Path) -> None:
    run = _run(tmp_path)
    scores, loadings, status = _save_model(
        run,
        "06_UPDATED_GLOBAL_MODELS",
        "SYNTHETIC_FAILURE",
        "synthetic",
        "INTENTIONAL_FAILURE_PROBE",
        lambda: (_ for _ in ()).throw(ValueError("insufficient rank")),
        [POOLED],
    )
    assert scores.empty and loadings.empty
    assert status["status"] == "NOT_ESTIMABLE" and "insufficient rank" in status["reason"]
    assert run.analysis_rows[-1]["status"] == "NOT_ESTIMABLE"


def test_final_audit_model_suite_persists_multivariate_and_distance_outputs(tmp_path: Path) -> None:
    run = _run(tmp_path)
    roster, contract, matrices, calls = _matrix_inputs()
    pairs, _ = all_pairwise(matrices, contract, roster, metric_function(calls, contract))
    status = _model_suite(
        run,
        "SYNTHETIC",
        matrices["common_rhr"],
        calls["call_binary_alpha001"],
        calls["call_binary_alpha0001"],
        pairs,
        contract,
        "06_UPDATED_GLOBAL_MODELS",
        reference=roster[2:],
        projections=roster[:2],
    )
    assert len(status) == 10
    assert status["status"].isin({"PASS", "PASS_WITH_LIMITATION", "NOT_ESTIMABLE"}).all()
    assert status["status"].eq("PASS").sum() >= 7
    assert len(run.table_rows) >= 12 and len(run.figures.rows) >= 10
    assert all((run.root / row["output_file"]).exists() for row in run.figures.rows)


def test_pairwise_numerical_and_nearest_family_audits_run_on_complete_synthetic_data(tmp_path: Path) -> None:
    run = _run(tmp_path)
    roster, contract, matrices, calls = _matrix_inputs()
    pairs, _ = all_pairwise(matrices, contract, roster, metric_function(calls, contract))
    pairs["reused_or_recomputed"] = "REUSED_VALIDATED_SOURCE_RUN"
    audit = _numerical_integrity(run, pairs, pairs.copy(), matrices, calls, roster, roster)
    nearest = _nearest_family(pairs)
    assert len(audit) >= 25 and audit["status"].eq("PASS").sum() >= 20
    assert len(nearest) == 50
    assert nearest["interpretation"].eq("DESCRIPTIVE_EXPLORATORY_NOT_CLASS_ASSIGNMENT").all()


def test_family_pairwise_outputs_emit_complete_metabolite_packet(tmp_path: Path) -> None:
    run = _run(tmp_path)
    features = [f"f{i}" for i in range(1, 7)]
    contract = pd.DataFrame({"feature_id": features, "target": ["T1", "T1", "T2", "T2", "T3", "T3"], "tissue": ["B1", "B2", "B1", "B2", "B1", "B2"], "feature_order": range(6)})
    common = pd.DataFrame(
        [[index + offset / 10 for offset in range(6)] for index in range(1, len(FINAL_FAMILY_ORDER) + 1)],
        index=FINAL_FAMILY_ORDER,
        columns=features,
        dtype=float,
    )
    common.columns.name = "feature_id"
    raw = common * 2
    matrices = {"raw_hr": raw, "common_rhr": common, "support": raw.notna().astype(int)}
    binary = (common > 3).astype(float)
    strict = (common > 6).astype(float)
    calls = {"call_binary_alpha001": binary, "call_score_alpha001": binary * common, "call_binary_alpha0001": strict, "call_score_alpha0001": strict * common}
    pairs, _ = all_pairwise(matrices, contract, FINAL_FAMILY_ORDER, metric_function(calls, contract))
    _family_pairwise_outputs(run, pairs, matrices, calls, contract)
    assert len(run.table_rows) >= 70
    assert len(run.figures.rows) >= 20
    assert len(run.analysis_rows) == 7
    assert all((run.root / row["output_file"]).exists() for row in run.figures.rows)


def test_common_scale_fingerprint_and_nearest_reference_audits(tmp_path: Path) -> None:
    run = _run(tmp_path)
    roster, _, _, calls = _matrix_inputs()
    query = run.source_run / "01_QUERY_AUTHORITY"
    heatmaps = run.source_run / "02_HEATMAP_REPAIR"
    pair_dir = run.source_run / "03_EXTERNAL_PAIRWISE_CONTINUOUS"
    for path in (query, heatmaps, pair_dir):
        path.mkdir(parents=True)
    strict = pd.DataFrame({"canonical_target_id": np.repeat([f"T{i}" for i in range(58)], 18)})
    projected = strict.rename(columns={"canonical_target_id": "canonical_target_id"}).copy()
    projected["common_scale_compatible"] = projected["canonical_target_id"].ne("T57")
    projected.loc[projected["canonical_target_id"].eq("T57"), "canonical_target_id"] = "GRIN3B"
    strict.loc[strict["canonical_target_id"].eq("T57"), "canonical_target_id"] = "GRIN3B"
    strict.to_csv(query / "POOLED_PARENT_STRICT18_HR_AUTHORITY.csv", index=False)
    projected.to_csv(query / "POOLED_PARENT_STRICT18_COMMON_SCALE_PROJECTION.csv", index=False)
    common = _common_scale_audit(run, run.source_run)
    assert common["status"].eq("PASS").all()

    for alpha, count in (("001", 19), ("0001", 14)):
        features = [f"f{i}" for i in range(1, count + 1)]
        pd.DataFrame({"feature_id_common": features}).to_csv(query / f"POOLED_PARENT_FINGERPRINT_ALPHA_0p{alpha}.csv", index=False)
        pd.DataFrame({"target": ["T"], **{feature: [1.0] for feature in features}}).to_csv(heatmaps / f"POOLED_PARENT_FINGERPRINT_ALPHA{alpha}_HEATMAP_MATRIX.csv", index=False)
        matrix = pd.DataFrame(np.nan, index=roster, columns=[f"f{i}" for i in range(1, 20)])
        matrix.loc[POOLED, features] = 1.0
        matrix.loc[roster[1], "f1"] = 0.0
        calls[f"call_binary_alpha{alpha}"] = matrix
    fingerprint = _fingerprint_audit(run, run.source_run, calls)
    assert fingerprint["status"].eq("PASS").all()

    external = ["Propofol", "Chlorpromazine", "Aripiprazole", "Other"]
    rows = []
    for index, drug in enumerate(external):
        rows.append({"drug_a": POOLED, "drug_b": drug, "rms_common_rhr": 0.1 + index, "cosine_common_rhr": 0.9 - index / 10, "spearman_common_rhr": 0.8 - index / 10, "alpha001_call_jaccard": 0.9 if drug == "Chlorpromazine" else 0.1, "support_jaccard": 0.9 if drug == "Aripiprazole" else 0.2, "matched_features": 10, "matched_targets": 5, "support_union_features": 12})
    pd.DataFrame(rows).to_csv(pair_dir / "POOLED_PARENT_VS_25_EXTERNAL_METRICS.csv", index=False)
    nearest = _nearest_reference_audit(run, run.source_run)
    assert len(nearest) == 5 and nearest["status"].eq("PASS").all()


def test_class_coverage_and_multivariate_audits_preserve_explicit_statuses(tmp_path: Path) -> None:
    run = _run(tmp_path)
    class_dir = run.source_run / "07_CLASS_ANALYSES"
    summary_dir = run.source_run / "09_CLASS_SUMMARIES"
    global_dir = run.source_run / "06_GLOBAL_MULTIVARIATE"
    for path in (class_dir, summary_dir, global_dir):
        path.mkdir(parents=True)
    pd.DataFrame({"class_id": ["C1", "C1"], "class_label": ["Class 1", "Class 1"], "status": ["PASS", "NOT_ESTIMABLE"]}).to_csv(class_dir / "CLASS_STATUS.csv", index=False)
    pd.DataFrame({"class_id": ["C1"], "value": [1]}).to_csv(summary_dir / "CLASS_SUMMARY.csv", index=False)
    class_audit = _class_audit(run, run.source_run)
    assert class_audit.loc[0, "status"] == "PASS"

    roster, contract, matrices, _ = _matrix_inputs()
    coverage = _coverage_audit(run, matrices, contract, roster)
    assert len(coverage) == len(roster) and set(coverage["status"]).issubset({"PASS", "FAIL"})

    loadings = pd.DataFrame({"feature_id": ["f1", "f2"], "loading_PC1": [0.5, -0.5], "loading_PC2": [0.2, 0.2]})
    loadings.to_csv(global_dir / "GLOBAL_FIXED_REFERENCE_PCA_LOADINGS.csv", index=False)
    loadings.to_csv(run.root / "06_UPDATED_GLOBAL_MODELS" / "GLOBAL_FIXED_REFERENCE_PCA_LOADINGS.csv", index=False)
    statuses = pd.DataFrame([
        {"analysis_id": "SYNTHETIC_PCA", "representation": "common", "method": "EM_SVD", "status": "PASS", "rank": 2, "component_count": 2, "sample_count": 5, "feature_count": 6, "input_roster": ";".join(roster)},
        {"analysis_id": "SYNTHETIC_FIXED_REFERENCE", "representation": "common", "method": "FROZEN", "status": "PASS", "rank": 2, "component_count": 2, "reference_axes_refit_with_query": False},
    ])
    audit = _multivariate_audit(run, statuses, run.source_run)
    assert audit["audit_status"].eq("PASS").all()


def test_real_figure_table_and_protected_hash_qa(tmp_path: Path) -> None:
    run = _run(tmp_path)
    source_table = run.source_run / "table.csv"
    pd.DataFrame({"a": [1]}).to_csv(source_table, index=False)
    new_table = run.table(pd.DataFrame({"b": [2]}), "new.csv", "NEW", "A", "New", "synthetic")
    source_tables = pd.DataFrame({"table_id": ["SOURCE"], "output_file": ["table.csv"], "row_count": [1], "column_count": [1]})
    new_tables = pd.DataFrame(run.table_rows)
    table_audit = _table_qa(run, source_tables, new_tables)
    assert table_audit["status"].eq("PASS").all() and new_table.exists()

    source_figure = scatter(pd.DataFrame({"compound": ["A", "B"], "PC1": [0, 1], "PC2": [1, 0]}), "Source", "PC1", "PC2")
    source_recorder = AuditRun(run.source_run, run.source_run, run.code_root)
    source_recorder.figure(source_figure, "source_fig", "SOURCE", "A", "Source", "table.csv")
    new_figure = scatter(pd.DataFrame({"compound": ["A", "B"], "PC1": [0, 1], "PC2": [0, 1]}), "New", "PC1", "PC2")
    run.figure(new_figure, "new_fig", "NEW", "A", "New", "new.csv")
    figure_audit = _figure_qa(run, pd.DataFrame(source_recorder.figures.rows), pd.DataFrame(run.figures.rows))
    assert figure_audit["status"].eq("PASS").all()

    manifest_dir = run.source_run / "15_QA_AND_MANIFESTS"
    manifest_dir.mkdir()
    protected = tmp_path / "protected.csv"
    protected.write_text("x\n1\n", encoding="utf-8")
    from cardozo_ketamine_hr.utilities import sha256_file
    pd.DataFrame({"input_role": ["base"], "path": [str(protected)], "bytes": [protected.stat().st_size], "sha256": [sha256_file(protected)]}).to_csv(manifest_dir / "INPUT_MANIFEST.csv", index=False)
    additions = {}
    for key in ["e7_identity_accounting", "e7_numeric_compounds", "e7_raw_matrix", "e7_common_matrix", "e7_primary_calls", "e7_sensitivity_calls", "e7_hydroxy_identity_audit"]:
        path = tmp_path / f"{key}.txt"
        path.write_text(key, encoding="utf-8")
        additions[key] = path
    manifest, before = _protected_input_hashes(additions, run.source_run)
    result = _finalize_input_hash_audit(manifest, before)
    assert len(result) == 8 and result["status"].eq("PASS").all()


def test_registry_completeness_requires_every_final_analysis_and_no_orphans(tmp_path: Path) -> None:
    run = _run(tmp_path)
    tokens = [
        "FAMILY_PROFILE_AVAILABILITY_AUDIT", "FAMILY_VECTOR_IDENTITY_FORENSIC_AUDIT",
        "FAMILY_ALL_PAIR_METRICS_FINAL", "POOLED_PARENT_VS_METABOLITE",
        "FAMILY_JOINT_CONTINUOUS_PCA", "GLOBAL_JOINT_CONTINUOUS_PCA",
        "FINAL_NUMERICAL_INTEGRITY_AUDIT", "COMMON_SCALE_COMPATIBILITY_AUDIT",
        "FINAL_FINGERPRINT_AUDIT", "FINAL_MULTIVARIATE_AUDIT",
        "FINAL_NEAREST_REFERENCE_AUDIT", "FINAL_CLASS_AUDIT", "FINAL_COVERAGE_AUDIT",
        "FINAL_FIGURE_QA", "FINAL_TABLE_QA", "PREVIOUS_VS_FINAL_OUTPUT_COVERAGE",
        "FINAL_INPUT_PRE_POST_HASH_AUDIT",
    ]
    registry = pd.DataFrame({"analysis_id": tokens})
    result = _registry_completeness(run, registry)
    assert len(result) == 18 and result["status"].eq("PASS").all()
    assert run.qa_rows[-1]["check_id"] == "ANALYSIS_REGISTRY_COMPLETENESS"
