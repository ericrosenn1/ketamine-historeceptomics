# SPDX-License-Identifier: MIT
"""Independently validate a completed run from persisted artifacts.

Stage
-----
This acceptance pass runs after all scientific, QA, figure, table, manifest,
and handoff outputs have been written.

Inputs
------
The derivative run root and source-code root are read back from disk; no
in-memory pipeline state is accepted as evidence.

Outputs
-------
A detailed acceptance table is written under ``15_QA_AND_MANIFESTS`` and
returned to the caller.

Side Effects
------------
Reads CSV, ZIP, PDF, and source files; computes hashes; writes the independent
acceptance CSV; raises on any failed check.

Invariants
----------
Frozen dimensions, call counts, identity separation, metric bounds, manifests,
file hashes, ZIP CRC, and paper-facing PDF readability must all pass exactly.

Lane
----
Independent persisted-output validation lane.
"""

from __future__ import annotations

import math
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pypdf import PdfReader

from .utilities import sha256_file


def validate_run(run_root: Path, code_root: Path) -> pd.DataFrame:
    """Validate a completed run without reusing in-memory pipeline state.

    Parameters
    ----------
    run_root : pathlib.Path
        Completed derivative run root.
    code_root : pathlib.Path
        Source tree recorded in the run's code manifest.

    Returns
    -------
    pandas.DataFrame
        One PASS/FAIL row per independent acceptance check.

    Raises
    ------
    RuntimeError
        If one or more persisted checks fail.

    Side Effects
    ------------
    Writes ``INDEPENDENT_ACCEPTANCE_AUDIT.csv`` beneath the run QA directory.
    """
    run_root, code_root = Path(run_root), Path(code_root)
    rows: list[dict[str, Any]] = []

    def check(check_id: str, condition: bool, observed: Any, expected: Any) -> None:
        """Append one normalized acceptance result.

        Parameters
        ----------
        check_id : str
            Stable acceptance-check identifier.
        condition : bool
            Evaluated pass condition.
        observed, expected : Any
            Audit values serialized into the result row.
        """
        rows.append({"check_id": check_id, "status": "PASS" if condition else "FAIL", "observed": observed, "expected": expected})

    qa_dir = run_root / "15_QA_AND_MANIFESTS"
    query_dir = run_root / "01_QUERY_AUTHORITY"
    heatmap_dir = run_root / "02_HEATMAP_REPAIR"
    full = pd.read_csv(query_dir / "POOLED_PARENT_FULL77_HR_AUTHORITY.csv", low_memory=False)
    strict = pd.read_csv(query_dir / "POOLED_PARENT_STRICT18_HR_AUTHORITY.csv", low_memory=False)
    primary_calls = pd.read_csv(query_dir / "POOLED_PARENT_FINGERPRINT_ALPHA_0p001.csv", low_memory=False)
    sensitivity_calls = pd.read_csv(query_dir / "POOLED_PARENT_FINGERPRINT_ALPHA_0p0001.csv", low_memory=False)
    missing = pd.read_csv(query_dir / "POOLED_PARENT_MISSING_EXPRESSION_TARGETS.csv", low_memory=False)
    check("QUERY_FULL_CONTRACT", (full["canonical_target_id"].nunique(), full["tissue_id"].nunique(), len(full)) == (58, 77, 4466), f"{full['canonical_target_id'].nunique()}x{full['tissue_id'].nunique()}={len(full)}", "58x77=4466")
    check("QUERY_STRICT_CONTRACT", (strict["canonical_target_id"].nunique(), strict["tissue_id"].nunique(), len(strict)) == (58, 18, 1044), f"{strict['canonical_target_id'].nunique()}x{strict['tissue_id'].nunique()}={len(strict)}", "58x18=1044")
    check("QUERY_CALL_COUNTS", (len(primary_calls), len(sensitivity_calls)) == (19, 14), f"{len(primary_calls)}/{len(sensitivity_calls)}", "19/14")
    check("QUERY_CALL_SUBSET", set(sensitivity_calls["feature_id_common"]).issubset(set(primary_calls["feature_id_common"])), len(sensitivity_calls), "alpha0001 subset alpha001")
    check("MISSING_EXPRESSION_TARGETS", missing["canonical_target_id"].nunique() == 18, missing["canonical_target_id"].nunique(), 18)
    primary_heatmap = pd.read_csv(heatmap_dir / "POOLED_PARENT_FINGERPRINT_ALPHA001_HEATMAP_MATRIX.csv", index_col=0)
    sensitivity_heatmap = pd.read_csv(heatmap_dir / "POOLED_PARENT_FINGERPRINT_ALPHA0001_HEATMAP_MATRIX.csv", index_col=0)
    check("HEATMAP_RENDERED_CELLS", (int(primary_heatmap.notna().sum().sum()), int(sensitivity_heatmap.notna().sum().sum())) == (19, 14), f"{int(primary_heatmap.notna().sum().sum())}/{int(sensitivity_heatmap.notna().sum().sum())}", "19/14")

    pairwise = pd.read_csv(run_root / "03_EXTERNAL_PAIRWISE_CONTINUOUS" / "ALL_UNORDERED_DRUG_PAIR_METRICS.csv", low_memory=False)
    check("PAIRWISE_COUNT", len(pairwise) == 435, len(pairwise), 435)
    check("PAIRWISE_NO_SELF_OR_DUPLICATE", not (pairwise["drug_a"] == pairwise["drug_b"]).any() and not pairwise.apply(lambda row: "||".join(sorted([row.drug_a, row.drug_b])), axis=1).duplicated().any(), "unique unordered pairs", "unique unordered pairs")
    check("EXTERNAL_REUSED_PAIRS", int(pairwise["reused_or_recomputed"].eq("REUSED_UNCHANGED_AFTER_NUMERICAL_EQUALITY_QA").sum()) == 300, int(pairwise["reused_or_recomputed"].eq("REUSED_UNCHANGED_AFTER_NUMERICAL_EQUALITY_QA").sum()), 300)
    for column in ["cosine_common_rhr", "pearson_common_rhr", "spearman_common_rhr"]:
        values = pd.to_numeric(pairwise[column], errors="coerce").dropna()
        check("BOUNDS_" + column.upper(), bool(values.between(-1.0000001, 1.0000001).all()), f"min={values.min()} max={values.max()}", "[-1,1]")
    for column in [value for value in pairwise.columns if "jaccard" in value or "overlap_coefficient" in value]:
        values = pd.to_numeric(pairwise[column], errors="coerce").dropna()
        check("BOUNDS_" + column.upper(), bool(values.between(-1e-12, 1 + 1e-12).all()), f"min={values.min()} max={values.max()}", "[0,1]")
    check("IDENTITY_SEPARATION", len(set(pairwise["drug_a"]) | set(pairwise["drug_b"])) == 30 and "Ketamine, pooled parent" in set(pairwise["drug_a"]) | set(pairwise["drug_b"]) and "Ketamine, confirmed racemate" in set(pairwise["drug_a"]) | set(pairwise["drug_b"]), len(set(pairwise["drug_a"]) | set(pairwise["drug_b"])), "30 distinct numerical compounds including both ketamine identities")
    family = pd.read_csv(run_root / "05_KETAMINE_FAMILY" / "KETAMINE_FAMILY_ALL_10_PAIR_METRICS.csv", low_memory=False)
    check("FAMILY_PAIR_COUNT", len(family) == math.comb(5, 2), len(family), 10)

    model = pd.read_csv(qa_dir / "MODEL_STATUS.csv", low_memory=False)
    required_model = {"analysis_id", "representation", "method", "status", "sample_count", "feature_count", "rank", "component_count", "input_roster"}
    check("MODEL_STATUS_SCHEMA", required_model.issubset(model.columns), sorted(model.columns), sorted(required_model))
    forced = model[(pd.to_numeric(model["component_count"], errors="coerce") > pd.to_numeric(model["rank"], errors="coerce")) & model["rank"].notna()]
    check("NO_FORCED_COMPONENTS", forced.empty, len(forced), 0)
    registry = pd.read_csv(qa_dir / "ANALYSIS_REGISTRY.csv", low_memory=False)
    required_registry = {"analysis_id", "analysis_family", "query_compound", "status", "output_table", "output_figure", "QA_status", "compute_backend", "gpu_used"}
    check("ANALYSIS_REGISTRY_SCHEMA", required_registry.issubset(registry.columns), sorted(registry.columns), sorted(required_registry))
    check("ANALYSIS_REGISTRY_ROWS", len(registry) == 195, len(registry), 195)
    check("PAPER_PACKET_REGISTERED", registry["analysis_id"].eq("PAPER_FACING_PACKET").sum() == 1, int(registry["analysis_id"].eq("PAPER_FACING_PACKET").sum()), 1)
    ancillary = pd.read_csv(run_root / "13_ANCILLARY_ANALYSES" / "ANCILLARY_ANALYSIS_STATUS.csv", low_memory=False)
    check("ANCILLARY_EXPLICIT_STATUS", len(ancillary) == 17 and ancillary["status"].notna().all(), len(ancillary), 17)

    figures = pd.read_csv(qa_dir / "FIGURE_MANIFEST.csv", low_memory=False)
    tables = pd.read_csv(qa_dir / "TABLE_MANIFEST.csv", low_memory=False)
    check("FIGURE_INDEX_COUNT_AND_QA", len(figures) == 107 and figures["QA_status"].eq("PASS").all(), len(figures), "107 all PASS")
    check("TABLE_INDEX_COUNT_AND_QA", len(tables) == 609 and tables["QA_status"].eq("PASS").all(), len(tables), "609 all PASS")
    figure_missing = sum(not (run_root / path).exists() or (run_root / path).stat().st_size < 5000 for path in figures["output_file"])
    check("FIGURE_FILES_READBACK", figure_missing == 0, figure_missing, 0)
    prior_coverage = pd.read_csv(qa_dir / "PREVIOUS_VS_NEW_OUTPUT_COVERAGE.csv", low_memory=False)
    check("PRIOR_OUTPUT_COVERAGE", len(prior_coverage) == 881 and prior_coverage["status"].notna().all(), len(prior_coverage), 881)

    input_audit = pd.read_csv(qa_dir / "INPUT_PRE_POST_HASH_AUDIT.csv", low_memory=False)
    check("INPUT_HASHES_UNCHANGED", input_audit["sha256_pre"].eq(input_audit["sha256_post"]).all(), int((input_audit["sha256_pre"] != input_audit["sha256_post"]).sum()), 0)
    qa = pd.read_csv(qa_dir / "QA_SUMMARY.csv", low_memory=False)
    check("PRIMARY_QA_NO_FAILURES", not qa["status"].eq("FAIL").any(), int(qa["status"].eq("FAIL").sum()), 0)
    stages = pd.read_csv(run_root / "00_RUN_CONTROL" / "STAGE_STATUS.csv", low_memory=False)
    check("STAGE_COMPLETION", len(stages) == 17 and stages["status"].astype(str).str.startswith("PASS").all(), f"rows={len(stages)} statuses={sorted(stages['status'].unique())}", "17 PASS-prefixed stages")
    failures = pd.read_csv(run_root / "00_RUN_CONTROL" / "FAILURE_LEDGER.csv", low_memory=False)
    check("FAILURE_LEDGER_EMPTY", failures.empty, len(failures), 0)

    manifest = pd.read_csv(qa_dir / "OUTPUT_MANIFEST.csv", low_memory=False)
    missing_or_bad = 0
    # Recompute size and digest from persisted bytes rather than trusting the
    # manifest or any in-memory producer state.
    for row in manifest.itertuples(index=False):
        path = run_root / row.relative_path
        if not path.exists() or path.stat().st_size != int(row.bytes) or sha256_file(path) != row.sha256:
            missing_or_bad += 1
    check("OUTPUT_MANIFEST_HASH_READBACK", missing_or_bad == 0, missing_or_bad, 0)
    code_manifest = pd.read_csv(qa_dir / "CODE_MANIFEST.csv", low_memory=False)
    code_bad = 0
    for row in code_manifest.itertuples(index=False):
        path = code_root / row.relative_path
        if not path.exists() or path.stat().st_size != int(row.bytes) or sha256_file(path) != row.sha256:
            code_bad += 1
    check("CODE_MANIFEST_HASH_READBACK", code_bad == 0, code_bad, 0)

    zip_path = next((run_root / "16_HANDOFF").glob("*.zip"))
    with zipfile.ZipFile(zip_path, "r") as archive:
        bad_member = archive.testzip()
        member_count = len(archive.namelist())
    check("HANDOFF_ZIP_CRC", bad_member is None and member_count >= 70, f"bad={bad_member}; members={member_count}", "CRC clean and >=70 members")
    for name in ["ALL_FIGURES_COMBINED.pdf", "ALL_TABLES_COMBINED.pdf", "COMPLETE_FIGURES_AND_TABLES_PACKET.pdf"]:
        path = run_root / "14_PAPER_FACING" / name
        pages = len(PdfReader(str(path)).pages) if path.exists() else 0
        check("PDF_PACKET_" + name.replace(".pdf", ""), path.exists() and pages > 0, pages, ">0 pages")

    result = pd.DataFrame(rows)
    destination = qa_dir / "INDEPENDENT_ACCEPTANCE_AUDIT.csv"
    result.to_csv(destination, index=False)
    if result["status"].eq("FAIL").any():
        failed = ", ".join(result.loc[result["status"].eq("FAIL"), "check_id"])
        raise RuntimeError("Independent acceptance failed: " + failed)
    return result
