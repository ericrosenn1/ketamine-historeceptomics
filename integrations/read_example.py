"""Demonstrate validation before consuming a versioned file export.

Inputs: an explicit compatible bundle directory; outputs: concise record counts.
Side effects: none. Synthetic labels and unknown coordinates remain explicit.
Invariants: missing rows are never interpreted as tested non-calls.
Lane: consumer example; not a production adapter for either hosted application.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
from pathlib import Path

from cardozo_ketamine_hr.integration import validate_bundle


def main() -> None:
    """Read validated records and count only explicit fingerprint memberships."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    manifest, records = validate_bundle(args.directory)
    calls = [row for row in records if row["fingerprint_member"] is True]
    noncalls = [row for row in records if row["fingerprint_member"] is False]
    unknown = [row for row in records if row["fingerprint_member"] is None]
    print(f"synthetic={manifest['synthetic']}; coverage={manifest['scope']['coverage']}")
    print(f"Explicit calls={len(calls)}, tested non-calls={len(noncalls)}, unknown={len(unknown)}")
    print("Absent coordinates remain unknown; no implicit zero filling.")


if __name__ == "__main__":
    main()
