"""Configure public tests and manifest-gated access to excluded frozen inputs."""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_INPUT_ENV = "CARDOZO_HR_EXTERNAL_INPUT_ROOT"
EXTERNAL_INPUT_MANIFEST = REPO_ROOT / "EXTERNAL_INPUT_MANIFEST.tsv"


def _sha256(path: Path) -> str:
    """Return the uppercase SHA-256 digest of one external authority."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _validate_external_input_root() -> tuple[Path | None, str | None]:
    """Resolve and validate the optional 20-file external authority tree."""

    configured = os.environ.get(EXTERNAL_INPUT_ENV, "").strip()
    if not configured:
        return None, f"{EXTERNAL_INPUT_ENV} is not set"
    root = Path(configured).expanduser().resolve()
    if not root.is_dir():
        return None, f"{EXTERNAL_INPUT_ENV} is not an existing directory: {root}"

    try:
        with EXTERNAL_INPUT_MANIFEST.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        if len(rows) != 20:
            return None, f"external manifest records {len(rows)} files, expected 20"
        invalid: list[str] = []
        for row in rows:
            relative_path = Path(row["external_relative_path"])
            path = root / relative_path
            if (
                not path.is_file()
                or path.stat().st_size != int(row["bytes"])
                or _sha256(path) != row["sha256"].upper()
            ):
                invalid.append(relative_path.as_posix())
    except (KeyError, OSError, ValueError) as exc:
        return None, f"external authority validation failed: {exc}"
    if invalid:
        return None, "external authority mismatch: " + ", ".join(invalid)
    return root, None


EXTERNAL_INPUT_ROOT, EXTERNAL_INPUT_ERROR = _validate_external_input_root()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip only tests marked as consumers of redistribution-excluded inputs."""

    del config
    if EXTERNAL_INPUT_ERROR is None:
        return
    skip_external = pytest.mark.skip(reason=EXTERNAL_INPUT_ERROR)
    for item in items:
        if "external_data" in item.keywords:
            item.add_marker(skip_external)


@pytest.fixture(scope="session")
def governed_paths() -> dict[str, Path]:
    """Return public metadata/output paths plus the validated external data root."""

    # Scientific authorities route through the external tree; public configs,
    # reference results, and release metadata remain rooted in this repository.
    data_root = EXTERNAL_INPUT_ROOT or REPO_ROOT / "data" / "frozen"
    return {
        "project_root": REPO_ROOT,
        "external_input_root": data_root,
        "pooled_activity": data_root / "core" / "pooled_target_activity.csv",
        "pooled_expression": data_root / "core" / "pooled_expression58.parquet",
        "pooled_full_hr": data_root / "core" / "pooled_full77_hr.parquet",
        "pooled_strict_hr": data_root / "core" / "pooled_strict18_hr.csv",
        "pooled_calls_001": data_root / "core" / "pooled_strict18_calls_alpha001.csv",
        "pooled_calls_0001": data_root / "core" / "pooled_strict18_calls_alpha0001.csv",
        "pooled_missing_expression": data_root / "core" / "pooled_missing_expression.csv",
        "feature_dictionary": data_root / "metadata" / "feature_dictionary.parquet",
        "prior_profiles": data_root / "profiles" / "prior_external_profiles.parquet",
        "prior_pairwise": data_root / "profiles" / "prior_pairwise.parquet",
        "prior_calls_001": data_root / "profiles" / "prior_calls_alpha001.parquet",
        "prior_calls_0001": data_root / "profiles" / "prior_calls_alpha0001.parquet",
    }
