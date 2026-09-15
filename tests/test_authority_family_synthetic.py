# SPDX-License-Identifier: MIT
"""Exercise authority projection and family completion using synthetic governed fixtures."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from cardozo_ketamine_hr.family_analysis import FAMILY_LABELS, family_roster, load_family_calls, load_family_profiles
from cardozo_ketamine_hr.family_completion import (
    E7_LABELS,
    FINAL_FAMILY_ORDER,
    availability_audit,
    extend_call_matrices,
    forensic_audit,
    load_e7_call_rows,
    load_e7_profiles,
    strict_contract_from_profiles,
)
from cardozo_ketamine_hr.query_freeze import EXPECTED, feature_contracts, freeze_query, map_pooled_to_contract, project_common_rhr


def _large_authority_fixture(root: Path) -> dict[str, Path]:
    targets = [f"T{i:02d}" for i in range(58)]
    tissues = [f"S{i:02d}" for i in range(77)]
    records = []
    for target_index, target in enumerate(targets):
        for tissue_index, tissue in enumerate(tissues):
            records.append(
                {
                    "feature_order": target_index * 77 + tissue_index,
                    "feature_id": f"{target}__{tissue}",
                    "target_canonical_id": target,
                    "gene_symbol": target,
                    "target_grain_class": "EXACT_SINGLE_PROTEIN",
                    "tissue_canonical_id": tissue,
                    "tissue_label": tissue,
                    "expression_profile_id": "SYNTHETIC_PROFILE",
                    "expression_Z": float(tissue_index) / 10,
                    "STRICT_CNS_HUMAN": tissue_index < 18,
                    "FULL_HUMAN_77_TISSUE_EXACT_PROTEIN": True,
                }
            )
    dictionary = pd.DataFrame(records)
    full = dictionary.rename(columns={"target_canonical_id": "canonical_target_id", "tissue_canonical_id": "tissue_id"}).copy()
    full["HR_numeric_boundary_or_exact"] = np.linspace(-2, 2, len(full))
    full["expression_ddof"] = 1
    strict = full[full["STRICT_CNS_HUMAN"]].copy()
    strict["hr_numeric_collapsed"] = strict["HR_numeric_boundary_or_exact"]
    call_features = strict.iloc[:19]
    calls001 = call_features[["canonical_target_id", "tissue_id", "feature_id"]].copy()
    calls0001 = calls001.iloc[:14].copy()
    missing = pd.DataFrame({"canonical_target_id": targets[:18]})
    activity = pd.DataFrame({"canonical_target_id": targets, "activity": np.arange(58)})
    summary = pd.DataFrame({"canonical_target_id": targets, "selected": True})
    paths = {
        "pooled_full_hr": root / "full.parquet",
        "pooled_strict_hr": root / "strict.csv",
        "pooled_calls_001": root / "calls001.csv",
        "pooled_calls_0001": root / "calls0001.csv",
        "pooled_missing_expression": root / "missing.csv",
        "pooled_activity": root / "activity.csv",
        "pooled_activity_summary": root / "activity_summary.csv",
        "feature_dictionary": root / "dictionary.parquet",
        "common_model_bundle": root / "model.joblib",
    }
    root.mkdir(parents=True)
    full.to_parquet(paths["pooled_full_hr"], index=False)
    strict.to_csv(paths["pooled_strict_hr"], index=False)
    calls001.to_csv(paths["pooled_calls_001"], index=False)
    calls0001.to_csv(paths["pooled_calls_0001"], index=False)
    missing.to_csv(paths["pooled_missing_expression"], index=False)
    activity.to_csv(paths["pooled_activity"], index=False)
    summary.to_csv(paths["pooled_activity_summary"], index=False)
    dictionary.to_parquet(paths["feature_dictionary"], index=False)
    joblib.dump({"knots": pd.DataFrame({"value": [-2.0, 0.0, 2.0], "weight": [1.0, 2.0, 1.0]})}, paths["common_model_bundle"])
    return paths


def test_query_freeze_validates_exact_contract_and_preserves_missingness(tmp_path: Path) -> None:
    paths = _large_authority_fixture(tmp_path / "inputs")
    full_contract, strict_contract = feature_contracts(paths["feature_dictionary"])
    assert (len(full_contract), len(strict_contract)) == (EXPECTED["full_rows"], EXPECTED["strict_rows"])
    projected = project_common_rhr(pd.Series([-2.0, -1.0, 0.0, 1.0, 2.0, np.nan]), paths["common_model_bundle"])
    assert np.isnan(projected[-1]) and np.all(np.diff(projected[:-1]) >= 0)
    pooled = pd.DataFrame({"canonical_target_id": ["T00", "UNKNOWN"], "tissue_id": ["S00", "S00"], "value": [0.0, 1.0]})
    mapped = map_pooled_to_contract(pooled, strict_contract, "value", paths["common_model_bundle"])
    assert mapped["common_scale_compatible"].tolist() == [True, False]
    assert np.isnan(mapped.loc[1, "common_rhr"])

    result = freeze_query(paths, tmp_path / "frozen")
    assert result["counts"] == EXPECTED
    assert len(result["input_manifest"]) == 9
    assert result["calls0001"]["feature_id_common"].notna().all()
    assert (tmp_path / "frozen" / "QUERY_MANIFEST.json").exists()
    assert len(list((tmp_path / "frozen").glob("*"))) >= 10


def _small_contract() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "feature_id": ["f1", "f2", "f3"],
            "target": ["T1", "T1", "T2"],
            "target_canonical_id": ["T1", "T1", "T2"],
            "tissue": ["B1", "B2", "B1"],
            "tissue_canonical_id": ["B1", "B2", "B1"],
            "feature_order": [0, 1, 2],
        }
    )


def _family_fixture(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True)
    features = ["f1", "f2", "f3"]
    family_ids = list(FAMILY_LABELS)
    family = pd.DataFrame([[compound, 1.0 + i, 2.0 + i, np.nan] for i, compound in enumerate(family_ids)], columns=["canonical_compound_id", *features])
    family_common = family.copy()
    family_common[features] = family_common[features] / 2
    family_raw_path = root / "family" / "07_SPARSE_AND_CONTINUOUS_MATRICES" / "U1" / "RAW_HR_QUERY_MATRIX.csv"
    family_common_path = family_raw_path.with_name("COMMON_RHR_QUERY_MATRIX.csv")
    family_raw_path.parent.mkdir(parents=True)
    family.to_csv(family_raw_path, index=False)
    family_common.to_csv(family_common_path, index=False)
    call_rows = []
    for compound in family_ids:
        for feature in features:
            call_rows.append({"canonical_compound_id": compound, "feature_id": feature, "fingerprint_status": "CALLED" if feature == "f1" else "NOT_CALLED", "raw_hr": 1.0, "common_RHR": 0.5})
    calls001 = root / "family_calls001.parquet"
    calls0001 = root / "family_calls0001.parquet"
    pd.DataFrame(call_rows).to_parquet(calls001, index=False)
    pd.DataFrame(call_rows).to_parquet(calls0001, index=False)

    e7_ids = list(E7_LABELS)
    e7 = pd.DataFrame([[compound, 2.0 + i, np.nan, 3.0 + i] for i, compound in enumerate(e7_ids)], columns=["compound_id", *features])
    e7_common = e7.copy()
    e7_common[features] = e7_common[features] / 2
    e7_raw_path = root / "e7_raw.csv"
    e7_common_path = root / "e7_common.csv"
    e7.to_csv(e7_raw_path, index=False)
    e7_common.to_csv(e7_common_path, index=False)
    e7_calls = pd.DataFrame(
        [{"compound_id": compound, "feature_id": "f1", "called": True, "raw_HR_point": 2.0, "common_RHR_mean": 1.0} for compound in e7_ids]
        + [{"compound_id": compound, "feature_id": "f2", "called": False, "raw_HR_point": np.nan, "common_RHR_mean": np.nan} for compound in e7_ids]
    )
    primary = root / "e7_primary.csv"
    sensitivity = root / "e7_sensitivity.csv"
    e7_calls.to_csv(primary, index=False)
    e7_calls.to_csv(sensitivity, index=False)
    accounting = root / "e7_accounting.csv"
    pd.DataFrame({"compound_id": [*e7_ids, "DEHYDRONORKETAMINE", "HNK_2R_6S"], "reference_only_reason": ["" for _ in e7_ids] + ["NO PROFILE", "NO PROFILE"]}).to_csv(accounting, index=False)
    return {
        "family_raw_matrix": family_raw_path,
        "family_common_matrix": family_common_path,
        "family_calls_001": calls001,
        "family_calls_0001": calls0001,
        "e7_raw_matrix": e7_raw_path,
        "e7_common_matrix": e7_common_path,
        "e7_primary_calls": primary,
        "e7_sensitivity_calls": sensitivity,
        "e7_identity_accounting": accounting,
    }


def test_family_profile_call_loading_and_extension(tmp_path: Path) -> None:
    paths = _family_fixture(tmp_path / "inputs")
    contract = _small_contract()
    family_profiles = load_family_profiles(paths, contract)
    assert len(family_profiles) == 12 and set(family_profiles["drug"]) == set(FAMILY_LABELS.values())
    family_calls = load_family_calls(paths, "001")
    assert len(family_calls) == 4 and family_calls["common_rhr"].eq(0.5).all()
    assert len(family_roster()) == 5
    assert strict_contract_from_profiles(family_profiles)["feature_id"].tolist() == ["f1", "f2", "f3"]

    e7_profiles = load_e7_profiles(paths, contract)
    assert len(e7_profiles) == 15 and set(e7_profiles["drug"]) == set(E7_LABELS.values())
    assert len(load_e7_call_rows(paths, "001")) == 5
    existing = {}
    for alpha in ("001", "0001"):
        existing[f"call_binary_alpha{alpha}"] = pd.DataFrame([[1.0, 0.0, np.nan]], index=["Ketamine, pooled parent"], columns=contract["feature_id"])
        existing[f"call_score_alpha{alpha}"] = pd.DataFrame([[1.0, 0.0, np.nan]], index=["Ketamine, pooled parent"], columns=contract["feature_id"])
    extended = extend_call_matrices(existing, e7_profiles, paths, contract)
    assert extended["call_binary_alpha001"].index.tolist() == ["Ketamine, pooled parent", *E7_LABELS.values()]
    assert extended["call_binary_alpha001"].loc[E7_LABELS["HNK_2R_6R"], "f1"] == 1.0
    assert np.isnan(extended["call_binary_alpha001"].loc[E7_LABELS["HNK_2R_6R"], "f2"])


def test_family_availability_and_forensic_audits_keep_identities_separate(tmp_path: Path) -> None:
    paths = _family_fixture(tmp_path / "inputs")
    contract = _small_contract()
    family_profiles = load_family_profiles(paths, contract)
    e7_profiles = load_e7_profiles(paths, contract)
    pooled = contract.copy()
    pooled["drug"] = "Ketamine, pooled parent"
    pooled["raw_hr"] = [1.0, 2.0, 3.0]
    pooled["common_rhr"] = [0.5, 1.0, 1.5]
    profiles = pd.concat([pooled, family_profiles, e7_profiles], ignore_index=True)
    call_index = FINAL_FAMILY_ORDER
    calls = {f"call_binary_alpha{alpha}": pd.DataFrame(1.0, index=call_index, columns=contract["feature_id"]) for alpha in ("001", "0001")}
    source_run = tmp_path / "source_run"
    query_file = source_run / "01_QUERY_AUTHORITY" / "POOLED_PARENT_STRICT18_COMMON_SCALE_PROJECTION.csv"
    query_file.parent.mkdir(parents=True)
    query_file.write_text("synthetic query\n", encoding="utf-8")
    availability = availability_audit(paths, source_run, profiles, calls)
    assert len(availability) == 12
    assert availability["compound_id"].nunique() == 12
    assert availability.set_index("compound_id").loc["DEHYDRONORKETAMINE", "numerical_status"] == "STATUS_ONLY"

    selection = paths["family_raw_matrix"].parents[2] / "02_TARGET_SELECTION" / "PRINCIPAL_U1_SELECTED_TARGET_ESTIMATES.csv"
    selection.parent.mkdir(parents=True)
    selected_rows = []
    for compound in ["esketamine", "arketamine", "hydroxyketamine_unspecified_isomer_aggregate"]:
        selected_rows.extend([{"canonical_compound_id": compound, "canonical_target_id": "T1", "activity_strength_score": 1.0}, {"canonical_compound_id": compound, "canonical_target_id": "T2", "activity_strength_score": 2.0}])
    pd.DataFrame(selected_rows).to_csv(selection, index=False)
    audit, summary = forensic_audit(paths, contract)
    assert len(audit) == 15
    assert set(audit["representation"]) == {"SELECTED_TARGET_ACTIVITY_STRENGTH", "RAW_HR_STRICT18", "COMMON_RHR_STRICT18", "FINGERPRINT_ALPHA_001", "FINGERPRINT_ALPHA_0001"}
    assert len(summary["pair_summaries"]) == 3
    assert audit["conclusion"].str.contains("NOT_ALIAS_OR_COPY_BUG").all()
