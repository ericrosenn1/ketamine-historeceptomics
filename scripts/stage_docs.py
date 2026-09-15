"""Stage the tracked public documentation tree for a strict MkDocs build.

Stage: documentation preparation before MkDocs rendering.
Inputs: tracked Git files in the current repository checkout.
Outputs: ``build/docs-source`` containing Markdown and linked public evidence.
Side effects: replaces only the fixed, ignored documentation staging directory.
Invariants: source files are copied byte-for-byte; untracked/private files are
never selected; scientific results and configuration sources remain read-only.
Lane: local documentation validation and the public Pages workflow.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path, PurePosixPath


ROOT_FILES = {
    "ANALYSIS_REPRODUCIBILITY_MATRIX.csv",
    "CHANGELOG.md",
    "CITATION.bib",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv",
    "DATA_LICENSE.md",
    "DATA_MANIFEST.csv",
    "EXTERNAL_INPUT_MANIFEST.tsv",
    "LICENSE",
    "MULTIVARIATE_MODEL_STATUS.csv",
    "PUBLIC_RELEASE_DECISIONS.md",
    "PUBLIC_RELEASE_FILE_DECISIONS.tsv",
    "PUBLIC_RELEASE_MANIFEST.tsv",
    "README.md",
    "RELEASE_NOTES.md",
    "SECURITY.md",
    "SHA256SUMS.txt",
    "SUPPORT.md",
    "THIRD_PARTY_NOTICES.md",
    "environment.yml",
    "pyproject.toml",
    "requirements-lock.txt",
}
PUBLIC_PREFIXES = (
    "audits/",
    "configs/",
    "data/fixtures/",
    "data/frozen/",
    "docs/",
    "optional/",
    "results/reference/",
)


def tracked_files(root: Path) -> list[PurePosixPath]:
    """Return repository-relative paths reported by the Git index."""

    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return [PurePosixPath(item.decode("utf-8")) for item in output.split(b"\0") if item]


def include(path: PurePosixPath) -> bool:
    """Select documentation and the public files targeted by its local links."""

    text = path.as_posix()
    return text in ROOT_FILES or text.startswith(PUBLIC_PREFIXES)


def main() -> int:
    """Replace the fixed staging directory with byte-preserved tracked files."""

    root = Path(__file__).resolve().parents[1]
    stage = (root / "build" / "docs-source").resolve()
    expected = (root / "build" / "docs-source").resolve()
    if stage != expected or stage.parent != (root / "build").resolve():
        raise SystemExit("Refusing to stage outside the repository build directory")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    selected = [path for path in tracked_files(root) if include(path)]
    if not selected or PurePosixPath("README.md") not in selected:
        raise SystemExit("Documentation staging selection is unexpectedly empty")
    for relative in selected:
        source = root.joinpath(*relative.parts)
        target = stage.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print(f"Documentation staging: PASS; {len(selected)} tracked public files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
