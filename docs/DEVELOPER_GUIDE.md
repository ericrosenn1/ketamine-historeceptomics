# Developer guide

## Supported toolchain

Use Python 3.12 (`>=3.12,<3.13` in `pyproject.toml`) and PowerShell 7 for the
supported Windows launchers. Release-equivalent numerical execution is CPU
float64 with one BLAS/OpenMP thread. Git is required for deterministic staged-
blob manifests. The exact package set is pinned in `requirements-lock.txt`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Do not upgrade scientific dependencies as an incidental documentation or
packaging change. Dependency changes require the same numerical regression
review as code changes.

## Repository conventions

- Treat `results/reference/`, governed configuration, external-input hashes,
  accepted coordinates, and scientific thresholds as protected contracts.
- Keep generated runs under `results/runs/` or an explicitly chosen derivative
  directory. Never overwrite retained references during normal execution.
- Preserve missingness. Use zero only for a tested non-call in a binary
  fingerprint matrix.
- Preserve source identity, compound stereochemistry, target grain, tissue
  identity, concentration relation operators, and censored boundaries.
- Resolve inputs by explicit path, role, manifest, and hash. Do not use newest
  directory, broad filesystem discovery, or an apparently similar substitute.
- Keep the primary sparse-fingerprint lane distinct from exploratory continuous
  analyses in code, filenames, status fields, and prose.
- Use deterministic sorting and fixed seeds where order affects an artifact.
- Write paths in public artifacts relative to the repository or with neutral
  aliases; never commit usernames, machine-specific directories, credentials,
  or sensitive source locators.
- Make a targeted correction and preserve unaffected validated work.

The package and stage map is in [`CODE_ARCHITECTURE.md`](CODE_ARCHITECTURE.md).

## Source layout

| Path | Developer responsibility |
|---|---|
| `src/cardozo_ketamine_hr/` | Scientific implementation, orchestration, QA, and packaging |
| `src/cardozo_ketamine_hr/upstream/` | Recovered pooled-parent reconstruction scripts; preserve their scientific contracts |
| `configs/` | Governed identities, rosters, tissues, thresholds, missingness, and analysis registry |
| `launchers/` | Supported PowerShell user interface and clear failure reporting |
| `tests/` | Unit, contract, regression, and external-data tests |
| `data/fixtures/` | Invented public test data only |
| `results/reference/` | Immutable accepted regression outputs |
| `scripts/` | Public exposure, documentation, metadata, and manifest tooling |
| `docs/` | Reader, operator, architecture, and contributor documentation |

`workflow/Snakefile` is a retained wrapper, not the recommended execution
entry point. Keep its descriptors and external-input assumptions synchronized,
but direct users to `launchers/`.

## Documentation convention

Production Python modules and executable scripts require a module docstring
that states purpose, scientific stage, inputs, outputs, side effects,
invariants, and execution lane. Public functions/classes and nontrivial private
functions require NumPy-style docstrings with parameters, returns, raises, and
notes where they add meaning. Include units, schemas, missing-data behavior,
determinism, and interpretation constraints where applicable.

PowerShell scripts require comment-based help with `.SYNOPSIS`, `.DESCRIPTION`,
parameter documentation, at least one example, `.INPUTS`, `.OUTPUTS`, and
`.NOTES`. Keep `Set-StrictMode -Version Latest` and
`$ErrorActionPreference = 'Stop'` in nontrivial launchers.

Configuration and workflow files need concise top-level comments describing
purpose, execution context, scientific impact, and invariants. Test modules
need a descriptor explaining the contract being tested and whether external
data are required.

Comments should explain why a non-obvious scientific or numerical rule exists,
not restate syntax. In particular, document unit conversion, negative-log
relation reversal, species/endpoint priority, exact-protein restrictions,
`ddof = 1`, upper-tail GESD, tie order, tested non-calls, matched support,
fixed-reference projection, nonconvergence, provenance-gated resume, and
fail-closed validation near the implementation that enforces them.

## Changing a compound

Adding a compound changes a scientific roster and is not a metadata-only edit.

1. Define the canonical identity and only defensible aliases in
   `configs/compounds.yaml`; preserve stereochemistry and source context.
2. Establish that the supplied profile uses the governed feature contract and
   record its source, retrieval/version, terms, and hash outside Git when its
   redistribution basis is unclear.
3. Supply activity/profile/call information through the external input boundary;
   do not append a scientific row to a synthetic fixture.
4. Update roster and availability contracts deliberately. Recalculate expected
   unordered pair counts rather than hard-coding around a failure.
5. Add identity, support, call, pairwise, missingness, and roster tests.
6. Run Smoke, the complete test suite, external Verify, and the full scientific
   equivalence review. Escalate any changed accepted output.

Do not promote an ambiguous label to racemate, enantiomer, or stereospecific
metabolite without explicit evidence and review.

## Changing a target

1. Confirm exact canonical protein identity and gene mapping. Generic receptor,
   complex, or family records cannot be decomposed into subunits.
2. Add/update the governed feature dictionary in the external input set and
   record the exact hash. If the public decision changes, repeat the
   redistribution audit.
3. Supply compatible 77-tissue expression and document normalization provenance.
4. Preserve unrepresented target states as missing; do not zero-fill.
5. Review the effect on activity selection, 58-target/76-target accounting,
   feature dimensions, GESD candidate universes, pair support, and every
   downstream model.
6. Add mapping, grain, expression, HR, missingness, and regression tests.

A target addition normally changes accepted scientific results and therefore
requires explicit scientific approval and a versioned reference update, not a
silent patch.

## Changing a tissue

Tissue identities live in the full 77-tissue contract, with the strict-CNS
18-tissue subset governed by `configs/tissues_cns18.yaml`. A label-only change
must preserve its canonical tissue ID. Adding, removing, or reclassifying a
tissue changes expression standardization, matrix shape, feature IDs, GESD
candidate universes, and downstream results.

For a substantive tissue change, update the full and CNS contracts together,
recompute within-gene expression with sample standard deviation (`ddof = 1`),
preserve missingness, add dimension/roster tests, and obtain scientific review
before replacing any reference.

## Adding a reference drug

1. Add its governed public label and order to `configs/reference_drugs.yaml`.
2. Add a canonical identity/alias rule without collapsing stereochemistry.
3. Supply its external profile and calls under the fixed feature contract.
4. Add descriptive class memberships only where justified; class membership is
   many-to-many and not a numerical class assignment.
5. Review global profile and pair counts, nearest-reference eligibility,
   complete-subset membership, sparse models, fixed-reference axes, and Figure
   4 scope.
6. Add tests and run external Verify. Adding a reference profile cannot retain
   the current 25-drug fixed-reference model without an explicit decision about
   whether that model remains frozen or is replaced.

## Tests

Run the self-contained suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

An ordinary unit test should use invented minimal data and assert one scientific
contract. Keep expected tolerances and missingness explicit. Do not copy
restricted source rows into a fixture.

Tests requiring the excluded 20-file tree must use the `external_data` marker
and obtain the root from `CARDOZO_HR_EXTERNAL_INPUT_ROOT`:

```powershell
$env:CARDOZO_HR_EXTERNAL_INPUT_ROOT = 'D:\ketamine-inputs\data-frozen'
.\.venv\Scripts\python.exe -m pytest -m external_data -q
```

Only the exact tests that need excluded inputs may skip when the variable is
absent. A skip must not turn an available-but-invalid hash or scientific
regression into a pass.

When changing documentation or comments in Python, compare normalized
executable ASTs with `scripts/compare_executable_ast.py`. Strip docstring nodes
and location metadata only; review and justify every remaining difference.

## Run the supported lanes

```powershell
# Self-contained software check
pwsh -NoProfile -File .\launchers\Smoke.ps1

# Complete downstream scientific verification
pwsh -NoProfile -File .\launchers\Verify.ps1 `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen'

# Recovered upstream stages plus downstream verification
pwsh -NoProfile -File .\launchers\Full.ps1 `
  -InitialActivityTable 'D:\governed\POOLED_PARENT_KETAMINE_ACTIVITY_TABLE.csv' `
  -PdspWorkbook 'D:\governed\KiDatabase.xlsx' `
  -ProjectRoot 'D:\governed\Ketamine-project' `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen'
```

Never claim Verify or Full is self-contained. Review `task_state.json`, every
required QA row, and the output manifest before accepting a run.

## Documentation and exposure audits

After editing code or documentation, generate the public audit reports as
defined by their command help and then check the committed bytes:

```powershell
.\.venv\Scripts\python.exe scripts\audit_repository.py --root . --write
.\.venv\Scripts\python.exe scripts\audit_repository.py --root . --check
.\.venv\Scripts\python.exe scripts\audit_code_documentation.py --root . --write
.\.venv\Scripts\python.exe scripts\audit_code_documentation.py --root . --check
```

The documentation audit covers module/function documentation, PowerShell help,
configuration descriptors, test descriptors, unresolved markers, public links,
CFF/BibTeX structure, licensing metadata, and narrow recorded exceptions. Do
not weaken an audit rule merely to suppress a real finding.

## Repository metadata and manifests

`scripts/build_repository_metadata.py` refreshes versioned metadata derived from
the governed tree. Run it only when its affected records have been reviewed for
the public data boundary, inspect the complete diff, and use check mode to prove
that the generated bytes are current:

```powershell
.\.venv\Scripts\python.exe scripts\build_repository_metadata.py --root .
git diff -- DATA_MANIFEST.csv CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv audits/CODE_INVENTORY.csv
.\.venv\Scripts\python.exe scripts\build_repository_metadata.py --root . --check
```

The release manifest is generated from exact stage-zero Git blobs. Stage the
intended files first, generate the two nonrecursive manifests, stage their new
bytes, and verify them:

```powershell
git add --all
.\.venv\Scripts\python.exe scripts\build_release_manifests.py --root .
git add PUBLIC_RELEASE_MANIFEST.tsv SHA256SUMS.txt
.\.venv\Scripts\python.exe scripts\build_release_manifests.py --root . --check
```

Review every manifest change. A correct hash proves identity, not permission or
scientific validity.

## Citations and data-source records

For software metadata, keep `CITATION.cff`, the software entry in
`CITATION.bib`, `pyproject.toml`, and the release version/date synchronized. Do
not add an email, infer manuscript authors, or create a manuscript preferred
citation before authorship is finalized.

For a method or source update:

1. verify bibliographic metadata against a DOI resolver, publisher, primary
   paper, or official database documentation;
2. update `CITATION.bib` and `docs/REFERENCES.md` together;
3. update `docs/DATA_SOURCES.md`, `THIRD_PARTY_NOTICES.md`, and
   `PUBLIC_RELEASE_FILE_DECISIONS.tsv` when a source or its terms change;
4. record retrieval/version information without embedding machine-specific paths or
   credentials;
5. parse BibTeX, validate CFF, test DOI links, and run the documentation audit.

Current terms can change. Recheck official source pages before adding or
redistributing data.

## Scientific change validation

Any change to activity values, pActivity conversion, relation handling,
species/endpoint priority, target/tissue/compound identities, expression
standardization, HR, GESD, thresholds, missingness, support gates, pairwise
metrics, ordinations, fixed projections, or tolerances is substantive.

Before acceptance:

1. state the proposed scientific change and obtain explicit approval;
2. preserve the prior reference set and create derivative candidate outputs;
3. run focused unit tests and the complete suite;
4. run external Verify and, when upstream behavior is affected, Full;
5. compare schema, dimensions, rosters, pairs, missingness, calls, statuses,
   values, and fixed coordinates independently;
6. document why every difference is scientifically intended;
7. update references only through a reviewed versioned replacement;
8. rerun exposure, redistribution, documentation, clean-clone, and release
   validation.

Do not make a numerical edit simply to match a reference, and do not replace a
reference simply to make a changed implementation pass.

## Release procedure

1. Confirm the public file-decision table has no unresolved row and no excluded
   input is tracked.
2. Run exposure/PII/secret scans, documentation audit, locked tests, Smoke,
   external Verify, Full argument/routing tests, and scientific equivalence.
3. Confirm normalized executable AST equivalence for documentation-only edits.
4. Regenerate deterministic metadata and manifests twice and require no Git
   drift.
5. Validate from a fresh clone with a fresh environment.
6. Push the exact reviewed commit and require public CI, secret scanning, and
   CodeQL to pass.
7. Apply branch protection/rules, then create annotated tag `v0.1.1` on that
   exact commit.
8. Build the source archive from the tag, generate SHA-256 checksums, verify ZIP
   CRC and exact tagged-file coverage, and attach only cleared assets.
9. Publish a non-draft, non-prerelease GitHub release and validate it from a
   second unauthenticated clone and downloaded assets.
10. Record final commit, tag, workflow, release, security, clean-clone, and asset
    evidence without adding machine-specific paths to the repository.

No release step authorizes publication of restricted data, nonpublic logs,
manuscripts, correspondence, literature PDFs, credentials, or internal
handoffs.
