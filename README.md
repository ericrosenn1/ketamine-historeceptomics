# Ketamine Historeceptomics

[![CI](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/ci.yml/badge.svg)](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-blue.svg)](https://ericrosenn1.github.io/ketamine-historeceptomics/)
[![Docs Build](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/docs.yml/badge.svg)](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/docs.yml)
[![Package Build](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/package.yml/badge.svg)](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/package.yml)
[![Coverage](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/coverage.yml/badge.svg)](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/coverage.yml)
[![CodeQL](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/codeql.yml/badge.svg)](https://github.com/ericrosenn1/ketamine-historeceptomics/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ericrosenn1/ketamine-historeceptomics/badge)](https://securityscorecards.dev/viewer/?uri=github.com/ericrosenn1/ketamine-historeceptomics)

[![Release](https://img.shields.io/github/v/release/ericrosenn1/ketamine-historeceptomics?display_name=tag)](https://github.com/ericrosenn1/ketamine-historeceptomics/releases/latest)
[![Release Date](https://img.shields.io/github/release-date/ericrosenn1/ketamine-historeceptomics)](https://github.com/ericrosenn1/ketamine-historeceptomics/releases)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/github/license/ericrosenn1/ketamine-historeceptomics)](LICENSE)
[![CITATION.cff](https://img.shields.io/badge/citation-CITATION.cff-blue.svg)](CITATION.cff)

[![Last Commit](https://img.shields.io/github/last-commit/ericrosenn1/ketamine-historeceptomics)](https://github.com/ericrosenn1/ketamine-historeceptomics/commits/main)
[![Open Issues](https://img.shields.io/github/issues/ericrosenn1/ketamine-historeceptomics)](https://github.com/ericrosenn1/ketamine-historeceptomics/issues)
[![Repository Size](https://img.shields.io/github/repo-size/ericrosenn1/ketamine-historeceptomics)](https://github.com/ericrosenn1/ketamine-historeceptomics)
[![Code Size](https://img.shields.io/github/languages/code-size/ericrosenn1/ketamine-historeceptomics)](https://github.com/ericrosenn1/ketamine-historeceptomics)
[![Top Language](https://img.shields.io/github/languages/top/ericrosenn1/ketamine-historeceptomics)](https://github.com/ericrosenn1/ketamine-historeceptomics)

Ketamine Historeceptomics is a computational pharmacology project that combines compound-target activity with human tissue expression to quantify target-anatomy relationships for ketamine and comparator drugs. The analysis covers ketamine, its enantiomers and metabolites, together with 25 psychoactive reference drugs.

The repository accompanies the working manuscript **_Historeceptomic Profiling of Ketamine, Its Enantiomers, and Metabolites_** by Eric Rosenn and Timothy Cardozo. It contains the analysis software, reproducibility tests, selected reference results, documentation, and publicly distributable data and reference results for inspecting and reproducing the analysis.

## What the method measures

For each supported compound-target-tissue combination, the workflow calculates an **HR score**:

**HR score = target-level pharmacological activity × standardized tissue expression**

The complete collection of numerical HR values at supported target-anatomy coordinates for a compound forms an **HR-score matrix**; unsupported coordinates remain missing. A **historeceptomic fingerprint** is then defined by selecting target-anatomy coordinates from that HR-score matrix that are upper-tail outliers by one-sided generalized extreme Studentized deviate (GESD) testing.

The primary fingerprint threshold is **α = 0.001**. A more stringent **α = 0.0001** threshold is used as a sensitivity analysis.

```text
pharmacological activity + standardized expression
  -> HR-score matrix
  -> GESD outlier selection
  -> historeceptomic fingerprint
```

A fingerprint therefore represents the selected target-anatomy features of an HR profile. It is distinct from the complete numerical HR-score matrix.

A **fingerprint-call matrix** encodes fingerprint membership across compounds and target-anatomy coordinates: `1` means called, `0` means tested but not called, and missing means unsupported or untested. It is not an HR-score matrix.

## Analysis overview

The project evaluates:

- Ketamine strict-CNS and whole-body fingerprints;
- ketamine-family profiles, including confirmed racemate, S-ketamine, R-ketamine, hydroxyketamine and hydroxynorketamine forms, and norketamine;
- pairwise comparisons among 10 ketamine-family profiles;
- comparison with 25 psychoactive reference drugs;
- fingerprint overlap, Jaccard similarity, overlap coefficient, subtraction of nonshared calls, and signed cosine similarity;
- PCA of fingerprint-call matrices at the primary and sensitivity thresholds;
- exploratory continuous comparisons using matched common-RHR coordinates, including PCA, PCoA, MDS, clustering, cosine similarity, and correlation.

The fingerprint analyses are the principal comparisons. Continuous common-RHR analyses are provided as exploratory numerical comparisons of the underlying HR profiles.

## Analysis workflow

![Ketamine historeceptomics analysis workflow](docs/figures/ketamine_historeceptomics_workflow.png)

## Compounds represented

The ketamine-family analysis contains Ketamine, confirmed racemate, S-ketamine (esketamine), R-ketamine (arketamine), an unspecified-isomer hydroxyketamine aggregate, (2R,6R)- and (2S,6S)-hydroxynorketamine, generic hydroxynorketamine/HNK, generic hydroxyketamine, and norketamine.

**Ketamine** refers to the pooled-parent ketamine analysis profile used throughout this repository; the confirmed racemate profile is retained separately.

The reference panel contains bupropion, fluoxetine, duloxetine, venlafaxine, scopolamine, dextromethorphan, morphine, propofol, dexmedetomidine, lysergide (LSD), psilocin, clozapine, chlorpromazine, sertraline, mirtazapine, aripiprazole, haloperidol, olanzapine, risperidone, quetiapine, ziprasidone, PCP, valproate, lamotrigine, and psilocybin.

## Key results represented in the repository

| Analysis | Accepted scope |
|---|---:|
| Strict-CNS Ketamine HR-score matrix | 58 targets × 18 tissues = 1,044 coordinates |
| Strict-CNS primary fingerprint | 19 calls at α = 0.001 |
| Strict-CNS sensitivity fingerprint | 14 calls at α = 0.0001 |
| Whole-body Ketamine HR-score matrix | 58 targets × 77 tissues = 4,466 coordinates |
| Whole-body primary fingerprint | 59 calls at α = 0.001 |
| Whole-body sensitivity fingerprint | 38 calls at α = 0.0001 |
| Ketamine-family comparison | 10 profiles; 45 unordered pairs |
| External reference panel | 25 profiles |
| Combined comparison | 35 profiles; 595 unordered pairs |
| S-ketamine vs R-ketamine, α = 0.001 | 11 shared calls; 12-call union; Jaccard 0.92; overlap coefficient 1.00 |
| Family fingerprint PCA, α = 0.001 | 17 variable features; PC1 68.2%; PC2 30.4% |
| Global fingerprint PCA, α = 0.001 | 30 variable features; PC1 51.0%; PC2 44.5% |

For Ketamine against selected external drugs at α = 0.001, pairwise results include chlorpromazine with 8 shared calls, clozapine with 6, sertraline with 5, fluoxetine with 5, and olanzapine with 6.

Representative outputs are available under [`results/reference/`](results/reference/).

## Manuscript-linked analyses

The working manuscript also includes literature-based interpretation of fingerprint relationships in:

- CNS phenotype mapping; and
- neuropsychiatric pathology mapping.

Those interpretation analyses are documented in the repository but are not part of the executable public reproduction workflow. See [`optional/README.md`](optional/README.md) and [`ANALYSIS_REPRODUCIBILITY_MATRIX.csv`](ANALYSIS_REPRODUCIBILITY_MATRIX.csv).

## Data availability and reproducibility

The public repository contains the analysis software, test data, selected reference outputs, and documentation needed to inspect the implementation and validate the public workflow.

Some source datasets used in the full analysis cannot be redistributed with the repository. Users who want to reproduce analyses that depend on those sources must obtain the corresponding inputs separately. The expected files and validation information are documented in [`EXTERNAL_INPUT_MANIFEST.tsv`](EXTERNAL_INPUT_MANIFEST.tsv) and [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

For a detailed description of the public release boundary, validation modes, retained reference files, and exact input checks, see:

- [Reproducibility guide](docs/REPRODUCIBILITY.md)
- [Input provenance and data availability](docs/PROVENANCE.md)
- [Data sources and acquisition](docs/DATA_SOURCES.md)
- [Technical release README preserved from the previous public version](https://github.com/ericrosenn1/ketamine-historeceptomics/blob/archive/readme-technical-20260920/README.md)

## Quick start

The validated release environment is Python 3.12 on Windows with PowerShell 7.

```powershell
git clone https://github.com/ericrosenn1/ketamine-historeceptomics.git
Set-Location ketamine-historeceptomics
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-lock.txt
pwsh -NoProfile -File .\launchers\Smoke.ps1
```

The quick-start command runs the repository's self-contained software validation workflow using test fixtures. It does not require the nonredistributed scientific inputs.

Instructions for reproducing analyses that require external inputs are in [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

## Documentation

- [Computational methods](docs/METHODS.md)
- [Reproducibility guide](docs/REPRODUCIBILITY.md)
- [Input provenance and data availability](docs/PROVENANCE.md)
- [Data sources and acquisition](docs/DATA_SOURCES.md)
- [Scientific and software references](docs/REFERENCES.md)
- [Code architecture](docs/CODE_ARCHITECTURE.md)
- [Developer guide](docs/DEVELOPER_GUIDE.md)
- [Validated environment](docs/ENVIRONMENT.md)

Full documentation is also available at the [project documentation site](https://ericrosenn1.github.io/ketamine-historeceptomics/).

## Repository layout

| Path | Purpose |
|---|---|
| `src/cardozo_ketamine_hr/` | Analysis implementation |
| `configs/` | Compound identities, tissues, thresholds, and analysis parameters |
| `results/reference/` | Selected accepted reference outputs |
| `tests/` | Unit, contract, and reproducibility tests |
| `data/fixtures/` | Self-contained test inputs |
| `launchers/` | PowerShell entry points |
| `docs/` | Methods, provenance, data-source, and developer documentation |
| `scripts/` | Repository validation and metadata utilities |

## Citation

To cite the software, use **Eric Rosenn, _Ketamine Historeceptomics_, version 0.1.1**, with the machine-readable record in [`CITATION.cff`](CITATION.cff) or [`CITATION.bib`](CITATION.bib).

The related manuscript currently has the working title **_Historeceptomic Profiling of Ketamine, Its Enantiomers, and Metabolites_** and the author list **Eric Rosenn and Timothy Cardozo**. A journal, DOI, publication date, or publication status is not asserted here.

## Interpretation notes

- HR scores depend on the pharmacological activity and tissue-expression inputs used by the workflow; they are not direct measures of tissue exposure, mechanism, therapeutic benefit, clinical response, or causality.
- The configured α values are statistical outlier-selection thresholds, not biological-significance thresholds.
- Strict-CNS and whole-body fingerprints are generated from different candidate sets.
- Support varies by compound, and missing values are kept distinct from tested non-calls.
- Reference-drug similarities depend on the compounds, target support, and comparison metric included in a given analysis.
- Some fingerprint and continuous PCA fits reached their iteration limit before convergence; retained estimates carry the recorded limitation, as reported in the corresponding outputs and documentation.

## Support, licensing, and security

Original software and repository documentation are released under the [MIT License](LICENSE). Data and derived-output terms are documented separately in [`DATA_LICENSE.md`](DATA_LICENSE.md) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Use [GitHub Issues](https://github.com/ericrosenn1/ketamine-historeceptomics/issues) for reproducibility problems, bugs, and support. Follow [`SECURITY.md`](SECURITY.md) for security concerns.

Copyright © 2026 Eric Rosenn.
