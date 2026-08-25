"""Normalize strict-CNS tissue labels without changing tissue identity.

Purpose
-------
Provide deterministic comparison keys and publication-facing display labels
for the governed strict-CNS tissue panel.

Scientific stage
----------------
Tissue-label normalization supports feature alignment before fingerprint and
pairwise analysis.

Primary inputs
--------------
Source and optional display labels for tissues.

Primary outputs
---------------
Canonical alphanumeric keys and governed display labels.

Side effects
------------
None; all functions are deterministic and write no files.

Invariants
----------
Normalization changes typography only, never merges a label into an unrelated
tissue, and falls back to the supplied text when no governed display mapping
exists.

Execution lane
--------------
Used by fingerprint construction in Smoke, Verify, and Full-derived checks.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import re
from typing import Any


DISPLAY_BY_KEY = {
    "amygdala": "Amygdala",
    "caudatenucleus": "Caudate nucleus",
    "cerebellum": "Cerebellum",
    "cerebellumpeduncles": "Cerebellum peduncles",
    "cingulatecortex": "Cingulate Cortex",
    "globuspallidus": "Globus Pallidus",
    "hypothalamus": "Hypothalamus",
    "medullaoblongata": "Medulla Oblongata",
    "occipitallobe": "Occipital Lobe",
    "olfactorybulb": "Olfactory Bulb",
    "parietallobe": "Parietal Lobe",
    "pons": "Pons",
    "prefrontalcortex": "Prefrontal Cortex",
    "spinalcord": "Spinal cord",
    "subthalamicnucleus": "Subthalamic nucleus",
    "temporallobe": "Temporal Lobe",
    "thalamus": "Thalamus",
    "wholebrain": "Whole brain",
}


def canonical_tissue_key(value: Any) -> str:
    """Convert a tissue label to its canonical alphanumeric comparison key.

    Parameters
    ----------
    value
        Tissue label or value coercible to text.

    Returns
    -------
    str
        Lowercase key with non-alphanumeric characters removed.
    """

    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def display_tissue(value: Any) -> str:
    """Return the governed display label for a tissue key or source label.

    Parameters
    ----------
    value
        Canonical key or source tissue label.

    Returns
    -------
    str
        Governed display label when known, otherwise stripped source text.
    """

    key = canonical_tissue_key(value)
    return DISPLAY_BY_KEY.get(key, str(value).strip())


def normalize_tissue_pair(source_label: Any, display_label: Any = None) -> tuple[str, str]:
    """Resolve a canonical key and display label from paired tissue labels.

    Parameters
    ----------
    source_label
        Original tissue label used as the identity fallback.
    display_label
        Optional preferred display label.

    Returns
    -------
    tuple[str, str]
        Canonical key and governed or fallback display label.

    Notes
    -----
    An unrecognized display label falls back to the source label's key so a
    cosmetic label cannot silently change tissue identity.
    """

    key = canonical_tissue_key(display_label if display_label not in (None, "") else source_label)
    if key not in DISPLAY_BY_KEY:
        key = canonical_tissue_key(source_label)
    return key, DISPLAY_BY_KEY.get(key, str(display_label or source_label).strip())
