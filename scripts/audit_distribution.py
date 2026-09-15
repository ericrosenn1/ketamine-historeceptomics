"""Audit built Python distributions against the public release boundary.

Stage: package validation after sdist and wheel construction.
Inputs: an explicit directory containing exactly one sdist and one wheel.
Outputs: a concise member-count and SHA-256 summary on standard output.
Side effects: reads archives only; it does not extract or modify them.
Invariants: fail on restricted file types, private-work markers, local absolute
paths, credential markers, malformed archives, or unexpected archive counts.
Lane: public package-build CI and local release validation.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
import zipfile
from pathlib import Path


FORBIDDEN_SUFFIXES = {
    ".docx",
    ".duckdb",
    ".env",
    ".pdf",
    ".sqlite",
    ".sqlite3",
    ".xls",
    ".xlsm",
    ".xlsx",
    ".zip",
}
FORBIDDEN_NAME_PARTS = {
    "/local/",
    "/manuscript/",
    "handoff",
    "private",
    "restricted",
}
FORBIDDEN_CONTENT = (
    re.compile(rb"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(rb"github_pat_[A-Za-z0-9_]+"),
    re.compile(rb"ghp_[A-Za-z0-9]+"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest for one distribution file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_member(name: str, payload: bytes) -> list[str]:
    """Return boundary violations for one normalized archive member."""

    normalized = "/" + name.replace("\\", "/").lower().lstrip("/")
    findings: list[str] = []
    if Path(normalized).suffix in FORBIDDEN_SUFFIXES:
        findings.append(f"forbidden file type: {name}")
    if any(marker in normalized for marker in FORBIDDEN_NAME_PARTS):
        findings.append(f"forbidden path marker: {name}")
    if len(payload) <= 10 * 1024 * 1024:
        for pattern in FORBIDDEN_CONTENT:
            if pattern.search(payload):
                findings.append(f"forbidden content marker: {name}")
    return findings


def audit_wheel(path: Path) -> tuple[int, list[str]]:
    """Read and audit every regular member in a wheel ZIP."""

    findings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            findings.append(f"CRC failure: {bad}")
        members = [item for item in archive.infolist() if not item.is_dir()]
        for item in members:
            findings.extend(audit_member(item.filename, archive.read(item)))
    return len(members), findings


def audit_sdist(path: Path) -> tuple[int, list[str]]:
    """Read and audit every regular member in a gzipped source archive."""

    findings: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        members = [item for item in archive.getmembers() if item.isfile()]
        for item in members:
            handle = archive.extractfile(item)
            if handle is None:
                findings.append(f"unreadable member: {item.name}")
                continue
            findings.extend(audit_member(item.name, handle.read()))
    return len(members), findings


def main() -> int:
    """Validate exactly one wheel and one sdist and print their digests."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.dist_dir.glob("*.whl"))
    sdists = sorted(args.dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(
            f"Expected exactly one wheel and one sdist; found {len(wheels)} and {len(sdists)}"
        )

    findings: list[str] = []
    for path, audit in ((wheels[0], audit_wheel), (sdists[0], audit_sdist)):
        member_count, file_findings = audit(path)
        findings.extend(f"{path.name}: {finding}" for finding in file_findings)
        print(
            f"{path.name}\tmembers={member_count}\tsha256={sha256(path)}\t"
            f"status={'FAIL' if file_findings else 'PASS'}"
        )
    if findings:
        raise SystemExit("Distribution boundary audit failed:\n" + "\n".join(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
