# SPDX-License-Identifier: MIT
"""Exercise derivative orchestration helpers without governed or restricted inputs."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cardozo_ketamine_hr.pipeline import (
    QUERY,
    RunContext,
    _ancillary_registry,
    _input_manifest,
    _model_suite,
    _pair_row,
    _pool_calls,
    _pool_profile,
    _previous_coverage,
    _reuse_external_only,
)
from cardozo_ketamine_hr.qa import QARecorder


def _context(tmp_path: Path) -> RunContext:
    project = tmp_path / "project"
    code = tmp_path / "code"
    project.mkdir()
    code.mkdir()
    return RunContext(project, code, tmp_path / "run")


def test_run_context_records_pass_optional_limit_and_required_failure(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assert context.run_stage("01_QUERY_AUTHORITY", lambda: 7) == 7
    assert context.run_stage("02_HEATMAP_REPAIR", lambda: (_ for _ in ()).throw(ValueError("optional")), optional=True) is None
    with pytest.raises(RuntimeError, match="required"):
        context.run_stage("03_EXTERNAL_PAIRWISE_CONTINUOUS", lambda: (_ for _ in ()).throw(RuntimeError("required")))
    assert [row["status"] for row in context.stage_rows] == ["PASS", "PASS_WITH_DOCUMENTED_LIMITATION", "FAILED_QA"]
    assert len(context.failure_rows) == 2
    context.add_analysis("A1", "family", "A", "representation", "method", "PASS_COMPLETE", runtime=1.5, workers=2)
    row = context.analysis_rows[0]
    assert row["query_compound"] == QUERY and row["QA_status"] == "PASS"
    assert row["cpu_workers"] == 2 and row["gpu_used"] is False


def test_pool_profile_calls_and_pair_lookup_preserve_contract() -> None:
    contract = pd.DataFrame(
        {
            "feature_id": ["f1", "f2"], "target": ["T1", "T2"],
            "target_canonical_id": ["T1", "T2"], "tissue": ["B1", "B2"],
            "tissue_canonical_id": ["B1", "B2"], "feature_order": [1, 2],
        }
    )
    projection = pd.DataFrame({"feature_id_common": ["f1", "f2", None], "raw_hr": [1.0, 2.0, 9.0], "common_rhr": [0.5, 1.0, 9.0], "common_scale_compatible": [True, True, False]})
    profile = _pool_profile({"strict_contract": contract, "strict_mapped": projection})
    assert profile["drug"].eq(QUERY).all() and profile["feature_id"].tolist() == ["f1", "f2"]
    calls = pd.DataFrame({"feature_id_common": ["f1"], "raw_hr": [999], "other": ["kept"]})
    mapped = _pool_calls(calls, projection)
    assert mapped.loc[0, "raw_hr"] == 1.0 and mapped.loc[0, "drug"] == QUERY
    pairs = pd.DataFrame({"drug_a": ["A"], "drug_b": ["B"], "value": [3]})
    assert _pair_row(pairs, "B", "A")["value"] == 3
    with pytest.raises(RuntimeError, match="exactly one pair"):
        _pair_row(pairs, "A", "C")


def test_external_pair_reuse_requires_and_preserves_300_equal_pairs() -> None:
    external = [f"D{i:02d}" for i in range(25)]
    rows = []
    for index, (a, b) in enumerate(combinations(external, 2)):
        rows.append({"drug_a": a, "drug_b": b, "rms_common_rhr": index / 100, "flag": index % 2 == 0, "label": "stable"})
    prior = pd.DataFrame(rows)
    computed = prior.copy()
    computed.loc[:, "rms_common_rhr"] += 1e-12
    computed = pd.concat([computed, pd.DataFrame([{"drug_a": QUERY, "drug_b": "D00", "rms_common_rhr": 9.0, "flag": True, "label": "new"}])], ignore_index=True)
    qa = QARecorder()
    result, comparison = _reuse_external_only(computed, prior, external, qa)
    reused = result[result["drug_a"].isin(external) & result["drug_b"].isin(external)]
    assert len(reused) == 300 and reused["reused_or_recomputed"].eq("REUSED_UNCHANGED_AFTER_NUMERICAL_EQUALITY_QA").all()
    assert result.iloc[-1]["reused_or_recomputed"] == "RECOMPUTED"
    assert set(comparison["metric"]) == {"rms_common_rhr", "flag"}
    assert qa.overall() == "PASS"


def _model_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    compounds = [QUERY, "Ketamine, confirmed racemate", "A", "B", "C"]
    features = ["f1", "f2", "f3", "f4", "f5"]
    matrix = pd.DataFrame(
        [[1, 2, 3, 4, 5], [1.1, 2.1, 3.1, 4.1, 5.1], [-1, -2, -3, -4, -5], [2, 1, 0, -1, -2], [0.5, 1.2, 2.5, 3.3, 4.8]],
        index=compounds,
        columns=features,
        dtype=float,
    )
    binary = (matrix > matrix.median()).astype(float)
    contract = pd.DataFrame({"feature_id": features, "target": ["T1", "T1", "T2", "T2", "T3"], "tissue": ["B1", "B2", "B1", "B2", "B1"], "target_canonical_id": ["T1", "T1", "T2", "T2", "T3"], "tissue_canonical_id": ["B1", "B2", "B1", "B2", "B1"]})
    pair_rows = []
    for a, b in combinations(compounds, 2):
        pair_rows.append({"drug_a": a, "drug_b": b, "rms_common_rhr": float(np.sqrt(np.mean((matrix.loc[a] - matrix.loc[b]) ** 2)))})
    return matrix, binary, contract, pd.DataFrame(pair_rows)


def test_model_suite_persists_models_distances_and_figures(tmp_path: Path) -> None:
    context = _context(tmp_path)
    matrix, binary, contract, pairwise = _model_inputs()
    output = context.run_root / "06_GLOBAL_MULTIVARIATE"
    result = _model_suite(
        context,
        "SYNTHETIC",
        matrix,
        binary,
        binary,
        pairwise,
        contract,
        output,
        reference=["A", "B", "C"],
        projections=[QUERY, "Ketamine, confirmed racemate"],
    )
    assert len(result["status"]) == 10
    assert result["status"]["status"].eq("PASS").sum() >= 8
    assert not result["scores"].empty and not result["loadings"].empty
    assert not result["linkage"].empty and result["rms"].shape == (5, 5)
    assert len(context.tables.frame()) >= 10
    assert len(context.figures.frame()) >= 10
    assert all((context.run_root / path).exists() for path in context.figures.frame()["output_file"])


def test_input_previous_and_ancillary_registries_are_complete(tmp_path: Path) -> None:
    context = _context(tmp_path)
    input_file = tmp_path / "input.csv"
    input_file.write_text("x\n1\n", encoding="utf-8")
    manifest = _input_manifest({"project_root": tmp_path, "prior_root": tmp_path, "input": input_file, "missing": tmp_path / "missing"})
    assert manifest["input_role"].tolist() == ["input"] and len(manifest.loc[0, "sha256"]) == 64

    prior_root = tmp_path / "prior"
    paper_root = tmp_path / "paper"
    prior_root.mkdir()
    paper_root.mkdir()
    prior_manifest = tmp_path / "prior_manifest.csv"
    paper_manifest = tmp_path / "paper_manifest.csv"
    pd.DataFrame({"relative_path": ["tables/pairwise.csv", "support/log.txt"]}).to_csv(prior_manifest, index=False)
    pd.DataFrame({"relative_path": ["figures/ordination.png", "notes.txt"]}).to_csv(paper_manifest, index=False)
    paths = {
        "project_root": context.project_root,
        "prior_manifest": prior_manifest,
        "prior_root": prior_root,
        "prior_paper_manifest": paper_manifest,
        "prior_paper_root": paper_root,
    }
    coverage = _previous_coverage(paths, "15_QA_AND_MANIFESTS/ANALYSIS_REGISTRY.csv")
    assert len(coverage) == 4
    assert set(coverage["status"]) == {"POOLED_PARENT_EQUIVALENT_AVAILABLE", "RECOMPUTED_OR_AUDITED_UNCHANGED"}
    ancillary = _ancillary_registry(context, paths, context.run_root / "13_ANCILLARY_ANALYSES")
    assert len(ancillary) == 17
    assert ancillary["status"].eq("PASS_WITH_DOCUMENTED_LIMITATION").sum() == 3
    assert len(context.analysis_rows) == 17
