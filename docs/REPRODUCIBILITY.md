# Reproducibility guide

## Supported environment

Release-equivalent execution uses Windows 11, Python 3.12, PowerShell 7, Git,
CPU float64 arithmetic, and one BLAS/OpenMP thread. Exact Python versions are
pinned in [`requirements-lock.txt`](../requirements-lock.txt). Seeded methods
use the governed seed `20260813`. GPU acceleration is not used for release
equivalence.

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-lock.txt
```

The launchers use `.venv` when present. Set `CARDOZO_HR_PYTHON` to an explicit
Python executable when another managed environment is required. The recorded
validation environment is in [`ENVIRONMENT.md`](ENVIRONMENT.md).

## Three execution lanes

| Lane | Self-contained | Input boundary | Result |
|---|---|---|---|
| Smoke | Yes | Invented CSV fixtures plus retained public-output hashes | Fast software and contract validation; no scientific regeneration |
| Verify | No | User-supplied 20-file frozen-input mirror | Complete downstream 35-profile regeneration and reference comparison |
| Full | No | Verify inputs plus initial activity table, PDSP workbook, and project resources | Seven recovered pooled-parent stages followed by Verify |

No lane downloads scientific inputs. A missing file is an execution failure,
not evidence of scientific absence.

## Manuscript analysis boundary

The current manuscript, **_Historeceptomic Profiling of Ketamine, Its
Enantiomers, and Metabolites_** by Eric Rosenn and Timothy Cardozo, includes
analyses on both sides of the public execution boundary:

| Manuscript analysis | Public execution status |
|---|---|
| HR-score matrices and derived pooled-parent fingerprints | Verify/Full with governed external inputs |
| Ketamine-family and external-drug fingerprint comparisons | Verify/Full with governed external inputs |
| Fingerprint PCA | Verify/Full with governed external inputs |
| CNS phenotype literature mapping and Sankey | Documented manuscript analysis; `BLOCKED` in this public release |
| Neuropsychiatric pathology mapping and matrix | Documented manuscript analysis; `BLOCKED` in this public release |
| Manuscript figure/table assembly outside retained Figure 4 | Not part of Smoke, Verify, or Full |

`BLOCKED` here means that the public repository lacks a complete,
redistribution-approved input/source/adjudication/build/validation contract. It
does not mean the manuscript analysis was not performed, and it is not a
scientific negative. See
[`ANALYSIS_REPRODUCIBILITY_MATRIX.csv`](../ANALYSIS_REPRODUCIBILITY_MATRIX.csv).

## Smoke

Run the public self-contained lane:

```powershell
pwsh -NoProfile -File .\launchers\Smoke.ps1
```

Smoke validates all retained public reference/class-registry hashes and uses
the invented files in [`data/fixtures/`](../data/fixtures/) to exercise:

- the HR multiplication contract;
- finite-value and missingness behavior;
- sparse call-set and pairwise conventions;
- deterministic multivariate behavior;
- figure rendering and output packaging.

Synthetic identifiers such as `SMOKE_T1` and `SYNTHETIC_A` are not biological
entities. Smoke cannot reproduce or validate ketamine call membership because
the near-source scientific inputs are intentionally absent.

## Prepare the external Verify tree

Verify and Full require the exact 20-file set listed in
[`EXTERNAL_INPUT_MANIFEST.tsv`](../EXTERNAL_INPUT_MANIFEST.tsv). Supply a root
that mirrors the excluded `data/frozen` layout:

```text
D:\ketamine-inputs\data-frozen\
|-- core\
|-- e7\
|-- metadata\
`-- profiles\
```

The manifest paths are relative to this root; do not add another `data/frozen`
layer beneath it. Before computation, the program checks that all 20 files
exist and match their recorded byte sizes and SHA-256 hashes. The cleared
`metadata/class_membership.csv` can be resolved from the repository when it is
not repeated in the external root.

The public repository does not distribute or broker access to the excluded
files. Follow the source-specific acquisition and use conditions in
[`DATA_SOURCES.md`](DATA_SOURCES.md) and the file-level decisions in
[`PUBLIC_RELEASE_FILE_DECISIONS.tsv`](../PUBLIC_RELEASE_FILE_DECISIONS.tsv).

## Verify

Run the complete downstream comparison with a manifest-valid external root:

```powershell
pwsh -NoProfile -File .\launchers\Verify.ps1 `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen'
```

Equivalent generic launcher:

```powershell
pwsh -NoProfile -File .\launchers\run_reproduction.ps1 `
  -Mode Verify `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen' `
  -OutputDir '.\results\runs\publication_verify'
```

Verify checks the supplied pooled-parent activity, expression, HR-score
matrices, call tables, profiles, feature contract, prior calls, and metabolite
inputs. It then rebuilds the family and global profile matrices, fingerprints,
fingerprint-call matrices, all 595 unordered pairs, primary sparse multivariate
analyses, exploratory continuous analyses, class-context summaries, whole-body
fingerprints, and the fixed-coordinate Figure 4 derivative.

Regenerated artifacts are compared with the 60 accepted files under
[`results/reference/`](../results/reference/). The required downstream ledger
contains 87 checks in the accepted workflow.

## Full

Full additionally requires lawful access to the earliest validated
pooled-parent activity assertion table, the governed PDSP workbook, and the
historical project resources used by the recovered processing stages:

```powershell
pwsh -NoProfile -File .\launchers\Full.ps1 `
  -InitialActivityTable 'D:\governed\POOLED_PARENT_KETAMINE_ACTIVITY_TABLE.csv' `
  -PdspWorkbook 'D:\governed\KiDatabase.xlsx' `
  -ProjectRoot 'D:\governed\Ketamine-project' `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen'
```

An explicit expression-authority directory can be supplied through the generic
launcher when authorized:

```powershell
pwsh -NoProfile -File .\launchers\run_reproduction.ps1 `
  -Mode Full `
  -InitialActivityTable 'D:\governed\POOLED_PARENT_KETAMINE_ACTIVITY_TABLE.csv' `
  -PdspWorkbook 'D:\governed\KiDatabase.xlsx' `
  -ProjectRoot 'D:\governed\Ketamine-project' `
  -ExpressionAuthority 'D:\governed\expression-authority' `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen'
```

Full runs the recovered species cleanup, source-evidence finalization, final
activity selection, initial full-tissue HR construction, expression recovery,
expanded 58-target HR construction, and strict-CNS fingerprint stages. Their
outputs must pass eight upstream equivalence checks before entering downstream
Verify, for a combined accepted ledger of 95 checks.

Successful stages can be reused only when their implementation, supplied
external inputs, parent inputs, selected source records, and output hashes all
match recorded provenance. Missing or mismatched provenance prevents reuse.
See [`FULL_MODE.md`](FULL_MODE.md) for the complete boundary and limitations.

## Outputs

When `-OutputDir` is omitted, each run creates a timestamped directory beneath
ignored `results/runs/`. A normal completed run contains:

- `task_state.json`, including terminal status, environment, and failure detail;
- `QA_SUMMARY.csv`, the required validation ledger;
- mode-specific regenerated tables and figures;
- `MANIFEST.tsv`, with derivative file sizes and SHA-256 hashes.

Verify writes HR-score matrices, GESD calls, fingerprint-call matrices, aligned
profile matrices, pairwise tables, multivariate scores and loadings,
model-status tables, whole-body fingerprints, and Figure 4 derivatives. Full
also writes
`FULL_UPSTREAM_VALIDATION.csv`, the combined root ledger, and the downstream
Verify tree under `verify_after_upstream_equivalence/`.

Input files are read in place. Scientific outputs are written only under the
selected derivative directory; retained reference outputs are never updated by
a run.

## Fail-closed validation

The process exits nonzero if a required hash, schema, key, dimension, roster,
call set, missingness pattern, text/status value, numerical table, fixed
coordinate, or figure check fails. The launcher reports the output location
and points to `task_state.json` and the QA tables; it does not print success
after an earlier error.

Downstream regression tables use the established absolute tolerance of
`1e-10`; stricter recovered-upstream comparisons use `1e-12` where recorded.
Call membership, roster membership, dimensions, categorical fields, and hashes
are exact. Passing means computational reproduction against accepted
contracts, not independent proof of biological validity.

## Tests and public CI

Run the self-contained test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests marked `external_data` require `CARDOZO_HR_EXTERNAL_INPUT_ROOT` to point
to the same manifest-valid 20-file tree. When the variable is absent, only
those exact external-input tests are skipped; synthetic, unit, contract, and
public-reference tests still run.

The public `public-validation` workflow installs the exact lock, runs the
self-contained tests and Smoke, checks repository exposure and code
documentation, verifies deterministic manifests, and scans the complete public
history for secrets. Verify and Full are deliberately not run in public CI
because CI does not receive excluded scientific inputs.

## Repository metadata checks

After the public Git index contains the intended release bytes, regenerate and
then verify the nonrecursive public manifests:

```powershell
.\.venv\Scripts\python.exe scripts\build_release_manifests.py --root .
.\.venv\Scripts\python.exe scripts\build_release_manifests.py --root . --check
```

Run the public-tree and code-documentation audits in check mode:

```powershell
.\.venv\Scripts\python.exe scripts\audit_repository.py --root . --check
.\.venv\Scripts\python.exe scripts\audit_code_documentation.py --root . --check
```

[`PUBLIC_RELEASE_MANIFEST.tsv`](../PUBLIC_RELEASE_MANIFEST.tsv) and
[`SHA256SUMS.txt`](../SHA256SUMS.txt) intentionally exclude themselves to avoid
recursive hashes. Each generated scientific run has its own separate derivative
manifest.

## Reproducibility and interpretation limits

- Smoke validates software behavior with invented data; it is not a scientific
  replication.
- Verify and Full are not self-contained and require exact user-supplied files.
- The original producer of the 17,715-row pooled-parent activity assertion
  table was not recovered; Full starts at that validated boundary.
- The frozen common-RHR mapping is not refit after raw-HR equivalence is
  established.
- Missingness is preserved, and absent access is never converted to zero or a
  negative observation.
- Strict-CNS and whole-body fingerprint candidate universes differ, so call-set
  differences are descriptive.
- Some inherited EM-SVD fits reached their iteration limit; their frozen point
  estimates retain that limitation.
- Historeceptomic representations are observational and do not establish
  mechanism, tissue exposure, clinical response, or causality.
- The manuscript's 400-cell CNS phenotype mapping and Sankey, 114-cell
  pathology mapping and matrix, and manuscript production are documented but
  not executable in this release.

See [`PROVENANCE.md`](PROVENANCE.md) for input lineage and public data scope.
