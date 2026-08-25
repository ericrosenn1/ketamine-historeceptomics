"""Test versioned governance configs against public and external authorities."""

# SPDX-License-Identifier: MIT

from pathlib import Path

import pandas as pd
import pytest
import yaml


def _load(root: Path, name: str):
    """Load one public governance configuration."""

    return yaml.safe_load((root / "configs" / name).read_text(encoding="utf-8"))


def _external_authority_path(governed_paths: dict[str, Path], repo_path: str) -> Path:
    """Map a configured ``data/frozen`` path into the validated external tree."""

    relative = Path(repo_path).relative_to(Path("data") / "frozen")
    return governed_paths["external_input_root"] / relative


def test_required_governance_configs_are_release_versioned(governed_paths):
    root = governed_paths["project_root"]
    for name in (
        "compounds.yaml",
        "tissues_cns18.yaml",
        "tissues_full77.yaml",
        "reference_drugs.yaml",
        "analysis_registry.yaml",
    ):
        config = _load(root, name)
        assert config["schema_version"] == "1.0"
        assert config["config_version"] == "0.1.0"
        assert config["effective_date"] == "2026-08-24"


def test_compound_config_has_ten_distinct_numerical_family_profiles(governed_paths):
    config = _load(governed_paths["project_root"], "compounds.yaml")
    numerical = [row for row in config["compounds"] if row["numerical_profile_eligible"]]
    assert len(numerical) == 10
    assert len({row["canonical_id"] for row in config["compounds"]}) == len(config["compounds"])
    assert config["policy"]["unspecified_ketamine_is_not_racemate"] is True
    assert config["policy"]["racemate_activity_may_not_be_assigned_to_an_enantiomer"] is True


@pytest.mark.external_data
def test_tissue_configs_exactly_match_frozen_contracts(governed_paths):
    root = governed_paths["project_root"]
    cns = _load(root, "tissues_cns18.yaml")
    full = _load(root, "tissues_full77.yaml")
    strict_authority = pd.read_csv(_external_authority_path(governed_paths, cns["authority"]))
    feature_contract = pd.read_parquet(
        _external_authority_path(governed_paths, full["authority"])
    )
    assert len(cns["tissues"]) == cns["expected_tissues"] == 18
    assert len(full["tissues"]) == full["expected_tissues"] == 77
    assert [row["order"] for row in cns["tissues"]] == list(range(1, 19))
    assert [row["order"] for row in full["tissues"]] == list(range(1, 78))
    assert {row["tissue_id"] for row in cns["tissues"]} == set(strict_authority["tissue_id"])
    assert {row["tissue_id"] for row in full["tissues"]} == set(
        feature_contract["tissue_canonical_id"]
    )
    assert sum(row["strict_cns"] for row in full["tissues"]) == 18


@pytest.mark.external_data
def test_external_reference_roster_exactly_matches_frozen_profiles(governed_paths):
    root = governed_paths["project_root"]
    config = _load(root, "reference_drugs.yaml")
    profiles = pd.read_csv(
        _external_authority_path(governed_paths, config["authority"]),
        low_memory=False,
    )
    observed = set(profiles.loc[profiles["data_role"].eq("EXTERNAL"), "drug"])
    configured = {row["label"] for row in config["reference_drugs"]}
    assert configured == observed
    assert len(configured) == config["expected_external_drugs"] == 25
    assert config["expected_total_profiles"] == 35
    assert config["expected_unordered_pairs"] == 35 * 34 // 2 == 595


def test_analysis_registry_points_to_existing_numerical_outputs(governed_paths):
    root = governed_paths["project_root"]
    registry = _load(root, "analysis_registry.yaml")
    assert registry["governed_defaults"]["random_seed"] == 20260813
    assert registry["governed_defaults"]["force_unestimable_components"] is False
    for analysis_id, record in registry["analyses"].items():
        output = record.get("output_coordinates") or record.get("output_matrix")
        assert output, analysis_id
        assert (root / output).is_file(), (analysis_id, output)
