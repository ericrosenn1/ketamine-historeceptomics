"""Exercise export continuity, consumer corruption failures, and missingness.

Inputs are approved public call derivatives or invented fixtures. Tests never
load restricted inputs, recompute GESD, or write accepted scientific outputs.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cardozo_ketamine_hr.integration import APPROVED_SOURCES, CompatibilityError, canonical_json, digest, export_approved, validate_bundle


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "integrations/fixtures/synthetic-v1"


def mutable_bundle(tmp_path):
    """Copy the approved synthetic fixture for adversarial consumer tests."""

    destination = tmp_path / "bundle"
    shutil.copytree(FIXTURE, destination)
    manifest, records = validate_bundle(destination)
    return destination, manifest, records


def rewrite(directory, manifest, records):
    """Update integrity metadata so semantic failures are tested independently."""

    content = canonical_json(records)
    manifest["files"][0].update(sha256=digest(content), bytes=len(content), record_count=len(records))
    (directory / "records.json").write_bytes(content)
    (directory / "manifest.json").write_bytes(canonical_json(manifest))


def test_approved_export_determinism_and_exact_source_values(tmp_path):
    """Two exports preserve all 97 accepted call rows with identical bytes."""

    first, second = tmp_path / "first", tmp_path / "second"
    export_approved(ROOT, first)
    export_approved(ROOT, second)
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {p.name: p.read_bytes() for p in second.iterdir()}
    manifest, records = validate_bundle(first)
    assert manifest["scope"]["coverage"] == "positive_calls_only"
    assert len(records) == 97
    assert {row["profile_id"] for row in records} == {"POOLED_PARENT_KETAMINE"}
    for relative, (alpha, count) in APPROVED_SOURCES.items():
        with (ROOT / relative).open(encoding="utf-8", newline="") as handle:
            sources = list(csv.DictReader(handle))
        selected = [row for row in records if row["gesd_alpha"] == alpha]
        assert len(selected) == count
        for record, source in zip(selected, sources, strict=True):
            assert record["hr_score"] == float(source["HR_score"])
            assert record["target_id"] == source["canonical_target_id"]
            assert record["tissue_id"] == source["tissue_id"]
            assert record["fingerprint_member"] is True
    assert "source_HR_file" not in (first / "records.json").read_text()
    with pytest.raises(CompatibilityError, match="not empty"):
        export_approved(ROOT, first)


def test_synthetic_states_and_consumer_pins():
    """Zero, tested non-call, untested, and unsupported remain distinct."""

    manifest, records = validate_bundle(FIXTURE, expected_namespace="SYNTHETIC_INTEGRATION_V1", expected_dataset="SYNTHETIC_EXPRESSION_V1")
    assert manifest["synthetic"] is True
    assert [(r["hr_score"], r["fingerprint_member"], r["support_status"]) for r in records] == [(12.0, True, "supported"), (0.0, False, "supported"), (2.0, None, "untested"), (None, None, "unsupported")]
    validate_bundle(FIXTURE, accepted_identities=manifest["identities"])
    for kwargs in ({"expected_dataset": "unknown"}, {"expected_namespace": "unknown"}, {"accepted_identities": {}}):
        with pytest.raises(CompatibilityError, match="Unsupported"):
            validate_bundle(FIXTURE, **kwargs)


@pytest.mark.parametrize("mutation,diagnostic", [
    ("mandatory", "required property"), ("version", "1.0.0"),
    ("unknown_target", "unsupported identity"), ("profile_alias", "source_profile_id"),
    ("duplicate_record", "duplicate profile"), ("membership", "not of type"),
    ("unsupported_zero", "never zero-fill"), ("untested_false", "untested coordinates"),
    ("supported_null", "supported coordinates"), ("source_row", "source_artifact/source_row"),
    ("path_traversal", "Unsafe artifact path"), ("duplicate_identity", "duplicate ID"),
    ("alpha", "outside manifest scope"), ("call_only", "positive_calls_only"),
    ("huge_number", "HR must be finite"),
])
def test_actionable_incompatibilities(tmp_path, mutation, diagnostic):
    """Malformed or incompatible records fail after their bytes pass integrity."""

    directory, manifest, records = mutable_bundle(tmp_path)
    if mutation == "mandatory": del records[0]["target_id"]
    elif mutation == "version": manifest["schema_version"] = "2.0.0"
    elif mutation == "unknown_target": records[0]["target_id"] = "UNMAPPED"
    elif mutation == "profile_alias": records[0]["source_profile_id"] = "ketamine"
    elif mutation == "duplicate_record": records.append(copy.deepcopy(records[0]))
    elif mutation == "membership": records[0]["fingerprint_member"] = 1
    elif mutation == "unsupported_zero": records[3]["hr_score"] = 0
    elif mutation == "untested_false": records[2]["fingerprint_member"] = False
    elif mutation == "supported_null": records[0]["hr_score"] = None
    elif mutation == "source_row": records[0]["source_row"] = 999
    elif mutation == "path_traversal": manifest["source_artifacts"][0]["path"] = "../restricted.csv"
    elif mutation == "duplicate_identity": manifest["identities"]["profiles"].append(copy.deepcopy(manifest["identities"]["profiles"][0]))
    elif mutation == "alpha": records[0]["gesd_alpha"] = 0.0001
    elif mutation == "call_only": manifest["scope"]["coverage"] = "positive_calls_only"
    elif mutation == "huge_number": records[0]["hr_score"] = 10 ** 1000
    rewrite(directory, manifest, records)
    with pytest.raises(CompatibilityError, match=diagnostic):
        validate_bundle(directory)


def test_integrity_and_json_ambiguity_failures(tmp_path):
    """Corruption, duplicate keys and nonfinite JSON never silently load."""

    directory, manifest, records = mutable_bundle(tmp_path)
    (directory / "records.json").write_bytes(b"[]")
    with pytest.raises(CompatibilityError, match="integrity"):
        validate_bundle(directory)
    rewrite(directory, manifest, records)
    text = (directory / "manifest.json").read_text()
    (directory / "manifest.json").write_text(text.replace('"synthetic": true', '"synthetic": false, "synthetic": true'))
    with pytest.raises(CompatibilityError, match="Duplicate JSON key"):
        validate_bundle(directory)
    rewrite(directory, manifest, records)
    (directory / "manifest.json").write_text(text.replace('"synthetic": true', '"synthetic": NaN'))
    with pytest.raises(CompatibilityError, match="Nonfinite"):
        validate_bundle(directory)


def test_cli_nonzero_failure_and_example(tmp_path):
    """Shell consumers receive nonzero failure, and the documented reader works."""

    failed = subprocess.run([sys.executable, "-m", "cardozo_ketamine_hr.integration", "validate", str(tmp_path / "absent")], capture_output=True, text=True)
    assert failed.returncode == 2
    assert "Compatibility FAIL" in failed.stderr
    example = subprocess.run([sys.executable, str(ROOT / "integrations/read_example.py"), str(FIXTURE)], capture_output=True, text=True, check=True)
    assert "Explicit calls=1, tested non-calls=1, unknown=2" in example.stdout


def test_synthetic_fixture_reproducible(tmp_path):
    """The documented generator reproduces both checked synthetic bundle files."""

    output = tmp_path / "synthetic"
    subprocess.run([sys.executable, str(ROOT / "integrations/generate_synthetic.py"), "--output", str(output)], check=True, capture_output=True)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == {p.name: p.read_bytes() for p in FIXTURE.iterdir()}


def test_changed_approved_result_refused(tmp_path, monkeypatch):
    """A changed public result cannot pass the adapter publication gate."""

    from cardozo_ketamine_hr import integration

    for relative in ["PUBLIC_RELEASE_FILE_DECISIONS.tsv", "configs/tissues_full77.yaml", *APPROVED_SOURCES]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    source = tmp_path / next(iter(APPROVED_SOURCES))
    source.write_bytes(source.read_bytes() + b"\n")
    monkeypatch.setattr(integration, "_git", lambda root, *args: str(tmp_path))
    with pytest.raises(CompatibilityError, match="KEEP/checksum mismatch"):
        export_approved(tmp_path, tmp_path / "export")


def test_export_cannot_write_protected_authority_tree():
    """Even a new directory cannot add files beneath protected references."""

    with pytest.raises(CompatibilityError, match="protected scientific authority"):
        export_approved(ROOT, ROOT / "results/reference/not-an-export")
