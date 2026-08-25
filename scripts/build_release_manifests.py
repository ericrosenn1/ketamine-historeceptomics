"""Build deterministic manifests from sanitized files or staged Git blobs.

Stage: final byte inventory after public preflight and before release tagging.
Inputs: an explicit root plus staged index blobs or ``--source worktree`` files.
Outputs: ``PUBLIC_RELEASE_MANIFEST.tsv`` and ``SHA256SUMS.txt`` content.
Side effects: writes those files unless ``--check`` requests byte comparison.
Invariants: exclude recursive outputs and ignored/runtime paths; hash exact bytes.
Lane: public preflight, release packaging, and CI manifest verification.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import subprocess
from dataclasses import dataclass
from pathlib import Path


EXCLUDED = {"PUBLIC_RELEASE_MANIFEST.tsv", "SHA256SUMS.txt"}
WORKTREE_SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "local",
    "release_artifacts",
    "runs",
}


@dataclass(frozen=True)
class GitBlob:
    """A stage-zero Git index entry used by the public release."""

    path: str
    mode: str
    object_id: str
    content: bytes


def parse_args() -> argparse.Namespace:
    """Parse the repository root and optional no-write verification mode."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Git working-tree root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check existing manifest bytes instead of updating them.",
    )
    parser.add_argument(
        "--source",
        choices=("index", "worktree"),
        default="index",
        help="Hash exact staged blobs (release default) or a pre-Git worktree preflight.",
    )
    return parser.parse_args()


def git(root: Path, *args: str) -> bytes:
    """Run a read-only Git query and return its standard output bytes."""

    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def staged_blobs(root: Path) -> list[GitBlob]:
    """Read every stage-zero release blob directly from the Git object store."""

    raw = git(root, "ls-files", "--stage", "-z")
    blobs: list[GitBlob] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise RuntimeError("Unmerged index entries cannot form a public release")
        path = raw_path.decode("utf-8").replace("\\", "/")
        if path in EXCLUDED:
            continue
        content = git(root, "cat-file", "blob", object_id)
        blobs.append(GitBlob(path, mode, object_id, content))
    return sorted(blobs, key=lambda item: item.path)


def worktree_blobs(root: Path) -> list[GitBlob]:
    """Read the sanitized pre-Git file set for the publication audit preflight."""

    blobs: list[GitBlob] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        public_path = rel.as_posix()
        if public_path in EXCLUDED or any(
            part in WORKTREE_SKIP_PARTS or part.endswith(".egg-info") for part in rel.parts
        ):
            continue
        blobs.append(GitBlob(public_path, "100644", "WORKTREE_PREFLIGHT", path.read_bytes()))
    return blobs


def sha256(content: bytes) -> str:
    """Return an uppercase SHA-256 digest for *content*."""

    return hashlib.sha256(content).hexdigest().upper()


def render(blobs: list[GitBlob]) -> tuple[str, str]:
    """Render the tabular manifest and common checksum-file representation."""

    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(["path", "git_mode", "bytes", "sha256"])
    checksum_lines: list[str] = []
    for blob in blobs:
        digest = sha256(blob.content)
        writer.writerow([blob.path, blob.mode, len(blob.content), digest])
        checksum_lines.append(f"{digest}  {blob.path}\n")
    return stream.getvalue(), "".join(checksum_lines)


def write_or_check(path: Path, expected: str, check: bool) -> None:
    """Write one LF-normalized output or verify its exact current bytes."""

    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            raise SystemExit(f"Release manifest is stale: {path.name}")
        return
    path.write_text(expected, encoding="utf-8", newline="\n")


def main() -> None:
    """Generate or verify the two non-recursive public release manifests."""

    args = parse_args()
    root = args.root.resolve()
    blobs = staged_blobs(root) if args.source == "index" else worktree_blobs(root)
    if not blobs:
        raise SystemExit("No staged Git blobs found; initialize and stage the release first")
    manifest, checksums = render(blobs)
    write_or_check(root / "PUBLIC_RELEASE_MANIFEST.tsv", manifest, args.check)
    write_or_check(root / "SHA256SUMS.txt", checksums, args.check)
    total_bytes = sum(len(blob.content) for blob in blobs)
    print(
        f"Public release manifest: PASS; source={args.source}; {len(blobs)} files; "
        f"{total_bytes} bytes"
    )
    print(
        "PUBLIC_RELEASE_MANIFEST.tsv and SHA256SUMS.txt intentionally exclude "
        "themselves to avoid recursive hashes."
    )


if __name__ == "__main__":
    main()
