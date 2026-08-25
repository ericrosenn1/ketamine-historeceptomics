"""Test release reproducibility and multivariate-status governance tables."""

# SPDX-License-Identifier: MIT

import pandas as pd


REPRODUCIBILITY_STATUSES = {
    "FULLY_REPRODUCIBLE",
    "REPRODUCIBLE_FROM_FROZEN_INPUT",
    "RECONSTRUCTED_AND_VALIDATED",
    "PARTIALLY_REPRODUCIBLE",
    "BLOCKED",
    "SUPERSEDED",
}

MODEL_STATUSES = {
    "CURRENT_SUCCESS",
    "FAILED_NONCONVERGENCE",
    "NONESTIMABLE",
    "SUPERSEDED",
    "NOT_REQUIRED",
}

REQUIRED_ANALYSES = {
    "Compound identity",
    "Target harmonization",
    "Activity harmonization",
    "Expression processing",
    "HR calculation",
    "Strict-CNS matrix",
    "Full-body matrix",
    "Strict-CNS α=.001 fingerprint",
    "Strict-CNS α=.0001 fingerprint",
    "Whole-body α=.001 fingerprint",
    "Whole-body α=.0001 fingerprint",
    "S-ketamine fingerprint",
    "R-ketamine fingerprint",
    "Metabolite fingerprints",
    "External-drug fingerprints",
    "Family fingerprint pairwise analysis",
    "Global fingerprint pairwise analysis",
    "Family continuous pairwise analysis",
    "Global continuous pairwise analysis",
    "Family fingerprint multivariate",
    "Global fingerprint multivariate",
    "Family continuous multivariate",
    "Global continuous multivariate",
    "Final figure generation",
}


def test_reproducibility_matrix_has_all_required_rows_and_only_allowed_statuses(governed_paths):
    matrix = pd.read_csv(governed_paths["project_root"] / "ANALYSIS_REPRODUCIBILITY_MATRIX.csv")
    assert REQUIRED_ANALYSES <= set(matrix["analysis"])
    assert set(matrix["status"]) <= REPRODUCIBILITY_STATUSES
    assert matrix["analysis"].is_unique


def test_model_status_uses_governed_classifications_and_preserves_trace(governed_paths):
    root = governed_paths["project_root"]
    status = pd.read_csv(root / "MULTIVARIATE_MODEL_STATUS.csv", low_memory=False)
    source = pd.read_csv(root / "results/reference/FINAL_MODEL_STATUS.csv", low_memory=False)
    assert len(status) == len(source) == 117
    assert set(status["status"]) <= MODEL_STATUSES
    assert status["analysis_id"].is_unique
    assert set(status["trace_source"]) == {"results/reference/FINAL_MODEL_STATUS.csv"}
    assert status["trace_record_number"].tolist() == list(range(2, 119))
    comparison = status[["analysis_id", "authority_validation_status"]].merge(
        source[["analysis_id", "status"]], on="analysis_id", validate="one_to_one"
    )
    assert comparison["authority_validation_status"].equals(comparison["status"])
    assert status["status"].value_counts().to_dict() == {
        "CURRENT_SUCCESS": 109,
        "NONESTIMABLE": 8,
    }
