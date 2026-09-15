# SPDX-License-Identifier: MIT
"""Exercise class models, target/tissue governance, and authority routing synthetically."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cardozo_ketamine_hr.authority_discovery import discover
from cardozo_ketamine_hr.class_analysis import run_class_models, summarize_classes
from cardozo_ketamine_hr.targets import harmonize_target, load_target_contract
from cardozo_ketamine_hr.tissue_normalization import canonical_tissue_key, display_tissue, normalize_tissue_pair


def _class_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    compounds = ["Q", "A", "B", "C"]
    features = ["f1", "f2", "f3", "f4"]
    common = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0], [1.2, 2.1, 2.8, 3.9], [-1.0, -2.0, -3.0, -4.0], [0.5, 1.0, 1.5, 2.0]],
        index=compounds,
        columns=features,
    )
    calls = pd.DataFrame([[1.0, 0.0, 1.0, 0.0], [1.0, 1.0, 0.0, 0.0], [0.0, 1.0, 1.0, 0.0], [1.0, 0.0, 0.0, 1.0]], index=compounds, columns=features)
    contract = pd.DataFrame({"feature_id": features, "target": ["T1", "T1", "T2", "T2"], "tissue": ["B1", "B2", "B1", "B2"]})
    rows = []
    for a, b in combinations(compounds, 2):
        distance = float(np.sqrt(np.mean((common.loc[a] - common.loc[b]) ** 2)))
        rows.append({"drug_a": a, "drug_b": b, "rms_common_rhr": distance})
    pairwise = pd.DataFrame(rows)
    classes = pd.DataFrame({"class_id": ["full", "full", "full", "empty"], "class_label": ["Full", "Full", "Full", "Empty"], "drug": ["A", "B", "C", "MISSING"]})
    return common, calls, pairwise, contract, classes


def test_class_model_suite_records_success_and_inestimable_statuses() -> None:
    common, calls, pairwise, contract, classes = _class_inputs()
    result = run_class_models(common, calls, pairwise, contract, classes, ["Q"])
    status = result["status"]
    assert len(status) == 14
    assert set(status["class_id"]) == {"full", "empty"}
    full = status[status["class_id"].eq("full")]
    empty = status[status["class_id"].eq("empty")]
    assert full["status"].eq("PASS").sum() >= 5
    assert empty["status"].eq("NOT_ESTIMABLE").all()
    assert not result["scores"].empty
    assert not result["pcoa"].empty and not result["linkage"].empty


def test_class_summary_preserves_missing_classes_and_query_orientation() -> None:
    common, calls, _, contract, classes = _class_inputs()
    summary, residuals = summarize_classes(common, calls, contract, classes, "Q")
    summary = summary.set_index("class_id")
    assert summary.loc["full", "status"] == "PASS"
    assert summary.loc["full", "numerical_member_count"] == 3
    assert summary.loc["empty", "status"] == "BLOCKED_MISSING_DATA"
    assert set(residuals["class_id"]) == {"full"}
    first = residuals[residuals["feature_id"].eq("f1")].iloc[0]
    assert first["query_minus_class_median"] == pytest.approx(0.5)


def test_target_contract_validation_and_resolution_states(tmp_path: Path) -> None:
    valid_path = tmp_path / "valid.parquet"
    pd.DataFrame(
        {
            "target_canonical_id": ["T1", "T1", "T2"],
            "gene_symbol": ["G1", "G1", "G2"],
            "target_grain_class": ["EXACT_SINGLE_PROTEIN"] * 3,
            "tissue": ["B1", "B2", "B1"],
        }
    ).to_parquet(valid_path, index=False)
    contract = load_target_contract(valid_path)
    assert len(contract) == 2
    resolved = harmonize_target("g1", contract=contract)
    assert resolved.status == "RESOLVED" and resolved.canonical_target_id == "T1"
    assert harmonize_target({"canonical_target_id": "T2", "target_grain": "EXACT PROTEIN"}, contract=contract).status == "RESOLVED"
    assert harmonize_target({"target": "T1", "target_grain": "GENERIC_RECEPTOR"}, contract=contract).status == "UNSUPPORTED_TARGET_GRAIN"
    assert harmonize_target("NMDA receptor", contract=contract).status == "AMBIGUOUS_TARGET_GRAIN"
    assert harmonize_target("missing", contract=contract).status == "UNRESOLVED"
    ambiguous = pd.concat([contract, pd.DataFrame({"target_canonical_id": ["X"], "gene_symbol": ["G1"], "target_grain_class": ["EXACT_SINGLE_PROTEIN"]})], ignore_index=True)
    assert harmonize_target("G1", contract=ambiguous).status == "AMBIGUOUS_TARGET_MAPPING"

    missing_path = tmp_path / "missing.parquet"
    pd.DataFrame({"target_canonical_id": ["T"]}).to_parquet(missing_path, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        load_target_contract(missing_path)
    conflict_path = tmp_path / "conflict.parquet"
    pd.DataFrame({"target_canonical_id": ["T", "T"], "gene_symbol": ["G1", "G2"], "target_grain_class": ["EXACT", "EXACT"]}).to_parquet(conflict_path, index=False)
    with pytest.raises(ValueError, match="conflicting"):
        load_target_contract(conflict_path)


def test_tissue_normalization_changes_typography_not_identity() -> None:
    assert canonical_tissue_key("Prefrontal Cortex") == "prefrontalcortex"
    assert canonical_tissue_key(None) == ""
    assert display_tissue("prefrontal-cortex") == "Prefrontal Cortex"
    assert display_tissue(" Novel Region ") == "Novel Region"
    assert normalize_tissue_pair("caudate nucleus", "Caudate-Nucleus") == ("caudatenucleus", "Caudate nucleus")
    assert normalize_tissue_pair("whole brain", "Unknown cosmetic label") == ("wholebrain", "Whole brain")
    assert normalize_tissue_pair("Novel", None) == ("novel", "Novel")


def test_authority_discovery_requires_explicit_complete_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="external project root"):
        discover(None)
    with pytest.raises(FileNotFoundError, match="Missing governed inputs") as exc:
        discover(tmp_path)
    assert "pooled_activity" in str(exc.value) and "e7_final_manifest" in str(exc.value)
