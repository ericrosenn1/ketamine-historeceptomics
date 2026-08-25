"""Test portable lane outputs, regression gates, and provenance-safe reuse."""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import cardozo_ketamine_hr.portable as portable
from cardozo_ketamine_hr.portable import (
    CheckLedger,
    build_pairwise,
    build_profiles_and_calls,
    compare_outputs,
    persist_hr_outputs,
    persist_strict_cns_fingerprints,
    run_smoke_analysis_checks,
    verify_hr_construction,
    write_run_manifest,
)


def _assert_ledger_passes(ledger: CheckLedger) -> None:
    """Assert that a test ledger contains no failed validation rows."""

    failures = [row for row in ledger.rows if row["status"] != "PASS"]
    assert not failures, failures


def _write_test_pdsp(path: Path, *, ki_value: float = 100.0) -> None:
    """Write the minimal deterministic PDSP workbook used by inventory tests."""

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "Ki ID": [1],
            "Species": ["Homo sapiens"],
            "Receptor": ["GRIN1"],
            "Test Ligands": ["ketamine"],
            "Ki Value": [ki_value],
        }
    ).to_excel(path, index=False)


def _write_reusable_test_stage(
    tmp_path: Path,
    *,
    summary: dict[str, object] | None = None,
    output_name: str = "result.csv",
) -> tuple[Path, Path, dict[str, Path]]:
    """Create a coherent miniature stage, producer, input, summary, and output."""

    # Reuse validation hashes this connected fixture as one provenance unit;
    # mutations in later tests therefore exercise exactly one governed edge.
    stage = tmp_path / "stage"
    stage.mkdir()
    script = tmp_path / "producer.py"
    script.write_text("print('producer')\n", encoding="utf-8")
    inputs = {"input": tmp_path / "input.csv"}
    inputs["input"].write_text("value\n1\n", encoding="utf-8")
    (stage / "SUMMARY.json").write_text(
        json.dumps(summary or {"status": "PASS"}), encoding="utf-8"
    )
    (stage / output_name).write_text("value\n1\n", encoding="utf-8")
    return stage, script, inputs


@pytest.mark.external_data
def test_core_hr_fingerprint_and_nearest_outputs_are_persisted_and_manifested(
    tmp_path: Path, governed_paths
):
    ledger = CheckLedger()
    data_root = governed_paths["external_input_root"]
    full, strict = verify_hr_construction(ledger, data_root=data_root)
    pooled_provenance: dict[str, object] = {}
    contract, matrices, calls, drugs = build_profiles_and_calls(
        strict,
        ledger,
        pooled_source_label="TEST_REGENERATED_STRICT18_AFTER_EQUIVALENCE",
        pooled_provenance=pooled_provenance,
        data_root=data_root,
    )
    (tmp_path / "family").mkdir()
    (tmp_path / "global").mkdir()
    persist_hr_outputs(full, strict, contract, matrices, drugs, tmp_path, ledger)
    persist_strict_cns_fingerprints(calls, matrices, contract, drugs, tmp_path, ledger)
    pairwise = build_pairwise(contract, matrices, calls, drugs, tmp_path, ledger)
    write_run_manifest(tmp_path)
    _assert_ledger_passes(ledger)

    assert full.shape == (4466, 100)
    assert strict.shape == (1044, 11)
    assert matrices["raw_hr"].shape == (35, 1368)
    assert len(pairwise) == 595
    assert pooled_provenance["raw_hr_source"] == "TEST_REGENERATED_STRICT18_AFTER_EQUIVALENCE"
    assert pooled_provenance["raw_hr_injected"] is True
    assert pooled_provenance["common_contract_coordinates"] == 1026
    assert pooled_provenance["raw_hr_max_abs_delta_before_injection"] <= portable.TOLERANCE

    expected = {
        "hr/POOLED_PARENT_FULL77_HR_REGENERATED.parquet",
        "hr/POOLED_PARENT_STRICT18_HR_REGENERATED.csv",
        "hr/STRICT18_FEATURE_CONTRACT.csv",
        "hr/ALL_35_PROFILES_STRICT18_RAW_HR_MATRIX.csv",
        "hr/ALL_35_PROFILES_STRICT18_COMMON_RHR_MATRIX.csv",
        "fingerprints/strict_cns/ALL_35_PROFILES_STRICT_CNS_CALLS_ALPHA001.csv",
        "fingerprints/strict_cns/ALL_35_PROFILES_STRICT_CNS_CALLS_ALPHA0001.csv",
        "fingerprints/strict_cns/ALL_35_PROFILES_STRICT_CNS_CALL_BINARY_ALPHA001.csv",
        "fingerprints/strict_cns/ALL_35_PROFILES_STRICT_CNS_CALL_BINARY_ALPHA0001.csv",
        "fingerprints/strict_cns/STRICT_CNS_FINGERPRINT_FILE_INDEX.csv",
        "nearest_reference/POOLED_PARENT_VS_25_EXTERNAL_NEAREST_REFERENCE_SUMMARY.csv",
        "nearest_reference/FAMILY_NEAREST_MEMBER_SUMMARY.csv",
    }
    manifest = pd.read_csv(tmp_path / "MANIFEST.tsv", sep="\t")
    assert expected.issubset(set(manifest["path"]))

    index = pd.read_csv(tmp_path / "fingerprints/strict_cns/STRICT_CNS_FINGERPRINT_FILE_INDEX.csv")
    assert len(index) == 70
    assert index["drug"].nunique() == 35
    assert index.groupby("drug")["alpha"].nunique().eq(2).all()
    assert index["call_count"].eq(0).any()
    assert all((tmp_path / value).exists() for value in index["calls_file"])
    assert set(index["calls_file"]).issubset(set(manifest["path"]))

    binary = pd.read_csv(
        tmp_path / "fingerprints/strict_cns/ALL_35_PROFILES_STRICT_CNS_CALL_BINARY_ALPHA001.csv"
    ).set_index("drug")
    finite = binary.to_numpy(float)
    assert set(np.unique(finite[np.isfinite(finite)])).issubset({0.0, 1.0})
    assert np.isnan(finite).any()


def test_smoke_checks_pairwise_pca_clustering_and_persists_rendered_figure(tmp_path: Path):
    ledger = CheckLedger()
    run_smoke_analysis_checks(tmp_path, ledger)
    write_run_manifest(tmp_path)
    _assert_ledger_passes(ledger)
    expected = {
        "smoke/SMOKE_PCA_SCORES.csv",
        "smoke/SMOKE_AVERAGE_LINKAGE.csv",
        "smoke/SMOKE_PCA_SCATTER.png",
    }
    manifest = pd.read_csv(tmp_path / "MANIFEST.tsv", sep="\t")
    assert expected.issubset(set(manifest["path"]))
    assert (tmp_path / "smoke/SMOKE_PCA_SCATTER.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.external_data
def test_verify_hr_construction_consumes_explicit_regenerated_overrides(
    tmp_path: Path, governed_paths
):
    data_root = governed_paths["external_input_root"]
    full = pd.read_parquet(governed_paths["pooled_full_hr"])
    strict = pd.read_csv(governed_paths["pooled_strict_hr"], low_memory=False)
    target = str(strict.loc[0, "canonical_target_id"])
    tissue = str(strict.loc[0, "tissue_id"])
    full_mask = full["canonical_target_id"].astype(str).eq(target) & full["tissue_id"].astype(str).eq(tissue)
    epsilon = 5e-12
    full.loc[full_mask, "HR_numeric_boundary_or_exact"] = (
        pd.to_numeric(full.loc[full_mask, "HR_numeric_boundary_or_exact"], errors="raise") + epsilon
    )
    strict.loc[0, "hr_numeric_collapsed"] = float(strict.loc[0, "hr_numeric_collapsed"]) + epsilon
    full_path = tmp_path / "regenerated_full.parquet"
    strict_path = tmp_path / "regenerated_strict.csv"
    full.to_parquet(full_path, index=False)
    strict.to_csv(strict_path, index=False)

    ledger = CheckLedger()
    observed_full, observed_strict = verify_hr_construction(
        ledger, full_path, strict_path, data_root=data_root
    )
    _assert_ledger_passes(ledger)
    assert observed_full.loc[full_mask, "HR_numeric_boundary_or_exact"].iloc[0] == full.loc[
        full_mask, "HR_numeric_boundary_or_exact"
    ].iloc[0]
    assert observed_strict.loc[0, "hr_numeric_collapsed"] == pd.read_csv(strict_path).loc[
        0, "hr_numeric_collapsed"
    ]


def test_compare_outputs_fails_when_a_required_reference_matched_output_is_missing(
    tmp_path: Path, monkeypatch
):
    reference = tmp_path / "reference"
    output = tmp_path / "output"
    for section in ["family", "global", "class"]:
        (reference / section).mkdir(parents=True)
        (output / section).mkdir(parents=True)
    frame = pd.DataFrame({"id": ["A"], "value": [1.0]})
    frame.to_csv(reference / "family" / "REQUIRED_FAMILY.csv", index=False)
    frame.to_csv(reference / "global" / "REQUIRED_GLOBAL.csv", index=False)
    frame.to_csv(output / "family" / "REQUIRED_FAMILY.csv", index=False)
    for name in [
        "CLASS_SCORES.csv",
        "CLASS_LOADINGS.csv",
        "CLASS_STATUS.csv",
        "CLASS_SUMMARY.csv",
        "CLASS_RESIDUALS_LONG.csv",
    ]:
        frame.to_csv(reference / "class" / name, index=False)
        frame.to_csv(output / "class" / name, index=False)
    monkeypatch.setattr(portable, "REFERENCE", reference)

    missing_ledger = CheckLedger()
    compare_outputs(output, missing_ledger)
    missing = [row for row in missing_ledger.rows if row["status"] == "FAIL"]
    assert [row["check"] for row in missing] == ["regression_global_REQUIRED_GLOBAL"]
    assert missing[0]["observed"] == "MISSING"

    frame.to_csv(output / "global" / "REQUIRED_GLOBAL.csv", index=False)
    complete_ledger = CheckLedger()
    compare_outputs(output, complete_ledger)
    _assert_ledger_passes(complete_ledger)


@pytest.mark.parametrize("changed_input", ["initial_activity_table", "pdsp_workbook", "parent_output"])
def test_stage_reuse_rejects_changed_input_or_parent_hash(tmp_path: Path, changed_input: str):
    stage = tmp_path / "stage"
    stage.mkdir()
    script = tmp_path / "producer.py"
    script.write_text("print('producer')\n", encoding="utf-8")
    inputs = {
        "initial_activity_table": tmp_path / "initial.csv",
        "pdsp_workbook": tmp_path / "pdsp.xlsx",
        "parent_output": tmp_path / "parent.csv",
    }
    for name, path in inputs.items():
        path.write_bytes(f"{name}:v1".encode("utf-8"))
    (stage / "SUMMARY.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    (stage / "result.csv").write_text("value\n1\n", encoding="utf-8")

    portable._write_stage_provenance(stage, script, inputs, ["result.csv"])
    assert portable._validate_stage_reuse(stage, script, inputs, ["result.csv"]) == "PASS"

    inputs[changed_input].write_bytes(f"{changed_input}:v2".encode("utf-8"))
    with pytest.raises(RuntimeError, match=rf"input:{changed_input}"):
        portable._validate_stage_reuse(stage, script, inputs, ["result.csv"])


def test_v2_project_inventory_closes_identity_and_pdsp_absent_to_present_changes(
    tmp_path: Path,
):
    project_root = tmp_path / "project"
    supplied_pdsp = project_root / "02_HR_SCORES" / "PDSP_Ki_source.xlsx"
    _write_test_pdsp(supplied_pdsp)

    before = portable._resolve_v2_project_inventory(project_root, supplied_pdsp)
    assert before["identity_master"]["exists"] is False
    assert len(before["pdsp_candidates"]) == 1
    assert before["pdsp_candidates"][0]["selected"] is True

    stage, script, inputs = _write_reusable_test_stage(tmp_path)
    portable._write_stage_provenance(
        stage, script, inputs, ["result.csv"], project_input_inventory=before
    )
    assert (
        portable._validate_stage_reuse(
            stage, script, inputs, ["result.csv"], project_input_inventory=before
        )
        == "PASS"
    )

    identity_master = (
        project_root
        / "12_QA_AUDITS_AND_PROVENANCE"
        / "Audit_Reports"
        / "Racemic_Ketamine_Identity_Coverage_Audit_20260805_165431_492"
        / "02_SOURCE_RECORD_INVENTORY"
        / "KETAMINE_SOURCE_ASSERTION_MASTER.parquet"
    )
    identity_master.parent.mkdir(parents=True, exist_ok=True)
    identity_master.write_bytes(b"new identity authority")
    higher_ranked = project_root / "02_HR_SCORES" / "KiDatabase_new.xlsx"
    higher_ranked.write_bytes(supplied_pdsp.read_bytes())

    after = portable._resolve_v2_project_inventory(project_root, supplied_pdsp)
    assert after["identity_master"]["exists"] is True
    assert len(after["pdsp_candidates"]) == 2
    assert Path(after["pdsp_selected"]["path"]) == higher_ranked.resolve()
    assert after["pdsp_selected"]["sha256"] == after["pdsp_supplied"]["sha256"]
    with pytest.raises(RuntimeError, match="project_input_inventory"):
        portable._validate_stage_reuse(
            stage, script, inputs, ["result.csv"], project_input_inventory=after
        )

    _write_test_pdsp(higher_ranked, ki_value=101.0)
    with pytest.raises(RuntimeError, match="differs from the explicitly supplied"):
        portable._resolve_v2_project_inventory(project_root, supplied_pdsp)


def test_v3_project_inventory_closes_candidate_source_appearance_mutation_and_removal(
    tmp_path: Path,
):
    project_root = tmp_path / "project"
    supplied_pdsp = tmp_path / "supplied_pdsp.xlsx"
    _write_test_pdsp(supplied_pdsp)
    v2_dir = tmp_path / "v2"
    v2_dir.mkdir()
    legacy_source = (
        r"SYNTHETIC_ROOT\Ketamine project\ketamine_hr_analysis\\data_raw\legacy_source.csv"
    )
    pd.DataFrame(
        {
            "source_assertion_id": ["SID1"],
            "source_file": [legacy_source],
            "source_rows": ["1"],
        }
    ).to_csv(v2_dir / "POOLED_PARENT_KETAMINE_ACTIVITY_TABLE_SPECIES_CLEANED.csv", index=False)
    pd.DataFrame(
        {
            "proposed_selected_pActivity": [5.0],
            "proposed_selected_source_database": ["PDSP"],
            "proposed_selection_status": ["SELECTED_BOUNDED_DIRECTION_UNKNOWN_REVIEW_REQUIRED"],
            "proposed_selected_source_assertion_id": ["SID1"],
        }
    ).to_csv(v2_dir / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY.csv", index=False)

    before = portable._resolve_v3_project_inventory(project_root, supplied_pdsp, v2_dir)
    assert before["pdsp_fallback_candidates"] == []
    assert before["legacy_source_resolutions"][0]["resolved"]["exists"] is False

    stage, script, inputs = _write_reusable_test_stage(tmp_path)
    portable._write_stage_provenance(
        stage, script, inputs, ["result.csv"], project_input_inventory=before
    )
    reorganized_source = (
        project_root
        / "09_CODE_AND_PIPELINES"
        / "Historical_Project_Trees"
        / "ketamine_hr_analysis"
        / "data_raw"
        / "legacy_source.csv"
    )
    reorganized_source.parent.mkdir(parents=True, exist_ok=True)
    reorganized_source.write_text("relation,value\n>,100\n", encoding="utf-8")
    fallback_pdsp = (
        project_root
        / "09_CODE_AND_PIPELINES"
        / "Historical_Project_Trees"
        / "KiDatabase_fallback.xlsx"
    )
    _write_test_pdsp(fallback_pdsp)

    present = portable._resolve_v3_project_inventory(project_root, supplied_pdsp, v2_dir)
    assert [Path(row["path"]) for row in present["pdsp_fallback_candidates"]] == [
        fallback_pdsp.resolve()
    ]
    resolved = present["legacy_source_resolutions"][0]["resolved"]
    assert resolved["exists"] is True
    assert Path(resolved["path"]) == reorganized_source.resolve()
    with pytest.raises(RuntimeError, match="project_input_inventory"):
        portable._validate_stage_reuse(
            stage, script, inputs, ["result.csv"], project_input_inventory=present
        )

    portable._write_stage_provenance(
        stage, script, inputs, ["result.csv"], project_input_inventory=present
    )
    reorganized_source.write_text("relation,value\n<,100\n", encoding="utf-8")
    mutated = portable._resolve_v3_project_inventory(project_root, supplied_pdsp, v2_dir)
    with pytest.raises(RuntimeError, match="project_input_inventory"):
        portable._validate_stage_reuse(
            stage, script, inputs, ["result.csv"], project_input_inventory=mutated
        )

    portable._write_stage_provenance(
        stage, script, inputs, ["result.csv"], project_input_inventory=mutated
    )
    reorganized_source.unlink()
    removed = portable._resolve_v3_project_inventory(project_root, supplied_pdsp, v2_dir)
    assert removed["legacy_source_resolutions"][0]["resolved"]["exists"] is False
    with pytest.raises(RuntimeError, match="project_input_inventory"):
        portable._validate_stage_reuse(
            stage, script, inputs, ["result.csv"], project_input_inventory=removed
        )


@pytest.mark.parametrize(
    ("mutation", "expected_mismatch"),
    [
        ("script", "script_sha256"),
        ("output", "output:SELECTED_SOURCE_ROW_FORENSIC.csv"),
        ("external", "external:source_input"),
    ],
)
def test_stage_reuse_rejects_script_output_and_summary_external_mutation(
    tmp_path: Path, mutation: str, expected_mismatch: str
):
    external = tmp_path / "external.csv"
    external.write_text("value\n1\n", encoding="utf-8")
    output_name = "SELECTED_SOURCE_ROW_FORENSIC.csv"
    stage, script, inputs = _write_reusable_test_stage(
        tmp_path,
        summary={"status": "PASS", "source_input": str(external.resolve())},
        output_name=output_name,
    )
    assert output_name in portable.V3_OUTPUT_NAMES
    portable._write_stage_provenance(stage, script, inputs, [output_name])

    if mutation == "script":
        script.write_text("print('changed producer')\n", encoding="utf-8")
    elif mutation == "output":
        (stage / output_name).write_text("value\n2\n", encoding="utf-8")
    else:
        external.write_text("value\n2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=expected_mismatch):
        portable._validate_stage_reuse(stage, script, inputs, [output_name])


def test_full_root_qa_combines_eight_upstream_and_87_downstream_checks(tmp_path: Path):
    upstream = CheckLedger()
    for index in range(8):
        upstream.add(f"upstream_{index}", True, "PASS", "PASS")
    downstream = tmp_path / portable.FULL_DOWNSTREAM_DIRNAME
    downstream.mkdir()
    pd.DataFrame(
        {
            "check": [f"downstream_{index}" for index in range(87)],
            "status": ["PASS"] * 87,
            "observed": ["PASS"] * 87,
            "expected": ["PASS"] * 87,
            "detail": [""] * 87,
        }
    ).to_csv(downstream / "QA_SUMMARY.csv", index=False)

    assert downstream.name == "verify_after_upstream_equivalence"
    assert portable._write_combined_full_qa(tmp_path, upstream, downstream) == 95
    combined = pd.read_csv(tmp_path / "QA_SUMMARY.csv")
    assert len(combined) == 95
    assert combined["category"].value_counts().to_dict() == {
        "DOWNSTREAM_VERIFY_AFTER_UPSTREAM_EQUIVALENCE": 87,
        "UPSTREAM_AUTHORITY_EQUIVALENCE": 8,
    }
