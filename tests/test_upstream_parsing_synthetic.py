# SPDX-License-Identifier: MIT
"""Test recovered upstream parsers and selection rules with synthetic source records."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cardozo_ketamine_hr.upstream import cleanup_pooled_parent_ketamine_activity_v2 as cleanup
from cardozo_ketamine_hr.upstream import forensic_finalize_pooled_parent_ketamine_activity_v3 as forensic


def test_cleanup_scalar_unit_relation_and_species_normalization(tmp_path: Path) -> None:
    assert cleanup.s(None) == "" and cleanup.s(np.nan) == ""
    assert cleanup.upper(" ketamine ") == "KETAMINE"
    assert cleanup.fnum("2.5") == 2.5 and math.isnan(cleanup.fnum("bad"))
    assert cleanup.inum("2.6") == 3 and cleanup.inum(np.inf) is None
    source = tmp_path / "source.txt"
    source.write_text("source bytes", encoding="utf-8")
    assert len(cleanup.sha256(source)) == 64
    assert cleanup.uniq_join(["a", "", "a", "b", np.nan]) == "a | b"
    assert cleanup.first_nonblank(["NA", "unknown", " value "]) == "value"
    assert cleanup.split_ids("A | B|| C") == ["A", "B", "C"]
    assert cleanup.normalize_unit("μMolar") == "UM"
    assert cleanup.pactivity_from_value(10, "nM") == pytest.approx(8.0)
    assert math.isnan(cleanup.pactivity_from_value(0, "nM"))
    assert math.isnan(cleanup.pactivity_from_value(1, "unsupported"))
    assert [cleanup.relation_class(value) for value in ["=", ">", "<=", "bounded", "?"]] == ["EXACT", "GT_BOUND", "LT_BOUND", "BOUNDED_DIRECTION_UNKNOWN", "UNKNOWN"]
    assert cleanup.classify_species("", 9606) == ("Homo sapiens", 9606, "HUMAN")
    assert cleanup.classify_species("mouse", None)[2] == "MAMMALIAN_NONHUMAN"
    assert cleanup.classify_species("zebrafish", None)[2] == "NON_MAMMALIAN"
    assert cleanup.classify_species("rat tissue", None)[2] == "MAMMALIAN_NONHUMAN"
    assert cleanup.classify_species("unknown creature", None)[2] == "UNRESOLVED"
    assert cleanup.norm_target_text("5-HT2A receptor") == "5HT2ARECEPTOR"


def test_identity_audit_master_and_relation_recovery(tmp_path: Path) -> None:
    audit_path = tmp_path / "12_QA_AUDITS_AND_PROVENANCE" / "Audit_Reports" / "Racemic_Ketamine_Identity_Coverage_Audit_20260805_165431_492" / "02_SOURCE_RECORD_INVENTORY" / "KETAMINE_SOURCE_ASSERTION_MASTER.parquet"
    audit_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "source_assertion_id": ["A1", "A2", "A3"],
            "duplicate_group_id": ["D1", "D1", "D2"],
            "organism": ["human", "Homo sapiens", "mouse"],
            "relation_operator": [">", ">=", "="],
        }
    ).to_parquet(audit_path, index=False)
    messages: list[str] = []
    frame, rowmap, duplicates = cleanup.load_identity_audit_master(tmp_path, messages.append)
    assert len(frame) == 3 and set(rowmap) == {"A1", "A2", "A3"}
    assert duplicates["D1"][2] == "HUMAN"
    species = cleanup.resolve_from_audit_ids({"source_assertion_id": "A1|A2"}, rowmap)
    assert species[:3] == ("Homo sapiens", 9606, "HUMAN")
    assert cleanup.resolve_from_audit_ids({"source_assertion_id": "A1|A3"}, rowmap)[2] == "UNRESOLVED"
    assert cleanup.recover_relation_from_audit({"activity_relation": "="}, rowmap) == ("=", "POOLED_TABLE_EXACT")
    recovered = cleanup.recover_relation_from_audit({"activity_relation": "BOUNDED", "source_assertion_id": "A1|A2"}, rowmap)
    assert cleanup.relation_class(recovered[0]) == "GT_BOUND"
    conflicting = cleanup.recover_relation_from_audit({"activity_relation": "BOUNDED", "source_assertion_id": "A1|A3"}, rowmap)
    assert conflicting == ("BOUNDED", "POOLED_TABLE_DIRECTION_UNKNOWN")
    missing, rowmap, duplicates = cleanup.load_identity_audit_master(tmp_path / "missing", messages.append)
    assert missing is None and rowmap == {} and duplicates == {}


def _pdsp_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Ki ID": [1, 2, 3, 3],
            "Species": ["Human", "Rat", "Human", "Rat"],
            "Receptor": ["GRIN1", "HTR2A", "DRD2", "DRD2"],
            "Test Ligands": ["ketamine", "ketamine", "ketamine", "ketamine"],
            "Ki Value": [10.0, 20.0, 30.0, 30.0],
            "Relation": ["=", ">", "=", "="],
            "Units": ["nM", "nM", "nM", "nM"],
        }
    )


def test_cleanup_pdsp_discovery_loading_and_id_resolution(tmp_path: Path) -> None:
    workbook = tmp_path / "02_HR_SCORES" / "KiDatabase_synthetic.xlsx"
    workbook.parent.mkdir(parents=True)
    _pdsp_frame().to_excel(workbook, index=False)
    found = cleanup.find_pdsp_workbooks(tmp_path)
    assert found == [workbook]
    logs: list[str] = []
    audit, idmap, targetmap = cleanup.load_pdsp_raw(tmp_path, logs.append)
    assert audit["rows"] == 4
    assert set(idmap) == {"1", "2"}
    assert targetmap[cleanup.norm_target_text("GRIN1")]["species_class"] == "HUMAN"
    assert cleanup.detect_col(["Ki ID", "Species"], ["id", "ki id"]) == "Ki ID"
    assert cleanup.detect_col(["x"], ["missing"]) is None
    assert cleanup.pdsp_id_from_assay("PDSP Ki: 123.0") == "123"
    assert cleanup.pdsp_id_from_assay("other") is None
    assert cleanup.load_pdsp_raw(tmp_path / "empty", logs.append) == (None, {}, {})


def test_working_activity_lanes_and_exact_target_selection() -> None:
    supplied = cleanup.working_pactivity({"pActivity_if_available": 8.1, "standardized_activity_value": 1e-8, "standardized_activity_unit": "M"})
    assert supplied[:3] == (8.1, 1e-8, "SUPPLIED_PACTIVITY_AND_STANDARDIZED_M")
    recomputed = cleanup.working_pactivity({"standardized_activity_value": 10, "standardized_activity_unit": "nM", "activity_value_original": 10, "activity_unit_original": "nM"})
    assert recomputed[0] == pytest.approx(8.0)
    p_only = cleanup.working_pactivity({"pActivity_if_available": 7.0})
    assert p_only[1] == pytest.approx(1e-7)
    invalid = cleanup.working_pactivity({"standardized_activity_value": 0, "standardized_activity_unit": "M"})
    assert invalid[2:] == ("NO_NUMERICAL_ACTIVITY", True)
    assert cleanup.activity_lane({"activity_type": "assigned", "pActivity_working": 5}) == "ASSIGNED_SCENARIO"
    assert cleanup.activity_lane({"activity_origin": "modeled", "pActivity_working": 5}) == "MODELED_OR_IMPUTED"
    assert cleanup.activity_lane({"activity_origin": "measured", "pActivity_working": 5}) == "MEASURED_NUMERICAL"
    assert cleanup.activity_lane({"activity_origin": "measured", "pActivity_working": np.nan}) == "MEASURED_NONNUMERICAL"
    assert cleanup.activity_lane({}) == "OTHER"
    assert cleanup.is_exact_target({"canonical_target_id": "GRIN1", "activity_table_status": "MAPPED_EXACT_TARGET", "target_grain": "EXACT_SINGLE_PROTEIN"})
    assert not cleanup.is_exact_target({"canonical_target_id": "", "activity_table_status": "MAPPED_EXACT_TARGET", "target_grain": "EXACT"})
    assert not cleanup.is_exact_target({"canonical_target_id": "NMDA", "activity_table_status": "UNRESOLVED", "target_grain": "GENERIC"})

    exact = pd.DataFrame(
        {
            "activity_type": ["BINDING_KI", "BINDING_KI", "INHIBITION_IC50"],
            "pActivity_working": [7.0, 8.0, 10.0],
            "source_assertion_id": ["B", "A", "C"],
        }
    )
    assert cleanup.choose_exact(exact)["source_assertion_id"] == "A"
    assert cleanup.choose_exact(exact.assign(activity_type="unknown")) is None
    assert cleanup.choose_exact(exact.assign(pActivity_working=np.nan)) is None


@pytest.mark.parametrize(
    ("relations", "molar", "expected_reason", "expected_id"),
    [
        (["GT_BOUND", "GT_BOUND"], [1e-9, 2e-9], "GT_TIGHTEST_LOWER_CONCENTRATION_BOUND", "B"),
        (["LT_BOUND", "LT_BOUND"], [2e-9, 1e-9], "LT_TIGHTEST_UPPER_CONCENTRATION_BOUND", "B"),
        (["GT_BOUND", "LT_BOUND"], [1e-9, 2e-9], "MIXED_BOUND_DIRECTIONS_REVIEW_REQUIRED", None),
        (["BOUNDED_DIRECTION_UNKNOWN", "BOUNDED_DIRECTION_UNKNOWN"], [1e-9, 2e-9], "UNKNOWN_DIRECTION_PROVISIONAL_STRONGEST_BOUNDARY", "A"),
    ],
)
def test_bounded_activity_selection_preserves_direction(relations: list[str], molar: list[float], expected_reason: str, expected_id: str | None) -> None:
    frame = pd.DataFrame(
        {
            "activity_type": ["BINDING_KI", "BINDING_KI"],
            "activity_value_M_working": molar,
            "pActivity_working": [9.0, 8.0],
            "source_assertion_id": ["A", "B"],
            "relation_class_clean": relations,
        }
    )
    selected, reason = cleanup.choose_bounded(frame)
    assert reason == expected_reason
    assert (None if selected is None else selected["source_assertion_id"]) == expected_id
    assert cleanup.choose_bounded(frame.assign(activity_type="unknown"))[1] == "NO_ELIGIBLE_BOUNDED_ENDPOINT"
    assert cleanup.choose_bounded(frame.assign(activity_value_M_working=0))[1] == "NO_NONZERO_NUMERICAL_BOUNDARY"


def test_forensic_scalar_relation_and_source_record_parsing(tmp_path: Path) -> None:
    assert forensic.s(None) == "" and forensic.up(" x ") == "X"
    assert forensic.fnum("1.5") == 1.5 and forensic.inum("2.6") == 3
    assert forensic.uniq_join(["a", "a", "b"]) == "a | b"
    assert forensic.norm("5-HT2A") == "5HT2A"
    assert forensic.parse_source_rows("1|2.0, bad; 3") == [1, 2, 3]
    assert forensic.detect_relation_in_text("value >= 10") == ">="
    assert forensic.detect_relation_in_text("value < 2") == "<"
    assert forensic.detect_relation_in_text("none") == ""
    assert forensic.parse_numeric_from_raw("~1,234.5 nM") == 1234.5
    assert math.isnan(forensic.parse_numeric_from_raw("missing"))
    assert forensic.find_col(["Ki ID", "Species"], ["id", "ki id"]) == "Ki ID"

    csv_path = tmp_path / "source.csv"
    pd.DataFrame({"target": ["A", "B", "C", "D"], "relation": ["=", ">", "<", ""]}).to_csv(csv_path, index=False)
    records = forensic.read_selected_csv_records(csv_path, [2], lambda _: None)
    assert set(records) == {1, 2, 3}
    assert forensic.read_selected_csv_records(csv_path, [], lambda _: None) == {}
    assert forensic.relation_from_source_record({"operator": ">="}) == (">=", "SOURCE_FIELD:operator")
    assert forensic.relation_from_source_record({"Ki value": "< 10 nM"}) == ("<", "SOURCE_VALUE_TEXT:Ki value")
    assert forensic.relation_from_source_record({}) == ("", "")
    assert forensic.record_match_score({"text": "PDSP GRIN1 10"}, "GRIN1", 10.0, "PDSP") == 11
    assert forensic.record_match_score({}, "GRIN1", 10.0, "PDSP") == -999


def test_forensic_pdsp_loading_matching_and_path_resolution(tmp_path: Path) -> None:
    workbook = tmp_path / "KiDatabase_synthetic.xlsx"
    frame = _pdsp_frame().iloc[:2].copy().astype(object)
    frame.loc[0, "Ki Value"] = ">= 10"
    frame.loc[0, "Relation"] = ">="
    frame.loc[1, "Relation"] = "<"
    frame.to_excel(workbook, index=False)
    loaded, audit = forensic.load_pdsp(workbook, lambda _: None)
    assert audit["rows"] == 2
    assert loaded.loc[0, "_explicit_relation_marker"] == ">="
    assert loaded.loc[1, "_explicit_relation_marker"] == "<"
    cleaned = pd.DataFrame({"source_database": ["PDSP"], "canonical_target_id": ["GRIN1"], "original_target_name": ["GRIN1"]})
    matches = forensic.raw_pdsp_target_matches(loaded, cleaned)
    assert len(matches["GRIN1"]) == 1

    malformed = tmp_path / "malformed.xlsx"
    pd.DataFrame({"Species": ["Human"]}).to_excel(malformed, index=False)
    with pytest.raises(RuntimeError, match="missing"):
        forensic.load_pdsp(malformed, lambda _: None)
    assert forensic.find_pdsp(tmp_path, workbook, lambda _: None) == workbook
    assert forensic.find_pdsp(tmp_path / "nothing", tmp_path / "missing.xlsx", lambda _: None) is None

    direct = tmp_path / "direct.csv"
    direct.write_text("x\n", encoding="utf-8")
    assert forensic.resolve_legacy_source_path(str(direct), tmp_path) == direct
    fallback = tmp_path / "98_DEPRECATED" / "nested" / "legacy.csv"
    fallback.parent.mkdir(parents=True)
    fallback.write_text("x\n", encoding="utf-8")
    assert forensic.resolve_legacy_source_path("C:\\old\\legacy.csv", tmp_path) == fallback
    assert forensic.resolve_legacy_source_path("C:\\old\\absent.csv", tmp_path) is None
