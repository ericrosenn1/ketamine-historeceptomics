"""Resolve governed paths within one explicitly supplied external project.

Stage: external-authority routing before comparative or recovered processing.
Inputs: a project-root path or ``CARDOZO_HR_EXTERNAL_PROJECT_ROOT`` value.
Outputs: a stable role-to-path mapping; no scientific table is loaded here.
Side effects: resolves paths only and never creates, edits, or scans for files.
Invariants: no newest-directory guessing, fallback root, or silent substitution.
Lane: external-authority comparative audit and recovered Full processing.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT_DEFAULT = (
    Path(os.environ["CARDOZO_HR_EXTERNAL_PROJECT_ROOT"]).expanduser()
    if os.environ.get("CARDOZO_HR_EXTERNAL_PROJECT_ROOT")
    else None
)


def discover(project_root: Path | None = PROJECT_ROOT_DEFAULT) -> dict[str, Path]:
    """Return governed source paths below an explicitly supplied project root."""

    if project_root is None:
        raise ValueError(
            "An external project root is required; pass project_root or set "
            "CARDOZO_HR_EXTERNAL_PROJECT_ROOT"
        )
    root = project_root.resolve()
    pooled_base = (
        root
        / "02_HR_SCORES"
        / "Ketamine_Family"
        / "Pooled_Parent_Ketamine_Activity_20260813_072204"
        / "Species_Cleanup_Bounded_v2_20260813_081429"
        / "Forensic_Finalization_v3_20260813_083903"
        / "Final_Activity_v4_20260813_084842"
    )
    expanded = pooled_base / "Full_Tissue_HR_v1_20260813_085417" / "Expanded58_Full_Tissue_HR_v2_20260813_123324"
    strict = expanded / "Strict18_Fingerprint_v1_20260813_124501"
    hpf = (
        root
        / "01_AUTHORITIES"
        / "Ketamine_HPF"
        / "Human_Priority_Mammalian_Fallback_U1_Fingerprint_Authority_20260807_051641_664"
    )
    common = (
        root
        / "01_AUTHORITIES"
        / "External_Drug_CommonScale"
        / "E1_E4_External_CommonScale_Multivariate_Ready_20260804_202946_056"
    )
    prior = (
        root
        / "04_KETAMINE_VS_DRUGS"
        / "Final_OneShot"
        / "S_Ketamine_Expanded_Strict18_Complete_Analysis_20260812_210153"
    )
    paper = (
        root
        / "04_KETAMINE_VS_DRUGS"
        / "Paper_Facing"
        / "S_Ketamine_Paper_Facing_Fingerprint_Comparisons_20260813_011432"
    )
    e7 = (
        root
        / "03_DRUG_ATLAS"
        / "Multivariate"
        / "E7_Five_Metabolite_CommonScale_CNS_Fingerprints_Multivariate_Ready_20260804_210051"
    )
    e7_final = (
        root
        / "03_DRUG_ATLAS"
        / "Multivariate"
        / "E7_Final_Multivariate_Analysis_With_E1_E4_Reference_20260805_033655"
    )
    family_matrices = hpf / "07_SPARSE_AND_CONTINUOUS_MATRICES" / "U1_HUMAN_PRIORITY_MAMMALIAN_FALLBACK"
    family_calls = hpf / "06_FINGERPRINT_CALLS" / "U1_HUMAN_PRIORITY_MAMMALIAN_FALLBACK"
    paths = {
        "project_root": root,
        "current_authorities": root / "00_START_HERE" / "CURRENT_AUTHORITIES.md",
        "project_index": root / "00_START_HERE" / "PROJECT_INDEX.md",
        "current_results": root / "00_START_HERE" / "CURRENT_RESULTS.md",
        "pooled_activity": pooled_base / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv",
        "pooled_activity_summary": pooled_base / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FINAL_V4.csv",
        "pooled_full_hr": expanded / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.parquet",
        "pooled_full_hr_csv": expanded / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.csv",
        "pooled_missing_expression": expanded / "POOLED_PARENT_KETAMINE_MISSING_EXPRESSION_TARGETS_EXPANDED58_V2.csv",
        "pooled_old_coordinate_crosscheck": expanded / "HR_V1_VS_EXPANDED58_CROSSCHECK.csv",
        "pooled_strict_hr": strict / "POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv",
        "pooled_calls_001": strict / "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p001_V1.csv",
        "pooled_calls_0001": strict / "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p0001_V1.csv",
        "pooled_fingerprint_combined": strict / "POOLED_PARENT_KETAMINE_FINGERPRINT_COMBINED_V1.csv",
        "feature_dictionary": hpf / "01_INPUT_AUTHORITIES" / "FINAL_FEATURE_DICTIONARY.parquet",
        "family_raw_matrix": family_matrices / "RAW_HR_QUERY_MATRIX_4x5852.csv",
        "family_common_matrix": family_matrices / "COMMON_RHR_QUERY_MATRIX_4x5852.csv",
        "family_sparse_001": family_matrices / "SPARSE_FINGERPRINT_MATRIX_STRICT_CNS_ALPHA_001.csv",
        "family_sparse_0001": family_matrices / "SPARSE_FINGERPRINT_MATRIX_STRICT_CNS_ALPHA_0001.csv",
        "family_calls_001": family_calls / "FINGERPRINT_CALLS_STRICT_CNS_ALPHA_001.parquet",
        "family_calls_0001": family_calls / "FINGERPRINT_CALLS_STRICT_CNS_ALPHA_0001.parquet",
        "common_model_bundle": common / "04_COMMON_SCALE_MODEL" / "COMMON_SCALE_MODEL_BUNDLE.joblib",
        "common_knots": common / "04_COMMON_SCALE_MODEL" / "HR_REFERENCE_CDF_KNOTS.parquet",
        "external_master": common / "05_GLOBAL_LONG_TABLES" / "E1_E4_EXTERNAL_COMMON_RHR_MASTER_LONG.parquet",
        "prior_root": prior,
        "prior_profiles": prior / "02_UNIFIED_PROFILES" / "ALL_NUMERIC_DRUGS_STRICT18_LONG.parquet",
        "prior_pairwise": prior / "04_PAIRWISE_METRICS" / "ALL_UNORDERED_DRUG_PAIR_METRICS.parquet",
        "prior_calls_001": prior / "03_FRESH_FINGERPRINTS" / "FRESH_GESD_CALLS_ALPHA001.parquet",
        "prior_calls_0001": prior / "03_FRESH_FINGERPRINTS" / "FRESH_GESD_CALLS_ALPHA0001.parquet",
        "prior_class_registry": prior / "01_INPUTS" / "CLASS_MEMBERSHIP_MANY_TO_MANY.csv",
        "prior_figure_index": prior / "08_FIGURES" / "FIGURE_INDEX.csv",
        "prior_model_status": prior / "07_MULTIVARIATE" / "STATUS.csv",
        "prior_manifest": prior / "15_MANIFEST" / "MANIFEST.csv",
        "prior_paper_root": paper,
        "prior_paper_figure_index": paper / "00_RUN_CONTROL" / "FIGURE_INDEX.csv",
        "prior_paper_table_index": paper / "00_RUN_CONTROL" / "TABLE_INDEX.csv",
        "prior_paper_manifest": paper / "08_MANIFEST" / "MANIFEST.csv",
        "e7_root": e7,
        "e7_identity_accounting": e7 / "01_AUTHORITIES" / "E7_ALL_GOVERNED_IDENTITY_ACCOUNTING.csv",
        "e7_numeric_compounds": e7 / "01_AUTHORITIES" / "E7_FIVE_NUMERIC_COMPOUNDS.csv",
        "e7_raw_matrix": e7 / "05_E7_PROFILES" / "E7_CNS_RAW_HR_MEAN_COMPOUND_BY_FEATURE.csv",
        "e7_common_matrix": e7 / "05_E7_PROFILES" / "E7_CNS_COMMON_RHR_MEAN_COMPOUND_BY_FEATURE.csv",
        "e7_primary_calls": e7 / "06_FINGERPRINTS" / "E7_CNS_FINGERPRINT_CALLS_PRIMARY.csv",
        "e7_sensitivity_calls": e7 / "06_FINGERPRINTS" / "E7_CNS_FINGERPRINT_CALLS_SENSITIVITY.csv",
        "e7_release_manifest": e7 / "RELEASE_MANIFEST.csv",
        "e7_final_root": e7_final,
        "e7_final_manifest": e7_final / "MASTER_MANIFEST.csv",
        "e7_hydroxy_identity_audit": e7_final / "02_IDENTITY_AND_METHODS" / "HYDROXYKETAMINE_IDENTITY_AUDIT.csv",
    }
    missing = [name for name, path in paths.items() if name not in {"project_root", "prior_root", "prior_paper_root", "e7_root", "e7_final_root"} and not path.exists()]
    if missing:
        raise FileNotFoundError("Missing governed inputs: " + ", ".join(missing))
    return paths
