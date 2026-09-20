"""Regress manuscript-facing facts against retained public authorities."""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import math

import pandas as pd


MANUSCRIPT_TITLE = "Historeceptomic Profiling of Ketamine, Its Enantiomers, and Metabolites"
WORKFLOW_SHA256 = "0E819BB4C7D8B21C14472EB556499C3E41A3F47DAB5509E50B87AFD2E855C8CA"


def _pair(table: pd.DataFrame, name_a: str, name_b: str) -> pd.Series:
    """Return one unordered pair from a retained pairwise authority."""

    selected = table[
        ((table["drug_a"] == name_a) & (table["drug_b"] == name_b))
        | ((table["drug_a"] == name_b) & (table["drug_b"] == name_a))
    ]
    assert len(selected) == 1
    return selected.iloc[0]


def test_manuscript_identity_and_workflow_figure_are_fixed(governed_paths):
    root = governed_paths["project_root"]
    reader_text = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in ["README.md", "docs/REFERENCES.md", "optional/README.md"]
    )
    assert MANUSCRIPT_TITLE in reader_text
    assert "Eric Rosenn and Timothy Cardozo" in reader_text

    workflow = root / "docs" / "figures" / "ketamine_historeceptomics_workflow.png"
    assert hashlib.sha256(workflow.read_bytes()).hexdigest().upper() == WORKFLOW_SHA256


def test_reader_facing_hr_and_fingerprint_objects_are_distinct(governed_paths):
    import re

    readme = (
        (governed_paths["project_root"] / "README.md")
        .read_text(encoding="utf-8")
        .lower()
    )
    paragraphs = [
        " ".join(re.sub(r"[*`_]", "", paragraph).split())
        for paragraph in re.split(r"\n\s*\n", readme)
        if paragraph.strip() and not paragraph.lstrip().startswith("|")
    ]

    def describes(*concepts: str) -> bool:
        """Require related concepts together in one explanatory paragraph."""
        return any(
            all(re.search(concept, paragraph) for concept in concepts)
            for paragraph in paragraphs
        )

    assert describes(
        r"hr-score matrix", r"\b(?:complete|full)\b", r"\bnumerical\b",
        r"\bhr (?:scores|values)\b", r"\bsupported\b", r"target[- ×]+anatomy",
    ), "Define the complete numerical HR matrix over supported coordinates"
    assert describes(
        r"historeceptomic fingerprint.*\bselect(?:ed|ing|ion)?\b.*"
        r"\bfrom (?:the |that |an? )?hr-score matrix",
        r"upper-tail", r"one-sided", r"\bgesd\b",
    ), "Define fingerprint selection from the HR matrix by one-sided upper-tail GESD"
    assert describes(
        r"fingerprint", r"hr-score matrix",
        r"distinct from|different from|not (?:itself|the same (?:object|matrix))",
    ), "Distinguish a fingerprint from the complete HR-score matrix"
    assert describes(
        r"fingerprint-call (?:matrix|matrices)", r"\bmembership\b",
        r"\b1\s+(?:means|denotes|=)\s+called\b",
        r"\b0\s+(?:means|denotes|=)\s+tested (?:but not called|non-calls?)\b",
        r"\bmissing\s+(?:means|denotes|=)\s+unsupported or untested\b",
        r"not an hr-score matrix|distinct from (?:an?|the) hr-score matrix",
    ), "Define call membership while keeping tested non-calls and missingness distinct"

    clauses = [
        clause
        for paragraph in paragraphs
        for clause in re.split(r"(?<=[.!?;])\s+|,\s*|\s+(?:while|whereas|and)\s+", paragraph)
    ]
    assert any(
        re.search(r"\bprimary\b", clause)
        and re.search(r"(?:α|alpha)\s*=\s*0\.001(?!\d)", clause)
        for clause in clauses
    ), "Associate the primary fingerprint threshold with alpha = 0.001"
    assert any(
        re.search(r"\bsensitivity\b", clause)
        and re.search(r"(?:α|alpha)\s*=\s*0\.0001(?!\d)", clause)
        and re.search(r"more stringent|stricter", clause)
        for clause in clauses
    ), "Associate the more stringent sensitivity threshold with alpha = 0.0001"


def test_family_pair_and_sparse_pca_match_manuscript(governed_paths):
    root = governed_paths["project_root"] / "results" / "reference"
    pairs = pd.read_csv(root / "family" / "KETAMINE_FAMILY_ALL_PAIR_METRICS_FINAL.csv")
    s_vs_r = _pair(pairs, "S-ketamine", "R-ketamine")
    assert int(s_vs_r["alpha001_shared_calls"]) == 11
    assert int(s_vs_r["alpha001_union_calls"]) == 12
    assert math.isclose(s_vs_r["alpha001_call_jaccard"], 11 / 12, abs_tol=1e-12)
    assert math.isclose(s_vs_r["alpha001_call_overlap_coefficient"], 1.0, abs_tol=1e-12)

    loadings = pd.read_csv(root / "family" / "FAMILY_SPARSE_ALPHA001_PCA_LOADINGS.csv")
    scores = pd.read_csv(root / "family" / "FAMILY_SPARSE_ALPHA001_PCA_SCORES.csv")
    assert len(loadings) == 17
    assert math.isclose(scores["PC1_variance_fraction"].iat[0], 0.6817577297823315, abs_tol=1e-12)
    assert math.isclose(scores["PC2_variance_fraction"].iat[0], 0.3037918627463902, abs_tol=1e-12)


def test_external_examples_and_global_sparse_pca_match_manuscript(governed_paths):
    root = governed_paths["project_root"] / "results" / "reference"
    pairs = pd.read_csv(root / "global" / "ALL_UNORDERED_DRUG_PAIR_METRICS_FINAL.csv")
    expected = {
        "Chlorpromazine": (8, 8 / 21, 0.8),
        "Clozapine": (6, 6 / 21, 0.75),
        "Sertraline": (5, 0.25, 5 / 6),
        "Fluoxetine": (5, 0.25, 5 / 6),
        "Olanzapine": (6, 6 / 26, 6 / 13),
    }
    for drug, (shared, jaccard, overlap) in expected.items():
        row = _pair(pairs, "Ketamine, pooled parent", drug)
        assert int(row["alpha001_shared_calls"]) == shared
        assert math.isclose(row["alpha001_call_jaccard"], jaccard, abs_tol=1e-12)
        assert math.isclose(row["alpha001_call_overlap_coefficient"], overlap, abs_tol=1e-12)

    loadings = pd.read_csv(root / "global" / "GLOBAL_SPARSE_ALPHA001_PCA_LOADINGS.csv")
    scores = pd.read_csv(root / "global" / "GLOBAL_SPARSE_ALPHA001_PCA_SCORES.csv")
    assert len(loadings) == 30
    assert math.isclose(scores["PC1_variance_fraction"].iat[0], 0.5100082966626797, abs_tol=1e-12)
    assert math.isclose(scores["PC2_variance_fraction"].iat[0], 0.4446508551990167, abs_tol=1e-12)


def test_manuscript_only_analyses_remain_blocked(governed_paths):
    root = governed_paths["project_root"]
    matrix = pd.read_csv(root / "ANALYSIS_REPRODUCIBILITY_MATRIX.csv")
    expected = {
        "CNS phenotype literature mapping",
        "CNS phenotype Sankey construction",
        "Neuropsychiatric pathology literature mapping",
        "Pathology matrix construction",
        "Manuscript assembly and downstream figures",
    }
    selected = matrix[matrix["analysis"].isin(expected)]
    assert set(selected["analysis"]) == expected
    assert set(selected["status"]) == {"BLOCKED"}
    assert set(selected["production_path"]) == {"Not present in public repository"}
