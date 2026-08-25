# Public scientific-equivalence audit

Overall status: `PASS`

The public release changes licensing, documentation, repository infrastructure,
and the location from which governed inputs are supplied. It does not change the
accepted numerical authorities or scientific interpretation rules. The complete
machine-readable record is
[`PUBLIC_SCIENTIFIC_EQUIVALENCE.tsv`](PUBLIC_SCIENTIFIC_EQUIVALENCE.tsv).

## Preserved authorities

- The approved source tree remained read-only. Final aggregate rechecks matched
  the preflight values for all 21 governed source inputs, all 60 accepted
  reference outputs, and all six scientific configuration files.
- Every public file under `results/reference/**` is byte-identical to its
  approved source copy: 60 of 60. The retained
  `data/frozen/metadata/class_membership.csv` is also byte-identical.
- The other 20 governed inputs are not public. Their relative paths, exact byte
  sizes, and SHA-256 values are recorded in
  [`EXTERNAL_INPUT_MANIFEST.tsv`](../EXTERNAL_INPUT_MANIFEST.tsv). When the
  approved authority tree was supplied, all 20 records matched before numerical
  execution.
- The six YAML configuration files gained explanatory comments only. Their
  parsed structures and values remain exactly equal to the approved source.

## Executable-code review

A Python 3.12 normalized-AST comparison removed module, class, and function
docstrings and ignored comments and source locations. Twenty-seven production
files were exactly executable-AST-equivalent. Seventeen files had intentional,
reviewed executable differences: three public metadata/audit tools, the package
version, the four public orchestration and authority-routing modules, and eight
recovered upstream producers whose workstation defaults were replaced by
explicit external-input guards. The query-freeze output permission was hardened
from world-readable to owner-readable without changing file content. One public
documentation-audit tool is new, and one source-era local-provenance sanitizer
was removed.

The orchestration change also adds an invented-fixture Smoke assertion for HR
multiplication and missingness. No activity selection, expression
standardization, HR formula, GESD threshold, call set, pairwise metric,
multivariate algorithm, seed, tolerance, target/tissue/compound identity, or
accepted reference coordinate was altered.

The patched `pypdf` and `setuptools` pins affect PDF inspection and package
construction, not the numerical stack. Validation under those exact versions
reproduced all scientific machine-readable Verify outputs byte-for-byte;
rendered PNG and TIFF files were also byte-identical.

## Numerical validation

| Lane | Result | Meaning |
|---|---:|---|
| Public tests | 39 passed, 21 skipped | Only tests requiring the excluded 20-file authority skip, with an explicit marker. |
| External-input tests | 60 passed | The complete unchanged suite passes when exact governed inputs are supplied. |
| Smoke | 8/8 PASS | Self-contained synthetic execution, including HR values `-7`, `7`, `10`, and missing; no zero-fill. |
| Verify | 87/87 PASS | Complete derivative regeneration and comparison over 35 compounds and 595 unordered pairs. |
| Full routing | PASS | Missing required external resources fail clearly before computation. Full is not self-contained. |

Verify reproduced the 58 x 18 strict-CNS and 58 x 77 whole-body HR contracts,
the accepted strict-CNS 19/14 and whole-body 59/38 primary/sensitivity call
counts, all governed identity and missingness contracts, and the accepted
reference comparisons. Its task state reports
`scientific_assumptions_changed=false`.

## Interpretation boundary

Computational equivalence is not a claim of causal or clinical validity. HR
scores and fingerprints remain construction-dependent observational
representations. They do not by themselves establish tissue exposure,
mechanism, effect direction, therapeutic benefit, clinical response, or
causality. Continuous common-RHR analyses remain exploratory. The inherited
EM-SVD nonconvergence limitation remains disclosed; no public release step
refitted or moved its frozen point estimate.
