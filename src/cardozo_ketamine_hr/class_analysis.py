# SPDX-License-Identifier: MIT
"""Run class-stratified multivariate and residual analyses.

Stage
-----
This module consumes frozen common-scale profiles, fingerprint calls, pairwise
distances, feature contracts, and class membership after core matrices have
passed their contract checks.

Inputs
------
Inputs are in-memory pandas tables whose compound and feature labels already
use governed identities and frozen coordinates.

Outputs
-------
The public functions return model tables, explicit model-status records, class
summaries, and feature-level query residuals. No files are written here.

Side Effects
------------
None beyond numerical work performed by the imported multivariate routines.

Invariants
----------
Missingness is retained, query overlays remain distinct from external class
members, and failed models are reported as ``NOT_ESTIMABLE`` rather than being
silently substituted.

Lane
----
Portable comparative-analysis lane using frozen scientific inputs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .multivariate import (
    complete_distance_subset,
    em_svd_pca,
    fixed_reference_pca,
    linkage_table,
    mds_table,
    model_tables,
    pcoa_table,
    target_level_matrix,
)
from .pairwise_continuous import metric_matrix


def _blocked(analysis_id: str, representation: str, method: str, reason: str, roster: list[str]) -> dict[str, Any]:
    """Build a standardized status record for an inestimable model.

    Parameters
    ----------
    analysis_id : str
        Stable analysis identifier.
    representation : str
        Input representation requested by the model.
    method : str
        Scientific method that could not be estimated.
    reason : str
        Captured failure reason.
    roster : list of str
        Ordered participating-compound labels.

    Returns
    -------
    dict of str to Any
        Model-status row with unavailable numerical fields represented as
        ``NaN``.
    """
    return {
        "analysis_id": analysis_id,
        "representation": representation,
        "method": method,
        "status": "NOT_ESTIMABLE",
        "reason": reason,
        "sample_count": len(roster),
        "feature_count": np.nan,
        "rank": np.nan,
        "component_count": np.nan,
        "input_roster": "; ".join(roster),
    }


def run_class_models(
    common: pd.DataFrame,
    call_binary: pd.DataFrame,
    pairwise: pd.DataFrame,
    contract: pd.DataFrame,
    classes: pd.DataFrame,
    query_overlays: list[str],
) -> dict[str, pd.DataFrame]:
    """Fit the governed model suite independently within each drug class.

    Parameters
    ----------
    common : pandas.DataFrame
        Compound-by-feature strict18 common-RHR matrix.
    call_binary : pandas.DataFrame
        Compound-by-feature fingerprint matrix using ``1``, ``0``, and
        missing values.
    pairwise : pandas.DataFrame
        Long-form pairwise metric table containing RMS distances.
    contract : pandas.DataFrame
        Frozen feature metadata contract.
    classes : pandas.DataFrame
        Drug membership table with ``class_id``, ``class_label``, and ``drug``.
    query_overlays : list of str
        Query identities included in every class model but excluded from the
        external reference fit.

    Returns
    -------
    dict of str to pandas.DataFrame
        Concatenated scores, loadings, ordinations, linkages, and explicit
        status tables. A result table may be empty when every corresponding
        model is inestimable.

    Notes
    -----
    Model failures are converted to status rows; they do not trigger a change
    of representation, estimator, feature set, or scientific threshold.
    """
    score_frames: list[pd.DataFrame] = []
    loading_frames: list[pd.DataFrame] = []
    pcoa_frames: list[pd.DataFrame] = []
    mds_frames: list[pd.DataFrame] = []
    linkage_frames: list[pd.DataFrame] = []
    statuses: list[dict[str, Any]] = []
    target_matrix = target_level_matrix(common, contract)
    target_contract = pd.DataFrame({"feature_id": target_matrix.columns, "target": target_matrix.columns, "tissue": "TARGET_LEVEL_MEAN"})
    rms = metric_matrix(pairwise, "rms_common_rhr", list(common.index))
    coverage = common.notna().sum(axis=1)

    for class_id, membership in classes.groupby("class_id"):
        label = str(membership["class_label"].iloc[0])
        # Query identities are overlays, not members of the external reference
        # fit; preserving that distinction prevents information leakage.
        external = [drug for drug in membership["drug"] if drug in common.index and drug not in query_overlays]
        participants = list(dict.fromkeys(query_overlays + external))
        prefix = str(class_id)

        analysis_id = prefix + "__JOINT_CONTINUOUS_PCA"
        try:
            model = em_svd_pca(common.loc[participants])
            scores, loadings, status = model_tables(model, analysis_id, "strict18_common_rhr", contract)
            score_frames.append(scores.assign(class_id=class_id, class_label=label))
            loading_frames.append(loadings.assign(class_id=class_id, class_label=label))
            statuses.append({**status, "class_id": class_id, "class_label": label})
        except Exception as exc:
            statuses.append({**_blocked(analysis_id, "strict18_common_rhr", "EM_SVD_MISSINGNESS_AWARE_PCA", str(exc), participants), "class_id": class_id, "class_label": label})

        analysis_id = prefix + "__FIXED_REFERENCE_PCA"
        try:
            if len(external) < 3:
                raise ValueError("Fewer than three numerical external reference compounds")
            scores, loadings, status = fixed_reference_pca(common, external, query_overlays, analysis_id, "strict18_common_rhr", contract)
            score_frames.append(scores.assign(class_id=class_id, class_label=label))
            loading_frames.append(loadings.assign(class_id=class_id, class_label=label))
            statuses.append({**status, "class_id": class_id, "class_label": label})
        except Exception as exc:
            statuses.append({**_blocked(analysis_id, "strict18_common_rhr", "FROZEN_REFERENCE_PCA", str(exc), participants), "class_id": class_id, "class_label": label})

        analysis_id = prefix + "__TARGET_LEVEL_PCA"
        try:
            model = em_svd_pca(target_matrix.loc[participants])
            model["method"] = "TARGET_LEVEL_EM_SVD_PCA"
            scores, loadings, status = model_tables(model, analysis_id, "target_mean_common_rhr", target_contract)
            score_frames.append(scores.assign(class_id=class_id, class_label=label))
            loading_frames.append(loadings.assign(class_id=class_id, class_label=label))
            statuses.append({**status, "class_id": class_id, "class_label": label})
        except Exception as exc:
            statuses.append({**_blocked(analysis_id, "target_mean_common_rhr", "TARGET_LEVEL_EM_SVD_PCA", str(exc), participants), "class_id": class_id, "class_label": label})

        analysis_id = prefix + "__SPARSE_FINGERPRINT_PCA"
        try:
            sparse = call_binary.loc[participants].copy()
            union = [column for column in sparse if sparse[column].eq(1.0).any()]
            if len(union) < 2:
                raise ValueError("Fewer than two union fingerprint calls")
            model = em_svd_pca(sparse[union], min_observed_per_feature=2)
            model["method"] = "SUPPORT_AWARE_SPARSE_FINGERPRINT_EM_SVD_PCA"
            scores, loadings, status = model_tables(model, analysis_id, "alpha001_binary_0_1_NA", contract)
            score_frames.append(scores.assign(class_id=class_id, class_label=label))
            loading_frames.append(loadings.assign(class_id=class_id, class_label=label))
            statuses.append({**status, "class_id": class_id, "class_label": label})
        except Exception as exc:
            statuses.append({**_blocked(analysis_id, "alpha001_binary_0_1_NA", "SUPPORT_AWARE_SPARSE_FINGERPRINT_EM_SVD_PCA", str(exc), participants), "class_id": class_id, "class_label": label})

        subset, excluded = complete_distance_subset(rms.loc[participants, participants], coverage)
        # PCoA, metric MDS, and linkage require one shared complete distance
        # submatrix, so all three use the same deterministic subset.
        complete = rms.loc[subset, subset] if len(subset) >= 3 else pd.DataFrame()
        analysis_id = prefix + "__RMS_PCOA"
        try:
            if complete.empty:
                raise ValueError("No complete RMS distance subset with at least three compounds")
            coordinates, status = pcoa_table(complete, analysis_id)
            pcoa_frames.append(coordinates.assign(class_id=class_id, class_label=label))
            statuses.append({**status, "class_id": class_id, "class_label": label, "excluded_compounds": "; ".join(excluded)})
        except Exception as exc:
            statuses.append({**_blocked(analysis_id, "pairwise_rms", "PCOA", str(exc), participants), "class_id": class_id, "class_label": label})

        analysis_id = prefix + "__WEIGHTED_MDS"
        try:
            if complete.empty:
                raise ValueError("No complete RMS distance subset with at least three compounds")
            coordinates, status = mds_table(complete, analysis_id)
            mds_frames.append(coordinates.assign(class_id=class_id, class_label=label))
            statuses.append({**status, "class_id": class_id, "class_label": label, "excluded_compounds": "; ".join(excluded)})
        except Exception as exc:
            statuses.append({**_blocked(analysis_id, "pairwise_rms", "WEIGHTED_METRIC_MDS", str(exc), participants), "class_id": class_id, "class_label": label})

        analysis_id = prefix + "__AVERAGE_LINKAGE"
        try:
            if complete.empty:
                raise ValueError("No complete RMS distance subset with at least three compounds")
            linked, status = linkage_table(complete, analysis_id)
            linkage_frames.append(linked.assign(class_id=class_id, class_label=label, input_roster="; ".join(complete.index)))
            statuses.append({**status, "class_id": class_id, "class_label": label, "excluded_compounds": "; ".join(excluded)})
        except Exception as exc:
            statuses.append({**_blocked(analysis_id, "pairwise_rms", "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", str(exc), participants), "class_id": class_id, "class_label": label})

    return {
        "scores": pd.concat(score_frames, ignore_index=True) if score_frames else pd.DataFrame(),
        "loadings": pd.concat(loading_frames, ignore_index=True) if loading_frames else pd.DataFrame(),
        "pcoa": pd.concat(pcoa_frames, ignore_index=True) if pcoa_frames else pd.DataFrame(),
        "mds": pd.concat(mds_frames, ignore_index=True) if mds_frames else pd.DataFrame(),
        "linkage": pd.concat(linkage_frames, ignore_index=True) if linkage_frames else pd.DataFrame(),
        "status": pd.DataFrame(statuses),
    }


def summarize_classes(common: pd.DataFrame, call_binary: pd.DataFrame, contract: pd.DataFrame, classes: pd.DataFrame, query: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare a query with each class median and fingerprint union.

    Parameters
    ----------
    common : pandas.DataFrame
        Compound-by-feature common-RHR matrix.
    call_binary : pandas.DataFrame
        Compound-by-feature fingerprint call matrix.
    contract : pandas.DataFrame
        Feature metadata containing target and tissue mappings.
    classes : pandas.DataFrame
        External drug-class membership table.
    query : str
        Query compound label present in both matrices.

    Returns
    -------
    summary : pandas.DataFrame
        One row per class with continuous residual and fingerprint-overlap
        statistics.
    residuals : pandas.DataFrame
        Matched feature-level query-minus-class-median residuals with metadata.

    Notes
    -----
    Class medians ignore missing cells. Fingerprint unions retain the source
    matrix's tested-versus-missing semantics.
    """
    summary_rows = []
    residual_frames = []
    metadata = contract.set_index("feature_id")
    for class_id, membership in classes.groupby("class_id"):
        external = [drug for drug in membership["drug"] if drug in common.index and drug != query]
        label = membership["class_label"].iloc[0]
        if not external:
            summary_rows.append({"class_id": class_id, "class_label": label, "status": "BLOCKED_MISSING_DATA", "numerical_member_count": 0})
            continue
        median = common.loc[external].median(axis=0, skipna=True)
        query_values = common.loc[query]
        # Continuous residuals are restricted to coordinates observed for both
        # the query and the class median; missing coordinates remain absent.
        mask = median.notna() & query_values.notna()
        residual = pd.DataFrame({
            "feature_id": common.columns,
            "query_common_rhr": query_values.to_numpy(),
            "class_median_common_rhr": median.to_numpy(),
        })
        residual["query_minus_class_median"] = residual["query_common_rhr"] - residual["class_median_common_rhr"]
        residual = residual[residual["feature_id"].isin(mask.index[mask])].copy()
        residual["class_id"] = class_id
        residual["class_label"] = label
        residual["target"] = residual["feature_id"].map(metadata["target"])
        residual["tissue"] = residual["feature_id"].map(metadata["tissue"])
        residual_frames.append(residual)
        class_union = call_binary.loc[external].eq(1.0).any(axis=0)
        prevalence = call_binary.loc[external].eq(1.0).mean(axis=0, skipna=True)
        query_calls = call_binary.loc[query].eq(1.0)
        shared = int((query_calls & class_union).sum())
        union = int((query_calls | class_union).sum())
        differences = residual["query_minus_class_median"].dropna()
        summary_rows.append({
            "class_id": class_id,
            "class_label": label,
            "status": "PASS" if len(differences) else "NOT_ESTIMABLE",
            "numerical_member_count": len(external),
            "numerical_members": "; ".join(external),
            "matched_feature_count": int(mask.sum()),
            "mean_absolute_query_minus_class_median": float(differences.abs().mean()) if len(differences) else np.nan,
            "rms_query_minus_class_median": float(np.sqrt(np.mean(differences**2))) if len(differences) else np.nan,
            "class_fingerprint_union_calls": int(class_union.sum()),
            "query_fingerprint_calls": int(query_calls.sum()),
            "shared_fingerprint_calls": shared,
            "fingerprint_union": union,
            "pooled_parent_fingerprint_jaccard": shared / union if union else 1.0,
            "mean_class_call_prevalence": float(prevalence[class_union].mean()) if class_union.any() else 0.0,
        })
    return pd.DataFrame(summary_rows), pd.concat(residual_frames, ignore_index=True) if residual_frames else pd.DataFrame()
