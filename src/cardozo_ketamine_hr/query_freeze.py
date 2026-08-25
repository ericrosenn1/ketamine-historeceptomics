# SPDX-License-Identifier: MIT
"""Freeze the pooled-parent query and project it to the common RHR scale.

Stage
-----
Query freezing is the first numerical stage after authority resolution. It
validates the pooled-parent contracts before downstream comparisons begin.

Inputs
------
Path mappings identify frozen pooled HR, call, activity, expression-feature,
and common-scale model authorities.

Outputs
-------
The freeze writes immutable derivative query tables and manifests, then returns
the loaded and mapped tables for downstream stages.

Side Effects
------------
Reads frozen CSV/Parquet/joblib inputs, creates the query-output directory,
writes derivative CSV/Parquet/JSON files, and attempts to mark files read-only.

Invariants
----------
Expected dimensions and call counts are exact, alpha 0.0001 calls are a subset
of alpha 0.001 calls, missing values remain ``NaN``, and the frozen common-scale
model is applied without refitting.

Lane
----
Portable pooled-parent query-authority lane.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm

from .tissue_normalization import canonical_tissue_key, display_tissue
from .utilities import copy_small_file, now_iso, sha256_file, write_json, write_table


EXPECTED = {
    "full_targets": 58,
    "full_tissues": 77,
    "full_rows": 4466,
    "strict_targets": 58,
    "strict_tissues": 18,
    "strict_rows": 1044,
    "calls_001": 19,
    "calls_0001": 14,
    "missing_expression_targets": 18,
}


def _truthy(values: pd.Series) -> pd.Series:
    """Normalize supported textual truth values to a Boolean mask.

    Parameters
    ----------
    values : pandas.Series
        Source flag values.

    Returns
    -------
    pandas.Series
        Boolean membership mask recognizing ``1``, ``true``, ``yes``, and
        ``y`` case-insensitively.
    """
    return values.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def feature_contracts(feature_dictionary: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load ordered full-human and strict-CNS feature contracts.

    Parameters
    ----------
    feature_dictionary : pathlib.Path
        Frozen Parquet feature dictionary.

    Returns
    -------
    full : pandas.DataFrame
        Features flagged for the 77-tissue full-human contract.
    strict : pandas.DataFrame
        Features flagged for the strict-CNS contract.

    Notes
    -----
    Canonical target and display-tissue columns are copied without inventing
    classifications, and source ``feature_order`` controls row order.
    """
    frame = pd.read_parquet(feature_dictionary)
    keep = [
        "feature_order", "feature_id", "target_canonical_id", "gene_symbol", "target_grain_class",
        "tissue_canonical_id", "tissue_label", "expression_profile_id", "expression_Z",
        "STRICT_CNS_HUMAN", "FULL_HUMAN_77_TISSUE_EXACT_PROTEIN",
    ]
    frame = frame[[column for column in keep if column in frame.columns]].copy()
    frame["target"] = frame["target_canonical_id"].astype(str)
    frame["tissue"] = frame["tissue_label"].astype(str)
    frame["tissue_key"] = frame["tissue"].map(canonical_tissue_key)
    strict = frame[_truthy(frame["STRICT_CNS_HUMAN"])].copy()
    strict = strict.sort_values("feature_order").reset_index(drop=True)
    full = frame[_truthy(frame["FULL_HUMAN_77_TISSUE_EXACT_PROTEIN"])].copy()
    full = full.sort_values("feature_order").reset_index(drop=True)
    return full, strict


def project_common_rhr(raw_values: pd.Series | np.ndarray, model_bundle: Path) -> np.ndarray:
    """Project raw HR values through the frozen weighted empirical transform.

    Parameters
    ----------
    raw_values : pandas.Series or numpy.ndarray
        Raw HR values; non-finite entries remain missing.
    model_bundle : pathlib.Path
        Frozen joblib bundle containing knot values and weights.

    Returns
    -------
    numpy.ndarray
        Normal-score common-RHR values with the original shape.

    Notes
    -----
    Duplicate knots are aggregated stably. Exact knots use weighted mid-ranks;
    non-exact values use the governed left/right cumulative placement. Tail
    probabilities are clipped only to avoid infinite normal quantiles.
    """
    bundle = joblib.load(model_bundle)
    knots = bundle["knots"].copy()
    value_col = "value" if "value" in knots.columns else "latent_HR_raw"
    x = pd.to_numeric(knots[value_col], errors="coerce").to_numpy(float)
    weights = pd.to_numeric(knots["weight"], errors="coerce").to_numpy(float)
    mask = np.isfinite(x) & np.isfinite(weights) & (weights > 0)
    x, weights = x[mask], weights[mask]
    order = np.argsort(x, kind="mergesort")
    x, weights = x[order], weights[order]
    # Aggregate equal frozen knots before computing the weighted empirical CDF;
    # this preserves their combined mass independently of source row order.
    unique, first = np.unique(x, return_index=True)
    grouped = np.add.reduceat(weights, first)
    before = np.concatenate([[0.0], np.cumsum(grouped)[:-1]])
    query = np.asarray(raw_values, dtype=float)
    result = np.full(query.shape, np.nan, dtype=float)
    finite_query = np.isfinite(query)
    q = query[finite_query]
    position = np.clip(np.searchsorted(unique, q, side="left"), 0, len(unique) - 1)
    exact = unique[position] == q
    percentile = np.empty(q.shape, dtype=float)
    # Exact values receive the midpoint of their weight block; values between
    # knots receive the cumulative mass immediately to their left.
    percentile[exact] = (before[position[exact]] + 0.5 * grouped[position[exact]]) / grouped.sum()
    left = ~exact & (q < unique[position])
    percentile[left] = before[position[left]] / grouped.sum()
    right = ~exact & ~left
    right_position = np.searchsorted(unique, q[right], side="right") - 1
    percentile[right] = (before[right_position] + grouped[right_position]) / grouped.sum()
    result[finite_query] = norm.ppf(np.clip(percentile, 1e-6, 1 - 1e-6))
    return result


def map_pooled_to_contract(pooled: pd.DataFrame, contract: pd.DataFrame, raw_col: str, model_bundle: Path) -> pd.DataFrame:
    """Map pooled rows to a feature contract and apply frozen scale projection.

    Parameters
    ----------
    pooled : pandas.DataFrame
        Pooled-parent rows with canonical target and tissue identifiers.
    contract : pandas.DataFrame
        Feature contract unique by target/tissue coordinate.
    raw_col : str
        Column containing raw HR values.
    model_bundle : pathlib.Path
        Frozen common-scale transform bundle.

    Returns
    -------
    pandas.DataFrame
        Source rows augmented with common feature IDs, feature order, projected
        values, and compatibility flags.

    Raises
    ------
    pandas.errors.MergeError
        If the contract violates the required many-to-one mapping.
    """
    key = contract[["target_canonical_id", "tissue_canonical_id", "feature_id", "feature_order", "tissue_label"]].copy()
    key = key.rename(columns={"feature_id": "feature_id_common", "tissue_label": "contract_tissue_label"})
    merged = pooled.merge(
        key,
        left_on=["canonical_target_id", "tissue_id"],
        right_on=["target_canonical_id", "tissue_canonical_id"],
        how="left",
        validate="many_to_one",
    )
    merged["raw_hr"] = pd.to_numeric(merged[raw_col], errors="coerce")
    merged["common_rhr"] = project_common_rhr(merged["raw_hr"], model_bundle)
    merged.loc[merged["feature_id_common"].isna(), "common_rhr"] = np.nan
    merged["common_scale_compatible"] = merged["feature_id_common"].notna()
    return merged


def freeze_query(paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    """Validate, persist, and freeze the pooled-parent query authority.

    Parameters
    ----------
    paths : dict of str to pathlib.Path
        Resolved frozen input and model paths required by the query lane.
    output_dir : pathlib.Path
        Derivative query-authority destination.

    Returns
    -------
    dict of str to Any
        Loaded authorities, projected full/strict profiles, feature contracts,
        observed counts, and the input manifest.

    Raises
    ------
    RuntimeError
        If exact dimensions, call counts, call-set nesting, or call-to-contract
        mappings violate the frozen query contract.

    Side Effects
    ------------
    Writes query tables and manifests and attempts to mark output files
    owner-readable with mode ``0o400``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    full = pd.read_parquet(paths["pooled_full_hr"])
    strict = pd.read_csv(paths["pooled_strict_hr"], low_memory=False)
    calls001 = pd.read_csv(paths["pooled_calls_001"], low_memory=False)
    calls0001 = pd.read_csv(paths["pooled_calls_0001"], low_memory=False)
    missing = pd.read_csv(paths["pooled_missing_expression"], low_memory=False)
    activity = pd.read_csv(paths["pooled_activity"], low_memory=False)
    activity_summary = pd.read_csv(paths["pooled_activity_summary"], low_memory=False)
    observed = {
        "full_targets": int(full["canonical_target_id"].nunique()),
        "full_tissues": int(full["tissue_id"].nunique()),
        "full_rows": int(len(full)),
        "strict_targets": int(strict["canonical_target_id"].nunique()),
        "strict_tissues": int(strict["tissue_id"].nunique()),
        "strict_rows": int(len(strict)),
        "calls_001": int(len(calls001)),
        "calls_0001": int(len(calls0001)),
        "missing_expression_targets": int(missing["canonical_target_id"].nunique()),
    }
    if observed != EXPECTED:
        raise RuntimeError(f"Pooled query contract failed: {observed} != {EXPECTED}")
    # The stricter call set must be nested in the more permissive call set;
    # failure stops the lane rather than repairing calls.
    if not set(calls0001["feature_id"]).issubset(set(calls001["feature_id"])):
        raise RuntimeError("alpha=.0001 pooled call set is not a subset of alpha=.001")

    full_contract, strict_contract = feature_contracts(paths["feature_dictionary"])
    strict_mapped = map_pooled_to_contract(strict, strict_contract, "hr_numeric_collapsed", paths["common_model_bundle"])
    full_mapped = map_pooled_to_contract(full, full_contract, "HR_numeric_boundary_or_exact", paths["common_model_bundle"])

    call_key = strict_mapped[["canonical_target_id", "tissue_id", "feature_id_common"]].drop_duplicates()
    calls001 = calls001.merge(call_key, on=["canonical_target_id", "tissue_id"], how="left", validate="one_to_one")
    calls0001 = calls0001.merge(call_key, on=["canonical_target_id", "tissue_id"], how="left", validate="one_to_one")
    if calls001["feature_id_common"].isna().any() or calls0001["feature_id_common"].isna().any():
        raise RuntimeError("A pooled fingerprint call cannot be mapped to the external common-scale contract")

    write_table(full, output_dir / "POOLED_PARENT_FULL77_HR_AUTHORITY", parquet=True)
    write_table(strict, output_dir / "POOLED_PARENT_STRICT18_HR_AUTHORITY", parquet=True)
    write_table(calls001, output_dir / "POOLED_PARENT_FINGERPRINT_ALPHA_0p001", parquet=True)
    write_table(calls0001, output_dir / "POOLED_PARENT_FINGERPRINT_ALPHA_0p0001", parquet=True)
    write_table(missing, output_dir / "POOLED_PARENT_MISSING_EXPRESSION_TARGETS", parquet=False)
    write_table(activity, output_dir / "POOLED_PARENT_TARGET_ACTIVITY_INPUT", parquet=False)
    write_table(activity_summary, output_dir / "POOLED_PARENT_TARGET_ACTIVITY_SUMMARY", parquet=False)
    write_table(strict_mapped, output_dir / "POOLED_PARENT_STRICT18_COMMON_SCALE_PROJECTION", parquet=True)
    write_table(full_mapped, output_dir / "POOLED_PARENT_FULL77_COMMON_SCALE_PROJECTION", parquet=True)
    expression_ids = pd.DataFrame([{
        "expression_profile_id": "; ".join(sorted(full["expression_profile_id"].dropna().astype(str).unique())),
        "expression_ddof": "; ".join(sorted(full["expression_ddof"].dropna().astype(str).unique())),
        "feature_dictionary": str(paths["feature_dictionary"]),
        "common_scale_model": str(paths["common_model_bundle"]),
    }])
    write_table(expression_ids, output_dir / "EXPRESSION_AND_SCALE_AUTHORITY_IDENTIFIERS", parquet=False)

    source_files = [
        paths["pooled_full_hr"], paths["pooled_strict_hr"], paths["pooled_calls_001"],
        paths["pooled_calls_0001"], paths["pooled_missing_expression"], paths["pooled_activity"],
        paths["pooled_activity_summary"], paths["feature_dictionary"], paths["common_model_bundle"],
    ]
    manifest = pd.DataFrame([{
        "role": "QUERY_INPUT",
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "status": "FROZEN_SOURCE_UNMODIFIED",
    } for path in source_files])
    write_table(manifest, output_dir / "QUERY_INPUT_MANIFEST", parquet=False)
    write_json(output_dir / "QUERY_MANIFEST.json", {
        "generated": now_iso(),
        "compound_id": "POOLED_PARENT_KETAMINE",
        "display_label": "Ketamine, pooled parent",
        "counts": observed,
        "common_scale_compatible_strict_rows": int(strict_mapped["common_scale_compatible"].sum()),
        "common_scale_excluded_strict_rows": int((~strict_mapped["common_scale_compatible"]).sum()),
        "common_scale_excluded_targets": sorted(strict_mapped.loc[~strict_mapped["common_scale_compatible"], "canonical_target_id"].unique()),
        "missingness_policy": "NA preserved; no zero filling",
    })
    for file in output_dir.iterdir():
        if file.is_file():
            try:
                # Owner-readable marking avoids exposing frozen outputs to
                # other local accounts. Content hashes and contract checks
                # remain the portable authority.
                os.chmod(file, 0o400)
            except OSError:
                pass
    return {
        "full": full,
        "strict": strict,
        "calls001": calls001,
        "calls0001": calls0001,
        "strict_mapped": strict_mapped,
        "full_mapped": full_mapped,
        "strict_contract": strict_contract,
        "full_contract": full_contract,
        "counts": observed,
        "input_manifest": manifest,
    }
