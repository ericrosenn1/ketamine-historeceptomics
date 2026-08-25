"""Build deterministic public code and analysis-authority metadata.

Stage: metadata generation after file decisions and before release manifests.
Inputs: the public tree, data decisions/manifests, configuration, and package metadata.
Outputs: code inventory, resolved data manifest, and analysis-authority manifest.
Side effects: writes only those metadata files unless ``--check`` is selected.
Invariants: never read external sources, rerun science, or rewrite reference outputs.
Lane: public metadata build and CI idempotence check.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import tomllib
from pathlib import Path

import yaml


VERSION = "0.1.1"


def parse_args() -> argparse.Namespace:
    """Parse the repository root and deterministic check mode."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Public repository root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated metadata differs from checked files.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    """Return the uppercase SHA-256 digest of one public file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_csv(path: Path, delimiter: str = ",") -> tuple[list[str], list[dict[str, str]]]:
    """Read a UTF-8 delimited authority table without type coercion."""

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing header: {path}")
        return list(reader.fieldnames), list(reader)


def render_csv(fieldnames: list[str], rows: list[dict[str, object]]) -> str:
    """Render deterministic RFC-style CSV with LF line endings."""

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=fieldnames,
        extrasaction="ignore",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def refresh_code_inventory(root: Path) -> str:
    """Update included-code hashes and mark removed private tooling excluded."""

    path = root / "audits" / "CODE_INVENTORY.csv"
    fieldnames, rows = read_csv(path)
    for row in rows:
        destination = row.get("repo_destination", "")
        if row.get("included_in_repo") != "YES" or not destination:
            continue
        public_path = root / destination
        if not public_path.is_file():
            row["included_in_repo"] = "NO"
            row["current_status"] = "PUBLIC_EXCLUDED"
            row["validation_source"] = "PUBLIC_RELEASE_FILE_DECISIONS.tsv"
            row["notes"] = (row.get("notes", "") + "; excluded from sanitized public tree").strip("; ")
            continue
        digest = sha256(public_path)
        notes = re.sub(r"sha256=[A-Fa-f0-9]{64}", f"sha256={digest}", row.get("notes", ""))
        if "sha256=" not in notes:
            notes = f"sha256={digest}" + (f"; {notes}" if notes else "")
        row["notes"] = notes
        if destination.startswith(("src/", "tests/", "configs/")):
            row["validation_source"] = "audits/PUBLIC_SCIENTIFIC_EQUIVALENCE.md"
        elif destination.startswith("scripts/"):
            row["validation_source"] = "audits/CODE_DOCUMENTATION_AUDIT.md"
        elif destination.startswith("launchers/"):
            row["validation_source"] = "audits/PUBLIC_SCIENTIFIC_EQUIVALENCE.md"
        elif destination.startswith(".github/") or destination in {
            ".gitattributes",
            ".gitignore",
            "environment.yml",
            "pyproject.toml",
            "requirements-lock.txt",
            "requirements.txt",
        }:
            row["validation_source"] = "audits/CODE_DOCUMENTATION_AUDIT.md"
        if destination == "workflow/Snakefile":
            row["current_status"] = "PUBLIC_REFERENCE_ONLY_NOT_RELEASE_VALIDATED"
            row["validation_source"] = "docs/DEVELOPER_GUIDE.md"
    return render_csv(fieldnames, rows)


def resolve_data_manifest(root: Path) -> str:
    """Replace every private pending status with its approved public decision."""

    path = root / "DATA_MANIFEST.csv"
    fieldnames, rows = read_csv(path)
    for row in rows:
        rel = row["repo_path"]
        if rel == "data/frozen/metadata/class_membership.csv":
            row["redistribution_status"] = "PUBLIC_KEEP_PROJECT_METADATA_CC_BY_SA_4_0"
            row["note"] = (
                "Retained byte-identically as project-authored descriptive metadata; "
                "see DATA_LICENSE.md"
            )
        elif rel.startswith("results/reference/"):
            row["redistribution_status"] = "PUBLIC_KEEP_PROJECT_DERIVATIVE_CC_BY_SA_4_0"
            marker = "retained byte-identically as an accepted project analysis derivative"
            base_note = row.get("note", "").split(f"; {marker}", 1)[0].rstrip("; ")
            row["note"] = (
                base_note + f"; {marker}"
            ).lstrip("; ")
        else:
            row["redistribution_status"] = "PUBLIC_REPLACE_WITH_SYNTHETIC_FIXTURE"
            row["note"] = (
                "Excluded from the public tree; exact user-supplied file contract is in "
                "EXTERNAL_INPUT_MANIFEST.tsv and synthetic public tests are in data/fixtures/"
            )
    return render_csv(fieldnames, rows)


def public_authority_paths(root: Path) -> list[Path]:
    """Return present numerical, implementation, configuration, and lane files."""

    paths: list[Path] = []
    paths.extend(path for path in (root / "data" / "frozen").rglob("*") if path.is_file())
    paths.extend(path for path in (root / "results" / "reference").rglob("*") if path.is_file())
    paths.extend((root / "src" / "cardozo_ketamine_hr").glob("*.py"))
    paths.extend((root / "src" / "cardozo_ketamine_hr" / "upstream").glob("*.py"))
    paths.extend((root / "configs").glob("*.yaml"))
    paths.extend((root / "configs").glob("*.yml"))
    paths.extend(
        root / relative
        for relative in (
            "launchers/run_reproduction.ps1",
            "workflow/Snakefile",
            "requirements-lock.txt",
            "EXTERNAL_INPUT_MANIFEST.tsv",
        )
    )
    return sorted(set(path for path in paths if path.is_file()))


def classify_authority(root: Path, path: Path) -> tuple[str, str, str]:
    """Classify one public authority without changing its scientific meaning."""

    rel = path.relative_to(root).as_posix()
    if rel == "data/frozen/metadata/class_membership.csv":
        return (
            "PUBLIC_CLASS_METADATA",
            "Project-authored descriptive many-to-many class membership registry",
            "PUBLIC_RETAINED_PROJECT_METADATA",
        )
    if rel.startswith("results/reference/"):
        return (
            "PUBLIC_REFERENCE_OUTPUT",
            "Accepted pooled-parent reference derivative from approved source snapshot",
            "PUBLIC_RETAINED_BYTE_IDENTICAL_REFERENCE",
        )
    if rel.startswith("src/cardozo_ketamine_hr/upstream/"):
        return (
            "RECOVERED_UPSTREAM_IMPLEMENTATION",
            "Recovered governed upstream implementation; external inputs required",
            "PUBLIC_ROUTED_IMPLEMENTATION",
        )
    if rel.startswith("src/cardozo_ketamine_hr/"):
        return (
            "GOVERNED_IMPLEMENTATION",
            "Validated historeceptomics implementation",
            "PUBLIC_DOCUMENTED_IMPLEMENTATION",
        )
    if rel.startswith("configs/"):
        return (
            "GOVERNED_CONFIGURATION",
            "Versioned scientific and analysis configuration",
            "PUBLIC_PARSED_VALUES_EQUIVALENT_DESCRIPTOR_ONLY_CHANGE",
        )
    if rel == "EXTERNAL_INPUT_MANIFEST.tsv":
        return (
            "EXTERNAL_INPUT_CONTRACT",
            "Exact checksums and sizes for the 20 user-supplied governed inputs",
            "PUBLIC_EXTERNAL_INPUT_ROUTING",
        )
    return (
        "EXECUTION_ENVIRONMENT",
        "Supported public execution or dependency authority",
        "PUBLIC_RELEASE_EXECUTION_INPUT",
    )


def build_authority_manifest(root: Path) -> str:
    """Render the complete present-file public analysis-authority index."""

    fields = [
        "role",
        "repo_path",
        "bytes",
        "sha256",
        "source_resource",
        "source_snapshot",
        "source_locator",
        "status",
    ]
    rows: list[dict[str, object]] = []
    for path in public_authority_paths(root):
        role, resource, status = classify_authority(root, path)
        rel = path.relative_to(root).as_posix()
        rows.append(
            {
                "role": role,
                "repo_path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "source_resource": resource,
                "source_snapshot": "APPROVED_PUBLICATION_SOURCE_SNAPSHOT_2026-08-25",
                "source_locator": "PUBLIC_RELEASE_FILE_DECISIONS.tsv",
                "status": status,
            }
        )
    return render_csv(fields, rows)


def validate_release_metadata(root: Path) -> None:
    """Validate public package, citation, data, and decision-table contracts."""

    with (root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    if project.get("version") != VERSION or project.get("license") != "MIT":
        raise RuntimeError("pyproject.toml must declare public version 0.1.1 and MIT")
    cff = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    if cff.get("version") != VERSION or cff.get("license") != "MIT":
        raise RuntimeError("CITATION.cff must declare public version 0.1.1 and MIT")

    _, data_rows = read_csv(root / "DATA_MANIFEST.csv")
    if len(data_rows) != 81:
        raise RuntimeError(f"DATA_MANIFEST.csv must retain all 81 reviewed rows, found {len(data_rows)}")
    decisions_path = root / "PUBLIC_RELEASE_FILE_DECISIONS.tsv"
    if decisions_path.is_file():
        fields, decisions = read_csv(decisions_path, delimiter="\t")
        required = {
            "source_repo_path",
            "public_repo_path",
            "role",
            "upstream_source",
            "source_version_or_retrieval_date",
            "original_redistribution_status",
            "public_decision",
            "license_or_terms",
            "citation_required",
            "reason",
            "replacement_or_acquisition_method",
            "sha256",
        }
        if not required.issubset(fields):
            raise RuntimeError("PUBLIC_RELEASE_FILE_DECISIONS.tsv is missing required columns")
        decided = {row["source_repo_path"] for row in decisions}
        missing = sorted(row["repo_path"] for row in data_rows if row["repo_path"] not in decided)
        if missing:
            raise RuntimeError("Data-manifest rows missing decisions: " + ", ".join(missing))


def write_or_check(path: Path, content: str, check: bool) -> None:
    """Write LF-normalized metadata or verify its checked bytes."""

    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Repository metadata is stale: {path.relative_to(path.parents[1])}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    """Build or check public metadata without touching numerical authorities."""

    args = parse_args()
    root = args.root.resolve()
    if not (root / "pyproject.toml").is_file():
        raise SystemExit(f"Not a repository root: {root}")
    validate_release_metadata(root)
    outputs = {
        root / "audits" / "CODE_INVENTORY.csv": refresh_code_inventory(root),
        root / "DATA_MANIFEST.csv": resolve_data_manifest(root),
        root / "CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv": build_authority_manifest(root),
    }
    for path, content in outputs.items():
        write_or_check(path, content, args.check)
    print(
        "Public repository metadata: PASS; deterministic code inventory and "
        "analysis-authority manifest"
    )


if __name__ == "__main__":
    main()
