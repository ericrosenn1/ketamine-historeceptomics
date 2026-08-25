# SPDX-License-Identifier: MIT
"""Load the frozen ketamine-family profiles, calls, and identity roster.

Stage
-----
Family loading occurs after authority resolution and before pairwise,
multivariate, or fingerprint analyses.

Inputs
------
Path mappings point to frozen family matrices and call tables; the strict
feature contract defines coordinate order and metadata.

Outputs
-------
Functions return normalized in-memory pandas tables. They do not mutate the
source authorities or write derivative files.

Side Effects
------------
Read-only CSV and Parquet access.

Invariants
----------
Racemic ketamine, enantiomers, and the unspecified-isomer metabolite aggregate
remain distinct identities, and missing numerical values remain missing.

Lane
----
Frozen ketamine-family U1/HPF ingestion lane.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


FAMILY_LABELS = {
    "ketamine_racemic": "Ketamine, confirmed racemate",
    "esketamine": "S-ketamine",
    "arketamine": "R-ketamine",
    "hydroxyketamine_unspecified_isomer_aggregate": "Hydroxyketamine, unspecified isomer aggregate",
}


def load_family_profiles(paths: dict[str, Path], strict_contract: pd.DataFrame) -> pd.DataFrame:
    """Load family raw-HR and common-RHR profiles on the strict contract.

    Parameters
    ----------
    paths : dict of str to pathlib.Path
        Authority paths containing ``family_raw_matrix`` and
        ``family_common_matrix``.
    strict_contract : pandas.DataFrame
        Ordered strict feature metadata.

    Returns
    -------
    pandas.DataFrame
        Long-form family profiles with governed identity, feature, target,
        tissue, source-lane, and data-role fields.

    Raises
    ------
    KeyError
        If a required identity or contract column is absent.
    """
    raw = pd.read_csv(paths["family_raw_matrix"], low_memory=False).set_index("canonical_compound_id")
    common = pd.read_csv(paths["family_common_matrix"], low_memory=False).set_index("canonical_compound_id")
    features = strict_contract["feature_id"].astype(str).tolist()
    records: list[pd.DataFrame] = []
    for source_id, label in FAMILY_LABELS.items():
        frame = strict_contract[["feature_id", "target", "target_canonical_id", "tissue", "tissue_canonical_id", "feature_order"]].copy()
        frame["drug"] = label
        frame["raw_hr"] = pd.to_numeric(raw.loc[source_id].reindex(features), errors="coerce").to_numpy()
        frame["common_rhr"] = pd.to_numeric(common.loc[source_id].reindex(features), errors="coerce").to_numpy()
        frame["source_lane"] = "FROZEN_KETAMINE_FAMILY_U1_HPF"
        frame["data_role"] = "KETAMINE_FAMILY"
        frame["source_compound_id"] = source_id
        records.append(frame)
    return pd.concat(records, ignore_index=True)


def load_family_calls(paths: dict[str, Path], alpha_key: str) -> pd.DataFrame:
    """Load called fingerprint rows for one governed alpha level.

    Parameters
    ----------
    paths : dict of str to pathlib.Path
        Authority paths for the two family call tables.
    alpha_key : str
        ``"001"`` selects alpha 0.001; any other governed caller value selects
        alpha 0.0001, matching the historical routing contract.

    Returns
    -------
    pandas.DataFrame
        Called rows with public drug labels, common feature identifiers, and
        numeric raw/common HR columns.
    """
    source = paths["family_calls_001" if alpha_key == "001" else "family_calls_0001"]
    frame = pd.read_parquet(source)
    frame = frame[frame["fingerprint_status"].astype(str).eq("CALLED")].copy()
    frame["drug"] = frame["canonical_compound_id"].map(FAMILY_LABELS)
    frame["feature_id_common"] = frame["feature_id"].astype(str)
    frame["raw_hr"] = pd.to_numeric(frame["raw_hr"], errors="coerce")
    frame["common_rhr"] = pd.to_numeric(frame["common_RHR"], errors="coerce")
    return frame


def family_roster() -> pd.DataFrame:
    """Return the fixed parent, identity-control, and family-member roster.

    Returns
    -------
    pandas.DataFrame
        Stable compound identifiers, display labels, and analytical roles.

    Notes
    -----
    The pooled parent and confirmed racemate are intentionally separate rows.
    """
    rows = [{
        "compound_id": "POOLED_PARENT_KETAMINE",
        "compound_label": "Ketamine, pooled parent",
        "role": "PRIMARY_PARENT_QUERY",
    }]
    rows.extend({
        "compound_id": key,
        "compound_label": label,
        "role": "IDENTITY_CONTROL" if key == "ketamine_racemic" else "ENANTIOMER_OR_METABOLITE",
    } for key, label in FAMILY_LABELS.items())
    return pd.DataFrame(rows)
