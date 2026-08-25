"""Test frozen family-profile completion and self-contained output manifests."""

# SPDX-License-Identifier: MIT

from pathlib import Path

import pandas as pd
import pytest

from cardozo_ketamine_hr.family_completion import E7_LABELS, load_e7_profiles, strict_contract_from_profiles
from cardozo_ketamine_hr.packaging import output_manifest
from cardozo_ketamine_hr.utilities import sha256_file


def _profiles_and_contract(data_root: Path):
    """Load the excluded profile authority and derive its strict contract."""

    profiles = pd.read_csv(
        data_root / "profiles" / "all_compound_profiles_strict18_long.csv",
        low_memory=False,
    )
    return profiles, strict_contract_from_profiles(profiles)


@pytest.mark.external_data
def test_e7_family_availability_and_norketamine_hnk_inclusion(governed_paths):
    data_root = governed_paths["external_input_root"]
    _, contract = _profiles_and_contract(data_root)
    paths = {
        "e7_raw_matrix": data_root / "e7" / "raw_hr.csv",
        "e7_common_matrix": data_root / "e7" / "common_rhr.csv",
    }
    e7 = load_e7_profiles(paths, contract)
    assert set(e7["source_compound_id"].drop_duplicates()) == set(E7_LABELS)
    assert set(E7_LABELS.values()).issubset(set(e7["drug"]))


@pytest.mark.external_data
def test_r_hydroxyketamine_equality_is_source_induced_not_identity_alias(governed_paths):
    profiles, _ = _profiles_and_contract(governed_paths["external_input_root"])
    common = profiles.pivot(index="drug", columns="feature_id", values="common_rhr")
    r = common.loc["R-ketamine"]
    hydroxy = common.loc["Hydroxyketamine, unspecified isomer aggregate"]
    matched = r.notna() & hydroxy.notna()
    assert int(matched.sum()) == 576
    assert float((r[matched] - hydroxy[matched]).abs().max()) == 0.0
    assert not r.notna().equals(hydroxy.notna())


@pytest.mark.external_data
def test_grin3b_1044_to_1026_contract_behavior(governed_paths):
    strict = pd.read_csv(governed_paths["pooled_strict_hr"], low_memory=False)
    profiles, _ = _profiles_and_contract(governed_paths["external_input_root"])
    pooled = profiles[profiles["drug"].eq("Ketamine, pooled parent")]
    compatible = pooled[pooled["common_rhr"].notna()]
    assert len(strict) == 1044
    assert len(compatible) == 1026
    assert set(strict["canonical_target_id"]) - set(compatible["target"]) == {"GRIN3B"}


@pytest.mark.external_data
def test_pooled_fingerprint_19_14_and_nested(governed_paths):
    primary = pd.read_csv(governed_paths["pooled_calls_001"], low_memory=False)
    strict = pd.read_csv(governed_paths["pooled_calls_0001"], low_memory=False)
    primary_ids = set(primary["feature_id"])
    strict_ids = set(strict["feature_id"])
    assert len(primary_ids) == 19
    assert len(strict_ids) == 14
    assert strict_ids.issubset(primary_ids)


def test_output_manifest_hash_completeness(tmp_path):
    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    manifest = output_manifest(tmp_path)
    assert set(manifest["relative_path"]) == {"one.txt", "two.txt"}
    for row in manifest.itertuples(index=False):
        assert sha256_file(tmp_path / row.relative_path) == row.sha256
