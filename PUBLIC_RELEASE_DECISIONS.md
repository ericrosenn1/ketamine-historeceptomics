# Public release file decisions

## Decision rule

Every tracked file proposed for public release was reviewed for scientific
role, provenance, upstream terms, privacy, and whether public distribution is
needed for the supported execution lane. The machine-readable controlling
record is
[`PUBLIC_RELEASE_FILE_DECISIONS.tsv`](PUBLIC_RELEASE_FILE_DECISIONS.tsv). It
records the source and public path, role, upstream source and version, original
redistribution status, final decision, applicable terms, citation requirement,
rationale, replacement or acquisition method, and SHA-256 where applicable.

The allowed decisions are `KEEP`, `REMOVE`,
`REPLACE_WITH_SYNTHETIC_FIXTURE`, `REPLACE_WITH_PUBLIC_DERIVATIVE`, and
`EXTERNAL_DOWNLOAD_REQUIRED`. Every file-level row has a terminal public
decision.

## Summary

The final record contains 231 rows across source-tree files and public
additions:

| Public decision | Rows | Meaning |
|---|---:|---|
| `KEEP` | 104 | Cleared source bytes retained without a public-content change |
| `REMOVE` | 6 | Superseded source-era license, validation, manifest, and sanitization files omitted |
| `REPLACE_WITH_PUBLIC_DERIVATIVE` | 98 | Public documentation, metadata, configuration descriptors, code documentation, or input routing replaces the source-era form |
| `REPLACE_WITH_SYNTHETIC_FIXTURE` | 23 | Twenty scientific inputs are excluded, with three invented public fixture records added |

No row uses `EXTERNAL_DOWNLOAD_REQUIRED` as its terminal treatment: excluded
scientific inputs are routed to a user-supplied hash-validated directory, and
the repository does not promise that each upstream source offers a direct
public download.

The scientific data/reference inventory contained 81 rows:

| Decision group | Files | Public treatment |
|---|---:|---|
| Accepted reference outputs | 60 | `KEEP`; retained byte-identically under `results/reference/` |
| Class-membership registry | 1 | `KEEP`; retained byte-identically at `data/frozen/metadata/class_membership.csv` |
| Near-source numerical inputs | 20 | `REPLACE_WITH_SYNTHETIC_FIXTURE`; excluded from Git and externally routed for Verify/Full |

The three small CSVs under [`data/fixtures/`](data/fixtures/) are invented test
data. They collectively exercise the public Smoke schemas and missingness
contracts; they are not one-to-one scientific replacements for the 20 excluded
files and cannot be used to reproduce the accepted ketamine results.

## Why 20 inputs were excluded

The excluded input tables combine or derive from pharmacology, expression,
profile, identity, and literature-curated resources whose redistribution terms
are source-specific or not sufficiently clear for public republication of the
assembled files. The relevant source families include ChEMBL, PubChem
BioAssay, BindingDB, IUPHAR/BPS Guide to Pharmacology, NIMH PDSP,
BioGPS/GeneAtlas, and primary-literature curation. Project authorization to
prepare this repository was not treated as permission to redistribute
third-party material.

Exclusion is conservative and does not mean that an upstream source is absent,
invalid, or negative. It means only that this repository does not grant itself
the right to republish the assembled near-source file.

For computational continuity:

- [`EXTERNAL_INPUT_MANIFEST.tsv`](EXTERNAL_INPUT_MANIFEST.tsv) records the 20
  expected relative paths, byte sizes, SHA-256 hashes, and analysis roles;
- [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) describes source terms,
  citations, and acquisition boundaries;
- [`docs/FULL_MODE.md`](docs/FULL_MODE.md) explains caller-supplied input routing;
- Verify and Full fail before scientific computation if a file is missing or
  differs from its manifest record.

The release does not bundle authentication material, source database exports,
or automatic downloaders. Users must obtain lawful access and comply with each
source's current terms.

## Why reference outputs were retained

The 60 files in [`results/reference/`](results/reference/) are accepted
analysis outputs used for transparent inspection and regression comparison.
They were reviewed individually, retained without byte changes, attributed to
their source resources and methods, and separated from the excluded
near-source input tables. The class-membership registry is an original
project-curated descriptive mapping and was retained under its recorded public
basis.

Retaining a derivative does not transfer ownership of an upstream database or
replace its citation and terms. The applicable qualifications are recorded in
[`DATA_LICENSE.md`](DATA_LICENSE.md) and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Software, documentation, and fixtures

Original software and original repository documentation are released under the
[MIT License](LICENSE). Third-party data are not relicensed under MIT. Synthetic
fixture terms are stated separately in [`DATA_LICENSE.md`](DATA_LICENSE.md),
and the fixture README makes their invented status explicit.

Public-facing input-routing changes are limited to enforcing the new boundary:
Smoke consumes only synthetic fixtures, while Verify and Full consume a
manifest-valid external root. The numerical implementation, governed
configuration, thresholds, missingness policy, accepted outputs, and
regression tolerances remain unchanged.

## Clean-history and asset boundary

The public repository was initialized with a new Git history. It does not
inherit source history, source tags, deleted development files, or source-era
release assets. Public release archives are constructed from the public tag and
may contain only files admitted by the file-decision record. Manuscripts,
correspondence, literature PDFs, credentials, raw licensed databases,
nonpublic logs, and internal handoffs are excluded.

[`PUBLIC_RELEASE_MANIFEST.tsv`](PUBLIC_RELEASE_MANIFEST.tsv) and
[`SHA256SUMS.txt`](SHA256SUMS.txt) provide the final nonrecursive byte inventory
of the public tag. File identity, permission to redistribute, and scientific
validity are distinct questions; the release records all three separately.
