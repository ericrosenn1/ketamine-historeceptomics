# Full mode: external reconstruction boundary

## Status

Full is a supported but non-self-contained lane for users who lawfully hold the
excluded project inputs. It reconstructs every recovered pooled-parent stage,
validates those outputs, and then runs the externally supplied Verify lane. It
does not download, copy into Git, or silently substitute scientific sources.

The original producer of the earliest pooled-parent activity assertion table
was not recovered. Full begins at that explicit validated table and must not be
described as raw-public-database-to-result reconstruction.

## Required inputs

Full requires all four of these inputs:

| Argument | Requirement |
|---|---|
| `-InitialActivityTable` | Exact governed 17,715-row × 45-column pooled-parent activity assertion table |
| `-PdspWorkbook` | Governed PDSP workbook used by the recovered source-record stages |
| `-ProjectRoot` | Historical project resource tree used for explicitly resolved stage inputs |
| `-ExternalInputRoot` | Exact 20-file directory listed in [`EXTERNAL_INPUT_MANIFEST.tsv`](../EXTERNAL_INPUT_MANIFEST.tsv) |

The external-input root mirrors the excluded `data/frozen` layout and begins
with `core/`, `e7/`, `metadata/`, and `profiles/`. Every one of its 20 files is
checked by relative path, byte size, and SHA-256 before downstream computation.

An authorized expression directory may be provided through
`-ExpressionAuthority`; otherwise the recovered stage resolves the expected
expression resource within `-ProjectRoot` by its governed contract. It does not
select a directory merely because it is newest.

## Command

```powershell
pwsh -NoProfile -File .\launchers\Full.ps1 `
  -InitialActivityTable 'D:\governed\POOLED_PARENT_KETAMINE_ACTIVITY_TABLE.csv' `
  -PdspWorkbook 'D:\governed\KiDatabase.xlsx' `
  -ProjectRoot 'D:\governed\Ketamine-project' `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen'
```

Use the generic launcher when an explicit expression authority or output
directory is needed:

```powershell
pwsh -NoProfile -File .\launchers\run_reproduction.ps1 `
  -Mode Full `
  -InitialActivityTable 'D:\governed\POOLED_PARENT_KETAMINE_ACTIVITY_TABLE.csv' `
  -PdspWorkbook 'D:\governed\KiDatabase.xlsx' `
  -ProjectRoot 'D:\governed\Ketamine-project' `
  -ExpressionAuthority 'D:\governed\expression-authority' `
  -ExternalInputRoot 'D:\ketamine-inputs\data-frozen' `
  -OutputDir 'D:\derivatives\ketamine-full'
```

The launcher validates argument existence and fails before claiming success if
any required path is missing.

## Recovered stages

Full executes seven recovered stages in derivative subdirectories:

1. species and censored-value activity cleanup;
2. targeted PDSP/source-record finalization;
3. final selected-activity correction;
4. initial full-tissue HR construction;
5. missing-expression recovery under the frozen 77-tissue, `ddof = 1`
   contract;
6. expanded 58-target × 77-tissue HR construction;
7. strict-CNS 58-target × 18-tissue fingerprint construction.

The stages preserve measured human priority, mammalian fallback, endpoint
priority, relation operators and censored boundaries, exact-protein target
grain, compound identity, expression normalization, missingness, HR values,
and GESD thresholds.

## Equivalence gate and downstream handoff

The regenerated pooled-parent activity, full77 HR, strict18 HR, and two call
tables must match the accepted contracts before downstream work starts. Exact
hash checks are used where the contract records exact bytes; structured tables
also require matching schema, keys, missingness, and numerical values. The
accepted upstream ledger contains eight checks.

After the upstream gate passes, regenerated full77 and strict18 outputs are
passed explicitly to Verify. The regenerated strict18 pooled raw-HR values
enter the comparison only after exact-key, missingness, and numerical
equivalence checks. The accepted common-RHR projection remains frozen because
it defines the versioned cross-profile scale; Full does not refit it. The
downstream ledger contains 87 checks, and the combined Full ledger contains 95.

## Provenance-gated resume

Each completed stage writes `PORTABLE_STAGE_PROVENANCE.json` and a terminal
summary. Reuse is allowed only when all of the following match:

- implementation hash;
- supplied initial-activity and PDSP hashes;
- parent-stage input hashes;
- declared external file hashes;
- selected source record;
- required output hashes and successful terminal status.

A missing or mismatched record fails closed and causes the affected stage to be
rerun or the workflow to stop. Directory timestamps and lexical ordering are
not scientific routing authorities.

## Outputs and side effects

Full reads source inputs in place and writes derivatives only under the chosen
output directory. It does not modify the public repository, the external-input
tree, the activity table, workbook, or project root. Important outputs include:

- `external_rebuild/`, containing recovered stage derivatives and provenance;
- `FULL_UPSTREAM_VALIDATION.csv`, the eight-check upstream ledger;
- `verify_after_upstream_equivalence/`, the complete downstream Verify output;
- root `QA_SUMMARY.csv`, containing all 95 checks;
- root `task_state.json` and `MANIFEST.tsv`.

## Limitations and permissions

- Possession of a file does not establish permission to use or redistribute it.
  Users are responsible for source-specific terms described in
  [`DATA_SOURCES.md`](DATA_SOURCES.md).
- The public repository cannot provide the excluded inputs or credentials.
- The unrecovered initial-table producer remains an upstream provenance gap.
- Full demonstrates computational agreement with the accepted workflow from
  its explicit input boundary. It does not independently establish biological
  validity or causality.
- Any change to species selection, endpoint handling, censored-bound
  interpretation, identity rules, expression standardization, target grain,
  thresholds, missingness, or fixed projections requires substantive
  scientific review.
