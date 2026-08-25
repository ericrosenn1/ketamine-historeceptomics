#!/usr/bin/env python3
r"""
Pooled Parent Ketamine — Final Activity v4 Correction
=====================================================

PURPOSE
-------
Patch the final v3 81-target pooled-parent-ketamine activity summary so that the
36 selected PDSP rows at the 10,000 nM ceiling are represented correctly as:

    Ki > 10,000 nM
    relation = >
    relation_class = GT_BOUND
    numerical boundary = 10,000 nM
    boundary pActivity = 5.0

The raw PDSP source-record audit established that these selected 10,000-nM rows all
carry an explicit ">" marker in the raw PDSP value field. Therefore they are NOT
exact Ki = 10,000 nM measurements.

This script:
1. Reads the v3 final target summary.
2. Patches ONLY selected PDSP pActivity=5 targets whose v3 source-record status states
   that raw PDSP has an explicit ">" relation at 10,000 nM.
3. Leaves every other target unchanged.
4. Recalculates final readiness/status fields.
5. Verifies the expected final counts:
      40 exact measured target values
      36 bounded GT target values
       5 targets with no selected activity
      81 total target rows
      76 total selected target values
6. Produces:
      - final 81-row target activity summary
      - 76-row HR-input target table
      - patch audit
      - summary/log/hash files
7. DOES NOT calculate HR.
8. DOES NOT overwrite v3 or any earlier output.

INPUT ROUTING
-------------
Supply the governed Forensic Finalization v3 directory with --v3-dir. No local
filesystem path or scientific input is inferred by the public script.

Publication contract
--------------------
Purpose: Correct the supported PDSP 10,000-nM relation boundary in the v3 summary.
Stage/lane: Recovered Final Activity v4, between forensic v3 and full-tissue HR.
Inputs: An explicit governed Forensic Finalization v3 directory.
Outputs: A new timestamped v4 directory with the 81-row summary, 76-row HR input,
patch audit, summaries, hashes, and run log.
Side effects: Creates derivative files only and never overwrites v3 or computes HR.
Invariants: Only source-supported PDSP boundary rows change; expected exact/bounded/
missing counts, target identities, numerical boundary 5.0, and operators are enforced.
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = None
DEFAULT_V3_DIR = None
DEFAULT_INPUT = None


def stamp() -> str:
    """Return a filesystem-safe local timestamp for a derivative run."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def s(v) -> str:
    """Normalize a nullable scalar to a stripped string."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v).strip()


def fnum(v) -> float:
    """Return a finite float or NaN when the value is not numeric."""
    try:
        x = float(v)
        return x if math.isfinite(x) else math.nan
    except Exception:
        return math.nan


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file read in bounded blocks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def ensure_column(df: pd.DataFrame, name: str, default):
    """Add a missing compatibility column with the supplied default."""
    if name not in df.columns:
        df[name] = default


def main() -> int:
    """Run the recovered producer with explicit inputs and fail-closed QA."""
    parser = argparse.ArgumentParser(
        description="Apply the final PDSP >10000 nM relation correction to pooled parent ketamine."
    )
    parser.add_argument("--v3-dir", type=Path, required=True)
    args = parser.parse_args()

    v3_dir = args.v3_dir.resolve()
    input_path = (
        v3_dir
        / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FORENSIC_V3.csv"
    )
    output_dir = v3_dir / f"Final_Activity_v4_{stamp()}"
    output_dir.mkdir(parents=True, exist_ok=False)

    log_path = output_dir / "RUN.log"

    def log(msg: str):
        """Write one timestamped run-log message."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    try:
        log("=== POOLED PARENT KETAMINE FINAL ACTIVITY V4 START ===")
        log(f"V3 directory: {v3_dir}")
        log(f"Input: {input_path}")
        log(f"Output: {output_dir}")

        if not input_path.is_file():
            raise FileNotFoundError(f"V3 target summary not found: {input_path}")

        input_hash = sha256(input_path)
        d = pd.read_csv(input_path, low_memory=False)

        log(f"Loaded target rows: {len(d)}")
        log(f"Input SHA256: {input_hash}")

        if len(d) != 81:
            raise RuntimeError(
                f"Expected exactly 81 target rows from v3; found {len(d)}."
            )

        required = [
            "canonical_target_id",
            "gene_symbol",
            "proposed_selected_source_database",
            "proposed_selected_pActivity",
            "pdsp_10000_forensic_status",
            "proposed_selection_status",
        ]
        missing = [c for c in required if c not in d.columns]
        if missing:
            raise RuntimeError(f"Missing required v3 columns: {missing}")

        # Ensure required patch columns exist even if the v3 CSV schema varies slightly.
        ensure_column(d, "proposed_selected_relation_original", "")
        ensure_column(d, "proposed_selected_relation_operator_clean", "")
        ensure_column(d, "proposed_selected_relation_class", "")
        ensure_column(d, "proposed_selected_is_bounded", False)
        ensure_column(d, "proposed_selected_boundary_direction_known", False)
        ensure_column(d, "proposed_selection_kind", "")
        ensure_column(d, "proposed_bound_selection_rule", "")
        ensure_column(d, "v3_relation_operator", "")
        ensure_column(d, "v3_relation_class", "")
        ensure_column(d, "v3_relation_evidence_source", "")
        ensure_column(d, "v3_relation_changed_from_v2", False)
        ensure_column(d, "HR_INPUT_READINESS_V3", "")
        ensure_column(d, "HR_INPUT_READINESS_RATIONALE", "")

        # Identify ONLY the rows proven by the v3 raw-PDSP source-record audit to have
        # an explicit > at the 10,000 nM ceiling.
        source_is_pdsp = (
            d["proposed_selected_source_database"]
            .fillna("")
            .astype(str)
            .str.contains("PDSP", case=False, na=False)
        )

        p_is_5 = pd.to_numeric(
            d["proposed_selected_pActivity"], errors="coerce"
        ).eq(5.0)

        raw_says_gt = (
            d["pdsp_10000_forensic_status"]
            .fillna("")
            .astype(str)
            .str.contains(
                r"RAW_PDSP_10000_WITH_EXPLICIT_RELATION_>",
                regex=False,
                na=False,
            )
        )

        patch_mask = source_is_pdsp & p_is_5 & raw_says_gt
        n_patch = int(patch_mask.sum())

        if n_patch != 36:
            raise RuntimeError(
                "Safety stop: expected exactly 36 selected PDSP pActivity=5 targets "
                f"with raw explicit '>' forensic status; found {n_patch}. "
                "No output authority will be accepted."
            )

        # Capture pre-patch audit.
        patch_audit = d.loc[
            patch_mask,
            [
                c for c in [
                    "canonical_target_id",
                    "gene_symbol",
                    "target_name",
                    "proposed_selected_source_assertion_id",
                    "proposed_selected_source_database",
                    "proposed_selected_activity_type",
                    "proposed_selected_pActivity",
                    "proposed_selected_activity_value_original",
                    "proposed_selected_activity_unit_original",
                    "proposed_selected_relation_original",
                    "proposed_selected_relation_operator_clean",
                    "proposed_selected_relation_class",
                    "v3_relation_operator",
                    "v3_relation_class",
                    "pdsp_10000_forensic_status",
                    "HR_INPUT_READINESS_V3",
                ]
                if c in d.columns
            ],
        ].copy()

        patch_audit = patch_audit.add_prefix("before__")

        # ---------------------------------------------------------------------
        # Apply the correction.
        # ---------------------------------------------------------------------
        d.loc[patch_mask, "proposed_selected_relation_original"] = ">"
        d.loc[patch_mask, "proposed_selected_relation_operator_clean"] = ">"
        d.loc[patch_mask, "proposed_selected_relation_class"] = "GT_BOUND"
        d.loc[patch_mask, "proposed_selected_is_bounded"] = True
        d.loc[patch_mask, "proposed_selected_boundary_direction_known"] = True
        d.loc[patch_mask, "proposed_selection_kind"] = "BOUNDED_MEASURED_BOUNDARY"
        d.loc[
            patch_mask, "proposed_bound_selection_rule"
        ] = "RAW_PDSP_EXPLICIT_GT_10000_NM_BOUNDARY"
        d.loc[
            patch_mask, "proposed_selection_status"
        ] = "SELECTED_BOUNDED_MEASURED_DIRECTION_PRESERVED"

        d.loc[patch_mask, "v3_relation_operator"] = ">"
        d.loc[patch_mask, "v3_relation_class"] = "GT_BOUND"
        d.loc[
            patch_mask, "v3_relation_evidence_source"
        ] = "RAW_PDSP_KI_VALUE_EXPLICIT_GT_10000"
        d.loc[patch_mask, "v3_relation_changed_from_v2"] = True

        d.loc[
            patch_mask, "HR_INPUT_READINESS_V3"
        ] = "READY_BOUNDED_RELATION_PRESERVED"
        d.loc[
            patch_mask, "HR_INPUT_READINESS_RATIONALE"
        ] = (
            "Raw PDSP ketamine Ki value explicitly reports >10000 nM. "
            "Numerical boundary 10000 nM / pActivity 5.0 retained with GT relation; "
            "not treated as an exact Ki."
        )

        # ---------------------------------------------------------------------
        # Add clean final v4 fields rather than relying on mixed historical names.
        # ---------------------------------------------------------------------
        d["final_activity_relation_operator_v4"] = d[
            "v3_relation_operator"
        ].fillna("").astype(str)

        d["final_activity_relation_class_v4"] = d[
            "v3_relation_class"
        ].fillna("").astype(str)

        d["final_activity_value_status_v4"] = np.where(
            d["final_activity_relation_class_v4"].eq("GT_BOUND"),
            "BOUNDED_GT",
            np.where(
                d["final_activity_relation_class_v4"].eq("LT_BOUND"),
                "BOUNDED_LT",
                np.where(
                    d["final_activity_relation_class_v4"].eq("EXACT"),
                    "EXACT",
                    np.where(
                        pd.to_numeric(
                            d["proposed_selected_pActivity"], errors="coerce"
                        ).notna(),
                        "REVIEW_RELATION",
                        "NO_SELECTED_ACTIVITY",
                    ),
                ),
            ),
        )

        d["final_selected_pActivity_v4"] = pd.to_numeric(
            d["proposed_selected_pActivity"], errors="coerce"
        )

        d["final_selected_activity_value_M_v4"] = pd.to_numeric(
            d.get("proposed_selected_activity_value_M", np.nan),
            errors="coerce",
        )

        d["final_selected_activity_boundary_nM_v4"] = np.where(
            d["final_activity_relation_class_v4"].isin(
                ["GT_BOUND", "LT_BOUND"]
            ),
            d["final_selected_activity_value_M_v4"] * 1e9,
            np.nan,
        )

        d["final_selected_activity_is_bounded_v4"] = d[
            "final_activity_relation_class_v4"
        ].isin(["GT_BOUND", "LT_BOUND"])

        d["final_selected_activity_boundary_direction_known_v4"] = d[
            "final_activity_relation_class_v4"
        ].isin(["GT_BOUND", "LT_BOUND"])

        d["final_hr_input_status_v4"] = np.where(
            d["final_selected_pActivity_v4"].isna(),
            "NO_SELECTED_ACTIVITY",
            np.where(
                d["final_activity_relation_class_v4"].eq("EXACT"),
                "READY_EXACT",
                np.where(
                    d["final_activity_relation_class_v4"].isin(
                        ["GT_BOUND", "LT_BOUND"]
                    ),
                    "READY_BOUNDED_RELATION_PRESERVED",
                    "REVIEW_RELATION",
                ),
            ),
        )

        d["final_hr_input_note_v4"] = np.where(
            d["final_activity_relation_class_v4"].eq("GT_BOUND"),
            (
                "Use pActivity boundary numerically for exploratory HR while preserving "
                "'>' relation; value is not an exact affinity."
            ),
            np.where(
                d["final_activity_relation_class_v4"].eq("LT_BOUND"),
                (
                    "Use pActivity boundary numerically for exploratory HR while preserving "
                    "'<' relation; value is not an exact affinity."
                ),
                np.where(
                    d["final_activity_relation_class_v4"].eq("EXACT"),
                    "Exact measured selected activity.",
                    "No selected activity or unresolved relation.",
                ),
            ),
        )

        # ---------------------------------------------------------------------
        # Final count verification.
        # ---------------------------------------------------------------------
        exact_n = int(
            (
                d["final_hr_input_status_v4"].eq("READY_EXACT")
                & d["final_selected_pActivity_v4"].notna()
            ).sum()
        )
        bounded_n = int(
            d["final_hr_input_status_v4"]
            .eq("READY_BOUNDED_RELATION_PRESERVED")
            .sum()
        )
        no_value_n = int(
            d["final_hr_input_status_v4"].eq("NO_SELECTED_ACTIVITY").sum()
        )
        review_n = int(
            d["final_hr_input_status_v4"].eq("REVIEW_RELATION").sum()
        )
        selected_n = int(d["final_selected_pActivity_v4"].notna().sum())

        expected = {
            "total": 81,
            "exact": 40,
            "bounded": 36,
            "no_value": 5,
            "review": 0,
            "selected": 76,
        }
        observed = {
            "total": len(d),
            "exact": exact_n,
            "bounded": bounded_n,
            "no_value": no_value_n,
            "review": review_n,
            "selected": selected_n,
        }

        if observed != expected:
            raise RuntimeError(
                "Safety stop: final v4 counts do not match expected counts.\n"
                f"Expected: {expected}\nObserved: {observed}"
            )

        # Final patch audit with after-values.
        after_cols = [
            c for c in [
                "canonical_target_id",
                "gene_symbol",
                "proposed_selected_relation_original",
                "proposed_selected_relation_operator_clean",
                "proposed_selected_relation_class",
                "v3_relation_operator",
                "v3_relation_class",
                "final_activity_relation_operator_v4",
                "final_activity_relation_class_v4",
                "final_activity_value_status_v4",
                "final_selected_pActivity_v4",
                "final_selected_activity_boundary_nM_v4",
                "final_hr_input_status_v4",
                "final_hr_input_note_v4",
            ]
            if c in d.columns
        ]
        after = d.loc[patch_mask, after_cols].copy().add_prefix("after__")
        patch_audit = patch_audit.reset_index(drop=True)
        after = after.reset_index(drop=True)
        patch_audit = pd.concat([patch_audit, after], axis=1)

        # ---------------------------------------------------------------------
        # Save final outputs.
        # ---------------------------------------------------------------------
        final81 = (
            output_dir
            / "POOLED_PARENT_KETAMINE_TARGET_ACTIVITY_SUMMARY_FINAL_V4.csv"
        )
        hr76 = (
            output_dir
            / "POOLED_PARENT_KETAMINE_HR_INPUT_TARGET_ACTIVITY_V4.csv"
        )
        audit_path = output_dir / "PDSP_GT10000_PATCH_AUDIT_V4.csv"

        d.to_csv(final81, index=False)
        patch_audit.to_csv(audit_path, index=False)

        # HR input: only the 76 selected targets, but preserve all relevant provenance.
        hr_input = d[
            d["final_hr_input_status_v4"].isin(
                ["READY_EXACT", "READY_BOUNDED_RELATION_PRESERVED"]
            )
        ].copy()

        hr_input = hr_input.sort_values(
            ["canonical_target_id"],
            kind="stable",
        ).reset_index(drop=True)

        hr_input.to_csv(hr76, index=False)

        # Simple unavailable-target list.
        unavailable = d[
            d["final_hr_input_status_v4"].eq("NO_SELECTED_ACTIVITY")
        ].copy()
        unavailable.to_csv(
            output_dir / "TARGETS_WITHOUT_SELECTED_ACTIVITY_V4.csv",
            index=False,
        )

        summary = {
            "status": "PASS",
            "input": str(input_path),
            "input_sha256": input_hash,
            "output_dir": str(output_dir),
            "pdsp_gt10000_targets_patched": n_patch,
            "final_counts": observed,
            "expected_counts": expected,
            "main_final_81_row_table": str(final81),
            "hr_input_76_row_table": str(hr76),
            "no_hr_calculated": True,
        }

        (output_dir / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        lines = [
            "=== POOLED PARENT KETAMINE FINAL ACTIVITY V4 COMPLETE ===",
            "",
            f"PDSP >10,000 nM selected targets patched: {n_patch}",
            "",
            "FINAL TARGET COUNTS",
            f"Exact measured target values: {exact_n}",
            f"Bounded GT target values: {bounded_n}",
            f"Targets without selected activity: {no_value_n}",
            f"Targets still requiring relation review: {review_n}",
            f"Total selected target values: {selected_n}",
            f"Total target rows: {len(d)}",
            "",
            "FINAL BOUNDED RULE",
            "Raw PDSP Ki >10,000 nM is represented as:",
            "  relation operator: >",
            "  relation class: GT_BOUND",
            "  numerical boundary: 10,000 nM",
            "  boundary pActivity: 5.0",
            "  value status: BOUNDED_GT",
            "It is NOT represented as exact Ki = 10,000 nM.",
            "",
            f"Final 81-row table: {final81}",
            f"HR-input 76-row table: {hr76}",
            f"Output folder: {output_dir}",
            "",
            "NO HR WAS CALCULATED.",
            "QA: PASS",
        ]

        (output_dir / "SUMMARY.txt").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        hashes = []
        for p in sorted(output_dir.iterdir()):
            if p.is_file() and p.name != "OUTPUT_SHA256SUMS.csv":
                hashes.append(
                    {
                        "filename": p.name,
                        "bytes": p.stat().st_size,
                        "sha256": sha256(p),
                    }
                )
        pd.DataFrame(hashes).to_csv(
            output_dir / "OUTPUT_SHA256SUMS.csv",
            index=False,
        )

        log("Final count verification PASS")
        log(f"Exact={exact_n}; bounded={bounded_n}; no_value={no_value_n}; selected={selected_n}")
        log("QA: PASS")
        log("NO HR CALCULATED")

        print()
        print("\n".join(lines))
        return 0

    except Exception as exc:
        tb = traceback.format_exc()
        log("=== FAILED ===")
        log(repr(exc))
        log(tb)
        (output_dir / "FAILURE.json").write_text(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": repr(exc),
                    "traceback": tb,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"\nFAILED: {exc}\nSee {log_path}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
