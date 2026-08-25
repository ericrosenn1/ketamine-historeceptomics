"""Construct governed multivariate summaries without hiding missingness limits.

Purpose
-------
Provide PCA, fixed-reference projection, PCoA, metric MDS, and hierarchical
clustering helpers used to summarize HR profiles and pairwise distances.

Scientific stage
----------------
This downstream multivariate stage follows profile/fingerprint and pairwise
construction; it is descriptive rather than causal or class-defining.

Primary inputs
--------------
Compound-by-feature matrices, symmetric distance matrices, feature metadata,
and fixed reference/query rosters.

Primary outputs
---------------
Model dictionaries, score/loading tables, model-status records, ordination
coordinates, complete-subset audit lists, and linkage tables.

Side effects
------------
None; estimators operate in memory and inputs are not mutated.

Invariants
----------
Missing values are never zero-filled, query rows never refit frozen reference
axes, rank limits are reported, deterministic seeds/tie rules are retained,
and EM-SVD nonconvergence is disclosed rather than silently promoted to full
success.

Execution lane
--------------
Used by Smoke synthetic checks and Verify/Full downstream analyses.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from sklearn.manifold import MDS


def complete_case_pca(frame: pd.DataFrame, n_components: int = 2) -> dict[str, Any]:
    """Fit deterministic SVD PCA to features observed for every compound.

    Parameters
    ----------
    frame
        Compound-by-feature matrix; columns containing any missing value are
        excluded.
    n_components
        Requested component count, bounded by the numerical rank.

    Returns
    -------
    dict[str, Any]
        Model arrays, labels, rank, variance fractions, convergence metadata,
        and reconstruction error.

    Raises
    ------
    ValueError
        If no variable complete feature remains or the centered matrix has
        zero rank.

    Notes
    -----
    Columns with population standard deviation at or below ``1e-12`` are
    removed. No imputation is performed.
    """

    complete = frame.dropna(axis=1, how="any").copy()
    variable = complete.columns[complete.std(axis=0, ddof=0) > 1e-12]
    complete = complete[variable]
    if complete.shape[0] < 2 or complete.shape[1] < 1:
        raise ValueError("No estimable complete-case PCA matrix")
    means = complete.mean(axis=0).to_numpy(float)
    centered = complete.to_numpy(float) - means
    u, singular, vt = np.linalg.svd(centered, full_matrices=False)
    rank = int(np.sum(singular > 1e-12))
    components = min(n_components, rank)
    if components < 1:
        raise ValueError("Complete-case PCA has zero rank")
    total = float(np.sum(singular**2))
    return {
        "method": "COMPLETE_CASE_SVD_PCA",
        "row_names": list(complete.index),
        "feature_names": list(complete.columns),
        "means": means,
        "loadings": vt[:components].T,
        "scores": u[:, :components] * singular[:components],
        "explained_variance_ratio": singular[:components] ** 2 / total,
        "n_components": components,
        "rank": rank,
        "n_features": complete.shape[1],
        "converged": True,
        "iterations": 1,
        "observed_reconstruction_rmse": float(np.sqrt(np.mean((centered - (u[:, :components] * singular[:components]) @ vt[:components]) ** 2))),
    }


def em_svd_pca(
    frame: pd.DataFrame,
    n_components: int = 2,
    min_observed_per_feature: int = 2,
    max_iter: int = 300,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Fit missingness-aware PCA by iterative low-rank SVD reconstruction.

    Parameters
    ----------
    frame
        Compound-by-feature matrix containing observed values and ``NaN``.
    n_components
        Requested latent component count, bounded by matrix dimensions/rank.
    min_observed_per_feature
        Minimum observed compound values required to retain a feature.
    max_iter
        Maximum EM-style reconstruction iterations.
    tolerance
        Relative root-mean-square update threshold on missing cells.

    Returns
    -------
    dict[str, Any]
        Model arrays and labels plus convergence, iteration, rank, variance,
        missing-cell update, and observed-cell reconstruction diagnostics.

    Raises
    ------
    ValueError
        If too few rows/features remain or an iteration becomes rank deficient.

    Notes
    -----
    Column means initialize only missing cells. Each iteration updates only
    those missing cells and restores observed values exactly. Exhausting
    ``max_iter`` returns ``converged=False`` so downstream status is
    ``PASS_WITH_LIMITATION`` rather than concealing nonconvergence.
    """

    if frame.shape[0] < 3:
        raise ValueError("EM-SVD PCA requires at least three rows")
    columns = list(frame.columns[frame.notna().sum(axis=0) >= min_observed_per_feature])
    data = frame[columns].copy()
    varying = [column for column in data if len(data[column].dropna()) >= min_observed_per_feature and data[column].dropna().std(ddof=0) > 1e-12]
    data = data[varying]
    if data.shape[1] < 2:
        raise ValueError("EM-SVD PCA retained fewer than two variable columns")
    array = data.to_numpy(float)
    observed = np.isfinite(array)
    missing = ~observed
    # Mean initialization supplies values only for missing cells; observed HR
    # coordinates remain the numerical authority throughout the iterations.
    means = np.nanmean(array, axis=0)
    filled = np.where(observed, array, means)
    rank_bound = min(data.shape[0] - 1, data.shape[1])
    components = min(n_components, rank_bound)
    converged = False
    delta = np.nan
    for iteration in range(1, max_iter + 1):
        means = filled.mean(axis=0)
        centered = filled - means
        u, singular, vt = np.linalg.svd(centered, full_matrices=False)
        effective = int(np.sum(singular > 1e-12))
        use = min(components, effective)
        if use < 1:
            raise ValueError("EM-SVD PCA became rank deficient")
        reconstruction = (u[:, :use] * singular[:use]) @ vt[:use] + means
        if missing.any():
            old = filled[missing].copy()
            new = reconstruction[missing]
            scale = max(float(np.sqrt(np.mean(old**2))), 1e-12)
            delta = float(np.sqrt(np.mean((new - old) ** 2)) / scale)
            filled[missing] = new
        else:
            delta = 0.0
        # Clamp observed cells back to their source values after every update,
        # preventing the low-rank reconstruction from altering evidence.
        filled[observed] = array[observed]
        if delta <= tolerance:
            converged = True
            break
    means = filled.mean(axis=0)
    centered = filled - means
    u, singular, vt = np.linalg.svd(centered, full_matrices=False)
    rank = int(np.sum(singular > 1e-12))
    components = min(components, rank)
    scores = u[:, :components] * singular[:components]
    loadings = vt[:components].T
    reconstruction = scores @ loadings.T + means
    total = float(np.sum(singular**2))
    return {
        "method": "EM_SVD_MISSINGNESS_AWARE_PCA",
        "row_names": list(data.index),
        "feature_names": list(data.columns),
        "means": means,
        "loadings": loadings,
        "scores": scores,
        "explained_variance_ratio": singular[:components] ** 2 / total if total > 0 else np.zeros(components),
        "n_components": components,
        "rank": rank,
        "n_features": data.shape[1],
        "converged": converged,
        "iterations": iteration,
        "relative_missing_update": delta,
        "observed_reconstruction_rmse": float(np.sqrt(np.mean((array[observed] - reconstruction[observed]) ** 2))) if observed.any() else np.nan,
    }


def project_row(row: pd.Series, model: dict[str, Any]) -> dict[str, Any]:
    """Project one partially observed query onto already fitted PCA axes.

    Parameters
    ----------
    row
        Feature-indexed query profile.
    model
        Fitted PCA model containing feature names, means, loadings, and
        component count.

    Returns
    -------
    dict[str, Any]
        Estimation status, observed-feature count, conditioning diagnostic,
        fixed-axis coordinates, and projection RMSE.

    Notes
    -----
    Weighted least squares uses only observed query features. Insufficient,
    rank-deficient, or ill-conditioned support produces explicit non-estimable
    status and ``NaN`` coordinates; reference axes are never refit.
    """

    values = pd.to_numeric(row.reindex(model["feature_names"]), errors="coerce")
    observed = values.notna().to_numpy()
    components = int(model["n_components"])
    if int(observed.sum()) < components + 1:
        return {"status": "NOT_ESTIMABLE_INSUFFICIENT_OBSERVED_FEATURES", "observed_features": int(observed.sum()), "condition_number": np.nan, "coordinates": [np.nan] * components, "projection_rmse": np.nan}
    loadings = np.asarray(model["loadings"])[observed, :components]
    centered = values.to_numpy(float)[observed] - np.asarray(model["means"])[observed]
    if np.linalg.matrix_rank(loadings) < components:
        return {"status": "NOT_ESTIMABLE_RANK_DEFICIENT", "observed_features": int(observed.sum()), "condition_number": np.inf, "coordinates": [np.nan] * components, "projection_rmse": np.nan}
    condition = float(np.linalg.cond(loadings))
    if not np.isfinite(condition) or condition > 1e8:
        return {"status": "NOT_ESTIMABLE_ILL_CONDITIONED", "observed_features": int(observed.sum()), "condition_number": condition, "coordinates": [np.nan] * components, "projection_rmse": np.nan}
    coordinates, *_ = np.linalg.lstsq(loadings, centered, rcond=None)
    rmse = float(np.sqrt(np.mean((centered - loadings @ coordinates) ** 2)))
    return {"status": "ESTIMATED", "observed_features": int(observed.sum()), "condition_number": condition, "coordinates": coordinates.tolist(), "projection_rmse": rmse}


def model_tables(model: dict[str, Any], analysis_id: str, representation: str, feature_meta: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Convert a PCA model into score, loading, and governed status outputs.

    Parameters
    ----------
    model
        Model dictionary returned by a PCA helper.
    analysis_id
        Stable analysis identifier written to all output records.
    representation
        Input representation label, such as common RHR or sparse calls.
    feature_meta
        Optional feature table providing target and tissue annotations.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.DataFrame, dict[str, Any]]
        Score table, loading table, and model-status record.

    Notes
    -----
    A nonconverged EM-SVD point estimate is retained only with
    ``PASS_WITH_LIMITATION`` and an explicit reason.
    """

    score_rows = []
    for index, compound in enumerate(model["row_names"]):
        row: dict[str, Any] = {"analysis_id": analysis_id, "compound": compound, "representation": representation, "method": model["method"]}
        for component in range(model["n_components"]):
            row[f"PC{component + 1}"] = float(model["scores"][index, component])
            row[f"PC{component + 1}_variance_fraction"] = float(model["explained_variance_ratio"][component])
        score_rows.append(row)
    metadata = feature_meta.set_index("feature_id") if feature_meta is not None and "feature_id" in feature_meta.columns else pd.DataFrame()
    loading_rows = []
    for index, feature in enumerate(model["feature_names"]):
        row = {"analysis_id": analysis_id, "feature_id": feature, "representation": representation}
        if len(metadata) and feature in metadata.index:
            meta = metadata.loc[feature]
            row.update({"target": meta.get("target", ""), "tissue": meta.get("tissue", "")})
        for component in range(model["n_components"]):
            row[f"PC{component + 1}_loading"] = float(model["loadings"][index, component])
        loading_rows.append(row)
    # Preserve the inherited point estimate while exposing nonconvergence in
    # machine-readable status; callers must not reinterpret it as full PASS.
    status = {
        "analysis_id": analysis_id,
        "representation": representation,
        "method": model["method"],
        "status": "PASS" if model.get("converged", True) else "PASS_WITH_LIMITATION",
        "reason": "" if model.get("converged", True) else "EM-SVD did not meet convergence tolerance; point estimate retained",
        "sample_count": len(model["row_names"]),
        "feature_count": model["n_features"],
        "rank": model["rank"],
        "component_count": model["n_components"],
        "explained_variance_sum": float(np.sum(model["explained_variance_ratio"])),
        "iterations": model.get("iterations", 1),
        "converged": model.get("converged", True),
        "observed_reconstruction_rmse": model.get("observed_reconstruction_rmse", np.nan),
        "input_roster": "; ".join(model["row_names"]),
    }
    return pd.DataFrame(score_rows), pd.DataFrame(loading_rows), status


def fixed_reference_pca(
    matrix: pd.DataFrame,
    reference_compounds: list[str],
    query_compounds: list[str],
    analysis_id: str,
    representation: str,
    feature_meta: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fit PCA on a fixed reference roster and project query compounds.

    Parameters
    ----------
    matrix
        Compound-by-feature matrix containing reference and query rows.
    reference_compounds
        Rows allowed to determine means and PCA axes.
    query_compounds
        Rows projected after the reference model is frozen.
    analysis_id
        Stable output analysis identifier.
    representation
        Input-representation label.
    feature_meta
        Optional target/tissue annotations for loading rows.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.DataFrame, dict[str, Any]]
        Combined reference/query scores, frozen loadings, and status metadata.

    Notes
    -----
    Query compounds never contribute to fitting, axis orientation, means, or
    variance fractions. Their coordinates use observed-feature least squares.
    """

    # Fit once on the declared reference roster; the following loop performs
    # projection only and therefore cannot move or refit those reference axes.
    model = em_svd_pca(matrix.loc[reference_compounds], n_components=2)
    model["method"] = "FROZEN_REFERENCE_EM_SVD_PCA_WITH_WLS_QUERY_PROJECTION"
    scores, loadings, status = model_tables(model, analysis_id, representation, feature_meta)
    projections = []
    projection_statuses = []
    for compound in query_compounds:
        projected = project_row(matrix.loc[compound], model)
        row: dict[str, Any] = {"analysis_id": analysis_id, "compound": compound, "representation": representation, "method": model["method"], "row_role": "PROJECTED_QUERY"}
        for component, coordinate in enumerate(projected["coordinates"], start=1):
            row[f"PC{component}"] = coordinate
            row[f"PC{component}_variance_fraction"] = float(model["explained_variance_ratio"][component - 1])
        scores = pd.concat([scores, pd.DataFrame([row])], ignore_index=True)
        projection_statuses.append(projected["status"])
        projections.append({"compound": compound, **projected})
    status["query_projection_status"] = "; ".join(projection_statuses)
    status["query_projection_details"] = str(projections)
    status["reference_roster"] = "; ".join(reference_compounds)
    status["reference_axes_refit_with_query"] = False
    if any(value != "ESTIMATED" for value in projection_statuses):
        status["status"] = "PASS_WITH_LIMITATION"
        status["reason"] = "At least one query projection was not estimable"
    return scores, loadings, status


def target_level_matrix(profile_matrix: pd.DataFrame, contract: pd.DataFrame) -> pd.DataFrame:
    """Average feature-level profiles within targets while preserving missingness.

    Parameters
    ----------
    profile_matrix
        Compound-by-feature values.
    contract
        Mapping from ``feature_id`` to target.

    Returns
    -------
    pandas.DataFrame
        Compound-by-target means calculated from available feature values.
    """

    target_by_feature = contract.set_index("feature_id")["target"]
    groups = {}
    for target, features in target_by_feature.groupby(target_by_feature):
        columns = [feature for feature in features.index if feature in profile_matrix.columns]
        groups[target] = profile_matrix[columns].mean(axis=1, skipna=True)
    return pd.DataFrame(groups, index=profile_matrix.index)


def complete_distance_subset(distance: pd.DataFrame, coverage: pd.Series | None = None) -> tuple[list[str], list[str]]:
    """Select a deterministic complete subset from an incomplete distance matrix.

    Parameters
    ----------
    distance
        Square pairwise distance matrix that may contain missing off-diagonals.
    coverage
        Optional per-compound support used to break equal-missingness ties.

    Returns
    -------
    tuple[list[str], list[str]]
        Retained compound order and the ordered exclusion audit trail.

    Notes
    -----
    At each step the row with most missing distances is removed. Ties remove
    lower coverage first, then lexical label order, making the subset stable.
    """

    current = list(distance.index)
    excluded: list[str] = []
    while len(current) >= 3:
        subset = distance.loc[current, current].copy()
        values = subset.to_numpy(copy=True)
        np.fill_diagonal(values, 0.0)
        missing = pd.DataFrame(np.isnan(values), index=current, columns=current)
        if not missing.to_numpy().any():
            return current, excluded
        counts = missing.sum(axis=1)
        worst = list(counts[counts == counts.max()].index)
        # Deterministic tie handling: lower support is excluded first; equal
        # support resolves lexically rather than by incidental dataframe order.
        worst.sort(key=lambda item: ((coverage.get(item, 0) if coverage is not None else 0), item))
        drop = worst[0]
        current.remove(drop)
        excluded.append(drop)
    return current, excluded


def pcoa(distance: pd.DataFrame, n_components: int = 2) -> dict[str, Any]:
    """Construct classical principal coordinates from a complete distance matrix.

    Parameters
    ----------
    distance
        Symmetric, complete square distance matrix with matching roster order.
    n_components
        Requested number of positive-eigenvalue axes.

    Returns
    -------
    dict[str, Any]
        Roster, coordinates, all eigenvalues, positive-variance fractions, and
        retained component count.

    Raises
    ------
    ValueError
        If fewer than three rows, missing values, asymmetry, or no positive
        eigenvalue prevents estimation.
    """

    values = distance.to_numpy(dtype=float, copy=True)
    if values.shape[0] < 3 or np.isnan(values).any():
        raise ValueError("PCoA requires a complete distance matrix with at least three rows")
    if not np.allclose(values, values.T, atol=1e-10):
        raise ValueError("Distance matrix is not symmetric")
    count = values.shape[0]
    centering = np.eye(count) - np.ones((count, count)) / count
    # Classical PCoA double-centers squared distances to obtain the Gram matrix.
    gram = -0.5 * centering @ (values**2) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(gram)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues, eigenvectors = eigenvalues[order], eigenvectors[:, order]
    positive = eigenvalues > 1e-12
    components = min(n_components, int(positive.sum()))
    if components < 1:
        raise ValueError("PCoA has no positive eigenvalue")
    coordinates = eigenvectors[:, :components] * np.sqrt(eigenvalues[:components])
    positive_total = float(eigenvalues[positive].sum())
    return {"row_names": list(distance.index), "coordinates": coordinates, "eigenvalues": eigenvalues, "explained_positive_fraction": eigenvalues[:components] / positive_total, "n_components": components}


def pcoa_table(distance: pd.DataFrame, analysis_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Render PCoA coordinates and model status as tabular outputs.

    Parameters
    ----------
    distance
        Complete symmetric distance matrix.
    analysis_id
        Stable identifier included in coordinate and status records.

    Returns
    -------
    tuple[pandas.DataFrame, dict[str, Any]]
        Coordinate table and governed PCoA status record.
    """

    model = pcoa(distance)
    rows = []
    for index, compound in enumerate(model["row_names"]):
        row: dict[str, Any] = {"analysis_id": analysis_id, "compound": compound}
        for component in range(model["n_components"]):
            row[f"Axis{component + 1}"] = float(model["coordinates"][index, component])
            row[f"Axis{component + 1}_positive_variance_fraction"] = float(model["explained_positive_fraction"][component])
        rows.append(row)
    status = {"analysis_id": analysis_id, "representation": "pairwise_rms", "method": "PCOA", "status": "PASS", "reason": "", "sample_count": len(distance), "feature_count": np.nan, "rank": int(np.sum(model["eigenvalues"] > 1e-12)), "component_count": model["n_components"], "explained_variance_sum": float(np.sum(model["explained_positive_fraction"])), "input_roster": "; ".join(distance.index)}
    return pd.DataFrame(rows), status


def mds_table(distance: pd.DataFrame, analysis_id: str, seed: int = 20260813) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit deterministic two-dimensional metric MDS and return tables.

    Parameters
    ----------
    distance
        Complete precomputed distance matrix.
    analysis_id
        Stable identifier included in output records.
    seed
        Fixed random seed governing MDS initialization.

    Returns
    -------
    tuple[pandas.DataFrame, dict[str, Any]]
        Two-axis coordinate table and status record containing stress and seed.

    Notes
    -----
    Reproducibility depends on retaining the fixed seed and estimator settings.
    """

    estimator = MDS(n_components=2, dissimilarity="precomputed", random_state=seed, n_init=8, max_iter=1000, normalized_stress="auto")
    coordinates = estimator.fit_transform(distance.to_numpy(float))
    frame = pd.DataFrame({"analysis_id": analysis_id, "compound": distance.index, "MDS1": coordinates[:, 0], "MDS2": coordinates[:, 1]})
    status = {"analysis_id": analysis_id, "representation": "pairwise_rms", "method": "WEIGHTED_METRIC_MDS", "status": "PASS", "reason": "", "sample_count": len(distance), "feature_count": np.nan, "rank": np.nan, "component_count": 2, "stress": float(estimator.stress_), "seed": seed, "input_roster": "; ".join(distance.index)}
    return frame, status


def linkage_table(distance: pd.DataFrame, analysis_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build average-linkage hierarchy from a complete distance matrix.

    Parameters
    ----------
    distance
        Symmetric square distance matrix.
    analysis_id
        Stable identifier included in linkage and status records.

    Returns
    -------
    tuple[pandas.DataFrame, dict[str, Any]]
        SciPy linkage rows and a governed clustering status record.

    Raises
    ------
    ValueError
        If ``squareform`` detects an invalid distance matrix.
    """

    values = distance.to_numpy(dtype=float, copy=True)
    condensed = squareform(values, checks=True)
    linked = linkage(condensed, method="average")
    frame = pd.DataFrame(linked, columns=["left_cluster", "right_cluster", "distance", "member_count"])
    frame.insert(0, "analysis_id", analysis_id)
    status = {"analysis_id": analysis_id, "representation": "pairwise_rms", "method": "AVERAGE_LINKAGE_HIERARCHICAL_CLUSTERING", "status": "PASS", "reason": "", "sample_count": len(distance), "feature_count": np.nan, "rank": np.nan, "component_count": np.nan, "input_roster": "; ".join(distance.index)}
    return frame, status
