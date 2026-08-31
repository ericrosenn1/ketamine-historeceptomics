# Input provenance and public data scope

## Provenance model

This release separates four kinds of material:

1. original public software and documentation;
2. invented fixtures used only by Smoke;
3. redistribution-cleared derived reference outputs and project metadata;
4. governed scientific inputs that are required by Verify or Full but are not
   redistributed.

This separation preserves scientific identity and missingness while respecting
source-specific terms. The public code never searches a local machine for a
newest-looking input, downloads a substitute, or treats inaccessible data as a
negative observation.

[`PUBLIC_RELEASE_FILE_DECISIONS.tsv`](../PUBLIC_RELEASE_FILE_DECISIONS.tsv) is
the file-level decision record. [`EXTERNAL_INPUT_MANIFEST.tsv`](../EXTERNAL_INPUT_MANIFEST.tsv)
is the exact size/hash contract for the 20 externally routed Verify inputs.
Source citations and acquisition boundaries are in
[`DATA_SOURCES.md`](DATA_SOURCES.md).

## Earliest reproducible boundary

The earliest recovered pooled-parent input is a 17,715-row × 45-column activity
assertion table with SHA-256
`1F799CB884DEA1A3663763F4B87068E0DAA7C348D490F7730665F59CA9F57F2C`.
The program that originally assembled this table from earlier pharmacology
records was not recovered. The repository therefore does not claim complete
raw-database-to-table reconstruction.

Full begins at that exact caller-supplied table and runs every recovered
downstream pooled-parent stage. Verify starts later from the exact 20-file
governed input tree. Smoke is independent of both boundaries and uses invented
fixtures only.

## Publicly retained scientific files

The release retains 61 scientific/reference files:

- 60 accepted output files beneath [`results/reference/`](../results/reference/),
  covering family, global, class-context, whole-body, and fixed Figure 4
  results;
- the descriptive many-to-many class registry at
  [`data/frozen/metadata/class_membership.csv`](../data/frozen/metadata/class_membership.csv).

Each retained file is byte-identical to its approved analysis-snapshot copy.
These files enable inspection and regression comparison. They do not contain
the complete near-source input set, do not transfer ownership of upstream
resources, and do not make Verify self-contained.

## Twenty externally routed Verify inputs

The excluded input tree contains:

| Group | Files | Analysis role |
|---|---:|---|
| `core/` | 8 | selected pooled-parent activity, standardized expression, whole-body/strict-CNS HR, missing-expression accounting, and strict-CNS calls |
| `e7/` | 6 | five additional metabolite profiles, common-scale values, calls, and identity accounting |
| `metadata/` | 1 | exact target-anatomy feature dictionary |
| `profiles/` | 5 | 30-profile comparison table and prior external/call/pairwise authorities |

These 20 files combine or derive from source-specific pharmacology,
expression, project-profile, and literature-curated material. Their public
redistribution basis was not sufficiently clear for inclusion, so they are
excluded conservatively. Verify and Full require the user to supply the exact
relative layout and validate every byte size and SHA-256 before analysis.

The public class registry is resolved from the repository if it is not repeated
in the external tree. No other absent input is filled from public files.

## Synthetic Smoke fixtures

[`data/fixtures/`](../data/fixtures/) contains three small invented CSVs. They
exercise the activity, expression, HR, missingness, sparse-call, pairwise, and
multivariate interfaces. The names, values, targets, tissues, and compounds are
fictional; no row was copied from an upstream database, publication, or project
input.

The fixtures replace the excluded files only as software-test material. They
cannot regenerate accepted ketamine outputs and must not be interpreted or
combined as scientific evidence.

## Historical source resources

The accepted workflow drew on the following source families. Most near-source
assemblies are not redistributed here.

| Resource family | Role | Public treatment |
|---|---|---|
| Pooled-parent activity assertion table | Earliest Full input | Caller supplied; exact hash boundary |
| NIMH PDSP and other pharmacology resources | Activity, species, endpoint, and censored-relation evidence | Source files excluded; lawful access required |
| ChEMBL, PubChem BioAssay, BindingDB, and IUPHAR/BPS | Pharmacology source context | Source-specific terms and citations apply |
| BioGPS/GeneAtlas GNF1H | 77-tissue human expression and compatible target recovery | Near-source expression files excluded |
| Ketamine-family and external-drug profiles | Strict-CNS comparison inputs | Governed 20-file tree excluded; accepted outputs retained |
| Whole-body fingerprint analysis | 77-tissue pooled-parent fingerprints | Accepted derived outputs retained |
| Fixed-reference PCA/Figure 4 | External-drug axes and ketamine projections | Accepted coordinates and visual derivatives retained |
| Frozen common-RHR mapping | Cross-profile continuous comparison scale | Projected inputs externally routed; model is not refit |

See [`DATA_SOURCES.md`](DATA_SOURCES.md) and
[`REFERENCES.md`](REFERENCES.md) for verified source and method citations.

## Scientific lineage

The accepted downstream lineage is:

```text
governed identities + activity observations
  -> species/endpoint/censoring selection
  -> selected target pActivity
  + standardized 77-tissue expression
  -> whole-body target × tissue HR
  -> strict-CNS subset
  -> upper-tail GESD fingerprints
  -> family/global sparse comparisons (primary)
  -> frozen common-RHR comparisons (exploratory)
  -> multivariate/class/fixed-reference derivatives
  -> accepted reference outputs
```

The current manuscript then uses selected computational outputs in a separate
interpretation layer:

```text
accepted fingerprint coordinates
  -> CNS target-tissue-phenotype literature search and semantic adjudication
  -> compound-pair-phenotype Sankey

accepted pooled-parent alpha=0.001 CNS fingerprint coordinates
  -> six-disease literature search and definitive source-level adjudication
  -> pathology matrix

computational core + literature mappings
  -> manuscript figures, tables, and narrative interpretation
```

The first block is represented by the governed public computational contracts.
The interpretation block is present in the current manuscript,
**_Historeceptomic Profiling of Ketamine, Its Enantiomers, and Metabolites_**
by Eric Rosenn and Timothy Cardozo, but is not added to the public execution
claim merely by being named here.

Full reconstructs the recovered pooled-parent stages before the downstream
comparison. Verify begins from the external 20-file governed snapshot. Both
routes compare their represented outputs against the same retained reference
contracts.

## Downstream interpretation audit

The manuscript-alignment audit located current derivative summaries for the
400-cell CNS phenotype review and 114-cell pathology review, along with
historical private Sankey/pathology figure packages. Those materials were not
promoted to this repository because the inspected set did not provide one
current, portable, redistribution-approved contract containing all qualifying
source records, governed search dictionaries, final adjudication authorities,
builders, manifests, licensing decisions, and deterministic validation
evidence.

In particular, the historical pathology figure packages predate the definitive
20-relationship source-level audit and therefore cannot be substituted for the
current manuscript result. The public tree documents the current scientific
scope while leaving both literature workflows `BLOCKED` in
[`ANALYSIS_REPRODUCIBILITY_MATRIX.csv`](../ANALYSIS_REPRODUCIBILITY_MATRIX.csv).
No manuscript file, literature PDF, or private absolute source path is required
by or committed to the public execution lanes.

## Compound identity safeguards

Identity resolution is conservative and configuration-driven:

- unspecified ketamine is not promoted to confirmed racemate;
- racemate evidence is not assigned to S-ketamine or R-ketamine;
- stereospecific and generic metabolite labels remain distinct;
- ambiguous aliases require an explicit source-context rule;
- unresolved identities remain unresolved.

Pooled-parent ketamine is an analysis-level aggregation under recorded
selection rules. It is not a claim that every contributing record was
chemically confirmed racemate.

## Target-grain safeguards

Source pharmacology may describe an exact protein, receptor complex, receptor
family, or ambiguous target. That grain is preserved. Only exact proteins with
a compatible feature-dictionary entry can be mapped to gene-specific tissue
expression. Generic receptor or complex records are not decomposed into
subunits; unsupported mappings remain excluded from numerical HR coordinates
and visible in source accounting where available.

## Activity and relation safeguards

Measured human pharmacology is selected when available, followed by measured
mammalian nonhuman evidence under the recorded policy. Endpoint priority and
exact-versus-censored status apply within the selected species stratum.
Relation operators such as `>` and `<` remain attached to their numerical
boundaries. Modeled, assigned, unresolved-species, and incompatible records are
not silently substituted.

## Missingness policy

Missing values are preserved. A target without compatible expression, a
compound without support for a coordinate, and an untested coordinate do not
become zero. Zero is used only for a tested non-call in a binary fingerprint
matrix. Pairwise support counts and multivariate inputs preserve that
distinction.

## Hashes, terms, and scientific meaning

A SHA-256 identity check establishes that a file has the expected bytes. It
does not establish permission to redistribute the file, biological validity,
or causal interpretation. Those questions are handled separately through:

- [`PUBLIC_RELEASE_FILE_DECISIONS.tsv`](../PUBLIC_RELEASE_FILE_DECISIONS.tsv)
  for the file-level public decision;
- [`DATA_LICENSE.md`](../DATA_LICENSE.md) and
  [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for terms;
- [`METHODS.md`](METHODS.md) and regression validation for computational
  meaning;
- explicit limitations in reader-facing results and documentation.

Some retained artifacts preserve neutral source-era labels required for
traceability. Such labels are identifiers, not biological categories, and do
not expose or require local absolute paths.
