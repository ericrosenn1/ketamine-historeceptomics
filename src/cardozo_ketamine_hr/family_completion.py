# SPDX-License-Identifier: MIT
"""Complete the governed ketamine-family lane with E7 metabolite evidence.

Stage
-----
This module runs after frozen pooled-parent and U1/HPF family profiles are
loaded. It appends the frozen E7 numerical profiles, constructs compatible
call matrices, and produces availability and forensic identity audits.

Inputs
------
Path mappings identify frozen U1/HPF and E7 authorities, while profile and
contract tables supply already-governed identities and feature coordinates.

Outputs
-------
Functions return derivative pandas tables and a forensic summary dictionary;
the module itself writes no output files.

Side Effects
------------
Read-only access to CSV and Parquet authorities and computation of source
SHA-256 digests.

Invariants
----------
Missing, tested non-call, and called cells remain distinct; stereochemical
identities are not merged; equality on shared modeled coordinates is audited
without being reinterpreted as biological equivalence.

Lane
----
Frozen ketamine-family completion and identity-QA lane.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .family_analysis import FAMILY_LABELS
from .utilities import sha256_file


POOLED = "Ketamine, pooled parent"
RACEMATE = "Ketamine, confirmed racemate"

E7_LABELS = {
    "HNK_2R_6R": "(2R,6R)-hydroxynorketamine",
    "HNK_2S_6S": "(2S,6S)-hydroxynorketamine",
    "HNK_GENERIC": "Hydroxynorketamine / HNK, generic identity",
    "HYDROXYKETAMINE_GENERIC": "Hydroxyketamine, generic E7 identity",
    "NORKETAMINE": "Norketamine",
}

FINAL_FAMILY_ORDER = [
    POOLED,
    RACEMATE,
    "S-ketamine",
    "R-ketamine",
    "Hydroxyketamine, unspecified isomer aggregate",
    E7_LABELS["HNK_2R_6R"],
    E7_LABELS["HNK_2S_6S"],
    E7_LABELS["HNK_GENERIC"],
    E7_LABELS["HYDROXYKETAMINE_GENERIC"],
    E7_LABELS["NORKETAMINE"],
]

METABOLITE_LABELS = [
    "Hydroxyketamine, unspecified isomer aggregate",
    E7_LABELS["HNK_2R_6R"],
    E7_LABELS["HNK_2S_6S"],
    E7_LABELS["HNK_GENERIC"],
    E7_LABELS["HYDROXYKETAMINE_GENERIC"],
    E7_LABELS["NORKETAMINE"],
]


def strict_contract_from_profiles(profiles: pd.DataFrame) -> pd.DataFrame:
    """Derive one ordered strict feature contract from long-form profiles.

    Parameters
    ----------
    profiles : pandas.DataFrame
        Long-form profile table containing feature and metadata columns.

    Returns
    -------
    pandas.DataFrame
        Unique features sorted stably by numeric feature order and identifier.
    """
    columns = ["feature_id", "target", "target_canonical_id", "tissue", "tissue_canonical_id", "feature_order"]
    contract = profiles[columns].drop_duplicates("feature_id").copy()
    contract["feature_order"] = pd.to_numeric(contract["feature_order"], errors="coerce")
    return contract.sort_values(["feature_order", "feature_id"], kind="stable").reset_index(drop=True)


def _wide(path: Path) -> pd.DataFrame:
    """Read a governed compound-by-feature CSV with compound IDs as index.

    Parameters
    ----------
    path : pathlib.Path
        CSV authority containing a ``compound_id`` column.

    Returns
    -------
    pandas.DataFrame
        Wide matrix indexed by compound identifier.
    """
    return pd.read_csv(path, low_memory=False).set_index("compound_id")


def load_e7_profiles(paths: dict[str, Path], contract: pd.DataFrame) -> pd.DataFrame:
    """Load the five frozen E7 metabolite profiles on the strict contract.

    Parameters
    ----------
    paths : dict of str to pathlib.Path
        Path mapping for E7 raw and common-scale matrices.
    contract : pandas.DataFrame
        Ordered strict feature contract.

    Returns
    -------
    pandas.DataFrame
        Long-form E7 raw-HR and common-RHR profiles with source provenance.
    """
    raw = _wide(paths["e7_raw_matrix"])
    common = _wide(paths["e7_common_matrix"])
    feature_ids = contract["feature_id"].astype(str).tolist()
    frames: list[pd.DataFrame] = []
    for compound_id, label in E7_LABELS.items():
        frame = contract.copy()
        frame["drug"] = label
        frame["raw_hr"] = pd.to_numeric(raw.loc[compound_id].reindex(feature_ids), errors="coerce").to_numpy()
        frame["common_rhr"] = pd.to_numeric(common.loc[compound_id].reindex(feature_ids), errors="coerce").to_numpy()
        frame["source_lane"] = "FROZEN_E7_FIVE_METABOLITE_COMMON_SCALE"
        frame["data_role"] = "EXPLORATORY_E7_METABOLITE_QUERY"
        frame["source_compound_id"] = compound_id
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def load_e7_call_rows(paths: dict[str, Path], alpha: str) -> pd.DataFrame:
    """Load E7 fingerprint calls for one alpha level.

    Parameters
    ----------
    paths : dict of str to pathlib.Path
        Mapping containing primary and sensitivity E7 call tables.
    alpha : str
        ``"001"`` routes to the sensitivity table; other governed values
        route to the primary alpha-0.0001 table.

    Returns
    -------
    pandas.DataFrame
        Called rows with normalized labels, common feature IDs, and numeric HR
        values.
    """
    key = "e7_sensitivity_calls" if alpha == "001" else "e7_primary_calls"
    frame = pd.read_csv(paths[key], low_memory=False)
    frame = frame[frame["called"].astype(bool)].copy()
    frame["drug"] = frame["compound_id"].map(E7_LABELS)
    frame["feature_id_common"] = frame["feature_id"].astype(str)
    frame["raw_hr"] = pd.to_numeric(frame["raw_HR_point"], errors="coerce")
    common_column = "common_RHR_mean" if "common_RHR_mean" in frame.columns else "common_RHR_point"
    frame["common_rhr"] = pd.to_numeric(frame[common_column], errors="coerce")
    return frame


def extend_call_matrices(
    existing: dict[str, pd.DataFrame],
    e7_profiles: pd.DataFrame,
    paths: dict[str, Path],
    contract: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Append E7 tested/called states to existing family call matrices.

    Parameters
    ----------
    existing : dict of str to pandas.DataFrame
        Existing binary and score matrices for both alpha levels.
    e7_profiles : pandas.DataFrame
        Long-form E7 raw/common profiles.
    paths : dict of str to pathlib.Path
        E7 call-table authorities.
    contract : pandas.DataFrame
        Ordered feature contract.

    Returns
    -------
    dict of str to pandas.DataFrame
        New matrices containing original rows followed by E7 identities.

    Notes
    -----
    Untested cells remain ``NaN``; tested non-calls become zero; called cells
    become one in binary matrices and receive common-RHR scores when finite.
    """
    features = contract["feature_id"].astype(str).tolist()
    result = {key: value.reindex(columns=features).copy() for key, value in existing.items()}
    raw = e7_profiles.pivot(index="drug", columns="feature_id", values="raw_hr").reindex(index=E7_LABELS.values(), columns=features)
    common = e7_profiles.pivot(index="drug", columns="feature_id", values="common_rhr").reindex(index=E7_LABELS.values(), columns=features)
    for alpha in ["001", "0001"]:
        binary = pd.DataFrame(np.nan, index=list(E7_LABELS.values()), columns=features, dtype=float)
        score = binary.copy()
        for drug in binary.index:
            # Only coordinates with raw support are known to have been tested;
            # unsupported coordinates must remain missing rather than zero.
            tested = raw.columns[raw.loc[drug].notna()]
            binary.loc[drug, tested] = 0.0
            score.loc[drug, tested] = 0.0
        called = load_e7_call_rows(paths, alpha)
        for row in called.itertuples(index=False):
            if row.drug not in binary.index or row.feature_id_common not in binary.columns:
                continue
            binary.loc[row.drug, row.feature_id_common] = 1.0
            value = common.loc[row.drug, row.feature_id_common]
            score.loc[row.drug, row.feature_id_common] = value if np.isfinite(value) else row.raw_hr
        result[f"call_binary_alpha{alpha}"] = pd.concat([result[f"call_binary_alpha{alpha}"], binary])
        result[f"call_score_alpha{alpha}"] = pd.concat([result[f"call_score_alpha{alpha}"], score])
    return result


def availability_audit(
    paths: dict[str, Path],
    source_run: Path,
    profiles: pd.DataFrame,
    call_matrices: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Audit numerical availability and downstream eligibility by identity.

    Parameters
    ----------
    paths : dict of str to pathlib.Path
        Frozen family/E7 authorities and accounting records.
    source_run : pathlib.Path
        Governed source-run root used only to locate frozen query artifacts.
    profiles : pandas.DataFrame
        Combined long-form family profiles.
    call_matrices : dict of str to pandas.DataFrame
        Combined fingerprint matrices for both alpha levels.

    Returns
    -------
    pandas.DataFrame
        Identity-level source provenance, coverage, eligibility, limitation,
        and checksum records.

    Notes
    -----
    Missing numerical profiles produce ``STATUS_ONLY`` records; they are never
    inferred from related identities.
    """
    e7_accounting = pd.read_csv(paths["e7_identity_accounting"], low_memory=False).set_index("compound_id")
    source_profile = source_run / "00_RUN_CONTROL" / "CACHED_MATRICES" / "ALL_COMPOUND_PROFILES_STRICT18_LONG.csv"
    rows: list[dict[str, Any]] = []
    identities = [
        ("POOLED_PARENT_KETAMINE", POOLED, "PARENT_REPRESENTATION", "PARENT", "UNSPECIFIED_PARENT_POOL", source_run / "01_QUERY_AUTHORITY" / "POOLED_PARENT_STRICT18_COMMON_SCALE_PROJECTION.csv"),
        ("ketamine_racemic", RACEMATE, "PARENT_IDENTITY_CONTROL", "PARENT", "CONFIRMED_RACEMATE", paths["family_common_matrix"]),
        ("esketamine", "S-ketamine", "PARENT_ENANTIOMER", "PARENT", "S", paths["family_common_matrix"]),
        ("arketamine", "R-ketamine", "PARENT_ENANTIOMER", "PARENT", "R", paths["family_common_matrix"]),
        ("hydroxyketamine_unspecified_isomer_aggregate", "Hydroxyketamine, unspecified isomer aggregate", "HYDROXYKETAMINE_AGGREGATE", "METABOLITE", "UNSPECIFIED_ISOMER_AGGREGATE", paths["family_common_matrix"]),
    ]
    identities.extend([
        (compound_id, label, "HYDROXYNORKETAMINE" if "HNK" in compound_id else "KETAMINE_METABOLITE", "METABOLITE", {
            "HNK_2R_6R": "2R,6R", "HNK_2S_6S": "2S,6S", "HNK_2R_6S": "2R,6S",
            "HNK_GENERIC": "UNSPECIFIED_HNK", "HYDROXYKETAMINE_GENERIC": "UNSPECIFIED_HYDROXYKETAMINE",
            "NORKETAMINE": "NOT_APPLICABLE", "DEHYDRONORKETAMINE": "NOT_APPLICABLE",
        }.get(compound_id, "UNSPECIFIED"), paths["e7_common_matrix"] if compound_id in E7_LABELS else paths["e7_identity_accounting"])
        for compound_id, label in [
            *E7_LABELS.items(),
            ("DEHYDRONORKETAMINE", "Dehydronorketamine"),
            ("HNK_2R_6S", "(2R,6S)-hydroxynorketamine"),
        ]
    ])
    for compound_id, label, compound_type, parent_or_metabolite, stereochemistry, source_file in identities:
        selected = profiles[profiles["drug"].eq(label)]
        raw_count = int(pd.to_numeric(selected.get("raw_hr"), errors="coerce").notna().sum()) if len(selected) else 0
        common_count = int(pd.to_numeric(selected.get("common_rhr"), errors="coerce").notna().sum()) if len(selected) else 0
        targets = int(selected.loc[pd.to_numeric(selected.get("common_rhr"), errors="coerce").notna(), "target"].nunique()) if len(selected) else 0
        alpha001 = label in call_matrices["call_binary_alpha001"].index
        alpha0001 = label in call_matrices["call_binary_alpha0001"].index
        numerical = raw_count > 0 and common_count > 0
        partial = numerical and (common_count < 20 or targets < 2)
        # Breadth thresholds annotate limitations only; they do not fabricate
        # support or remove an otherwise governed numerical profile.
        if numerical:
            status = "NUMERICAL_PARTIAL" if partial else "NUMERICAL_READY"
            reason = "LOW_STRICT18_BREADTH_RETAINED_WITH_EXPLICIT_LIMITATION" if partial else ""
        else:
            status = "STATUS_ONLY"
            reason = str(e7_accounting.loc[compound_id, "reference_only_reason"]) if compound_id in e7_accounting.index else "NO_GOVERNED_NUMERICAL_PROFILE"
        source_authority = "POOLED_PARENT_STRICT18_AUTHORITY" if compound_id == "POOLED_PARENT_KETAMINE" else ("FROZEN_E7_FIVE_METABOLITE_RELEASE" if compound_id in e7_accounting.index else "FROZEN_HPF_U1_FAMILY_AUTHORITY")
        rows.append({
            "compound_id": compound_id,
            "display_name": label,
            "compound_type": compound_type,
            "parent_or_metabolite": parent_or_metabolite,
            "stereochemistry": stereochemistry,
            "source_authority": source_authority,
            "source_file": str(source_file),
            "raw_HR_available": bool(raw_count),
            "common_RHR_available": bool(common_count),
            "strict18_available": bool(common_count),
            "fingerprint_alpha001_available": alpha001 and numerical,
            "fingerprint_alpha0001_available": alpha0001 and numerical,
            "supported_targets": targets,
            "supported_features": common_count,
            "numerical_status": status,
            "eligible_for_continuous_pairwise": numerical,
            "eligible_for_fingerprint_pairwise": numerical and alpha001 and alpha0001,
            "eligible_for_multivariate": numerical,
            "reason_if_not_eligible": reason,
            "QA_status": "PASS_WITH_LIMITATION" if partial or not numerical else "PASS",
            "source_sha256": sha256_file(source_file),
            "profile_cache": str(source_profile),
        })
    return pd.DataFrame(rows)


def forensic_audit(paths: dict[str, Path], contract: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Trace shared family values across activity, HR, and call layers.

    Parameters
    ----------
    paths : dict of str to pathlib.Path
        Frozen family matrices and fingerprint-call authorities.
    contract : pandas.DataFrame
        Strict feature contract used to align raw and common profiles.

    Returns
    -------
    audit : pandas.DataFrame
        Pair-by-representation equality, support, provenance, and conclusion
        records.
    summary : dict of str to Any
        Cross-layer conclusion, compact pair summaries, and source hashes.

    Notes
    -----
    Exact equality is measured only on shared non-missing support and does not
    collapse compound identities.
    """
    raw = pd.read_csv(paths["family_raw_matrix"], low_memory=False).set_index("canonical_compound_id")
    common = pd.read_csv(paths["family_common_matrix"], low_memory=False).set_index("canonical_compound_id")
    selected = pd.read_csv(paths["family_raw_matrix"].parents[2] / "02_TARGET_SELECTION" / "PRINCIPAL_U1_SELECTED_TARGET_ESTIMATES.csv", low_memory=False)
    calls001 = pd.read_parquet(paths["family_calls_001"])
    calls0001 = pd.read_parquet(paths["family_calls_0001"])
    ids = ["esketamine", "arketamine", "hydroxyketamine_unspecified_isomer_aggregate"]
    label = {key: FAMILY_LABELS[key] for key in ids}
    features = contract["feature_id"].astype(str).tolist()
    source_hashes = {
        "raw": sha256_file(paths["family_raw_matrix"]),
        "common": sha256_file(paths["family_common_matrix"]),
        "activity": sha256_file(paths["family_raw_matrix"].parents[2] / "02_TARGET_SELECTION" / "PRINCIPAL_U1_SELECTED_TARGET_ESTIMATES.csv"),
        "calls001": sha256_file(paths["family_calls_001"]),
        "calls0001": sha256_file(paths["family_calls_0001"]),
    }
    rows: list[dict[str, Any]] = []

    def compare(a: str, b: str, representation: str, av: pd.Series, bv: pd.Series, file_a: Path, file_b: Path, source_hash: str) -> dict[str, Any]:
        """Compare two aligned vectors and retain source-lineage fields.

        Parameters
        ----------
        a, b : str
            Canonical compound identifiers.
        representation : str
            Layer being compared.
        av, bv : pandas.Series
            Aligned source vectors; missing cells are excluded pairwise.
        file_a, file_b : pathlib.Path
            Source files for the compared vectors.
        source_hash : str
            Governed SHA-256 value recorded for both same-file vectors.

        Returns
        -------
        dict of str to Any
            Equality, support-mask, provenance, and placeholder synthesis
            fields for one comparison row.
        """
        av = pd.to_numeric(av, errors="coerce")
        bv = pd.to_numeric(bv, errors="coerce")
        mask = av.notna() & bv.notna()
        delta = (av[mask] - bv[mask]).abs()
        exact = int(delta.eq(0).sum())
        near = int(delta.le(1e-12).sum())
        return {
            "compound_a": label[a], "compound_b": label[b], "representation": representation,
            "matched_features": int(mask.sum()), "exact_equal_count": exact, "near_equal_count": near,
            "max_abs_difference": float(delta.max()) if len(delta) else np.nan,
            "mean_abs_difference": float(delta.mean()) if len(delta) else np.nan,
            "source_file_a": str(file_a), "source_file_b": str(file_b),
            "source_hash_a": source_hash, "source_hash_b": source_hash,
            "same_file_flag": file_a.resolve() == file_b.resolve(),
            "same_source_vector_flag": bool(len(delta) and exact == len(delta)),
            "same_activity_vector_flag": False,
            "same_raw_HR_flag": False, "same_common_RHR_flag": False,
            "same_support_mask_flag": bool(av.notna().equals(bv.notna())),
            "same_fingerprint_flag": False,
            "conclusion": "PENDING_CROSS_LAYER_SYNTHESIS", "QA_status": "PASS",
        }

    pair_summaries: dict[str, Any] = {}
    for a, b in combinations(ids, 2):
        pair_key = f"{a}__{b}"
        activity_a = selected[selected["canonical_compound_id"].eq(a)].set_index("canonical_target_id")["activity_strength_score"]
        activity_b = selected[selected["canonical_compound_id"].eq(b)].set_index("canonical_target_id")["activity_strength_score"]
        activity = compare(a, b, "SELECTED_TARGET_ACTIVITY_STRENGTH", activity_a, activity_b, paths["family_raw_matrix"].parents[2] / "02_TARGET_SELECTION" / "PRINCIPAL_U1_SELECTED_TARGET_ESTIMATES.csv", paths["family_raw_matrix"].parents[2] / "02_TARGET_SELECTION" / "PRINCIPAL_U1_SELECTED_TARGET_ESTIMATES.csv", source_hashes["activity"])
        activity["same_activity_vector_flag"] = activity["same_source_vector_flag"]
        rows.append(activity)
        raw_row = compare(a, b, "RAW_HR_STRICT18", raw.loc[a].reindex(features), raw.loc[b].reindex(features), paths["family_raw_matrix"], paths["family_raw_matrix"], source_hashes["raw"])
        common_row = compare(a, b, "COMMON_RHR_STRICT18", common.loc[a].reindex(features), common.loc[b].reindex(features), paths["family_common_matrix"], paths["family_common_matrix"], source_hashes["common"])
        raw_row["same_activity_vector_flag"] = activity["same_source_vector_flag"]
        raw_row["same_raw_HR_flag"] = raw_row["same_source_vector_flag"]
        common_row["same_activity_vector_flag"] = activity["same_source_vector_flag"]
        common_row["same_raw_HR_flag"] = raw_row["same_source_vector_flag"]
        common_row["same_common_RHR_flag"] = common_row["same_source_vector_flag"]
        rows.extend([raw_row, common_row])
        for alpha, calls, path_key in [("001", calls001, "family_calls_001"), ("0001", calls0001, "family_calls_0001")]:
            subsets = {}
            for compound in [a, b]:
                part = calls[calls["canonical_compound_id"].eq(compound)].set_index("feature_id")
                # Status equality is evaluated on the explicit call roster;
                # this local binary view is not used to fill absent features.
                subsets[compound] = part["fingerprint_status"].astype(str).eq("CALLED").astype(float)
            fp = compare(a, b, f"FINGERPRINT_ALPHA_{alpha}", subsets[a], subsets[b], paths[path_key], paths[path_key], source_hashes["calls001" if alpha == "001" else "calls0001"])
            fp["same_activity_vector_flag"] = activity["same_source_vector_flag"]
            fp["same_raw_HR_flag"] = raw_row["same_source_vector_flag"]
            fp["same_common_RHR_flag"] = common_row["same_source_vector_flag"]
            fp["same_fingerprint_flag"] = fp["same_source_vector_flag"] and fp["same_support_mask_flag"]
            rows.append(fp)
        pair_summaries[pair_key] = {
            "activity_exact": activity["same_source_vector_flag"],
            "raw_exact": raw_row["same_source_vector_flag"],
            "common_exact": common_row["same_source_vector_flag"],
            "matched_common_features": common_row["matched_features"],
            "support_identical": common_row["same_support_mask_flag"],
        }
    conclusion = (
        "VALID_INHERITED_MODELED_EQUALITY_NOT_ALIAS_OR_COPY_BUG: the frozen HPF authority deliberately assigns identical "
        "E4 modeled activity-strength values across many overlapping targets. Multiplication by the same expression "
        "coordinates and the same frozen monotone transform therefore induces exact raw-HR/common-RHR equality on "
        "shared support. Source assertion identifiers remain compound-specific and support masks differ."
    )
    for row in rows:
        row["conclusion"] = conclusion
    return pd.DataFrame(rows), {"conclusion": conclusion, "pair_summaries": pair_summaries, "source_hashes": source_hashes}
