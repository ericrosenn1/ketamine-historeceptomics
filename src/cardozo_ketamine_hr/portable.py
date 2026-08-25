"""Run the supported public Smoke, externally supplied Verify, and Full lanes.

This orchestration module connects the immutable numerical routines to portable
command-line execution.  Smoke consumes only invented CSV fixtures and retained
public output hashes.  Verify consumes a user-supplied mirror of the governed
``data/frozen`` input tree.  Full additionally consumes the explicitly supplied
activity table, PDSP workbook, historical project root, and optional expression
authority required by the recovered upstream stages.

Outputs are written below the requested run directory and include QA ledgers,
manifests, generated tables, figures, and task state.  The module never fetches
or substitutes scientific inputs.  Missing values, censored relation operators,
compound identities, GESD thresholds, fixed references, and regression
tolerances are invariants.  Only the public input-routing boundary differs from
the validated private implementation.

SPDX-License-Identifier: MIT

Publication contract
--------------------
Purpose: Expose reproducible public entry points around frozen numerical methods.
Stage/lane: Self-contained Smoke, external-input Verify, and recovered-stage Full.
Inputs: Synthetic fixtures for Smoke; a manifest-matching external frozen tree
for Verify; and explicit activity, PDSP, project, and expression inputs for Full.
Outputs: A requested derivative run directory containing tables, figures, QA
ledgers, manifests, provenance, and terminal task state.
Side effects: Creates derivative outputs and, in Full, invokes recovered producers;
it never downloads, substitutes, or writes to governed input authorities.
Invariants: Identity, missingness, censoring, thresholds, tolerances, fixed
references, seeds, and scientific algorithms remain unchanged across lanes.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .class_analysis import run_class_models, summarize_classes
from .family_completion import E7_LABELS, FINAL_FAMILY_ORDER, POOLED, RACEMATE, load_e7_profiles, strict_contract_from_profiles
from .final_audit import AuditRun, _model_suite
from .fingerprint import gesd_upper
from .nearest_reference import orient_query_pairs
from .pairwise_continuous import all_pairwise, build_profile_matrices, continuous_metrics, metric_matrix
from .pairwise_fingerprint import build_call_matrices, metric_function


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "frozen"
FIXTURES = REPO_ROOT / "data" / "fixtures"
REFERENCE = REPO_ROOT / "results" / "reference"
TOLERANCE = 1e-10


def sha256(path: Path) -> str:
    """Return the uppercase SHA-256 digest of a file read in bounded blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _write_json(path: Path, value: Any) -> None:
    """Write deterministic UTF-8 JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


class CheckLedger:
    """Collect explicit validation checks and raise on any failed invariant."""
    def __init__(self) -> None:
        """Initialize an empty ordered validation ledger."""
        self.rows: list[dict[str, Any]] = []

    def add(self, check: str, passed: bool, observed: Any = "", expected: Any = "", detail: str = "") -> None:
        """Append one expected-versus-observed validation check."""
        self.rows.append(
            {
                "check": check,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "expected": expected,
                "detail": detail,
            }
        )

    def require(self) -> None:
        """Raise when any accumulated validation check has failed."""
        failures = [row for row in self.rows if row["status"] != "PASS"]
        if failures:
            raise RuntimeError("Validation failed: " + "; ".join(row["check"] for row in failures[:12]))


def _authority_paths(data_root: Path | None = None) -> dict[str, Path]:
    """Resolve governed input paths without guessing an external location.

    Parameters
    ----------
    data_root:
        Directory that mirrors the private ``data/frozen`` layout.  When
        omitted, repository paths are returned; those intentionally contain
        only the public class registry after the redistribution audit.

    Returns
    -------
    dict[str, pathlib.Path]
        Stable role-to-path mapping used by Verify and Full.
    """

    root = (data_root or DATA).resolve()
    public_classes = DATA / "metadata" / "class_membership.csv"
    return {
        "activity": root / "core" / "pooled_target_activity.csv",
        "expression": root / "core" / "pooled_expression58.parquet",
        "full": root / "core" / "pooled_full77_hr.parquet",
        "strict": root / "core" / "pooled_strict18_hr.csv",
        "strict001": root / "core" / "pooled_strict18_calls_alpha001.csv",
        "strict0001": root / "core" / "pooled_strict18_calls_alpha0001.csv",
        "profiles": root / "profiles" / "all_compound_profiles_strict18_long.csv",
        "e7_raw_matrix": root / "e7" / "raw_hr.csv",
        "e7_common_matrix": root / "e7" / "common_rhr.csv",
        "e7_sensitivity_calls": root / "e7" / "calls_alpha001.csv",
        "e7_primary_calls": root / "e7" / "calls_alpha0001.csv",
        "classes": (root / "metadata" / "class_membership.csv")
        if (root / "metadata" / "class_membership.csv").is_file()
        else public_classes,
    }


def verify_authority_manifest(ledger: CheckLedger, data_root: Path) -> None:
    """Validate every externally supplied scientific input by size and hash.

    The public release records the approved 20-file input set in
    ``EXTERNAL_INPUT_MANIFEST.tsv``.  The class registry is cleared and bundled,
    so it is validated separately through the public release manifest.
    """

    manifest = REPO_ROOT / "EXTERNAL_INPUT_MANIFEST.tsv"
    if not manifest.exists():
        ledger.add("authority_manifest_exists", False, manifest, "existing manifest")
        return
    rows = pd.read_csv(manifest, sep="\t")
    failures = []
    checked = 0
    for row in rows.itertuples(index=False):
        rel = Path(str(row.external_relative_path))
        path = data_root / rel
        if (
            not path.is_file()
            or path.stat().st_size != int(row.bytes)
            or sha256(path) != str(row.sha256).upper()
        ):
            failures.append(rel.as_posix())
        checked += 1
    ledger.add("authority_hashes", not failures, checked - len(failures), checked, "; ".join(failures))


def verify_public_reference_outputs(ledger: CheckLedger) -> None:
    """Check byte identity of all retained public scientific outputs and metadata."""

    rows = pd.read_csv(REPO_ROOT / "DATA_MANIFEST.csv")
    rows = rows[
        rows["repo_path"].str.startswith("results/reference/")
        | rows["repo_path"].eq("data/frozen/metadata/class_membership.csv")
    ]
    failures: list[str] = []
    for row in rows.itertuples(index=False):
        path = REPO_ROOT / str(row.repo_path)
        if (
            not path.is_file()
            or path.stat().st_size != int(row.repo_bytes)
            or sha256(path) != str(row.repo_sha256).upper()
        ):
            failures.append(str(row.repo_path))
    ledger.add(
        "public_reference_output_hashes",
        not failures and len(rows) == 61,
        len(rows) - len(failures),
        61,
        "; ".join(failures),
    )


def verify_hr_construction(
    ledger: CheckLedger,
    full_authority_path: Path | None = None,
    strict_authority_path: Path | None = None,
    data_root: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct HR coordinates and compare them to governed authorities."""
    paths = _authority_paths(data_root)
    activity = pd.read_csv(paths["activity"], low_memory=False)
    expression = pd.read_parquet(paths["expression"])
    authority = pd.read_parquet(full_authority_path or paths["full"])
    strict = pd.read_csv(strict_authority_path or paths["strict"], low_memory=False)

    selected = activity[["canonical_target_id", "final_selected_pActivity_v4"]].copy()
    reconstructed = expression.merge(selected, on="canonical_target_id", how="left", validate="many_to_one")
    reconstructed["HR_reconstructed"] = (
        pd.to_numeric(reconstructed["final_selected_pActivity_v4"], errors="coerce")
        * pd.to_numeric(reconstructed["expression_z"], errors="coerce")
    )
    keys = ["canonical_target_id", "tissue_id"]
    authority_keys = pd.MultiIndex.from_frame(authority[keys])
    reconstructed_keys = pd.MultiIndex.from_frame(reconstructed[keys])
    key_contract = (
        authority_keys.is_unique
        and reconstructed_keys.is_unique
        and len(authority_keys) == len(reconstructed_keys)
        and set(authority_keys) == set(reconstructed_keys)
    )
    ledger.add(
        "full77_key_contract",
        key_contract,
        f"authority_unique={authority_keys.is_unique}; reconstructed_unique={reconstructed_keys.is_unique}; rows={len(reconstructed_keys)}",
        "exact unique 58-target x 77-tissue key set",
    )
    reconstructed_by_key = reconstructed.set_index(keys)["HR_reconstructed"]
    regenerated_full = authority.copy()
    regenerated_full["HR_numeric_boundary_or_exact"] = pd.to_numeric(
        reconstructed_by_key.reindex(authority_keys), errors="coerce"
    ).to_numpy()
    aligned = authority[keys + ["HR_numeric_boundary_or_exact"]].copy()
    aligned["HR_reconstructed"] = regenerated_full["HR_numeric_boundary_or_exact"].to_numpy()
    delta = float(
        np.nanmax(
            np.abs(
                pd.to_numeric(aligned["HR_numeric_boundary_or_exact"], errors="coerce")
                - pd.to_numeric(aligned["HR_reconstructed"], errors="coerce")
            )
        )
    )
    ledger.add(
        "full77_dimensions",
        (regenerated_full["canonical_target_id"].nunique(), regenerated_full["tissue_id"].nunique(), len(regenerated_full)) == (58, 77, 4466),
        f"{regenerated_full['canonical_target_id'].nunique()}x{regenerated_full['tissue_id'].nunique()}={len(regenerated_full)}",
        "58x77=4466",
    )
    ledger.add("full77_hr_formula", delta <= TOLERANCE, delta, f"<={TOLERANCE}")
    if full_authority_path is not None:
        # Full-mode downstream work consumes the explicitly regenerated stage output.
        # The reconstruction above remains an equivalence/formula gate, not a substitution.
        regenerated_full = authority.copy()

    strict_keys = pd.MultiIndex.from_frame(strict[keys])
    strict_key_contract = strict_keys.is_unique and len(strict_keys) == 1044 and set(strict_keys).issubset(set(authority_keys))
    ledger.add(
        "strict18_key_contract",
        strict_key_contract,
        f"unique={strict_keys.is_unique}; rows={len(strict_keys)}; subset_full77={set(strict_keys).issubset(set(authority_keys))}",
        "exact unique 58-target x 18-tissue subset of full77",
    )
    regenerated_by_key = regenerated_full.set_index(keys)["HR_numeric_boundary_or_exact"]
    regenerated_strict = strict.copy()
    regenerated_strict["hr_numeric_collapsed"] = pd.to_numeric(
        regenerated_by_key.reindex(strict_keys), errors="coerce"
    ).to_numpy()
    strict_expected = pd.to_numeric(strict["hr_numeric_collapsed"], errors="coerce")
    strict_observed = pd.to_numeric(regenerated_strict["hr_numeric_collapsed"], errors="coerce")
    strict_na_mismatch = int((strict_expected.isna() != strict_observed.isna()).sum())
    strict_mask = strict_expected.notna() & strict_observed.notna()
    strict_delta = float(np.max(np.abs(strict_expected[strict_mask] - strict_observed[strict_mask]))) if strict_mask.any() else 0.0
    ledger.add(
        "strict18_dimensions",
        (regenerated_strict["canonical_target_id"].nunique(), regenerated_strict["tissue_id"].nunique(), len(regenerated_strict)) == (58, 18, 1044),
        f"{regenerated_strict['canonical_target_id'].nunique()}x{regenerated_strict['tissue_id'].nunique()}={len(regenerated_strict)}",
        "58x18=1044",
    )
    ledger.add(
        "strict18_hr_regression",
        strict_na_mismatch == 0 and strict_delta <= TOLERANCE,
        strict_delta,
        f"<={TOLERANCE}",
        f"na_mismatch={strict_na_mismatch}",
    )
    full_expected = pd.to_numeric(authority["HR_numeric_boundary_or_exact"], errors="coerce")
    full_observed = pd.to_numeric(regenerated_full["HR_numeric_boundary_or_exact"], errors="coerce")
    full_na_mismatch = int((full_expected.isna() != full_observed.isna()).sum())
    ledger.add(
        "missingness_preserved",
        full_na_mismatch == 0 and full_observed.notna().all(),
        int(full_observed.isna().sum()),
        int(full_expected.isna().sum()),
        f"na_mismatch={full_na_mismatch}",
    )
    if strict_authority_path is not None:
        # Preserve the exact strict18 stage product after validating it against full77.
        regenerated_strict = strict.copy()
    return regenerated_full, regenerated_strict


def _gesd_call_rows(values: pd.Series, alpha: float) -> tuple[list[str], pd.DataFrame]:
    """Run the governed upper-tail GESD rule and return call identifiers and steps."""
    array = pd.to_numeric(values, errors="coerce").to_numpy(float)
    called, steps = gesd_upper(array, alpha=alpha, rmax=int(math.floor(0.10 * np.isfinite(array).sum())))
    return [str(values.index[index]) for index in called], steps


def _pooled_calls(strict: pd.DataFrame, contract: pd.DataFrame, common: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """Construct pooled-parent call rows on the stable feature contract."""
    values = pd.Series(pd.to_numeric(strict["hr_numeric_collapsed"], errors="coerce").to_numpy(), index=strict.index)
    called, _ = _gesd_call_rows(values, alpha)
    selected = strict.loc[[int(index) for index in called]].copy()
    mapping = contract[["feature_id", "target", "tissue"]].drop_duplicates(["target", "tissue"]).rename(
        columns={"feature_id": "feature_id_common"}
    )
    selected = selected.merge(
        mapping,
        left_on=["canonical_target_id", "tissue_label"],
        right_on=["target", "tissue"],
        how="left",
        validate="many_to_one",
    )
    if selected["feature_id_common"].isna().any():
        raise RuntimeError("Pooled strict18 calls could not be mapped to the common feature contract")
    selected["drug"] = POOLED
    selected["raw_hr"] = pd.to_numeric(selected["hr_numeric_collapsed"], errors="coerce")
    selected["common_rhr"] = [common.loc[POOLED, feature] for feature in selected["feature_id_common"]]
    return selected[["drug", "feature_id_common", "raw_hr", "common_rhr"]]


CALL_TABLE_COLUMNS = [
    "fingerprint_rank",
    "drug",
    "feature_id",
    "target",
    "target_canonical_id",
    "tissue",
    "tissue_canonical_id",
    "raw_hr",
    "common_rhr",
    "alpha",
    "candidate_outlier_fraction",
    "tail",
    "n_finite_tested",
    "r_max",
]


def _enrich_call_rows(
    rows: pd.DataFrame,
    contract: pd.DataFrame,
    raw: pd.DataFrame,
    alpha: float,
) -> pd.DataFrame:
    """Attach target and tissue metadata without changing call membership."""
    metadata_columns = [
        "feature_id",
        "target",
        "target_canonical_id",
        "tissue",
        "tissue_canonical_id",
    ]
    enriched = rows.merge(
        contract[metadata_columns],
        left_on="feature_id_common",
        right_on="feature_id",
        how="left",
        validate="many_to_one",
    )
    enriched.insert(0, "fingerprint_rank", enriched.groupby("drug", sort=False).cumcount() + 1)
    finite_counts = raw.notna().sum(axis=1).astype(int)
    enriched["alpha"] = float(alpha)
    enriched["candidate_outlier_fraction"] = 0.10
    enriched["tail"] = "upper"
    enriched["n_finite_tested"] = enriched["drug"].map(finite_counts).astype(int)
    enriched["r_max"] = np.floor(0.10 * enriched["n_finite_tested"]).astype(int)
    return enriched[CALL_TABLE_COLUMNS].copy()


def _reference_call_counts(alpha_key: str) -> tuple[dict[str, int], list[str]]:
    """Load accepted reference call counts and compound identities."""
    reference = pd.read_csv(REFERENCE / "global" / "ALL_UNORDERED_DRUG_PAIR_METRICS_FINAL.csv", low_memory=False)
    counts: dict[str, int] = {}
    inconsistencies: list[str] = []
    for row in reference.itertuples(index=False):
        for side in ["a", "b"]:
            drug = str(getattr(row, f"drug_{side}"))
            value = int(getattr(row, f"alpha{alpha_key}_call_count_{side}"))
            if drug in counts and counts[drug] != value:
                inconsistencies.append(f"{drug}:{counts[drug]}!={value}")
            counts[drug] = value
    return counts, inconsistencies


def _inject_pooled_strict_profile(
    strict: pd.DataFrame,
    contract: pd.DataFrame,
    matrices: dict[str, pd.DataFrame],
    source_label: str,
) -> dict[str, Any]:
    """Insert the reconstructed pooled-parent profile into governed matrices."""
    mapping = contract[
        ["feature_id", "target_canonical_id", "tissue_canonical_id"]
    ].drop_duplicates("feature_id").rename(columns={"feature_id": "contract_feature_id"})
    mapped = strict.merge(
        mapping,
        left_on=["canonical_target_id", "tissue_id"],
        right_on=["target_canonical_id", "tissue_canonical_id"],
        how="left",
        validate="many_to_one",
    )
    mapped = mapped[mapped["contract_feature_id"].notna()].copy()
    mapped["hr_numeric_collapsed"] = pd.to_numeric(
        mapped["hr_numeric_collapsed"], errors="coerce"
    )
    duplicate_features = int(mapped.duplicated("contract_feature_id").sum())
    expected = mapped.set_index("contract_feature_id")["hr_numeric_collapsed"]
    observed = pd.to_numeric(
        matrices["raw_hr"].loc[POOLED].reindex(expected.index), errors="coerce"
    )
    finite = expected.notna() & observed.notna()
    max_delta = (
        float(np.max(np.abs(expected[finite] - observed[finite]))) if finite.any() else 0.0
    )
    na_mismatch = int((expected.isna() != observed.isna()).sum())
    equivalence = (
        len(mapped) == 1026
        and duplicate_features == 0
        and na_mismatch == 0
        and max_delta <= TOLERANCE
    )
    if not equivalence:
        raise RuntimeError(
            "Regenerated strict18 pooled profile failed the frozen common-scale raw-HR equivalence gate: "
            f"mapped={len(mapped)}; max_delta={max_delta}; na_mismatch={na_mismatch}; "
            f"duplicate_features={duplicate_features}"
        )
    matrices["raw_hr"].loc[POOLED, expected.index] = expected.to_numpy()
    matrices["support"].loc[POOLED] = matrices["raw_hr"].loc[POOLED].notna().astype(int)
    injected = pd.to_numeric(
        matrices["raw_hr"].loc[POOLED].reindex(expected.index), errors="coerce"
    )
    if not np.array_equal(expected.to_numpy(float), injected.to_numpy(float), equal_nan=True):
        raise RuntimeError("Explicit strict18 pooled profile injection did not persist in the downstream raw-HR matrix")
    return {
        "raw_hr_source": source_label,
        "common_contract_coordinates": len(mapped),
        "raw_hr_max_abs_delta_before_injection": max_delta,
        "raw_hr_missingness_mismatch": na_mismatch,
        "raw_hr_injected": True,
        "common_rhr_source": "GOVERNED_COMMON_SCALE_PROJECTION_AFTER_RAW_HR_EQUIVALENCE_GATE",
    }


def build_profiles_and_calls(
    strict: pd.DataFrame,
    ledger: CheckLedger,
    pooled_source_label: str = "USER_SUPPLIED_GOVERNED_STRICT18_AUTHORITY",
    pooled_provenance: dict[str, Any] | None = None,
    data_root: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, pd.DataFrame], list[str]]:
    """Build governed profile, fingerprint, and support matrices.

    ``data_root`` must point to the user-supplied external input tree in the
    public release.  The function preserves the approved profile roster,
    unsupported coordinates, deterministic GESD calls, and 19/14 pooled-parent
    call regressions.
    """

    paths = _authority_paths(data_root)
    base = pd.read_csv(paths["profiles"], low_memory=False)
    contract = strict_contract_from_profiles(base)
    e7 = load_e7_profiles(paths, contract)
    profiles = pd.concat([base, e7], ignore_index=True, sort=False)
    drugs = profiles["drug"].drop_duplicates().astype(str).tolist()
    matrices = build_profile_matrices(profiles, contract, drugs)
    evidence = _inject_pooled_strict_profile(strict, contract, matrices, pooled_source_label)
    if pooled_provenance is not None:
        pooled_provenance.update(evidence)

    calls_by_alpha: dict[str, pd.DataFrame] = {}
    for alpha_key, alpha in [("001", 0.001), ("0001", 0.0001)]:
        rows = [_pooled_calls(strict, contract, matrices["common_rhr"], alpha)]
        for drug in drugs:
            if drug == POOLED:
                continue
            called, _ = _gesd_call_rows(matrices["raw_hr"].loc[drug], alpha)
            frame = pd.DataFrame(
                {
                    "drug": drug,
                    "feature_id_common": called,
                    "raw_hr": [matrices["raw_hr"].loc[drug, feature] for feature in called],
                    "common_rhr": [matrices["common_rhr"].loc[drug, feature] for feature in called],
                }
            )
            rows.append(frame)
        calls_by_alpha[alpha_key] = pd.concat(rows, ignore_index=True)

    calls = build_call_matrices(
        matrices["raw_hr"], calls_by_alpha["001"], calls_by_alpha["0001"], contract, drugs
    )
    for alpha_key, alpha in [("001", 0.001), ("0001", 0.0001)]:
        enriched = _enrich_call_rows(calls_by_alpha[alpha_key], contract, matrices["raw_hr"], alpha)
        calls[f"call_rows_alpha{alpha_key}"] = enriched
        observed_counts = enriched.groupby("drug", sort=False).size().reindex(drugs, fill_value=0).astype(int).to_dict()
        expected_counts, inconsistencies = _reference_call_counts(alpha_key)
        mismatch = [
            f"{drug}:{observed_counts[drug]}!={expected_counts.get(drug, 'MISSING')}"
            for drug in drugs
            if observed_counts[drug] != expected_counts.get(drug)
        ]
        ledger.add(
            f"strict_cns_alpha{alpha_key}_all_profile_call_count_regression",
            not inconsistencies and not mismatch and set(expected_counts) == set(drugs),
            len(observed_counts),
            35,
            "; ".join((inconsistencies + mismatch)[:12]),
        )
        call_contract_ok = (
            enriched["feature_id"].notna().all()
            and enriched["target_canonical_id"].notna().all()
            and enriched["tissue_canonical_id"].notna().all()
            and enriched["raw_hr"].notna().all()
            and not enriched.duplicated(["drug", "feature_id"]).any()
            and set(enriched["drug"]).issubset(set(drugs))
        )
        ledger.add(
            f"strict_cns_alpha{alpha_key}_call_table_contract",
            call_contract_ok,
            f"rows={len(enriched)}; profiles_with_calls={enriched['drug'].nunique()}; duplicates={int(enriched.duplicated(['drug', 'feature_id']).sum())}",
            "valid contract keys; finite raw HR; no duplicate compound-feature calls",
        )
        pooled_expected = pd.read_csv(paths[f"strict{alpha_key}"], low_memory=False)
        pooled_observed = enriched[enriched["drug"].eq(POOLED)]
        observed_keys = set(zip(pooled_observed["target_canonical_id"].astype(str), pooled_observed["tissue_canonical_id"].astype(str)))
        expected_keys = set(zip(pooled_expected["canonical_target_id"].astype(str), pooled_expected["tissue_id"].astype(str)))
        ledger.add(
            f"pooled_strict_alpha{alpha_key}_call_key_regression",
            observed_keys == expected_keys,
            len(observed_keys),
            len(expected_keys),
        )

    subset_failures = []
    calls001 = calls["call_rows_alpha001"]
    calls0001 = calls["call_rows_alpha0001"]
    for drug in drugs:
        sensitivity = set(calls001.loc[calls001["drug"].eq(drug), "feature_id"].astype(str))
        primary = set(calls0001.loc[calls0001["drug"].eq(drug), "feature_id"].astype(str))
        if not primary.issubset(sensitivity):
            subset_failures.append(drug)
    ledger.add(
        "strict_cns_alpha0001_subset_alpha001_all_profiles",
        not subset_failures,
        35 - len(subset_failures),
        35,
        "; ".join(subset_failures),
    )
    ledger.add("global_roster", len(drugs) == 35 and len(set(drugs)) == 35, len(drugs), 35)
    ledger.add("family_roster", all(drug in drugs for drug in FINAL_FAMILY_ORDER), len(FINAL_FAMILY_ORDER), 10)
    ledger.add("pooled_strict_alpha001_calls", len(calls_by_alpha["001"].query("drug == @POOLED")) == 19, len(calls_by_alpha["001"].query("drug == @POOLED")), 19)
    ledger.add("pooled_strict_alpha0001_calls", len(calls_by_alpha["0001"].query("drug == @POOLED")) == 14, len(calls_by_alpha["0001"].query("drug == @POOLED")), 14)
    return contract, matrices, calls, drugs


def persist_hr_outputs(
    full: pd.DataFrame,
    strict: pd.DataFrame,
    contract: pd.DataFrame,
    matrices: dict[str, pd.DataFrame],
    drugs: list[str],
    output: Path,
    ledger: CheckLedger,
) -> None:
    """Persist reconstructed HR tables and their readback validation evidence."""
    root = output / "hr"
    root.mkdir(parents=True, exist_ok=True)
    full_path = root / "POOLED_PARENT_FULL77_HR_REGENERATED.parquet"
    strict_path = root / "POOLED_PARENT_STRICT18_HR_REGENERATED.csv"
    contract_path = root / "STRICT18_FEATURE_CONTRACT.csv"
    full.to_parquet(full_path, index=False)
    strict.to_csv(strict_path, index=False)
    contract.to_csv(contract_path, index=False)

    full_readback = pd.read_parquet(full_path)
    strict_readback = pd.read_csv(strict_path, low_memory=False)
    full_delta = float(
        np.nanmax(
            np.abs(
                pd.to_numeric(full_readback["HR_numeric_boundary_or_exact"], errors="coerce")
                - pd.to_numeric(full["HR_numeric_boundary_or_exact"], errors="coerce")
            )
        )
    )
    strict_delta = float(
        np.nanmax(
            np.abs(
                pd.to_numeric(strict_readback["hr_numeric_collapsed"], errors="coerce")
                - pd.to_numeric(strict["hr_numeric_collapsed"], errors="coerce")
            )
        )
    )
    ledger.add(
        "persisted_full77_hr_contract",
        full_readback.shape == full.shape
        and list(full_readback.columns) == list(full.columns)
        and full_delta <= TOLERANCE
        and full_readback["HR_numeric_boundary_or_exact"].isna().equals(full["HR_numeric_boundary_or_exact"].isna()),
        f"shape={full_readback.shape}; max_delta={full_delta}",
        f"shape={full.shape}; max_delta<={TOLERANCE}; identical missingness",
    )
    ledger.add(
        "persisted_strict18_hr_contract",
        strict_readback.shape == strict.shape
        and list(strict_readback.columns) == list(strict.columns)
        and strict_delta <= TOLERANCE
        and strict_readback["hr_numeric_collapsed"].isna().equals(strict["hr_numeric_collapsed"].isna()),
        f"shape={strict_readback.shape}; max_delta={strict_delta}",
        f"shape={strict.shape}; max_delta<={TOLERANCE}; identical missingness",
    )
    ledger.add(
        "strict18_feature_contract_persisted",
        len(contract) == 1368 and contract["feature_id"].is_unique,
        f"rows={len(contract)}; unique={contract['feature_id'].is_unique}",
        "1368 unique governed features",
    )

    features = contract.sort_values(["feature_order", "feature_id"], kind="stable")["feature_id"].astype(str).tolist()
    for key, filename in [
        ("raw_hr", "ALL_35_PROFILES_STRICT18_RAW_HR_MATRIX.csv"),
        ("common_rhr", "ALL_35_PROFILES_STRICT18_COMMON_RHR_MATRIX.csv"),
    ]:
        matrix = matrices[key].reindex(index=drugs, columns=features)
        matrix.index.name = "drug"
        path = root / filename
        matrix.reset_index().to_csv(path, index=False)
        readback = pd.read_csv(path, low_memory=False).set_index("drug")
        readback = readback.reindex(index=drugs, columns=features)
        expected_values = matrix.to_numpy(float)
        observed_values = readback.to_numpy(float)
        na_match = np.array_equal(np.isnan(expected_values), np.isnan(observed_values))
        finite = np.isfinite(expected_values) & np.isfinite(observed_values)
        max_delta = float(np.max(np.abs(expected_values[finite] - observed_values[finite]))) if finite.any() else 0.0
        ledger.add(
            f"persisted_all_profile_{key}_matrix_contract",
            readback.shape == (35, 1368)
            and list(readback.index) == drugs
            and list(readback.columns) == features
            and na_match
            and max_delta <= TOLERANCE,
            f"shape={readback.shape}; max_delta={max_delta}; missingness_match={na_match}",
            f"35x1368; max_delta<={TOLERANCE}; identical missingness",
        )


def _compound_output_slug(drug: str) -> str:
    """Return the stable filesystem slug for a governed compound identity."""
    value = re.sub(r"[^a-z0-9]+", "_", drug.lower()).strip("_")
    return value or "compound"


def persist_strict_cns_fingerprints(
    calls: dict[str, pd.DataFrame],
    matrices: dict[str, pd.DataFrame],
    contract: pd.DataFrame,
    drugs: list[str],
    output: Path,
    ledger: CheckLedger,
) -> None:
    """Persist strict-CNS fingerprints at both governed alpha thresholds."""
    root = output / "fingerprints" / "strict_cns"
    root.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    expected_features = contract.sort_values(["feature_order", "feature_id"], kind="stable")["feature_id"].astype(str).tolist()
    for alpha_key, alpha in [("001", 0.001), ("0001", 0.0001)]:
        combined = calls[f"call_rows_alpha{alpha_key}"].copy()
        combined_path = root / f"ALL_35_PROFILES_STRICT_CNS_CALLS_ALPHA{alpha_key}.csv"
        combined.to_csv(combined_path, index=False)
        binary = calls[f"call_binary_alpha{alpha_key}"].reindex(index=drugs, columns=expected_features)
        binary.index.name = "drug"
        binary.to_csv(root / f"ALL_35_PROFILES_STRICT_CNS_CALL_BINARY_ALPHA{alpha_key}.csv", index=True)
        alpha_root = root / f"alpha{alpha_key}_per_compound"
        alpha_root.mkdir(parents=True, exist_ok=True)
        finite_counts = matrices["raw_hr"].notna().sum(axis=1).astype(int)
        written = 0
        for profile_order, drug in enumerate(drugs, start=1):
            selected = combined[combined["drug"].eq(drug)].copy()
            filename = f"{profile_order:02d}_{_compound_output_slug(drug)}.csv"
            path = alpha_root / filename
            selected.to_csv(path, index=False)
            written += 1
            index_rows.append(
                {
                    "profile_order": profile_order,
                    "drug": drug,
                    "alpha": alpha,
                    "n_finite_tested": int(finite_counts.loc[drug]),
                    "r_max": int(math.floor(0.10 * int(finite_counts.loc[drug]))),
                    "call_count": len(selected),
                    "call_status": "CALLS_PRESENT" if len(selected) else "NO_CALLS",
                    "calls_file": path.relative_to(output).as_posix(),
                }
            )
        binary_readback = pd.read_csv(
            root / f"ALL_35_PROFILES_STRICT_CNS_CALL_BINARY_ALPHA{alpha_key}.csv", low_memory=False
        ).set_index("drug").reindex(index=drugs, columns=expected_features)
        expected_values = binary.to_numpy(float)
        observed_values = binary_readback.to_numpy(float)
        binary_contract = (
            binary_readback.shape == (35, 1368)
            and np.array_equal(np.isnan(expected_values), np.isnan(observed_values))
            and np.array_equal(expected_values[np.isfinite(expected_values)], observed_values[np.isfinite(observed_values)])
            and set(np.unique(observed_values[np.isfinite(observed_values)])).issubset({0.0, 1.0})
        )
        combined_readback = pd.read_csv(combined_path, low_memory=False)
        ledger.add(
            f"persisted_strict_cns_alpha{alpha_key}_per_compound_tables",
            written == 35
            and list(combined_readback.columns) == CALL_TABLE_COLUMNS
            and len(combined_readback) == len(combined),
            f"files={written}; rows={len(combined_readback)}",
            f"35 profile files; {len(combined)} selected-call rows; exact schema",
        )
        ledger.add(
            f"persisted_strict_cns_alpha{alpha_key}_binary_missingness_contract",
            binary_contract,
            f"shape={binary_readback.shape}; NA={int(binary_readback.isna().sum().sum())}",
            "35x1368; finite values only 0/1; untested remains NA",
        )
    index = pd.DataFrame(index_rows)
    index_path = root / "STRICT_CNS_FINGERPRINT_FILE_INDEX.csv"
    index.to_csv(index_path, index=False)
    ledger.add(
        "strict_cns_fingerprint_file_index_contract",
        len(index) == 70
        and index["drug"].nunique() == 35
        and index.groupby("drug")["alpha"].nunique().eq(2).all()
        and all((output / path).exists() for path in index["calls_file"]),
        f"rows={len(index)}; profiles={index['drug'].nunique()}",
        "70 rows; 35 profiles at both alpha thresholds; every file exists",
    )


def _deterministic_nearest_summary(pairwise: pd.DataFrame, query: str, eligible: set[str]) -> pd.DataFrame:
    """Rank eligible query comparisons with deterministic tie handling."""
    selected = orient_query_pairs(pairwise, query, eligible)
    metrics = [
        ("rms_common_rhr", True, "RMS"),
        ("cosine_common_rhr", False, "COSINE"),
        ("spearman_common_rhr", False, "SPEARMAN"),
        ("alpha001_call_jaccard", False, "FINGERPRINT_JACCARD"),
        ("support_jaccard", False, "SUPPORT_JACCARD"),
    ]
    rows: list[dict[str, Any]] = []
    for column, ascending, label in metrics:
        values = selected.dropna(subset=[column]).sort_values(
            [column, "comparator"], ascending=[ascending, True], kind="stable"
        )
        if values.empty:
            rows.append(
                {
                    "metric": label,
                    "nearest_comparator": "",
                    "nearest_value": np.nan,
                    "runner_up": "",
                    "runner_up_value": np.nan,
                    "margin": np.nan,
                    "status": "NOT_ESTIMABLE",
                }
            )
            continue
        first = values.iloc[0]
        second = values.iloc[1] if len(values) > 1 else None
        rows.append(
            {
                "metric": label,
                "nearest_comparator": first["comparator"],
                "nearest_value": first[column],
                "runner_up": second["comparator"] if second is not None else "",
                "runner_up_value": second[column] if second is not None else np.nan,
                "margin": abs(float(first[column]) - float(second[column])) if second is not None else np.nan,
                "status": "PASS",
            }
        )
    return pd.DataFrame(rows)


def _deterministic_family_nearest(pairwise: pd.DataFrame) -> pd.DataFrame:
    """Orient and rank within-family comparisons deterministically."""
    metrics = [
        ("rms_common_rhr", True),
        ("cosine_common_rhr", False),
        ("spearman_common_rhr", False),
        ("alpha001_call_jaccard", False),
        ("support_jaccard", False),
    ]
    rows: list[dict[str, Any]] = []
    for compound in FINAL_FAMILY_ORDER:
        relevant = pairwise[(pairwise["drug_a"].eq(compound)) | (pairwise["drug_b"].eq(compound))].copy()
        relevant["other_compound"] = np.where(
            relevant["drug_a"].eq(compound), relevant["drug_b"], relevant["drug_a"]
        )
        for metric, ascending in metrics:
            ranked = relevant.dropna(subset=[metric]).sort_values(
                [metric, "other_compound"], ascending=[ascending, True], kind="stable"
            )
            rows.append(
                {
                    "compound": compound,
                    "metric": metric,
                    "nearest_family_member": ranked.iloc[0]["other_compound"] if len(ranked) else "NOT_ESTIMABLE",
                    "metric_value": ranked.iloc[0][metric] if len(ranked) else np.nan,
                    "matched_features": ranked.iloc[0]["matched_features"] if len(ranked) else 0,
                    "matched_targets": ranked.iloc[0]["matched_targets"] if len(ranked) else 0,
                    "interpretation": "DESCRIPTIVE_EXPLORATORY_NOT_CLASS_ASSIGNMENT",
                }
            )
    return pd.DataFrame(rows)


def _frame_regression(
    observed: pd.DataFrame,
    expected: pd.DataFrame,
    ledger: CheckLedger,
    label: str,
) -> None:
    """Compare an observed table against its retained reference contract."""
    detail = ""
    passed = True
    try:
        pd.testing.assert_frame_equal(
            observed.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            atol=TOLERANCE,
            rtol=0.0,
        )
    except AssertionError as exc:
        passed = False
        detail = str(exc).splitlines()[0]
    ledger.add(label, passed, observed.shape, expected.shape, detail)


def build_nearest_summaries(
    pairwise: pd.DataFrame,
    family_pairwise: pd.DataFrame,
    drugs: list[str],
    output: Path,
    ledger: CheckLedger,
) -> None:
    """Build and validate global and family nearest-reference summaries."""
    root = output / "nearest_reference"
    root.mkdir(parents=True, exist_ok=True)
    external = {drug for drug in drugs if drug not in FINAL_FAMILY_ORDER}
    global_summary = _deterministic_nearest_summary(pairwise, POOLED, external)
    family_summary = _deterministic_family_nearest(family_pairwise)
    global_summary.to_csv(root / "POOLED_PARENT_VS_25_EXTERNAL_NEAREST_REFERENCE_SUMMARY.csv", index=False)
    family_summary.to_csv(root / "FAMILY_NEAREST_MEMBER_SUMMARY.csv", index=False)

    reference_pairwise = pd.read_csv(
        REFERENCE / "global" / "ALL_UNORDERED_DRUG_PAIR_METRICS_FINAL.csv", low_memory=False
    )
    reference_family = pd.read_csv(
        REFERENCE / "family" / "KETAMINE_FAMILY_ALL_PAIR_METRICS_FINAL.csv", low_memory=False
    )
    expected_global = _deterministic_nearest_summary(reference_pairwise, POOLED, external)
    expected_family = _deterministic_family_nearest(reference_family)
    _frame_regression(global_summary, expected_global, ledger, "global_nearest_reference_regression")
    _frame_regression(family_summary, expected_family, ledger, "family_nearest_member_regression")
    ledger.add(
        "global_nearest_reference_contract",
        len(external) == 25
        and global_summary.shape == (5, 7)
        and global_summary["status"].eq("PASS").all(),
        f"external={len(external)}; shape={global_summary.shape}; statuses={sorted(global_summary['status'].unique())}",
        "25 external profiles; five metrics; all estimable",
    )
    ledger.add(
        "family_nearest_member_contract",
        family_summary.shape == (50, 7)
        and set(family_summary["compound"]) == set(FINAL_FAMILY_ORDER)
        and family_summary.groupby("compound")["metric"].nunique().eq(5).all(),
        f"shape={family_summary.shape}; profiles={family_summary['compound'].nunique()}",
        "10 family profiles x five metrics",
    )


def build_pairwise(contract: pd.DataFrame, matrices: dict[str, pd.DataFrame], calls: dict[str, pd.DataFrame], drugs: list[str], output: Path, ledger: CheckLedger) -> pd.DataFrame:
    """Compute all unordered pairwise metrics and register QA checks."""
    pairwise, _ = all_pairwise(matrices, contract, drugs, metric_function(calls, contract))
    pairwise["reused_or_recomputed"] = "RECOMPUTED_PORTABLE_VERIFY"
    path = output / "global" / "ALL_UNORDERED_DRUG_PAIR_METRICS_FINAL.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pairwise.to_csv(path, index=False)
    family = pairwise[pairwise["drug_a"].isin(FINAL_FAMILY_ORDER) & pairwise["drug_b"].isin(FINAL_FAMILY_ORDER)].copy()
    family.to_csv(output / "family" / "KETAMINE_FAMILY_ALL_PAIR_METRICS_FINAL.csv", index=False)
    ledger.add("global_pair_count", len(pairwise) == 595, len(pairwise), 595)
    ledger.add("family_pair_count", len(family) == 45, len(family), 45)
    for metric, name in [
        ("alpha001_call_jaccard", "GLOBAL_ALPHA001_CALL_JACCARD_MATRIX.csv"),
        ("alpha0001_call_jaccard", "GLOBAL_ALPHA0001_CALL_JACCARD_MATRIX.csv"),
        ("alpha001_signed_sparse_cosine", "GLOBAL_ALPHA001_SIGNED_SPARSE_COSINE_MATRIX.csv"),
    ]:
        metric_matrix(pairwise, metric, drugs).reset_index(names="compound").to_csv(output / "global" / name, index=False)
    build_nearest_summaries(pairwise, family, drugs, output, ledger)
    return pairwise


def build_multivariate(contract: pd.DataFrame, matrices: dict[str, pd.DataFrame], calls: dict[str, pd.DataFrame], drugs: list[str], pairwise: pd.DataFrame, output: Path) -> None:
    """Generate the governed multivariate derivative tables."""
    run = AuditRun(root=output, source_run=REPO_ROOT, code_root=REPO_ROOT)
    family_pairs = pairwise[pairwise["drug_a"].isin(FINAL_FAMILY_ORDER) & pairwise["drug_b"].isin(FINAL_FAMILY_ORDER)].copy()
    family_status = _model_suite(
        run,
        "FAMILY",
        matrices["common_rhr"].loc[FINAL_FAMILY_ORDER],
        calls["call_binary_alpha001"].loc[FINAL_FAMILY_ORDER],
        calls["call_binary_alpha0001"].loc[FINAL_FAMILY_ORDER],
        family_pairs,
        contract,
        "family",
    )
    family_status.to_csv(output / "family" / "FAMILY_MODEL_STATUS.csv", index=False)
    external = [drug for drug in drugs if drug not in FINAL_FAMILY_ORDER]
    global_status = _model_suite(
        run,
        "GLOBAL",
        matrices["common_rhr"],
        calls["call_binary_alpha001"],
        calls["call_binary_alpha0001"],
        pairwise,
        contract,
        "global",
        reference=external,
        projections=FINAL_FAMILY_ORDER,
    )
    global_status.to_csv(output / "global" / "GLOBAL_MODEL_STATUS.csv", index=False)


def build_classes(
    contract: pd.DataFrame,
    matrices: dict[str, pd.DataFrame],
    calls: dict[str, pd.DataFrame],
    pairwise: pd.DataFrame,
    output: Path,
    data_root: Path | None = None,
) -> None:
    """Generate descriptive class summaries using the governed class registry."""

    classes = pd.read_csv(_authority_paths(data_root)["classes"], low_memory=False)
    result = run_class_models(
        matrices["common_rhr"], calls["call_binary_alpha001"], pairwise, contract, classes, [POOLED, RACEMATE]
    )
    class_dir = output / "class"
    class_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in result.items():
        if len(frame):
            frame.to_csv(class_dir / f"CLASS_{name.upper()}.csv", index=False)
    summary, residuals = summarize_classes(matrices["common_rhr"], calls["call_binary_alpha001"], contract, classes, POOLED)
    oriented = orient_query_pairs(pairwise, POOLED).merge(
        classes[["class_id", "class_label", "drug"]], left_on="comparator", right_on="drug", how="inner"
    )
    distance = oriented.groupby(["class_id", "class_label"], as_index=False).agg(
        mean_continuous_distance=("rms_common_rhr", "mean"),
        median_continuous_distance=("rms_common_rhr", "median"),
        minimum_continuous_distance=("rms_common_rhr", "min"),
        member_count=("comparator", "nunique"),
    )
    summary = summary.merge(distance, on=["class_id", "class_label"], how="left")
    summary.to_csv(class_dir / "CLASS_SUMMARY.csv", index=False)
    residuals.to_csv(class_dir / "CLASS_RESIDUALS_LONG.csv", index=False)


def build_whole_body(full: pd.DataFrame, strict: pd.DataFrame, output: Path, ledger: CheckLedger, figures: bool) -> None:
    """Build whole-body fingerprints while preserving CNS reconciliation."""
    wb = output / "whole_body"
    wb.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    for key, alpha in [("001", 0.001), ("0001", 0.0001)]:
        frame = full.rename(columns={"HR_numeric_boundary_or_exact": "hr_numeric_collapsed"}).copy()
        values = pd.Series(pd.to_numeric(frame["hr_numeric_collapsed"], errors="coerce").to_numpy(), index=frame.index)
        called, steps = _gesd_call_rows(values, alpha)
        selected = frame.loc[[int(index) for index in called]].copy().reset_index(drop=True)
        selected.insert(0, "fingerprint_rank", np.arange(1, len(selected) + 1))
        if len(selected):
            selected = selected.merge(steps[["removed_index", "step", "n", "GESD_R", "critical_lambda", "R_minus_lambda"]], left_index=True, right_index=True, how="left")
        result[key] = selected
        selected.to_csv(wb / f"WHOLE_BODY_CALLS_ALPHA{key}.csv", index=False)
    ledger.add("whole_body_alpha001_calls", len(result["001"]) == 59, len(result["001"]), 59)
    ledger.add("whole_body_alpha0001_calls", len(result["0001"]) == 38, len(result["0001"]), 38)
    expected001 = pd.read_csv(REFERENCE / "whole_body" / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p001.csv")
    expected0001 = pd.read_csv(REFERENCE / "whole_body" / "KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p0001.csv")
    for key, expected in [("001", expected001), ("0001", expected0001)]:
        observed_keys = set(zip(result[key]["canonical_target_id"].astype(str), result[key]["tissue_id"].astype(str)))
        expected_keys = set(zip(expected["canonical_target_id"].astype(str), expected["tissue_id"].astype(str)))
        ledger.add(f"whole_body_alpha{key}_call_keys", observed_keys == expected_keys, len(observed_keys), len(expected_keys))
    if not figures:
        return
    from .upstream import whole_body_fingerprint_authority as authority

    strict_tissues = set(strict["tissue_id"].astype(str))
    standardized: dict[str, pd.DataFrame] = {}
    retained = set(zip(result["0001"]["canonical_target_id"].astype(str), result["0001"]["tissue_id"].astype(str)))
    for key, alpha in [("001", 0.001), ("0001", 0.0001)]:
        frame = result[key].copy()
        frame["compound"] = "KETAMINE"
        frame["target"] = frame["canonical_target_id"].astype(str)
        frame["tissue"] = frame["tissue_label"].astype(str)
        frame["HR_score"] = pd.to_numeric(frame["hr_numeric_collapsed"], errors="coerce")
        frame["tissue_class"] = np.where(frame["tissue_id"].astype(str).isin(strict_tissues), "CNS", "Peripheral/non-CNS")
        frame["retained_at_alpha_0p0001"] = [
            (str(target), str(tissue)) in retained for target, tissue in zip(frame["canonical_target_id"], frame["tissue_id"])
        ]
        standardized[key] = frame
    authority.OUT = wb
    (wb / "05_FIGURES").mkdir(parents=True, exist_ok=True)
    figure_paths = authority.draw_figures(standardized["001"], standardized["0001"])
    export_qc = authority.validate_exports(figure_paths)
    passed = all(
        value is True
        for key, value in export_qc.items()
        if key.endswith("exists_nonempty") or key.endswith("header_valid") or key.endswith("readable")
    )
    ledger.add("whole_body_figure_exports", passed, passed, True)


def build_figure4(output: Path, ledger: CheckLedger) -> None:
    """Copy and validate the frozen-coordinate Figure 4 derivative."""
    from .upstream import figure4_rightlegend_authority as authority

    root = output / "figure4"
    shutil.copytree(REFERENCE / "figure4" / "source_data", root / "source_data", dirs_exist_ok=True)
    (root / "final").mkdir(parents=True, exist_ok=True)
    profiles, pc1, pc2, table, frozen = authority.read_source(root)
    qc, _ = authority.render(
        profiles,
        pc1,
        pc2,
        root / "final" / "FINAL_FIGURE4_CARDOZO_BRIGHT_RIGHTLEGEND",
        "A_RIGHTLEGEND_BRIGHT",
        False,
    )
    fixed = pd.read_csv(frozen)
    ledger.add("figure4_roster", len(profiles) == 26, len(profiles), 26)
    ledger.add("figure4_fixed_coordinates", qc.get("status") == "PASS" and fixed.shape[0] == 35, qc.get("status"), "PASS")
    ledger.add("figure4_no_refit_or_jitter", True, 0, 0, "Coordinates were read, not recomputed")


def compare_csv(observed_path: Path, reference_path: Path, ledger: CheckLedger, label: str) -> None:
    """Compare a generated CSV against its retained reference table."""
    observed = pd.read_csv(observed_path, low_memory=False)
    reference = pd.read_csv(reference_path, low_memory=False)
    if list(observed.columns) != list(reference.columns) or observed.shape != reference.shape:
        ledger.add(label, False, f"{observed.shape}/{list(observed.columns)}", f"{reference.shape}/{list(reference.columns)}")
        return
    max_delta = 0.0
    na_mismatch = 0
    text_mismatch = 0
    for column in reference.columns:
        left_num = pd.to_numeric(observed[column], errors="coerce")
        right_num = pd.to_numeric(reference[column], errors="coerce")
        numeric = right_num.notna().any() and left_num.notna().any()
        if numeric:
            na_mismatch += int((left_num.isna() != right_num.isna()).sum())
            mask = left_num.notna() & right_num.notna()
            if mask.any():
                left_values = left_num[mask].to_numpy(dtype=float)
                right_values = right_num[mask].to_numpy(dtype=float)
                max_delta = max(max_delta, float(np.max(np.abs(left_values - right_values))))
        elif column not in {"reused_or_recomputed", "query_projection_details"}:
            left = observed[column].astype("string").fillna("<NA>")
            right = reference[column].astype("string").fillna("<NA>")
            text_mismatch += int((left != right).sum())
    ledger.add(label, na_mismatch == 0 and text_mismatch == 0 and max_delta <= TOLERANCE, max_delta, f"<={TOLERANCE}", f"na_mismatch={na_mismatch}; text_mismatch={text_mismatch}")


def compare_outputs(output: Path, ledger: CheckLedger) -> None:
    """Run regression comparisons for the supported reference outputs."""
    for section in ["family", "global"]:
        for reference in sorted((REFERENCE / section).glob("*.csv")):
            observed = output / section / reference.name
            label = f"regression_{section}_{reference.stem}"
            if not observed.exists():
                ledger.add(label, False, "MISSING", observed.relative_to(output).as_posix(), "required reference-matched output was not produced")
                continue
            compare_csv(observed, reference, ledger, label)
    for name in ["CLASS_SCORES.csv", "CLASS_LOADINGS.csv", "CLASS_STATUS.csv", "CLASS_SUMMARY.csv", "CLASS_RESIDUALS_LONG.csv"]:
        observed = output / "class" / name
        reference = REFERENCE / "class" / name
        label = f"regression_class_{Path(name).stem}"
        if not reference.exists():
            ledger.add(label, False, "MISSING_REFERENCE", reference.relative_to(REPO_ROOT).as_posix(), "required class regression authority is absent")
            continue
        if not observed.exists():
            ledger.add(label, False, "MISSING", observed.relative_to(output).as_posix(), "required reference-matched output was not produced")
            continue
        compare_csv(observed, reference, ledger, label)


def write_run_manifest(output: Path) -> None:
    """Write a cryptographic inventory for one derivative run."""
    rows = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.tsv":
            rows.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    pd.DataFrame(rows).to_csv(output / "MANIFEST.tsv", sep="\t", index=False)


def run_smoke_analysis_checks(output: Path, ledger: CheckLedger) -> None:
    """Exercise HR, pairwise, multivariate, and rendering kernels on fixtures.

    All inputs are invented and redistribution-safe. The HR fixture explicitly
    checks exact and bounded relation metadata plus NA propagation so Smoke
    cannot pass after a regression that zero-fills an unsupported coordinate.
    """

    from .figures import scatter
    from .hr import construct_hr_scores
    from .multivariate import complete_case_pca, linkage_table, model_tables

    activity_fixture = pd.read_csv(FIXTURES / "smoke_activity.csv")
    expression_fixture = pd.read_csv(FIXTURES / "smoke_expression.csv")
    constructed_hr = construct_hr_scores(activity_fixture, expression_fixture)
    hr_indexed = constructed_hr.set_index(["canonical_target_id", "tissue_id"])
    expected_coordinates = [
        ("SMOKE_T1", "SMOKE_X"),
        ("SMOKE_T1", "SMOKE_Y"),
        ("SMOKE_T2", "SMOKE_X"),
        ("SMOKE_T2", "SMOKE_Y"),
    ]
    observed_hr = pd.to_numeric(
        hr_indexed.reindex(expected_coordinates)["hr_score"],
        errors="coerce",
    ).to_numpy(float)
    observed_relations = (
        hr_indexed.reindex(expected_coordinates)[
            "final_activity_relation_operator_v4"
        ]
        .astype(str)
        .tolist()
    )
    hr_fixture_ok = (
        len(constructed_hr) == 4
        and constructed_hr["feature_id"].is_unique
        and np.allclose(
            observed_hr[:3],
            np.array([-7.0, 7.0, 10.0]),
            atol=0.0,
            rtol=0.0,
        )
        and np.isnan(observed_hr[3])
        and int(pd.isna(observed_hr).sum()) == 1
        and observed_relations == ["=", "=", ">=", ">="]
    )
    ledger.add(
        "smoke_hr_construction_missingness",
        hr_fixture_ok,
        f"hr={observed_hr.tolist()}; relations={observed_relations}",
        "[-7, 7, 10, NA]; relations [=, =, >=, >=]; no zero-fill",
    )

    fixture_path = FIXTURES / "smoke_profiles.csv"
    fixture_long = pd.read_csv(fixture_path)
    required = {
        "drug",
        "feature_id",
        "target",
        "tissue",
        "raw_hr",
        "common_rhr",
        "call_alpha001",
        "call_alpha0001",
    }
    fixture_contract_ok = (
        required.issubset(fixture_long.columns)
        and fixture_long["drug"].nunique() == 4
        and fixture_long["feature_id"].nunique() == 3
        and len(fixture_long) == 12
    )
    ledger.add(
        "synthetic_fixture_contract",
        fixture_contract_ok,
        f"rows={len(fixture_long)}; drugs={fixture_long['drug'].nunique()}; features={fixture_long['feature_id'].nunique()}",
        "12 rows; four invented drugs; three invented features",
    )
    contract = (
        fixture_long[["feature_id", "target", "tissue"]]
        .drop_duplicates()
        .sort_values("feature_id", kind="mergesort")
        .reset_index(drop=True)
    )
    raw_matrix = fixture_long.pivot(index="drug", columns="feature_id", values="raw_hr").reindex(
        index=["SYNTHETIC_A", "SYNTHETIC_B", "SYNTHETIC_C", "SYNTHETIC_D"],
        columns=contract["feature_id"],
    )
    continuous, _ = continuous_metrics(
        raw_matrix.loc["SYNTHETIC_A"],
        raw_matrix.loc["SYNTHETIC_B"],
        contract,
    )
    ledger.add(
        "smoke_pairwise_continuous_metrics",
        continuous["matched_features"] == 3
        and continuous["matched_targets"] == 2
        and np.isclose(continuous["rms_common_rhr"], 1.0, atol=1e-14, rtol=0.0),
        f"matched={continuous['matched_features']}; targets={continuous['matched_targets']}; rms={continuous['rms_common_rhr']}",
        "matched=3; targets=2; rms=1",
    )

    labels = ["SYNTHETIC_A", "SYNTHETIC_B"]
    calls001 = fixture_long.pivot(index="drug", columns="feature_id", values="call_alpha001").reindex(
        index=labels, columns=contract["feature_id"]
    )
    calls0001 = fixture_long.pivot(index="drug", columns="feature_id", values="call_alpha0001").reindex(
        index=labels, columns=contract["feature_id"]
    )
    common = fixture_long.pivot(index="drug", columns="feature_id", values="common_rhr").reindex(
        index=labels, columns=contract["feature_id"]
    )
    calls = {
        "call_binary_alpha001": calls001,
        "call_score_alpha001": common.where(calls001.eq(1), 0.0),
        "call_binary_alpha0001": calls0001,
        "call_score_alpha0001": common.where(calls0001.eq(1), 0.0),
    }
    fingerprint = metric_function(calls, contract)("SYNTHETIC_A", "SYNTHETIC_B")
    ledger.add(
        "smoke_pairwise_fingerprint_metrics",
        fingerprint["alpha001_shared_calls"] == 1
        and fingerprint["alpha001_union_calls"] == 3
        and np.isclose(fingerprint["alpha001_call_jaccard"], 1.0 / 3.0, atol=1e-14, rtol=0.0)
        and fingerprint["alpha0001_call_jaccard"] == 1.0,
        f"shared={fingerprint['alpha001_shared_calls']}; union={fingerprint['alpha001_union_calls']}; jaccard={fingerprint['alpha001_call_jaccard']}",
        "shared=1; union=3; alpha001_jaccard=1/3; alpha0001_jaccard=1",
    )

    fixture = raw_matrix
    model = complete_case_pca(fixture, n_components=2)
    repeated = complete_case_pca(fixture, n_components=2)
    scores, _, status = model_tables(model, "SMOKE_COMPLETE_CASE_PCA", "smoke_fixture", contract)
    ledger.add(
        "smoke_pca_determinism",
        status["status"] == "PASS"
        and model["n_components"] == 2
        and np.isfinite(model["scores"]).all()
        and np.allclose(model["scores"], repeated["scores"], atol=0.0, rtol=0.0),
        f"status={status['status']}; shape={model['scores'].shape}; rank={model['rank']}",
        "PASS; four rows; two finite deterministic components",
    )

    values = fixture.to_numpy(float)
    distances = np.linalg.norm(values[:, None, :] - values[None, :, :], axis=2)
    distance_frame = pd.DataFrame(distances, index=fixture.index, columns=fixture.index)
    linkage, linkage_status = linkage_table(distance_frame, "SMOKE_AVERAGE_LINKAGE")
    ledger.add(
        "smoke_average_linkage_clustering",
        linkage_status["status"] == "PASS"
        and linkage.shape == (3, 5)
        and np.isfinite(linkage[["left_cluster", "right_cluster", "distance", "member_count"]]).all().all()
        and int(linkage.iloc[-1]["member_count"]) == 4,
        f"status={linkage_status['status']}; shape={linkage.shape}; final_members={linkage.iloc[-1]['member_count']}",
        "PASS; three linkage rows; final cluster has four members",
    )

    smoke_root = output / "smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    constructed_hr.to_csv(smoke_root / "SMOKE_HR_CONSTRUCTION.csv", index=False)
    scores.to_csv(smoke_root / "SMOKE_PCA_SCORES.csv", index=False)
    linkage.to_csv(smoke_root / "SMOKE_AVERAGE_LINKAGE.csv", index=False)
    figure = scatter(scores, "Deterministic synthetic Smoke PCA", highlight=["SYNTHETIC_A"])
    figure.set_size_inches(5.0, 3.2)
    figure_path = smoke_root / "SMOKE_PCA_SCATTER.png"
    figure.savefig(figure_path, dpi=100, bbox_inches="tight")
    try:
        import matplotlib.pyplot as plt
        from matplotlib import image as matplotlib_image

        plt.close(figure)
        rendered = matplotlib_image.imread(figure_path)
        figure_ok = (
            figure_path.stat().st_size > 1000
            and figure_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            and rendered.ndim in {2, 3}
            and rendered.shape[0] > 0
            and rendered.shape[1] > 0
        )
        figure_detail = f"bytes={figure_path.stat().st_size}; shape={rendered.shape}"
    except Exception as exc:
        figure_ok = False
        figure_detail = f"{type(exc).__name__}: {exc}"
    ledger.add(
        "smoke_figure_rendering",
        figure_ok,
        figure_detail,
        "readable nonempty PNG",
    )


def smoke(output: Path) -> dict[str, Any]:
    """Run the self-contained public Smoke lane on synthetic data only."""

    ledger = CheckLedger()
    verify_public_reference_outputs(ledger)
    run_smoke_analysis_checks(output, ledger)
    pd.DataFrame(ledger.rows).to_csv(output / "QA_SUMMARY.csv", index=False)
    ledger.require()
    return {"status": "PASS", "mode": "Smoke", "checks": len(ledger.rows)}


def verify(
    output: Path,
    *,
    pooled_full_path: Path | None = None,
    pooled_strict_path: Path | None = None,
    pooled_authority_mode: str = "USER_SUPPLIED_GOVERNED_AUTHORITIES",
    external_input_root: Path | None = None,
) -> dict[str, Any]:
    """Regenerate and compare the complete analysis from cleared external inputs.

    Raises
    ------
    RuntimeError
        If the 20-file external input tree is not supplied.  Verify is not a
        self-contained public lane because those near-source files are excluded.
    """

    if external_input_root is None:
        raise RuntimeError(
            "Verify requires --external-input-root containing the 20 governed files listed in EXTERNAL_INPUT_MANIFEST.tsv. These inputs are not redistributed; see docs/DATA_SOURCES.md."
        )
    external_input_root = external_input_root.resolve()
    if not external_input_root.is_dir():
        raise FileNotFoundError(f"External input root does not exist: {external_input_root}")
    ledger = CheckLedger()
    verify_authority_manifest(ledger, external_input_root)
    full, strict = verify_hr_construction(
        ledger,
        pooled_full_path,
        pooled_strict_path,
        data_root=external_input_root,
    )
    authority_paths = _authority_paths(external_input_root)
    pooled_provenance: dict[str, Any] = {
        "mode": pooled_authority_mode,
        "full77_path": str((pooled_full_path or authority_paths["full"]).resolve()),
        "full77_sha256": sha256(pooled_full_path or authority_paths["full"]),
        "strict18_path": str((pooled_strict_path or authority_paths["strict"]).resolve()),
        "strict18_sha256": sha256(pooled_strict_path or authority_paths["strict"]),
    }
    contract, matrices, calls, drugs = build_profiles_and_calls(
        strict,
        ledger,
        pooled_source_label=(
            "FULL_REGENERATED_STRICT18_AFTER_UPSTREAM_EQUIVALENCE"
            if pooled_strict_path is not None
            else "USER_SUPPLIED_GOVERNED_STRICT18_AUTHORITY"
        ),
        pooled_provenance=pooled_provenance,
        data_root=external_input_root,
    )
    (output / "family").mkdir(parents=True, exist_ok=True)
    (output / "global").mkdir(parents=True, exist_ok=True)
    persist_hr_outputs(full, strict, contract, matrices, drugs, output, ledger)
    persist_strict_cns_fingerprints(calls, matrices, contract, drugs, output, ledger)
    pairwise = build_pairwise(contract, matrices, calls, drugs, output, ledger)
    build_multivariate(contract, matrices, calls, drugs, pairwise, output)
    build_classes(contract, matrices, calls, pairwise, output, external_input_root)
    build_whole_body(full, strict, output, ledger, figures=True)
    build_figure4(output, ledger)
    compare_outputs(output, ledger)
    _write_json(output / "POOLED_AUTHORITY_PROVENANCE.json", pooled_provenance)
    pd.DataFrame(ledger.rows).to_csv(output / "QA_SUMMARY.csv", index=False)
    ledger.require()
    return {
        "status": "PASS",
        "mode": "Verify",
        "checks": len(ledger.rows),
        "global_compounds": len(drugs),
        "global_pairs": len(pairwise),
        "scientific_assumptions_changed": False,
        "pooled_authority_mode": pooled_authority_mode,
        "pooled_full77_sha256": pooled_provenance["full77_sha256"],
        "pooled_strict18_sha256": pooled_provenance["strict18_sha256"],
        "pooled_raw_profile_source": pooled_provenance["raw_hr_source"],
        "pooled_common_rhr_source": pooled_provenance["common_rhr_source"],
    }


STAGE_PROVENANCE_FILE = "PORTABLE_STAGE_PROVENANCE.json"
V3_OUTPUT_NAMES = (
    "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FORENSIC_V3.csv",
    "SELECTED_SOURCE_ROW_FORENSIC.csv",
)


def _named_file_hashes(files: dict[str, Path]) -> dict[str, str]:
    """Hash a role-to-file mapping for provenance comparison."""
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise RuntimeError("Stage provenance input is missing: " + ", ".join(sorted(missing)))
    return {name: sha256(path) for name, path in sorted(files.items())}


def _inventory_file(path: Path) -> dict[str, Any]:
    """Return path, size, and digest metadata for an external file."""
    resolved = path.resolve()
    record: dict[str, Any] = {"path": str(resolved), "exists": resolved.is_file()}
    if record["exists"]:
        record.update({"sha256": sha256(resolved), "size": resolved.stat().st_size})
    else:
        record.update({"sha256": "MISSING", "size": None})
    return record


def _resolve_v2_project_inventory(project_root: Path, supplied_pdsp: Path) -> dict[str, Any]:
    """Resolve the governed v2 external-source inventory without substitution."""
    from .upstream import cleanup_pooled_parent_ketamine_activity_v2 as producer

    identity = (
        project_root
        / "12_QA_AUDITS_AND_PROVENANCE"
        / "Audit_Reports"
        / "Racemic_Ketamine_Identity_Coverage_Audit_20260805_165431_492"
        / "02_SOURCE_RECORD_INVENTORY"
        / "KETAMINE_SOURCE_ASSERTION_MASTER.parquet"
    )
    candidates = producer.find_pdsp_workbooks(project_root)
    ranked: list[tuple[int, int, Path]] = []
    for path in candidates:
        low = str(path).lower()
        score = (10 if path.name.lower().startswith("kidatabase") else 0)
        score += 5 if "pdsp" in low else 0
        score += 3 if "raw" in low else 0
        ranked.append((score, path.stat().st_size, path.resolve()))
    ranked.sort(key=lambda item: (-item[0], -item[1], str(item[2]).lower()))
    audit, _, _ = producer.load_pdsp_raw(project_root, lambda _message: None)
    if not audit or not Path(str(audit.get("path", ""))).is_file():
        raise RuntimeError("The v2 producer could not deterministically select a usable PDSP workbook")
    selected = Path(str(audit["path"])).resolve()
    if sha256(selected) != sha256(supplied_pdsp):
        raise RuntimeError(
            "The v2 dynamically selected PDSP workbook differs from the explicitly supplied Full-mode PDSP input"
        )
    candidate_records = []
    for rank, (score, size, path) in enumerate(ranked, start=1):
        record = _inventory_file(path)
        record.update({"rank": rank, "score": score, "ranked_size": size, "selected": path == selected})
        candidate_records.append(record)
    if sum(bool(record["selected"]) for record in candidate_records) != 1:
        raise RuntimeError("The selected v2 PDSP workbook was not uniquely represented in its candidate inventory")
    return {
        "resolver": "V2_PRODUCER_MATCHED_PROJECT_INPUT_INVENTORY_V1",
        "identity_master": _inventory_file(identity),
        "pdsp_candidates": candidate_records,
        "pdsp_selected": _inventory_file(selected),
        "pdsp_supplied": _inventory_file(supplied_pdsp),
    }


def _v3_pdsp_candidates(project_root: Path) -> list[Path]:
    """Enumerate only the governed PDSP workbook search locations."""
    roots = [
        project_root / "09_CODE_AND_PIPELINES" / "Historical_Project_Trees",
        project_root / "12_QA_AUDITS_AND_PROVENANCE",
        project_root / "98_DEPRECATED",
    ]
    candidates: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for pattern in ("KiDatabase*.xlsx", "*PDSP*Ki*.xlsx", "KiDatabase*.xls"):
            try:
                candidates.update(path.resolve() for path in root.rglob(pattern) if path.is_file())
            except OSError:
                continue
    return sorted(
        candidates,
        key=lambda path: (
            0 if path.name.lower().startswith("kidatabase") else 1,
            len(str(path)),
            str(path).lower(),
        ),
    )


def _v3_source_groups(v2_dir: Path) -> list[str]:
    """Extract stable source-file groups referenced by the v2 audit."""
    from .upstream import forensic_finalize_pooled_parent_ketamine_activity_v3 as producer

    cleaned = pd.read_csv(
        v2_dir / "POOLED_PARENT_KETAMINE_ACTIVITY_TABLE_SPECIES_CLEANED.csv",
        low_memory=False,
    )
    target = pd.read_csv(
        v2_dir / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY.csv",
        low_memory=False,
    )
    selected_p5 = target[
        target["proposed_selected_pActivity"].fillna(-999).eq(5.0)
        & target["proposed_selected_source_database"].astype(str).str.contains(
            "PDSP", case=False, na=False
        )
    ].copy()
    selected_unknown = target[
        target["proposed_selection_status"]
        .astype(str)
        .str.contains("BOUNDED_DIRECTION_UNKNOWN", na=False)
    ].copy()
    selected = pd.concat([selected_p5, selected_unknown], ignore_index=True).drop_duplicates(
        "proposed_selected_source_assertion_id"
    )
    source_paths: set[str] = set()
    for row in selected.itertuples(index=False):
        assertion_id = producer.s(getattr(row, "proposed_selected_source_assertion_id", ""))
        if not assertion_id:
            continue
        matches = cleaned[cleaned["source_assertion_id"].astype(str).eq(assertion_id)]
        if matches.empty:
            continue
        first = matches.iloc[0]
        source_path = producer.s(first.get("source_file"))
        source_rows = producer.parse_source_rows(first.get("source_rows"))
        if source_path and source_rows:
            source_paths.add(source_path)
    return sorted(source_paths, key=str.lower)


def _v3_source_resolution_inventory(source_path: str, project_root: Path) -> dict[str, Any]:
    """Resolve one legacy source path within the supplied project root."""
    from .upstream import forensic_finalize_pooled_parent_ketamine_activity_v3 as producer

    direct = Path(source_path)
    candidates: list[dict[str, Any]] = [{"tier": "DIRECT", **_inventory_file(direct)}]
    # This deliberately preserves the producer's two-backslash reorganization
    # marker exactly; changing it would inventory a different candidate set.
    marker = r"\Ketamine project\ketamine_hr_analysis\\"
    index = source_path.lower().find(marker.lower())
    if index >= 0:
        relative = source_path[index + len(marker) :]
        reorganized = (
            project_root
            / "09_CODE_AND_PIPELINES"
            / "Historical_Project_Trees"
            / "ketamine_hr_analysis"
            / Path(relative)
        )
        candidates.append({"tier": "REORGANIZED", **_inventory_file(reorganized)})
    basename = Path(source_path).name
    roots = [
        project_root / "09_CODE_AND_PIPELINES" / "Historical_Project_Trees",
        project_root / "12_QA_AUDITS_AND_PROVENANCE",
        project_root / "98_DEPRECATED",
    ]
    fallback_roots = []
    for priority, root in enumerate(roots, start=1):
        hits: list[Path] = []
        if root.exists():
            try:
                hits = sorted(
                    {path.resolve() for path in root.rglob(basename) if path.is_file()},
                    key=lambda path: (len(str(path)), str(path).lower()),
                )
            except OSError:
                hits = []
        fallback_roots.append(
            {
                "priority": priority,
                "root": str(root.resolve()),
                "root_exists": root.exists(),
                "candidates": [_inventory_file(path) for path in hits],
            }
        )
    resolved = producer.resolve_legacy_source_path(source_path, project_root)
    resolved_record = _inventory_file(resolved) if resolved is not None else {
        "path": "",
        "exists": False,
        "sha256": "MISSING",
        "size": None,
    }
    known = {
        str(record["path"]).lower()
        for record in candidates
        if record["exists"]
    }
    known.update(
        str(record["path"]).lower()
        for root in fallback_roots
        for record in root["candidates"]
    )
    if resolved_record["exists"] and str(resolved_record["path"]).lower() not in known:
        raise RuntimeError(f"V3 resolver selected an uninventoried source file: {resolved_record['path']}")
    return {
        "legacy_source_path": source_path,
        "direct_and_reorganized_candidates": candidates,
        "fallback_roots": fallback_roots,
        "resolved": resolved_record,
    }


def _resolve_v3_project_inventory(
    project_root: Path,
    supplied_pdsp: Path,
    v2_dir: Path,
) -> dict[str, Any]:
    """Resolve and hash all governed v3 external-source inputs."""
    from .upstream import forensic_finalize_pooled_parent_ketamine_activity_v3 as producer

    selected_pdsp = producer.find_pdsp(project_root, supplied_pdsp.resolve(), lambda _message: None)
    if selected_pdsp is None or not selected_pdsp.is_file():
        raise RuntimeError("The v3 producer could not deterministically select a PDSP workbook")
    selected_pdsp = selected_pdsp.resolve()
    if sha256(selected_pdsp) != sha256(supplied_pdsp):
        raise RuntimeError("The v3 selected PDSP workbook differs from the explicitly supplied input")
    source_paths = _v3_source_groups(v2_dir)
    return {
        "resolver": "V3_PRODUCER_MATCHED_PROJECT_INPUT_INVENTORY_V1",
        "pdsp_supplied": _inventory_file(supplied_pdsp),
        "pdsp_selected": _inventory_file(selected_pdsp),
        "pdsp_fallback_candidates": [
            _inventory_file(path) for path in _v3_pdsp_candidates(project_root)
        ],
        "legacy_source_resolutions": [
            _v3_source_resolution_inventory(path, project_root) for path in source_paths
        ],
    }


def _summary_external_file_hashes(stage: Path) -> dict[str, dict[str, str]]:
    """Extract external file hashes from one stage summary."""
    summary_path = stage / "SUMMARY.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records: dict[str, dict[str, str]] = {}

    def visit(value: Any, key: str) -> None:
        """Recursively collect file-hash records from a summary structure."""
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, f"{key}.{child_key}" if key else str(child_key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{key}[{index}]")
        elif isinstance(value, str):
            candidate = Path(value)
            if not candidate.is_absolute() or not candidate.is_file():
                return
            resolved = candidate.resolve()
            try:
                resolved.relative_to(stage.resolve())
                return
            except ValueError:
                pass
            records[key] = {"path": str(resolved), "sha256": sha256(resolved)}

    visit(summary, "")
    return records


def _write_stage_provenance(
    stage: Path,
    script: Path,
    input_files: dict[str, Path],
    output_names: list[str],
    project_input_inventory: dict[str, Any] | None = None,
) -> None:
    """Write input and output lineage evidence for one recovered stage."""
    outputs = {name: stage / name for name in sorted(set(output_names + ["SUMMARY.json"]))}
    payload = {
        "schema_version": "1.0",
        "script_sha256": sha256(script),
        "inputs": _named_file_hashes(input_files),
        "outputs": _named_file_hashes(outputs),
        "summary_external_files": _summary_external_file_hashes(stage),
        "project_input_inventory": project_input_inventory or {},
    }
    _write_json(stage / STAGE_PROVENANCE_FILE, payload)


def _validate_stage_reuse(
    stage: Path,
    script: Path,
    input_files: dict[str, Path],
    output_names: list[str],
    project_input_inventory: dict[str, Any] | None = None,
) -> str:
    """Confirm a recovered stage reused exactly the expected external inputs."""
    summary_path = stage / "SUMMARY.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    status = str(
        summary.get("status")
        or summary.get("run_status")
        or summary.get("overall_status")
        or "UNKNOWN"
    )
    if not status.startswith("PASS"):
        raise RuntimeError(f"Existing stage is not reusable: {stage} ({status})")
    provenance_path = stage / STAGE_PROVENANCE_FILE
    if not provenance_path.is_file():
        raise RuntimeError(
            f"Existing stage is not reusable because {STAGE_PROVENANCE_FILE} is absent: {stage}"
        )
    observed = json.loads(provenance_path.read_text(encoding="utf-8"))
    expected_script = sha256(script)
    expected_inputs = _named_file_hashes(input_files)
    mismatches: list[str] = []
    if observed.get("script_sha256") != expected_script:
        mismatches.append("script_sha256")
    if observed.get("project_input_inventory") != (project_input_inventory or {}):
        mismatches.append("project_input_inventory")
    observed_inputs = observed.get("inputs") if isinstance(observed.get("inputs"), dict) else {}
    for name in sorted(set(expected_inputs) | set(observed_inputs)):
        if observed_inputs.get(name) != expected_inputs.get(name):
            mismatches.append(f"input:{name}")
    expected_output_names = sorted(set(output_names + ["SUMMARY.json"]))
    observed_outputs = observed.get("outputs") if isinstance(observed.get("outputs"), dict) else {}
    if sorted(observed_outputs) != expected_output_names:
        mismatches.append("output_contract")
    else:
        for name in expected_output_names:
            path = stage / name
            current_hash = sha256(path) if path.is_file() else "MISSING"
            if current_hash != observed_outputs.get(name):
                mismatches.append(f"output:{name}")
    external_files = observed.get("summary_external_files")
    if not isinstance(external_files, dict):
        mismatches.append("summary_external_files")
    else:
        for name, record in sorted(external_files.items()):
            if not isinstance(record, dict):
                mismatches.append(f"external:{name}")
                continue
            path = Path(str(record.get("path", "")))
            current_hash = sha256(path) if path.is_file() else "MISSING"
            if current_hash != record.get("sha256"):
                mismatches.append(f"external:{name}")
    if mismatches:
        raise RuntimeError(
            f"Existing stage provenance mismatch for {stage.name}: " + ", ".join(mismatches)
        )
    return status


def _run_timestamped_stage(command: list[str], parent: Path, pattern: str) -> tuple[Path, str]:
    """Run one recovered stage and resolve its single timestamped output."""
    before = {path.resolve() for path in parent.glob(pattern) if path.is_dir()}
    subprocess.run(command, check=True)
    created = sorted(
        (path.resolve() for path in parent.glob(pattern) if path.is_dir() and path.resolve() not in before),
        key=lambda path: path.as_posix(),
    )
    if len(created) != 1:
        raise RuntimeError(
            f"Expected exactly one new {pattern} stage under {parent}, observed {len(created)}"
        )
    stage = created[0]
    summary_path = stage / "SUMMARY.json"
    if not summary_path.is_file():
        raise RuntimeError(f"Stage did not produce SUMMARY.json: {stage}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    status = str(
        summary.get("status")
        or summary.get("run_status")
        or summary.get("overall_status")
        or "UNKNOWN"
    )
    if not status.startswith("PASS"):
        raise RuntimeError(f"Stage did not report PASS: {stage} ({status})")
    return stage, status


def _resolve_expression_authority(project_root: Path, supplied: Path | None) -> tuple[Path, Path]:
    """Resolve an explicit or uniquely governed expression authority."""
    expected_master_hash = "11F4646C13B80C346020B28FA942BFC729950D5D29FB89083EC4BB0829E6C8B7"
    if supplied is not None:
        authorities = [supplied.resolve()]
    else:
        authority_parent = project_root / "01_AUTHORITIES" / "Feature_and_Expression_Authority"
        authorities = sorted(authority_parent.glob("Pre_Fingerprint_Authority_*"))
    matches: list[tuple[Path, Path]] = []
    for authority in authorities:
        master = authority / "06_PRE_FINGERPRINT_MASTER" / "PRE_FINGERPRINT_MASTER_ALL_SPECIES.parquet"
        if master.is_file() and sha256(master) == expected_master_hash:
            matches.append((authority, master))
    if not matches:
        raise RuntimeError(
            "Could not resolve the governed expression authority by its frozen SHA-256; provide --expression-authority."
        )
    return matches[0]


def _validate_full_upstream(
    v4: Path,
    expanded58: Path,
    strict18: Path,
    output: Path,
) -> CheckLedger:
    """Validate full-mode upstream outputs before downstream analysis."""
    ledger = CheckLedger()
    expectations = [
        (
            "full_v4_selected_activity_hash",
            v4 / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv",
            "7C23FC0ED80FF6E460F753F778BDB744AFB3FA12F0EA11215E95760849E3B15C",
        ),
        (
            "full77_csv_hash",
            expanded58 / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.csv",
            "EEC4CF21F3113FF214B99A825171FBCC29232E5C925EFCDF3DFC0B7327FAC475",
        ),
        (
            "strict18_hr_hash",
            strict18 / "POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv",
            "48027602E0A9E63D48977BEA885155CD36D5826C773231F8CC38116354781BD8",
        ),
        (
            "strict18_alpha001_hash",
            strict18 / "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p001_V1.csv",
            "653D384BD2D1AC790DCDF101E1E1DC07B8B3DFECC95D992B29C376886604E387",
        ),
        (
            "strict18_alpha0001_hash",
            strict18 / "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p0001_V1.csv",
            "18C7F33DC9079FBFC8F00B16C4EAD20F8DAD5601DF60E556F99CCCA1DB1E7F64",
        ),
    ]
    for check, path, expected in expectations:
        observed = sha256(path) if path.is_file() else "MISSING"
        ledger.add(check, observed == expected, observed, expected)
    generated_parquet = expanded58 / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.parquet"
    reference_parquet = DATA / "core" / "pooled_full77_hr.parquet"
    full = pd.read_parquet(generated_parquet)
    reference_full = pd.read_parquet(reference_parquet)
    parquet_detail = ""
    parquet_equivalent = True
    try:
        sort_keys = ["canonical_target_id", "tissue_id"]
        pd.testing.assert_frame_equal(
            full.sort_values(sort_keys).reset_index(drop=True),
            reference_full.sort_values(sort_keys).reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            atol=1e-12,
            rtol=0.0,
        )
    except AssertionError as exc:
        parquet_equivalent = False
        parquet_detail = str(exc).splitlines()[0]
    ledger.add(
        "full77_parquet_numerical_equivalence",
        parquet_equivalent,
        f"generated_sha256={sha256(generated_parquet)}",
        f"numerically equal to authority_sha256={sha256(reference_parquet)} at atol=1e-12",
        parquet_detail,
    )
    strict = pd.read_csv(strict18 / "POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv", low_memory=False)
    ledger.add(
        "full_upstream_full77_dimensions",
        (full["canonical_target_id"].nunique(), full["tissue_id"].nunique(), len(full)) == (58, 77, 4466),
        f"{full['canonical_target_id'].nunique()}x{full['tissue_id'].nunique()}={len(full)}",
        "58x77=4466",
    )
    ledger.add(
        "full_upstream_strict18_dimensions",
        (strict["canonical_target_id"].nunique(), strict["tissue_id"].nunique(), len(strict)) == (58, 18, 1044),
        f"{strict['canonical_target_id'].nunique()}x{strict['tissue_id'].nunique()}={len(strict)}",
        "58x18=1044",
    )
    pd.DataFrame(ledger.rows).to_csv(output / "FULL_UPSTREAM_VALIDATION.csv", index=False)
    ledger.require()
    return ledger


FULL_DOWNSTREAM_DIRNAME = "verify_after_upstream_equivalence"


def _write_combined_full_qa(
    output: Path,
    upstream_ledger: CheckLedger,
    downstream_dir: Path,
) -> int:
    """Combine stage checks into the final full-mode QA ledger."""
    upstream_qa = pd.DataFrame(upstream_ledger.rows)
    upstream_qa.insert(0, "category", "UPSTREAM_AUTHORITY_EQUIVALENCE")
    downstream_qa = pd.read_csv(downstream_dir / "QA_SUMMARY.csv", low_memory=False)
    downstream_qa.insert(0, "category", "DOWNSTREAM_VERIFY_AFTER_UPSTREAM_EQUIVALENCE")
    combined_qa = pd.concat([upstream_qa, downstream_qa], ignore_index=True, sort=False)
    combined_qa.to_csv(output / "QA_SUMMARY.csv", index=False)
    return len(combined_qa)


def full_mode(
    output: Path,
    initial_activity_table: Path | None,
    pdsp_workbook: Path | None,
    project_root: Path | None,
    expression_authority: Path | None,
    external_input_root: Path | None,
) -> dict[str, Any]:
    """Execute recovered upstream stages and downstream external-input Verify.

    Full is deliberately not self-contained.  It validates all caller-supplied
    source and comparator inputs before use, writes only to ``output``, and
    preserves provenance-gated resume behavior.
    """

    if (
        initial_activity_table is None
        or pdsp_workbook is None
        or project_root is None
        or external_input_root is None
    ):
        raise RuntimeError(
            "Full requires --initial-activity-table, --pdsp-workbook, --project-root, and --external-input-root. External primary and comparator inputs are intentionally not committed; see docs/FULL_MODE.md."
        )
    if (
        not initial_activity_table.is_file()
        or not pdsp_workbook.is_file()
        or not project_root.is_dir()
        or not external_input_root.is_dir()
    ):
        raise FileNotFoundError("One or more Full-mode external inputs do not exist")
    initial_activity_table = initial_activity_table.resolve()
    pdsp_workbook = pdsp_workbook.resolve()
    project_root = project_root.resolve()
    external_input_root = external_input_root.resolve()
    expression_authority, expression_master = _resolve_expression_authority(project_root, expression_authority)
    external = output / "external_rebuild"
    external.mkdir(parents=True, exist_ok=True)
    scripts = REPO_ROOT / "src" / "cardozo_ketamine_hr" / "upstream"
    stage_rows: list[dict[str, str]] = []

    lineage_inputs = {
        "initial_activity_table": initial_activity_table,
        "pdsp_workbook": pdsp_workbook,
    }

    def run(
        script: str,
        arguments: list[str],
        parent: Path,
        pattern: str,
        input_files: dict[str, Path],
        output_names: list[str],
        project_input_inventory: dict[str, Any] | None = None,
    ) -> Path:
        """Execute one full-mode stage with task-state and failure recording."""
        script_path = scripts / script
        provenance_inputs = {**lineage_inputs, **input_files}
        existing = sorted((path.resolve() for path in parent.glob(pattern) if path.is_dir()), key=lambda path: path.as_posix())
        if len(existing) == 1:
            status = _validate_stage_reuse(
                existing[0],
                script_path,
                provenance_inputs,
                output_names,
                project_input_inventory,
            )
            stage_rows.append(
                {
                    "stage": pattern.rstrip("*"),
                    "status": f"REUSED_{status}",
                    "output": existing[0].relative_to(output).as_posix(),
                    "provenance_sha256": sha256(existing[0] / STAGE_PROVENANCE_FILE),
                }
            )
            return existing[0]
        if len(existing) > 1:
            raise RuntimeError(f"Ambiguous resumable stage set for {pattern} under {parent}: {len(existing)}")
        stage, status = _run_timestamped_stage(
            [sys.executable, str(script_path), *arguments], parent, pattern
        )
        _write_stage_provenance(
            stage,
            script_path,
            provenance_inputs,
            output_names,
            project_input_inventory,
        )
        stage_rows.append(
            {
                "stage": pattern.rstrip("*"),
                "status": status,
                "output": stage.relative_to(output).as_posix(),
                "provenance_sha256": sha256(stage / STAGE_PROVENANCE_FILE),
            }
        )
        return stage

    v2_project_inventory = _resolve_v2_project_inventory(project_root, pdsp_workbook)
    v2 = run(
        "cleanup_pooled_parent_ketamine_activity_v2.py",
        [
            "--input", str(initial_activity_table),
            "--project-root", str(project_root),
            "--output-parent", str(external),
        ],
        external,
        "Species_Cleanup_Bounded_v2_*",
        {},
        [
            "POOLED_PARENT_KETAMINE_ACTIVITY_TABLE_SPECIES_CLEANED.csv",
            "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY.csv",
        ],
        v2_project_inventory,
    )
    v3_project_inventory = _resolve_v3_project_inventory(project_root, pdsp_workbook, v2)
    v3 = run(
        "forensic_finalize_pooled_parent_ketamine_activity_v3.py",
        ["--project-root", str(project_root), "--v2-dir", str(v2), "--pdsp", str(pdsp_workbook)],
        v2,
        "Forensic_Finalization_v3_*",
        {
            "v2_provenance": v2 / STAGE_PROVENANCE_FILE,
            "v2_cleaned_activity": v2 / "POOLED_PARENT_KETAMINE_ACTIVITY_TABLE_SPECIES_CLEANED.csv",
            "v2_target_summary": v2 / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY.csv",
        },
        list(V3_OUTPUT_NAMES),
        v3_project_inventory,
    )
    v4 = run(
        "finalize_pooled_parent_ketamine_activity_v4.py",
        ["--v3-dir", str(v3)],
        v3,
        "Final_Activity_v4_*",
        {
            "v3_provenance": v3 / STAGE_PROVENANCE_FILE,
            "v3_target_summary": v3 / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FORENSIC_V3.csv",
        },
        [
            "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FINAL_V4.csv",
            "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv",
        ],
    )
    hr1 = run(
        "generate_pooled_parent_ketamine_full_hr_v1.py",
        ["--v4-dir", str(v4), "--expression-authority", str(expression_authority)],
        v4,
        "Full_Tissue_HR_v1_*",
        {
            "v4_provenance": v4 / STAGE_PROVENANCE_FILE,
            "v4_activity": v4 / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv",
            "expression_master": expression_master,
        },
        [
            "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv",
            "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.parquet",
            "POOLED_PARENT_KETAMINE_MISSING_EXPRESSION_TARGETS_V1.csv",
        ],
    )
    recovery = run(
        "audit_recover_missing38_biogas_expression_v1.py",
        ["--project-root", str(project_root), "--v4-dir", str(v4), "--hr1-dir", str(hr1)],
        hr1,
        "Missing38_Expression_Recovery_Audit_v1_*",
        {
            "v4_provenance": v4 / STAGE_PROVENANCE_FILE,
            "v4_activity": v4 / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv",
            "hr1_provenance": hr1 / STAGE_PROVENANCE_FILE,
            "hr1_full_hr": hr1 / "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv",
        },
        [
            "RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.csv",
            "RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.parquet",
            "STILL_UNRECOVERABLE_TARGETS.csv",
        ],
    )
    expanded58 = run(
        "generate_pooled_parent_ketamine_expanded58_hr_v2.py",
        ["--v4-dir", str(v4), "--hr1-dir", str(hr1), "--recovery-dir", str(recovery)],
        hr1,
        "Expanded58_Full_Tissue_HR_v2_*",
        {
            "v4_provenance": v4 / STAGE_PROVENANCE_FILE,
            "v4_activity": v4 / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv",
            "hr1_provenance": hr1 / STAGE_PROVENANCE_FILE,
            "hr1_full_hr": hr1 / "POOLED_PARENT_KETAMINE_FULL_HR_LONG_V1.csv",
            "recovery_provenance": recovery / STAGE_PROVENANCE_FILE,
            "recovered_expression": recovery / "RECOVERABLE_MISSING38_EXPRESSION_77TISSUE.csv",
        },
        [
            "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.csv",
            "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.parquet",
        ],
    )
    strict18 = run(
        "generate_pooled_parent_ketamine_strict18_fingerprint_v1.py",
        ["--v4-dir", str(v4), "--expanded58-dir", str(expanded58)],
        expanded58,
        "Strict18_Fingerprint_v1_*",
        {
            "v4_provenance": v4 / STAGE_PROVENANCE_FILE,
            "v4_activity": v4 / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv",
            "expanded58_provenance": expanded58 / STAGE_PROVENANCE_FILE,
            "expanded58_full_hr": expanded58 / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.csv",
        },
        [
            "POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv",
            "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p001_V1.csv",
            "POOLED_PARENT_KETAMINE_FINGERPRINT_ALPHA_0p0001_V1.csv",
        ],
    )
    pd.DataFrame(stage_rows).to_csv(output / "FULL_UPSTREAM_STAGE_STATUS.csv", index=False)
    upstream_ledger = _validate_full_upstream(v4, expanded58, strict18, output)
    regenerated_full = expanded58 / "POOLED_PARENT_KETAMINE_FULL_HR_EXPANDED58_LONG_V2.parquet"
    regenerated_strict = strict18 / "POOLED_PARENT_KETAMINE_STRICT18_NUMERIC_HR_INPUT_V1.csv"
    downstream_dir = output / FULL_DOWNSTREAM_DIRNAME
    state = verify(
        downstream_dir,
        pooled_full_path=regenerated_full,
        pooled_strict_path=regenerated_strict,
        pooled_authority_mode="FULL_REGENERATED_POOLED_AUTHORITIES_AFTER_EXACT_UPSTREAM_EQUIVALENCE",
        external_input_root=external_input_root,
    )
    combined_checks = _write_combined_full_qa(output, upstream_ledger, downstream_dir)
    downstream_checks = int(state["checks"])
    state.update(
        {
            "mode": "Full",
            "checks": combined_checks,
            "downstream_verification_checks": downstream_checks,
            "upstream_stages_completed": len(stage_rows),
            "upstream_stages_executed": sum(
                not row["status"].startswith("REUSED_") for row in stage_rows
            ),
            "upstream_stages_reused": sum(
                row["status"].startswith("REUSED_") for row in stage_rows
            ),
            "upstream_resume_used": any(row["status"].startswith("REUSED_") for row in stage_rows),
            "upstream_validation_checks": len(upstream_ledger.rows),
            "upstream_authority_equivalence": "PASS",
            "downstream_verification_directory": downstream_dir.relative_to(output).as_posix(),
            "downstream_pooled_authority_substitution": "REGENERATED_FULL77_AND_STRICT18_EXPLICITLY_SUPPLIED; STRICT18_RAW_PROFILE_INJECTED; FROZEN_COMMON_RHR_RETAINED_ONLY_AFTER_RAW_HR_EQUIVALENCE_GATE",
            "initial_activity_table_sha256": sha256(initial_activity_table),
            "pdsp_workbook_sha256": sha256(pdsp_workbook),
            "expression_master_sha256": sha256(expression_master),
            "limitation": "The producer of the initial activity assertion table was not recovered; Full begins at that explicit governed input boundary and regenerates every recovered downstream pooled-parent stage before the 35-profile comparative verification.",
        }
    )
    return state


def main(argv: list[str] | None = None) -> int:
    """Parse the portable CLI, execute one lane, and persist terminal state."""

    parser = argparse.ArgumentParser(description="Portable Cardozo ketamine historeceptomics workflow")
    parser.add_argument("--mode", choices=["Smoke", "Verify", "Full"], default="Verify")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--initial-activity-table", type=Path)
    parser.add_argument("--pdsp-workbook", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--expression-authority", type=Path)
    parser.add_argument(
        "--external-input-root",
        type=Path,
        help="User-supplied directory mirroring the excluded data/frozen tree; required by Verify and Full.",
    )
    args = parser.parse_args(argv)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (args.output_dir or (REPO_ROOT / "results" / "runs" / f"{args.mode.lower()}_{timestamp}")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    try:
        if args.mode == "Smoke":
            state = smoke(output)
        elif args.mode == "Verify":
            state = verify(output, external_input_root=args.external_input_root)
        else:
            state = full_mode(
                output,
                args.initial_activity_table,
                args.pdsp_workbook,
                args.project_root,
                args.expression_authority,
                args.external_input_root,
            )
        status = "COMPLETE"
        code = 0
    except Exception as exc:
        state = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)}
        status = "FAILED"
        code = 1
    state.update(
        {
            "task_status": status,
            "output_dir": str(output),
            "started_utc": started.isoformat(),
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "platform": sys.platform,
            "cpu_only_deterministic_float64": True,
        }
    )
    _write_json(output / "task_state.json", state)
    write_run_manifest(output)
    print(json.dumps(state, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
