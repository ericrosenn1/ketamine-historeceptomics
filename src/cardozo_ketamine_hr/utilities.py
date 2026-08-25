# SPDX-License-Identifier: MIT
"""Provide shared deterministic I/O, hashing, coercion, and timing helpers.

Stage
-----
These utilities support authority loading, derivative writing, manifests, QA,
and packaging across the portable pipeline.

Inputs
------
Functions accept explicit paths, pandas objects, or scalar values; no implicit
project authority is resolved here.

Outputs
-------
Helpers return timestamps, hashes, tables, normalized scalars, timing records,
or portable relative paths, and write only when their names state that action.

Side Effects
------------
File-writing and copying helpers create parent directories and persist bytes;
``timed`` samples a monotonic clock.

Invariants
----------
SHA-256 is computed from file bytes, missing/non-finite numerical values are not
converted to zero, and manifest-facing relative paths use POSIX separators.

Lane
----
Cross-cutting portable infrastructure lane.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd


def now_iso() -> str:
    """Return the current timezone-aware UTC timestamp.

    Returns
    -------
    str
        ISO-8601 UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute an uppercase SHA-256 digest from file bytes.

    Parameters
    ----------
    path : pathlib.Path
        File to hash.
    chunk_size : int, default=1048576
        Number of bytes read per iteration.

    Returns
    -------
    str
        Uppercase hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_table(path: Path) -> pd.DataFrame:
    """Read a Parquet or CSV table based on its suffix.

    Parameters
    ----------
    path : pathlib.Path
        Table path; ``.parquet`` selects Parquet and every other suffix follows
        the established CSV fallback.

    Returns
    -------
    pandas.DataFrame
        Loaded table.
    """
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def write_table(frame: pd.DataFrame, base: Path, parquet: bool = True) -> list[Path]:
    """Write a required CSV and an optional best-effort Parquet companion.

    Parameters
    ----------
    frame : pandas.DataFrame
        Table to persist without an index.
    base : pathlib.Path
        Destination path without a format suffix.
    parquet : bool, default=True
        Attempt a Parquet companion when true.

    Returns
    -------
    list of pathlib.Path
        Successfully written paths, always beginning with the CSV.

    Side Effects
    ------------
    Creates the parent directory and writes table files.

    Notes
    -----
    Parquet is optional in this generic helper; a Parquet-engine failure leaves
    the required CSV intact and is reflected by its absence from the result.
    """
    base.parent.mkdir(parents=True, exist_ok=True)
    csv_path = base.with_suffix(".csv")
    frame.to_csv(csv_path, index=False)
    paths = [csv_path]
    if parquet:
        parquet_path = base.with_suffix(".parquet")
        try:
            frame.to_parquet(parquet_path, index=False)
            paths.append(parquet_path)
        except Exception:
            # CSV is the mandatory portable artifact for this helper; callers
            # detect Parquet success from the returned path list.
            pass
    return paths


def write_json(path: Path, payload: Any) -> None:
    """Serialize a payload as indented UTF-8 JSON.

    Parameters
    ----------
    path : pathlib.Path
        Destination JSON file.
    payload : Any
        JSON-compatible object or supported value handled by ``json_default``.

    Returns
    -------
    None

    Side Effects
    ------------
    Creates the parent directory and writes the JSON file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")


def json_default(value: Any) -> Any:
    """Convert supported scientific scalar types for JSON serialization.

    Parameters
    ----------
    value : Any
        Value not handled by the standard JSON encoder.

    Returns
    -------
    Any
        JSON-compatible path, scalar, null, or timestamp representation.

    Raises
    ------
    TypeError
        If ``value`` has no governed conversion.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def slug(value: Any) -> str:
    """Normalize an arbitrary value to a filesystem-safe identifier.

    Parameters
    ----------
    value : Any
        Value converted to text.

    Returns
    -------
    str
        Alphanumeric underscore-delimited slug, or ``"item"`` when empty.
    """
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_")
    return text or "item"


def finite(values: pd.Series) -> pd.Series:
    """Coerce a series to numeric values with infinities replaced by missing.

    Parameters
    ----------
    values : pandas.Series
        Values to normalize.

    Returns
    -------
    pandas.Series
        Numeric series in which invalid values and infinities are ``NaN``.
    """
    return pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)


def safe_float(value: Any) -> float:
    """Convert a scalar to a finite float or ``NaN``.

    Parameters
    ----------
    value : Any
        Scalar-like input.

    Returns
    -------
    float
        Finite converted value, otherwise ``math.nan``.
    """
    try:
        result = float(value)
    except Exception:
        return math.nan
    return result if math.isfinite(result) else math.nan


@contextmanager
def timed() -> Iterator[dict[str, float]]:
    """Measure elapsed wall-clock time for a context block.

    Yields
    ------
    dict of str to float
        Mutable result populated with ``runtime_seconds`` on context exit,
        including exceptional exits.
    """
    started = time.perf_counter()
    result: dict[str, float] = {}
    try:
        yield result
    finally:
        result["runtime_seconds"] = time.perf_counter() - started


def copy_small_file(source: Path, destination: Path) -> None:
    """Copy one small file through an explicit byte read/write.

    Parameters
    ----------
    source : pathlib.Path
        Existing source file.
    destination : pathlib.Path
        Destination file.

    Returns
    -------
    None

    Side Effects
    ------------
    Creates the destination parent and writes the source bytes.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def relative_posix(path: Path, root: Path) -> str:
    """Express a path relative to a root using POSIX separators.

    Parameters
    ----------
    path : pathlib.Path
        Path contained by ``root``.
    root : pathlib.Path
        Containing reference root.

    Returns
    -------
    str
        Portable relative path.

    Raises
    ------
    ValueError
        If ``path`` is not beneath ``root``.
    """
    return path.relative_to(root).as_posix()
