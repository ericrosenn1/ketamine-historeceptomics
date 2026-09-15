# SPDX-License-Identifier: MIT
"""Exercise deterministic public utility, QA, tabulation, and packaging contracts."""

from __future__ import annotations

import json
import math
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader, PdfWriter

from cardozo_ketamine_hr.coverage_diagnostics import distance_confounding, profile_coverage
from cardozo_ketamine_hr.nearest_reference import class_nearest, nearest_summary, orient_query_pairs
from cardozo_ketamine_hr.packaging import (
    code_manifest,
    combine_pdfs,
    compact_handoff_zip,
    copy_paper_item,
    output_manifest,
    summary_workbook,
)
from cardozo_ketamine_hr.qa import QARecorder, files_nonempty, matrix_symmetric, pairwise_contract
from cardozo_ketamine_hr.residual_analysis import recurrence
from cardozo_ketamine_hr.tables import TableRecorder, call_detail, pairwise_table_bundle, target_summary, tissue_summary
from cardozo_ketamine_hr.utilities import (
    copy_small_file,
    finite,
    json_default,
    read_table,
    relative_posix,
    safe_float,
    sha256_file,
    slug,
    timed,
    write_json,
    write_table,
)


def _contract() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "feature_id": ["f1", "f2", "f3"],
            "target": ["T1", "T1", "T2"],
            "tissue": ["brain", "cortex", "brain"],
        }
    )


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "feature_id": ["f1", "f2", "f3"],
            "target": ["T1", "T1", "T2"],
            "tissue": ["brain", "cortex", "brain"],
            "value_a": [3.0, 1.0, -1.0],
            "value_b": [1.0, 2.0, -1.5],
            "signed_difference_a_minus_b": [2.0, -1.0, 0.5],
            "absolute_difference": [2.0, 1.0, 0.5],
        }
    )


def test_table_io_hash_json_and_scalar_helpers(tmp_path: Path) -> None:
    frame = pd.DataFrame({"x": [1, 2], "label": ["a", "b"]})
    outputs = write_table(frame, tmp_path / "nested" / "table", parquet=True)
    assert [path.suffix for path in outputs] == [".csv", ".parquet"]
    pd.testing.assert_frame_equal(read_table(outputs[0]), frame)
    pd.testing.assert_frame_equal(read_table(outputs[1]), frame)
    assert len(sha256_file(outputs[0])) == 64

    payload_path = tmp_path / "payload.json"
    write_json(
        payload_path,
        {"path": tmp_path, "integer": np.int64(2), "float": np.float64(1.5), "missing": np.float64(np.inf), "flag": np.bool_(True), "time": pd.Timestamp("2026-01-01")},
    )
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["integer"] == 2 and math.isinf(payload["missing"]) and payload["flag"] is True
    assert payload["time"].startswith("2026-01-01")
    assert json_default(np.float64(np.inf)) is None
    with pytest.raises(TypeError, match="object"):
        json_default(object())
    assert slug("  A / beta  ") == "A_beta"
    assert slug("") == "item"
    values = finite(pd.Series(["1", "bad", np.inf, -np.inf]))
    assert values.notna().tolist() == [True, False, False, False]
    assert safe_float("2.5") == 2.5
    assert math.isnan(safe_float("bad")) and math.isnan(safe_float(np.inf))


def test_timing_copy_and_relative_paths(tmp_path: Path) -> None:
    with timed() as timing:
        time.sleep(0.001)
    assert timing["runtime_seconds"] > 0
    with pytest.raises(RuntimeError):
        with timed() as exceptional:
            raise RuntimeError("expected")
    assert exceptional["runtime_seconds"] >= 0
    source = tmp_path / "source.bin"
    source.write_bytes(b"preserved bytes")
    destination = tmp_path / "out" / "copy.bin"
    copy_small_file(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert relative_posix(destination, tmp_path) == "out/copy.bin"
    with pytest.raises(ValueError):
        relative_posix(tmp_path.parent / "outside", tmp_path)


def test_profile_coverage_and_confounding_preserve_missingness() -> None:
    raw = pd.DataFrame([[1.0, np.nan, 2.0], [np.nan, np.nan, 3.0]], index=["A", "B"], columns=["f1", "f2", "f3"])
    result = profile_coverage(raw, _contract())
    assert result.set_index("compound").loc["A", "supported_feature_count"] == 2
    assert result.set_index("compound").loc["A", "supported_target_count"] == 2
    assert result.set_index("compound").loc["B", "feature_coverage_fraction"] == pytest.approx(1 / 3)
    pairs = pd.DataFrame({"drug_a": ["Q"], "comparator": ["A"], "matched_features": [2], "rms_common_rhr": [0.5], "unused": [9]})
    selected = distance_confounding(pairs)
    assert selected.columns.tolist() == ["comparator", "matched_features", "rms_common_rhr"]
    selected.loc[0, "matched_features"] = 99
    assert pairs.loc[0, "matched_features"] == 2


def test_nearest_reference_ranking_and_unavailable_metrics() -> None:
    pairwise = pd.DataFrame(
        {
            "drug_a": ["Q", "A", "Q"],
            "drug_b": ["A", "Q", "C"],
            "rms_common_rhr": [0.2, 0.5, np.nan],
            "cosine_common_rhr": [0.7, 0.9, np.nan],
            "spearman_common_rhr": [0.6, 0.8, np.nan],
            "alpha001_call_jaccard": [0.4, 0.5, np.nan],
            "support_jaccard": [0.8, 0.9, np.nan],
        }
    )
    oriented = orient_query_pairs(pairwise, "Q", {"A"})
    assert oriented["comparator"].tolist() == ["A", "A"]
    summary = nearest_summary(pairwise, "Q", {"A", "C"}).set_index("metric")
    assert summary.loc["RMS", "nearest_comparator"] == "A"
    assert summary.loc["COSINE", "nearest_value"] == pytest.approx(0.9)
    missing = nearest_summary(pairwise.assign(rms_common_rhr=np.nan), "Q", {"C"})
    assert set(missing["status"]) == {"NOT_ESTIMABLE"}

    classes = pd.DataFrame({"class_id": ["x", "x", "y"], "class_label": ["X", "X", "Y"], "drug": ["A", "C", "Z"]})
    by_class = class_nearest(pairwise, "Q", classes).set_index("class_id")
    assert by_class.loc["x", "status"] == "PASS"
    assert by_class.loc["y", "status"] == "NOT_ESTIMABLE"


def test_qa_recorder_contracts_and_file_checks(tmp_path: Path) -> None:
    recorder = QARecorder()
    assert recorder.overall() == "FAIL"
    assert recorder.check("ok", True, 1, 1)
    recorder.check("limitation", True, "documented", "documented", severity="LIMITATION")
    assert recorder.overall() == "PASS_WITH_DOCUMENTED_LIMITATIONS"
    with pytest.raises(RuntimeError, match="fatal"):
        recorder.check("fatal", False, 0, 1)
    assert recorder.overall() == "FAIL"

    pairwise = pd.DataFrame(
        {
            "drug_a": ["A"], "drug_b": ["B"],
            "cosine_common_rhr": [0.2], "pearson_common_rhr": [-0.1], "spearman_common_rhr": [1.0],
            "alpha001_call_jaccard": [0.5],
        }
    )
    valid = QARecorder()
    pairwise_contract(pairwise, 1, valid, "SYNTHETIC")
    assert valid.overall() == "PASS" and len(valid.frame()) == 7
    symmetric, difference = matrix_symmetric(pd.DataFrame([[0.0, 1.0], [1.0, 0.0]]))
    assert symmetric and difference == 0.0
    symmetric, difference = matrix_symmetric(pd.DataFrame([[np.nan, np.nan], [np.nan, np.nan]]))
    assert symmetric and difference == 0.0
    assert matrix_symmetric(pd.DataFrame([[0.0, 1.0], [2.0, 0.0]]))[0] is False
    good = tmp_path / "good.txt"
    good.write_text("x" * 10, encoding="utf-8")
    assert files_nonempty([good], minimum_bytes=10) == (True, 0)
    assert files_nonempty([good, tmp_path / "missing"], minimum_bytes=11) == (False, 2)


def test_table_summaries_call_partitions_and_bundle() -> None:
    detail = _detail()
    targets = target_summary(detail).set_index("target")
    tissues = tissue_summary(detail).set_index("tissue")
    assert targets.loc["T1", "matched_feature_count"] == 2
    assert targets.loc["T1", "mean_difference"] == pytest.approx(0.5)
    assert tissues.loc["brain", "max_absolute_difference"] == 2.0
    assert target_summary(pd.DataFrame()).empty and tissue_summary(pd.DataFrame()).empty
    binary = pd.DataFrame([[1.0, 1.0, 0.0], [0.0, 1.0, 1.0]], index=["Q", "A"], columns=["f1", "f2", "f3"])
    calls = call_detail(binary, "Q", "A", _contract())
    assert calls["query_only"]["feature_id"].tolist() == ["f1"]
    assert calls["shared"]["feature_id"].tolist() == ["f2"]
    assert calls["comparator_only"]["feature_id"].tolist() == ["f3"]
    empty_calls = call_detail(pd.DataFrame([[0.0], [0.0]], index=["Q", "A"], columns=["f1"]), "Q", "A", _contract())
    assert all(frame.empty for frame in empty_calls.values())
    metrics = pd.Series({"matched_features": 3, "support_jaccard": 0.75, "ignored": 9})
    bundle = pairwise_table_bundle(detail, binary, "Q", "A", _contract(), metrics)
    assert set(bundle) == {
        "TOP_SHARED_TARGETS", "TOP_KETAMINE_HIGHER_TARGETS", "TOP_DRUG_HIGHER_TARGETS",
        "TOP_ABSOLUTE_RESIDUAL_TARGETS", "TOP_SHARED_TARGET_TISSUE_COORDINATES",
        "TOP_KETAMINE_ONLY_FINGERPRINT_CALLS", "TOP_DRUG_ONLY_FINGERPRINT_CALLS",
        "SHARED_FINGERPRINT_CALLS", "TOP_DIFFERING_TISSUES", "COVERAGE_AND_SUPPORT_SUMMARY",
    }
    assert bundle["COVERAGE_AND_SUPPORT_SUMMARY"].columns.tolist() == ["matched_features", "support_jaccard"]


def test_table_recorder_and_residual_orientation(tmp_path: Path) -> None:
    recorder = TableRecorder(tmp_path)
    path = recorder.write(pd.DataFrame({"value": ["long validated value", "second validated value"]}), tmp_path / "tables" / "values.csv", "T1", "analysis", "title", "Q", "A", "common")
    assert path.exists()
    assert recorder.frame().iloc[0].to_dict()["QA_status"] == "PASS"

    forward = _detail()
    reverse = _detail().copy()
    targets, tissues = recurrence({("Q", "A"): forward, ("B", "Q"): reverse, ("X", "Y"): forward}, "Q")
    assert set(targets["target"]) == {"T1", "T2"}
    assert set(tissues["tissue"]) == {"brain", "cortex"}
    assert targets.set_index("target").loc["T1", "comparator_count"] == 2
    assert targets.set_index("target").loc["T1", "mean_difference"] == pytest.approx(0.0)
    empty_target, empty_tissue = recurrence({}, "Q")
    assert empty_target.empty and empty_tissue.empty


def test_packaging_manifests_workbook_pdf_zip_and_copy(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    code_root = tmp_path / "code"
    run_root.mkdir()
    (run_root / "result.txt").write_text("validated result", encoding="utf-8")
    (run_root / "ignore.txt").write_text("ignored", encoding="utf-8")
    (code_root / "pkg").mkdir(parents=True)
    (code_root / "pkg" / "module.py").write_text("value = 1\n", encoding="utf-8")
    (code_root / "pkg" / "cached.pyc").write_bytes(b"cache")
    manifest = output_manifest(run_root, {"ignore.txt"})
    assert manifest["relative_path"].tolist() == ["result.txt"]
    assert code_manifest(code_root)["relative_path"].tolist() == ["pkg/module.py"]

    workbook = summary_workbook({"long/name": pd.DataFrame({"x": [1]})}, tmp_path / "summary.xlsx")
    assert pd.read_excel(workbook).loc[0, "x"] == 1
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    source_pdf = tmp_path / "one.pdf"
    with source_pdf.open("wb") as handle:
        writer.write(handle)
    combined, included = combine_pdfs([source_pdf, source_pdf, tmp_path / "missing.pdf"], tmp_path / "combined.pdf")
    assert combined is not None and len(included) == 1 and len(PdfReader(combined).pages) == 1
    assert combine_pdfs([tmp_path / "missing.pdf"], tmp_path / "none.pdf") == (None, [])

    external = tmp_path / "external.txt"
    external.write_text("support", encoding="utf-8")
    archive, zip_manifest = compact_handoff_zip(run_root, code_root, tmp_path / "handoff.zip", [run_root / "result.txt", external])
    with zipfile.ZipFile(archive) as handle:
        assert handle.testzip() is None
        assert set(handle.namelist()) == {"run/result.txt", "support/external.txt", "code/pkg/module.py"}
    assert len(zip_manifest) == 3
    copied = copy_paper_item(external, tmp_path / "paper")
    assert copied.read_text(encoding="utf-8") == "support"
