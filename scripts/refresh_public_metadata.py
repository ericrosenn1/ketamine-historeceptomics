"""Refresh public metadata from the exact staged source tree for review.

Stage: maintenance after staging intended source changes, before final commit.
Inputs: stage-zero Git blobs and the existing public audit/metadata generators.
Outputs: refreshed checked metadata, or a portable review patch outside the tree.
Side effects: only the fixed GENERATED outputs are copied back in write mode;
patch mode leaves the source checkout and its Git index untouched.
Invariants: no scientific computation, private inputs, remote writes, or automatic
staging; audit failures abort before any generated output is copied back.
Lane: dependency maintenance and public-release metadata remediation.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from build_release_manifests import staged_blobs


GENERATED = (
    "audits/CODE_INVENTORY.csv",
    "DATA_MANIFEST.csv",
    "CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv",
    "audits/CODE_DOCUMENTATION_AUDIT.md",
    "audits/CODE_DOCUMENTATION_AUDIT.tsv",
    "audits/PUBLIC_EXPOSURE_AUDIT.md",
    "audits/PUBLIC_EXPOSURE_FINDINGS.tsv",
    "audits/REPOSITORY_CONTENT_AUDIT.md",
    "PUBLIC_RELEASE_MANIFEST.tsv",
    "SHA256SUMS.txt",
)


def command(root: Path, *args: str) -> bytes:
    """Run a local command with failure propagation and return its output."""

    result = subprocess.run(args, cwd=root, check=True, capture_output=True)
    if result.stderr:
        print(result.stderr.decode("utf-8", errors="replace"), end="", file=sys.stderr)
    return result.stdout


def refresh(snapshot: Path) -> None:
    """Regenerate metadata in dependency order and prove a second run is stable."""

    steps = (
        ("build_repository_metadata.py",),
        ("audit_code_documentation.py",),
        ("audit_repository.py",),
    )
    for check in (False, True):
        for script, *options in steps:
            arguments = [sys.executable, str(snapshot / "scripts" / script), "--root", str(snapshot), *options]
            if check:
                arguments.append("--check")
            print(command(snapshot, *arguments).decode("utf-8", errors="replace"), end="")
        if not check:
            command(snapshot, "git", "add", "--force", "--", *GENERATED[:-2])
        arguments = [sys.executable, str(snapshot / "scripts/build_release_manifests.py"), "--root", str(snapshot)]
        if check:
            arguments.append("--check")
        print(command(snapshot, *arguments).decode("utf-8", errors="replace"), end="")


def materialize(root: Path, snapshot: Path) -> None:
    """Materialize only safe regular staged files, including recursive manifests."""

    blobs = staged_blobs(root)
    # The manifest generator intentionally excludes its two outputs; this tool
    # also needs their checked baseline to produce a complete review patch.
    for blob in blobs:
        relative = PurePosixPath(blob.path)
        if blob.mode not in {"100644", "100755"} or relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Unsafe or nonregular staged path: {blob.path}")
        destination = snapshot.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(blob.content)
    for relative in ("PUBLIC_RELEASE_MANIFEST.tsv", "SHA256SUMS.txt"):
        payload = command(root, "git", "show", ":" + relative)
        (snapshot / relative).write_bytes(payload)
    command(snapshot, "git", "init", "--quiet")
    command(snapshot, "git", "-c", "core.autocrlf=false", "add", "--force", "--all")
    for blob in blobs:
        if blob.mode == "100755":
            command(snapshot, "git", "update-index", "--chmod=+x", "--", blob.path)


def main() -> int:
    """Prepare a checked metadata diff without automatically accepting it."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--patch", type=Path, help="Write a review patch outside the repository instead of updating metadata")
    args = parser.parse_args()
    root = args.root.resolve()
    patch = args.patch.resolve() if args.patch else None
    if patch is not None and patch.is_relative_to(root):
        raise SystemExit("The review patch must be outside the source repository")
    if not (root / "pyproject.toml").is_file():
        raise SystemExit("Not a public repository root")

    try:
        with tempfile.TemporaryDirectory(prefix="ketamine-public-metadata-") as temporary:
            snapshot = Path(temporary)
            materialize(root, snapshot)
            baseline = command(snapshot, "git", "write-tree").decode("ascii").strip()
            refresh(snapshot)
            changed = [rel for rel in GENERATED if (snapshot / rel).read_bytes() != (root / rel).read_bytes()]
            if patch is not None:
                patch.parent.mkdir(parents=True, exist_ok=True)
                payload = command(snapshot, "git", "diff", "--binary", baseline, "--", *GENERATED)
                patch.write_bytes(payload)
                print(f"Review patch: {patch.name}; {len(payload)} bytes")
            else:
                for relative in changed:
                    (root / relative).write_bytes((snapshot / relative).read_bytes())
            print(f"Public metadata refresh: PASS; {len(changed)} generated files differ")
            print("Review the diff, stage the generated files, and run the strict --check commands before committing.")
        return 0
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout.decode("utf-8", errors="replace"), end="", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr.decode("utf-8", errors="replace"), end="", file=sys.stderr)
        print("Public metadata refresh: FAIL; source checkout and index were not updated", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
