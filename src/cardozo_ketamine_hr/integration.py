"""Export approved public calls and validate independent consumer bundles.

Stage: file exchange after scientific acceptance; no HR or GESD calculation.
Inputs: approved public reference CSVs or a manifest/records JSON pair.
Outputs: deterministic JSON with exact identities and explicit missingness.
Side effects: export writes a new empty directory; validation is read-only.
Invariants: no excluded inputs, zero imputation, alias merging, or app changes.
Lane: public integration compatibility, not scientific or app acceptance.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime
from importlib.resources import files
from pathlib import Path, PurePosixPath

import yaml
from jsonschema import Draft7Validator


SCHEMA_VERSION = "1.0.0"
REPOSITORY = "https://github.com/ericrosenn1/ketamine-historeceptomics"
MISSINGNESS = "absent_rows_are_unknown;null_is_not_zero;noncalls_require_explicit_testing"
DATASET = "HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1"
NAMESPACE = "KETAMINE_FAMILY_FEATURE_CONTRACT_1.0.0"
APPROVED_SOURCES = {
    "results/reference/whole_body/KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p001.csv": (0.001, 59),
    "results/reference/whole_body/KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p0001.csv": (0.0001, 38),
}


class CompatibilityError(ValueError):
    """A bundle fails a structural, identity, or integrity contract."""


def canonical_json(value: object) -> bytes:
    """Encode stable UTF-8 JSON while rejecting nonfinite numbers."""

    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def digest(content: bytes) -> str:
    """Return the lowercase SHA-256 of exact file bytes."""

    return hashlib.sha256(content).hexdigest()


def _unique_json_pairs(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys instead of silently taking the last value."""

    result = {}
    for key, value in pairs:
        if key in result:
            raise CompatibilityError(f"Duplicate JSON key {key!r}; supply an unambiguous object")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    """Reject nonstandard NaN and infinity JSON tokens."""

    raise CompatibilityError(f"Nonfinite JSON value {value}; use null and explicit support status")


def _read_json(path: Path) -> object:
    """Read strict JSON without duplicate fields or nonfinite tokens."""

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_pairs, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompatibilityError(f"Cannot read {path.name}: {exc}") from exc


def _schema_validate(value: object, *, records: bool = False) -> None:
    """Validate the packaged Draft-7 schema without remote schema fetching."""

    schema = json.loads(files("cardozo_ketamine_hr").joinpath("integration-v1.schema.json").read_text(encoding="utf-8"))
    if records:
        schema = {"definitions": schema["definitions"], "$ref": "#/definitions/records"}
    errors = sorted(Draft7Validator(schema).iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        first = errors[0]
        location = ".".join(map(str, first.path)) or "root"
        raise CompatibilityError(f"{'records' if records else 'manifest'}.{location}: {first.message}")


def _safe_relative(value: str) -> None:
    """Require portable source paths without traversal or workstation details."""

    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or value in {"", "."}:
        raise CompatibilityError(f"Unsafe artifact path {value!r}; use a repository-relative POSIX path")


def _registry(entries: list[dict], name: str) -> dict[str, dict]:
    """Index exact IDs and reject duplicate or ambiguous source mappings."""

    ids = [entry["id"] for entry in entries]
    sources = [entry.get("source_id", entry.get("source_label")) for entry in entries]
    if len(set(ids)) != len(ids) or len(set(sources)) != len(sources):
        raise CompatibilityError(f"identities.{name}: duplicate ID or unsupported many-to-one source mapping")
    return {entry["id"]: entry for entry in entries}


def validate_bundle(directory: Path, *, expected_dataset: str | None = None, expected_namespace: str | None = None, accepted_identities: dict | None = None) -> tuple[dict, list[dict]]:
    """Validate schema, integrity, exact identities, missingness, and provenance.

    Parameters
    ----------
    directory
        Directory containing exactly manifest.json and records.json.
    expected_dataset, expected_namespace
        Optional consumer requirements; incompatible datasets fail explicitly.
    accepted_identities
        Optional externally pinned registry. Equality is exact; no aliases,
        case folding, or automatic profile merging is performed.

    Returns
    -------
    tuple[dict, list[dict]]
        Validated manifest and coordinate records for a downstream consumer.

    Notes
    -----
    Checksums detect corruption, not a rewritten manifest. Pin the producer
    commit and manifest digest independently for trusted production use.
    Compatibility does not establish scientific or application acceptance.
    """

    directory = Path(directory)
    if not directory.is_dir():
        raise CompatibilityError("Bundle directory is missing; supply an exported directory")
    if any(p.is_symlink() for p in directory.iterdir()):
        raise CompatibilityError("Bundle contains a symlink; supply regular files")
    if {p.name for p in directory.iterdir()} != {"manifest.json", "records.json"}:
        raise CompatibilityError("Bundle must contain exactly manifest.json and records.json; remove extra files")
    manifest = _read_json(directory / "manifest.json")
    _schema_validate(manifest)
    try:
        stamp = datetime.fromisoformat(manifest["generation"]["generated_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise CompatibilityError("generation.generated_at requires an ISO-8601 timestamp with timezone") from exc
    scope = manifest["scope"]
    identities = manifest["identities"]
    if expected_dataset is not None and scope["expression_dataset_ids"] != [expected_dataset]:
        raise CompatibilityError(f"Unsupported expression dataset; consumer requires {expected_dataset!r}")
    if expected_namespace is not None and identities["namespace"] != expected_namespace:
        raise CompatibilityError(f"Unsupported identity namespace; consumer requires {expected_namespace!r}")
    if accepted_identities is not None and identities != accepted_identities:
        raise CompatibilityError("Unsupported identity mapping; bundle differs from consumer-pinned identities")
    profiles = _registry(identities["profiles"], "profiles")
    targets = _registry(identities["targets"], "targets")
    tissues = _registry(identities["tissues"], "tissues")
    sources = {}
    for artifact in manifest["source_artifacts"]:
        _safe_relative(artifact["path"])
        if artifact["path"] in sources:
            raise CompatibilityError("source_artifacts: duplicate artifact path")
        sources[artifact["path"]] = artifact
    metadata = manifest["files"][0]
    path = directory / metadata["path"]
    if not path.is_file():
        raise CompatibilityError("records.json is not a regular file")
    content = path.read_bytes()
    if len(content) != metadata["bytes"] or digest(content) != metadata["sha256"]:
        raise CompatibilityError("records.json integrity failure: byte size or SHA-256 mismatch; obtain a fresh export")
    records = _read_json(path)
    _schema_validate(records, records=True)
    if len(records) != metadata["record_count"]:
        raise CompatibilityError("records.json record_count differs from manifest")
    seen = set()
    for index, record in enumerate(records, 1):
        prefix = f"record {index}"
        for field, registry in (("profile_id", profiles), ("target_id", targets), ("tissue_id", tissues)):
            if record[field] not in registry:
                raise CompatibilityError(f"{prefix}: unsupported identity mapping for {field}={record[field]!r}")
        if record["source_profile_id"] != profiles[record["profile_id"]]["source_id"]:
            raise CompatibilityError(f"{prefix}: source_profile_id does not exactly match declared profile identity")
        if record["expression_dataset_id"] not in scope["expression_dataset_ids"] or record["gesd_alpha"] not in scope["gesd_alphas"]:
            raise CompatibilityError(f"{prefix}: dataset or GESD alpha is outside manifest scope")
        source = sources.get(record["source_artifact"])
        if source is None or record["source_row"] > source["record_count"]:
            raise CompatibilityError(f"{prefix}: source_artifact/source_row is not declared in provenance")
        key = tuple(record[field] for field in ("profile_id", "target_id", "tissue_id", "expression_dataset_id", "gesd_alpha"))
        if key in seen:
            raise CompatibilityError(f"{prefix}: duplicate profile-target-tissue-dataset-alpha coordinate")
        seen.add(key)
        hr, member, status = record["hr_score"], record["fingerprint_member"], record["support_status"]
        try:
            finite = hr is None or (not isinstance(hr, bool) and math.isfinite(hr))
        except (OverflowError, TypeError):
            finite = False
        if not finite:
            raise CompatibilityError(f"{prefix}: HR must be finite or null")
        if status == "supported" and (hr is None or type(member) is not bool):
            raise CompatibilityError(f"{prefix}: supported coordinates require finite HR and explicit true/false membership")
        if status == "unsupported" and (hr is not None or member is not None):
            raise CompatibilityError(f"{prefix}: unsupported coordinates require null HR and null membership; never zero-fill")
        if status == "untested" and member is not None:
            raise CompatibilityError(f"{prefix}: untested coordinates require null membership")
        if scope["coverage"] == "positive_calls_only" and (status != "supported" or member is not True):
            raise CompatibilityError(f"{prefix}: positive_calls_only requires supported true calls")
    return manifest, records


def _git(root: Path, *arguments: str) -> str:
    """Read public Git metadata without changing index or history."""

    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True, encoding="utf-8").strip()


def _write_bundle(output: Path, manifest: dict, records: list[dict]) -> None:
    """Write a new deterministic bundle and validate its consumer-facing bytes."""

    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise CompatibilityError("Output exists and is not empty; choose a new directory to preserve existing work")
    content = canonical_json(records)
    manifest["files"] = [{"path": "records.json", "bytes": len(content), "sha256": digest(content), "record_count": len(records)}]
    _schema_validate(manifest)
    _schema_validate(records, records=True)
    output.mkdir(parents=True, exist_ok=True)
    (output / "records.json").write_bytes(content)
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    validate_bundle(output)


def export_approved(root: Path, output: Path) -> dict:
    """Adapt approved v0.1.1 whole-body positive-call CSVs without refits.

    KEEP decisions and SHA-256 values gate the two source files. HR text is
    parsed once as a JSON number, with original source rows retained. Excluded
    matrices and source-only development fields are never exported.
    """

    root = Path(root).resolve()
    destination = Path(output).resolve()
    if any(destination.is_relative_to(root / protected) for protected in ("results/reference", "data/frozen", "configs")):
        raise CompatibilityError("Output is inside a protected scientific authority tree; choose a separate directory")
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise CompatibilityError("--root must be the computational repository Git root")
    with (root / "PUBLIC_RELEASE_FILE_DECISIONS.tsv").open(encoding="utf-8", newline="") as handle:
        decisions = {row["public_repo_path"]: row for row in csv.DictReader(handle, delimiter="\t")}
    panel = yaml.safe_load((root / "configs/tissues_full77.yaml").read_text(encoding="utf-8"))
    if panel["expression_profile_id"] != DATASET or panel["feature_contract_version"] != NAMESPACE:
        raise CompatibilityError("Unsupported tissue/expression contract; a reviewed adapter update is required")
    tissue_registry = {row["tissue_id"]: row["source_label"] for row in panel["tissues"]}
    records, artifacts = [], []
    used_targets, used_tissues = set(), set()
    for relative, (alpha, count) in APPROVED_SOURCES.items():
        decision = decisions.get(relative)
        content = (root / relative).read_bytes()
        if decision is None or decision["public_decision"] != "KEEP" or digest(content) != decision["sha256"].lower():
            raise CompatibilityError(f"{relative}: approved KEEP/checksum mismatch; do not export changed or restricted results")
        with (root / relative).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != count:
            raise CompatibilityError(f"{relative}: expected {count} accepted calls")
        artifacts.append({"path": relative, "sha256": digest(content), "bytes": len(content), "release": "v0.1.1", "record_count": count})
        for index, row in enumerate(rows, 1):
            if row["compound"] != "KETAMINE" or row["fingerprint_call"] != "True" or float(row["fingerprint_alpha"]) != alpha:
                raise CompatibilityError(f"{relative} row {index}: unexpected profile, threshold, or membership")
            target, tissue = row["canonical_target_id"], row["tissue_id"]
            if tissue_registry.get(tissue) != row["tissue"] or target != row["target"]:
                raise CompatibilityError(f"{relative} row {index}: unsupported source identity mapping")
            used_targets.add(target)
            used_tissues.add(tissue)
            records.append({"profile_id": "POOLED_PARENT_KETAMINE", "source_profile_id": row["compound"], "target_id": target, "tissue_id": tissue, "expression_dataset_id": DATASET, "hr_score": float(row["HR_score"]), "fingerprint_member": True, "support_status": "supported", "gesd_alpha": alpha, "source_artifact": relative, "source_row": index})
    manifest = {
        "schema_version": SCHEMA_VERSION, "synthetic": False,
        "producer": {"repository": REPOSITORY, "release": "v0.1.1", "commit": _git(root, "rev-parse", "HEAD"), "dirty": bool(_git(root, "status", "--porcelain", "--untracked-files=no"))},
        "generation": {"generated_at": _git(root, "show", "-s", "--format=%cI", "HEAD"), "time_basis": "producer_commit", "command": "python -m cardozo_ketamine_hr.integration export --output <new-directory>"},
        "scope": {"analysis_scope": "whole_body_pooled_parent_ketamine", "coverage": "positive_calls_only", "gesd_alphas": [0.001, 0.0001], "expression_dataset_ids": [DATASET], "missingness_policy": MISSINGNESS},
        "identities": {"namespace": NAMESPACE, "mapping_policy": "exact_source_ids_only", "profiles": [{"id": "POOLED_PARENT_KETAMINE", "source_id": "KETAMINE", "identity_grain": "GOVERNED_ANALYSIS_PROFILE"}], "targets": [{"id": key, "source_label": key} for key in sorted(used_targets)], "tissues": [{"id": key, "source_label": tissue_registry[key]} for key in sorted(used_tissues)]},
        "source_artifacts": artifacts,
        "data_use": {"license": "CC-BY-SA-4.0", "notice": REPOSITORY + "/blob/main/DATA_LICENSE.md", "restrictions": ["Project-authored contributions only; upstream source terms remain applicable.", "No reconstruction or redistribution of excluded near-source inputs.", "Preserve attribution, source release, modifications and ShareAlike notices."]},
        "validation": {"status": "PASS", "method": "schema_identity_missingness_integrity_v1", "scientific_scope": "Thin adapter of approved v0.1.1 positive calls; no GESD refit, full HR matrix, or inferred non-calls."},
    }
    _write_bundle(output, manifest, records)
    return manifest


def main() -> int:
    """Run explicit export or read-only consumer compatibility validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Export approved public positive-call tables")
    export.add_argument("--root", type=Path, default=Path.cwd())
    export.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="Validate a consumer bundle without changing it")
    validate.add_argument("directory", type=Path)
    validate.add_argument("--expected-dataset")
    validate.add_argument("--expected-namespace")
    validate.add_argument("--identity-registry", type=Path, help="Independently pinned identities JSON object")
    args = parser.parse_args()
    try:
        if args.command == "export":
            manifest = export_approved(args.root, args.output)
            print(f"Export PASS: {manifest['files'][0]['record_count']} positive-call records; schema {SCHEMA_VERSION}; output {args.output}")
        else:
            identities = _read_json(args.identity_registry) if args.identity_registry else None
            manifest, records = validate_bundle(args.directory, expected_dataset=args.expected_dataset, expected_namespace=args.expected_namespace, accepted_identities=identities)
            print(f"Compatibility PASS: {len(records)} records; schema {manifest['schema_version']}; synthetic={manifest['synthetic']}; coverage={manifest['scope']['coverage']}")
    except (CompatibilityError, OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Compatibility FAIL: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
