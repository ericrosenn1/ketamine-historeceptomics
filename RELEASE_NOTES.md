# Release notes

## v0.1.1 — first public publication-facing release

Ketamine Historeceptomics v0.1.1 is the first public, publication-facing
release. Its numerical analysis is derived from the validated private v0.1.0
workflow, and it was assembled in a new clean Git history from the approved
scientific source snapshot. The public history does not inherit
source-repository commits, tags, deleted files, release assets, or development
records.

### Scientific continuity

This release changes distribution, documentation, licensing, public input
routing, and repository infrastructure. It does not change accepted scientific
results. In particular:

- no accepted HR values were changed;
- no strict-CNS or whole-body fingerprint calls were changed;
- no target, tissue, compound, or pair roster was changed;
- no GESD threshold, missingness rule, censoring rule, or regression tolerance
  was changed;
- no accepted sparse or continuous multivariate coordinates were refit or
  moved;
- the 60 retained files under `results/reference/` and the retained
  `class_membership.csv` are byte-identical to their approved source copies.

The accepted numerical scope remains 58 × 18 strict-CNS HR coordinates with
19 primary and 14 sensitivity calls; 58 × 77 whole-body HR coordinates with
59 primary and 38 sensitivity calls; 10 ketamine-family profiles; 25 external
reference drugs; and 595 unordered pairs in the 35-profile global comparison.

### Public data boundary

Twenty near-source numerical inputs with mixed or unclear upstream
redistribution terms are not distributed. They are recorded by relative path,
size, and SHA-256 in `EXTERNAL_INPUT_MANIFEST.tsv`. Invented fixtures under
`data/fixtures/` replace them only for the self-contained Smoke lane; the
fixtures are not scientific evidence.

Smoke is self-contained. Verify requires a user-supplied mirror of the 20-file
input tree through `--external-input-root` or `-ExternalInputRoot`. Full
requires the same tree plus the explicitly supplied initial activity table,
PDSP workbook, and historical project resources. The repository does not fetch
or substitute excluded inputs.

The producer of the earliest pooled-parent activity assertion table was not
recovered. Full begins at that exact validated table and therefore does not
claim raw-public-database-to-result reconstruction.

### Public repository additions

- MIT licensing for original software and original documentation;
- separate data licensing and third-party notices;
- verified software, methods, and database citation records;
- module, function, launcher, configuration, architecture, and developer
  documentation;
- deterministic release manifests and file-level redistribution decisions;
- public CI, CodeQL, dependency review, Dependabot, issue forms, contribution
  guidance, and private vulnerability-reporting instructions;
- owner-readable permissions for generated query-freeze outputs, with no
  change to their bytes or numerical content;
- patched `pypdf` and `setuptools` dependency pins used for PDF validation and
  package construction;
- clean-clone, exposure, code-documentation, and scientific-equivalence audits.

### Interpretation limits

HR scores and historeceptomic fingerprints are construction-dependent,
observational representations. They do not by themselves establish tissue
exposure, mechanism, biological effect direction, therapeutic benefit,
clinical response, or causality. Continuous common-RHR analyses remain
exploratory. Candidate universes and observed support differ among analyses,
and nonconverged inherited EM-SVD point estimates retain their explicit
limitations.

Restricted raw sources, manuscripts, correspondence, literature PDFs, nonpublic
logs, and internal handoffs are not release assets. A manuscript citation may
be added after the manuscript title and authorship are finalized; neither is
inferred in this release.
