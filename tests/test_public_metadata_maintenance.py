"""Protect strict publication checks, staged-only refresh, and notebook scanning."""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import csv
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
audit = importlib.import_module("audit_repository")
maintenance = importlib.import_module("refresh_public_metadata")


def test_notebook_scans_decoded_sources_saved_outputs_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "example.ipynb"
    sensitive = "C:" + "\\Users\\" + "example\\work"
    notebook = {
        "nbformat": 4,
        "metadata": {"path": sensitive},
        "cells": [{"cell_type": "code", "source": ["x = 1"], "outputs": [{"output_type": "stream", "text": [sensitive]}]}],
    }
    path.write_text(json.dumps(notebook), encoding="utf-8")
    _, findings, _ = audit.scan(tmp_path)
    assert sum(item.category == "named_user_path" for item in findings) == 2
    assert all(sensitive not in item.note for item in findings)


def test_notebook_rejects_malformed_json_and_unreviewed_images(tmp_path: Path) -> None:
    path = tmp_path / "bad.ipynb"
    path.write_text("{broken", encoding="utf-8")
    assert any(item.category == "notebook_format" for item in audit.scan(tmp_path)[1])
    path.write_text(json.dumps({"nbformat": 4, "image/jpeg": "opaque", "image/png": "invalid"}), encoding="utf-8")
    assert sum(item.category == "notebook_image" for item in audit.scan(tmp_path)[1]) == 2
    (tmp_path / "new.png").write_bytes(b"unreviewed")
    assert any(item.category == "unapproved_binary_or_unknown_type" for item in audit.scan(tmp_path)[1])


def test_metadata_refresh_is_staged_only_deterministic_and_preserves_references(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    maintenance.materialize(root, snapshot)
    # Exercise the checked-out implementations even before a local edit is staged.
    for script in ("build_repository_metadata.py", "audit_code_documentation.py", "audit_repository.py", "build_release_manifests.py"):
        (snapshot / "scripts" / script).write_bytes((SCRIPTS / script).read_bytes())
    original = {path.relative_to(snapshot).as_posix(): path.read_bytes() for path in (snapshot / "results/reference").rglob("*") if path.is_file()}
    assert len(original) == 60
    with (snapshot / "requirements-docs.txt").open("a", encoding="utf-8") as handle:
        handle.write("\n# Synthetic dependency-metadata regression probe\n")
    schema = snapshot / "integrations" / "maintenance-test.schema.json"
    schema.parent.mkdir(exist_ok=True)
    schema.write_text('{"description":"Synthetic interface inventory probe"}\n', encoding="utf-8")
    maintenance.command(snapshot, "git", "add", "--force", "--all")
    maintenance.refresh(snapshot)
    # refresh writes, then runs every strict check again to prove stability.
    assert all((snapshot / rel).is_file() for rel in maintenance.GENERATED)
    with (snapshot / "audits/CODE_INVENTORY.csv").open(encoding="utf-8", newline="") as handle:
        assert "integrations/maintenance-test.schema.json" in {row["repo_destination"] for row in csv.DictReader(handle)}
    assert original == {rel: (snapshot / rel).read_bytes() for rel in original}
    assert not (root / "integrations/maintenance-test.schema.json").exists()

    # A real boundary violation must abort, even when metadata could be refreshed.
    (snapshot / "disallowed.env").write_text("synthetic=true\n", encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):
        maintenance.refresh(snapshot)
