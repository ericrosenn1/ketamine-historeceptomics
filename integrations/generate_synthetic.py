"""Generate an invented v1 consumer fixture with all missingness states.

Inputs: four literal invented coordinates in this source; no scientific data.
Outputs: manifest.json and records.json under a caller-selected new directory.
Side effects: writes only that directory; no production application is touched.
Invariant: SYNTHETIC names and fixed provenance cannot imply measured results.
Stage/lane: public synthetic integration fixture generation only.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
from pathlib import Path

from cardozo_ketamine_hr.integration import MISSINGNESS, REPOSITORY, _write_bundle, canonical_json, digest


def generate(output: Path) -> None:
    """Write a deterministic, explicitly synthetic four-coordinate bundle."""

    states = [("A", "X", 12.0, True, "supported"), ("A", "Y", 0.0, False, "supported"), ("B", "X", 2.0, None, "untested"), ("B", "Y", None, None, "unsupported")]
    records = [{"profile_id": "SYNTHETIC_PROFILE", "source_profile_id": "SYNTHETIC_PROFILE", "target_id": "SYNTHETIC_TARGET_" + target, "tissue_id": "SYNTHETIC_TISSUE_" + tissue, "expression_dataset_id": "SYNTHETIC_EXPRESSION_V1", "hr_score": hr, "fingerprint_member": member, "support_status": status, "gesd_alpha": 0.001, "source_artifact": "integrations/generate_synthetic.py", "source_row": index} for index, (target, tissue, hr, member, status) in enumerate(states, 1)]
    source = Path(__file__).read_bytes()
    manifest = {
        "schema_version": "1.0.0", "synthetic": True,
        "producer": {"repository": REPOSITORY, "release": "SYNTHETIC_DEMONSTRATION", "commit": "0" * 40, "dirty": False},
        "generation": {"generated_at": "2000-01-01T00:00:00Z", "time_basis": "synthetic_fixed_epoch", "command": "python integrations/generate_synthetic.py --output <new-directory>"},
        "scope": {"analysis_scope": "SYNTHETIC_DEMONSTRATION_NOT_SCIENTIFIC_EVIDENCE", "coverage": "explicit_coordinates", "gesd_alphas": [0.001], "expression_dataset_ids": ["SYNTHETIC_EXPRESSION_V1"], "missingness_policy": MISSINGNESS},
        "identities": {"namespace": "SYNTHETIC_INTEGRATION_V1", "mapping_policy": "exact_source_ids_only", "profiles": [{"id": "SYNTHETIC_PROFILE", "source_id": "SYNTHETIC_PROFILE", "identity_grain": "INVENTED_TEST_PROFILE"}], "targets": [{"id": "SYNTHETIC_TARGET_" + key, "source_label": "Invented target " + key} for key in "AB"], "tissues": [{"id": "SYNTHETIC_TISSUE_" + key, "source_label": "Invented tissue " + key} for key in "XY"]},
        "source_artifacts": [{"path": "integrations/generate_synthetic.py", "sha256": digest(source), "bytes": len(source), "release": "SYNTHETIC_DEMONSTRATION", "record_count": 4}],
        "data_use": {"license": "CC-BY-SA-4.0", "notice": REPOSITORY + "/blob/main/DATA_LICENSE.md", "restrictions": ["Wholly invented test values; never use as scientific evidence.", "Preserve synthetic labels, attribution and ShareAlike notices."]},
        "validation": {"status": "PASS", "method": "schema_identity_missingness_integrity_v1", "scientific_scope": "Synthetic compatibility fixture only; memberships are invented, not fitted GESD results."},
    }
    _write_bundle(output, manifest, records)


def main() -> None:
    """Generate the fixture at an explicit new output path."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate(args.output)
    print(f"Synthetic fixture PASS: four invented coordinates in {args.output}")


if __name__ == "__main__":
    main()
