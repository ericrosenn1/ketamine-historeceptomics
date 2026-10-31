# Public project integration regression audit

Review date: **2026-10-31**. Baseline: public `main`
`0390d9623ca5ce1326bfac542926f11704e8f952`, accepted scientific release
**v0.1.1**. This enhancement adds presentation and file exchange without
replacing scientific methods or production application loaders.

## Protected scientific authorities

[INTEGRATION_REFERENCE_CHECKSUMS.tsv](INTEGRATION_REFERENCE_CHECKSUMS.tsv)
records the v0.1.1, before, and after SHA-256 values for all **60** retained
reference artifacts. All match byte for byte. The class-membership registry,
six governed configurations, existing scientific implementation, citation
records, thresholds, missingness/censoring rules, and regression tolerances
remain unchanged. No numerical analysis was refit or reference file rewritten.

## Integration acceptance

The v1 producer exports only the two approved whole-body positive-call CSVs:
**59** calls at alpha **0.001**, **38** at **0.0001**. Publication decisions and
source SHA-256 values gate both inputs. Tests compare every exported identity,
threshold and numerical HR value directly with its retained source row and
verify two exports are byte-identical from unchanged producer state.

Compatibility tests cover malformed/duplicate records and JSON keys, mandatory
fields, schema version, consumer-pinned dataset/identity requirements, invalid
memberships, explicit missingness states, provenance bounds, path traversal,
nonfinite/overflowing numbers, corrupt bytes, protected output paths, changed
source rejection, and nonzero CLI diagnostics. The synthetic fixture's four
states and exact generator reproducibility are checked independently.

## Validation evidence

| Check | Local result |
|---|---|
| Public pytest suite, Python 3.12.10 / Windows | **116 passed, 21 external-input skips, 1 inherited expected failure** |
| Integration tests (included in suite) | **22 passed** |
| Metadata/security regression tests (included in suite) | **3 passed** |
| Synthetic Smoke lane | **PASS, 8 checks** |
| Notebook in a fresh execution kernel | **PASS, 8 code cells and saved inline figure** |
| Approved public export and consumer validation | **PASS, 97 threshold-specific positive-call records** |
| Deterministic repeated export and synthetic regeneration | **PASS, identical bytes** |
| Strict MkDocs build and local links/assets | **PASS** |
| Wheel/sdist build, metadata and distribution boundary | **PASS** |
| Installed wheel validator outside checkout, fresh locked environment | **PASS; packaged schema loaded, no broken requirements** |
| Before/after reference SHA-256 | **60/60 byte-identical to v0.1.1** |
| Excluded-input absence | **20/20 remain absent** |

The publication scan reported **zero findings**. Deterministic metadata,
documentation and release-manifest checks pass after staged-tree refresh.
Notebook/tooling dependencies are separate from the scientific environment;
the accepted scientific dependency lock and scientific configuration values
were not changed.

Final local validation and the proposed branch's GitHub Actions are recorded
in the pull request. Required checks remain strict; generated audit snapshots
must be refreshed and reviewed rather than ignored after dependency changes.
The [maintenance guide](../docs/CI_METADATA_MAINTENANCE.md) records the original
Dependabot failure and the reproducible repair procedure.

The executed notebook uses invented data with the actual expression, HR, GESD
and comparison functions. Its saved outputs include tables and a figure.
The gallery validates five frozen source hashes and displays stored results;
the original Figure 4 and its nonconvergence qualification remain intact.
Both screenshots are genuine public UI captures; assets have individual
publication decisions and exact binary allowlists.

## Publication boundary and remaining limitations

Twenty near-source inputs remain excluded. No private code, raw/restricted
datasets, manuscript files, correspondence, credentials, or unpublished
evidence tables were added. MIT and the separate qualified data/output grant
remain distinct. Current source access and app loaders were inspected read-only;
neither private application repository was changed or made public.

The public self-contained validation lane does not supply the excluded inputs.
Its external-data tests remain explicitly skipped; Verify/Full have not been
rerun for this enhancement. They retain the existing input requirements and
fail-closed hash gates. An inherited ordination missing-input bug remains an
existing expected failure, rather than being hidden or changed here.

Bounded implementation repairs included a notebook display/type compatibility
adjustment for pandas 3, finite-number overflow diagnostics in the validator,
and restoring the README's explicit matrix/fingerprint definitions required by
existing alignment tests. No scientific assumption or validation threshold changed.

The producer, schema and validator are functional. Neither production app
consumes the contract yet. A separate bounded adapter task must establish
scientific identity/scope compatibility, regression acceptance and deployment.
Positive-call-only exports cannot reconstruct full matrices or support-aware
non-call denominators. Checksums establish integrity, not authenticity or
scientific validity; production consumers must pin a trusted clean producer.

Existing Dependabot PRs need rebasing and a reviewed metadata refresh; this
task neither merges dependency changes nor grants CI a write token. The new
repair path emits a patch while preserving the original failing gate.
