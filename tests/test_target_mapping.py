"""Test exact-grain target harmonization against the excluded target contract."""

# SPDX-License-Identifier: MIT

import pytest

from cardozo_ketamine_hr.targets import harmonize_target, load_target_contract


pytestmark = pytest.mark.external_data


def test_target_contract_is_unique_and_exact_grain(governed_paths):
    contract = load_target_contract(governed_paths["feature_dictionary"])
    assert len(contract) == 76
    assert contract["target_canonical_id"].is_unique
    assert set(contract["target_grain_class"]) == {"EXACT_SINGLE_PROTEIN"}


def test_exact_target_id_and_gene_symbol_resolve(governed_paths):
    contract = load_target_contract(governed_paths["feature_dictionary"])
    by_id = harmonize_target({"canonical_target_id": "GRIN2B"}, contract=contract)
    by_gene = harmonize_target("slc6a4", contract=contract)
    assert (by_id.status, by_id.canonical_target_id, by_id.target_grain) == (
        "RESOLVED",
        "GRIN2B",
        "EXACT_SINGLE_PROTEIN",
    )
    assert (by_gene.status, by_gene.canonical_target_id) == ("RESOLVED", "SLC6A4")


def test_generic_nmda_measurement_is_not_decomposed(governed_paths):
    contract = load_target_contract(governed_paths["feature_dictionary"])
    result = harmonize_target({"target_name": "NMDA receptor"}, contract=contract)
    assert result.status == "AMBIGUOUS_TARGET_GRAIN"
    assert result.canonical_target_id is None


def test_nonexact_grain_is_rejected_without_invention(governed_paths):
    contract = load_target_contract(governed_paths["feature_dictionary"])
    result = harmonize_target(
        {"target_name": "GABA-A receptor", "target_grain": "PROTEIN_COMPLEX"},
        contract=contract,
    )
    assert result.status == "UNSUPPORTED_TARGET_GRAIN"
    assert result.mapping_method == "NONE"
