# Application integration

The project has four independently maintained components: this public
computational repository, a private scientific development repository, the
[Ketamine Phenotype Explorer](https://ketamine-phenotype-explorer.streamlit.app/),
and the [Expression-State Historeceptomics Explorer](https://huggingface.co/spaces/EricRosenn1/ketamine-state-historeceptomics).
The two application source repositories remain private. The
[assessment](../audits/PROJECT_INTEGRATION_ASSESSMENT.md) records the actual
loaders and the limits of shared numerical authority.

Repository visibility controls access to source code. Compatible data contracts
enable integration: an application does not need to become public to consume
approved public outputs, and publishing application source would not by itself
make scientific data redistributable.

## Available now

This repository provides a file-based **v1.0.0 export and validation interface**.
It is a connection point for downstream development, without an API service,
database, application backend or dependency on private code.

From an installed checkout:

```bash
python -m cardozo_ketamine_hr.integration export --output local/app-export
python -m cardozo_ketamine_hr.integration validate local/app-export
python -m cardozo_ketamine_hr.integration validate integrations/fixtures/synthetic-v1
```

The real-data export is limited to the **59 primary** and **38 sensitivity**
pooled-parent ketamine **whole-body positive calls** in the approved public
reference tables. They are separate threshold-specific records in the same
whole-body candidate universe.
It preserves their source HR values, membership and identifiers rather than
recalculating GESD. It does not include the excluded whole HR matrix, expression
matrix, pharmacology, CNS input calls, or private literature authorities.

See [the integration contract](../integrations/README.md) for the exact record
and manifest schemas, deterministic generation rules, diagnostics and example
consumer. Generated files belong in a new output directory, not over accepted
reference artifacts. Consumers should validate the bundle before displaying or
joining any scientific values.

## Scientific semantics

The exchange schema is separate from internal CSV/Parquet storage. It records
compound/profile, target, anatomy and expression-dataset identity; analysis
scope and GESD alpha; source artifacts and versions; validation metadata; and
data-use terms. Explicit identity registries preserve source IDs. An
unrecognized mapping requires review rather than guessing from a display name.

For a contract capable of carrying complete coordinates, fingerprint membership
has three states: **true** for a supported call, **false** for a tested
non-call, and **null** for an untested/unsupported coordinate, with its explicit
support status. An unavailable score is not zero. A missing row is never
automatically a negative call. The real export is a **positive-call-only**
selection, so it cannot establish tested non-calls, complete support, full
matrix coverage, or support-aware denominators by itself.

The synthetic bundle demonstrates the broader contract without substituting
for scientific inputs. Synthetic identities and values are visibly labeled
and must not be mixed with project measurements. A validator passing proves
structural compatibility and byte integrity; it does not prove scientific
validity, shared authority, clinical meaning or downstream adoption.

## Producer and consumer responsibilities

| Producer: computational repository | Consumer: independently developed application |
|---|---|
| Export only publication-approved artifacts; preserve accepted references | Validate schema version, source metadata, hashes and supported identities before use |
| Record exact sources, release/commit, thresholds, scope and redistribution notices | Pin the accepted bundle and retain source/release metadata in its own provenance |
| Declare completeness and missingness; never infer missing scientific values | Preserve true/false/null and support distinctions; never zero-fill absent rows |
| Version incompatible interface changes and provide synthetic fixtures | Add explicit, reviewed source-ID mappings; preserve source identity separately from UI labels |
| Keep producer code independent of applications | Keep evidence, additional atlases, processing and visualization under application governance |

Consumers must compare like scientific scopes. Matching a target/tissue label
does not make a new atlas's HR scale equivalent, establish an anatomical
crosswalk, or permit transplanting a human GNF1H call into a different species
or biological condition. Pooled-parent ketamine is not silently a confirmed
racemate; stereoisomers and generic metabolite identities remain distinct.

## Connecting the Phenotype Explorer

The current application reads a separately maintained, pinned coordinate CSV
and phenotype-evidence authority. It does not read this export. Its four-view
CNS membership table has different coverage and evidence obligations from this
first whole-body public export.

A future bounded adoption task should:

1. Select an approved export scope without presenting whole-body calls as CNS
   calls or as a replacement for the active phenotype authority.
2. Implement a thin adapter from validated exchange records to the existing
   coordinate contract, using explicit compound, target and anatomy mappings.
3. Retain the independently governed evidence/null ledger and join only at
   reviewed identities and thresholds. Export membership alone supplies no
   phenotype claim or negative evidence.
4. Pin bundle hashes and add tests for identity, expected membership, source
   preservation, evidence joins and missingness before changing production
   configuration.

The current public export does not provide all data needed to replace that
app's existing CNS authority. Any expansion of approved export scope needs its
own publication decision and scientific regression evidence.

## Connecting the Expression-State Explorer

The current state application loads a static packaged state plus independently
governed atlas, condition and literature overlays. Its local build consumes a
governed baseline and phenotype evidence; the public site does not recalculate
an entire scientific pipeline or accept expression uploads.

A future bounded adoption task should validate/pin a selected public bundle,
adapt its native identifiers into the existing profile/cell/fingerprint
representation, and keep the source dataset, candidate universe and alpha
attached. The first export can supply an explicit whole-body call overlay or
comparison input. It cannot reconstruct complete cells/HR matrices or the
original CNS testing universe. Those require separately authorized, compatible
inputs and current regression checks.

Additional atlases and condition-derived fingerprints must continue through
their existing source-specific processing and eligibility checks. Verify the
original human baseline, valid non-call support, graph filters, comparison
denominators and exports before enabling an adapter in production. In
particular, an evidence-linked graph subset must not replace a full call set.

## Future datasets and public application releases

New consumers can read the schema and synthetic example without importing any
private module. New datasets must declare their own source-native identities,
dataset/version, transformation provenance, support policy, scientific scope
and redistribution basis. Add a thin adapter and compatibility tests rather
than a circular dependency or a shared monolithic backend.

If either application later becomes public, release its independently reviewed
code, documentation and permitted fixtures in its own repository. Preserve
private inputs and source-specific restrictions. Its adapter can keep consuming
the same versioned files; no backend move or computational-repository redesign
is required. The publication decision, application adapter, scientific
regression acceptance and deployment remain separate reviewable tasks.

**Current operational status:** the computational producer/validator is
implemented here. Neither production application has adopted this contract;
no tested production data exchange with either app is claimed.
