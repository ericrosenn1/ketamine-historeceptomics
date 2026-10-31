# Versioned file integration

Contract **1.0.0** separates exchange records from internal scientific storage.
The normative [Draft-7 JSON Schema](../src/cardozo_ketamine_hr/integration-v1.schema.json)
is packaged with the [validator](../src/cardozo_ketamine_hr/integration.py).
Both work from an installed wheel without private code or a server.

## Export approved results

After installing the package from the public checkout:

```bash
python -m cardozo_ketamine_hr.integration export --output local/app-export
python -m cardozo_ketamine_hr.integration validate local/app-export
```

The explicit adapter permits only two `KEEP`-approved v0.1.1 whole-body
pooled-parent call CSVs, verifies their publication-decision SHA-256 values,
and exports **59 + 38 records** at alpha **0.001 / 0.0001**. Both thresholds
use the same whole-body candidate universe. It preserves stored HR numbers
and source row indices; it does not run GESD or export excluded matrices.
Only permitted scientific fields are selected. There is no automatic source
scan, arbitrary table export, or loading of private inputs.

The output directory must be new or empty. A bundle contains exactly
`manifest.json` and `records.json`. Never write an export over accepted results.

## Contract fields and semantics

| Field | Meaning |
|---|---|
| `profile_id`, `source_profile_id` | Governed analysis identity and exact source ID; pooled parent remains distinct from racemate/enantiomers |
| `target_id`, `tissue_id` | Exact IDs in the declared registry; labels remain separate |
| `expression_dataset_id` | Dataset identity and processing/version context; never an automatic atlas crosswalk |
| `hr_score` | Finite source HR value, or explicit JSON null; zero is a real score |
| `fingerprint_member` | true = call, false = explicitly tested non-call, null = unknown |
| `support_status` | `supported`, `unsupported`, or `untested` |
| `gesd_alpha` | 0.001 primary or 0.0001 sensitivity; threshold remains part of coordinate identity |
| `source_artifact`, `source_row` | Source-relative artifact and one-based data record index |

A `supported` coordinate requires a finite score and boolean membership.
An `unsupported` coordinate requires null score and membership. An `untested`
coordinate can retain a finite available score but must have null membership.
These are exchange states, not a new scientific definition of source support.

The real export declares **`positive_calls_only`**: every record is a supported
true call. An omitted row has unknown status; consumers must not turn absence
into zero or a negative call. Such a bundle cannot supply complete support-aware
comparison denominators. `explicit_coordinates` supports broader approved
future exports without claiming every possible coordinate is present.

The manifest records exact schema version, producer release/commit and dirty
state, generation command/time basis, analysis scope, thresholds, dataset IDs,
identity registries, source sizes/hashes/releases, output size/hash/count,
validation method, and data-use restrictions. `release` identifies the accepted
scientific authority v0.1.1; `commit` identifies the checkout running the adapter.
A dirty checkout is explicitly marked.

Production consumers should require `producer.dirty` to be false and pin that
clean commit. A dirty export is useful during development but does not identify
all unpublished implementation bytes and is unsuitable as a production authority.

Generation time comes from the producer commit, not the wall clock. Repeated
exports from an unchanged checkout, source bytes, commit and dirty state are
byte-identical. Source row order and scientific values are never re-sorted or
refitted. Identity registries are deterministically sorted.

## Validate before consuming

```bash
python -m cardozo_ketamine_hr.integration validate local/app-export --expected-dataset HUMAN_BIOGPS_GNF1H_GCRMA_77_TISSUE_DDOF1 --expected-namespace KETAMINE_FAMILY_FEATURE_CONTRACT_1.0.0
python integrations/read_example.py integrations/fixtures/synthetic-v1
```

The [example reader](read_example.py) calls `validate_bundle()` before counting
explicit calls, non-calls and unknown states. Python consumers can additionally
pass an independently pinned `accepted_identities` dictionary. The CLI accepts
that same object via `--identity-registry <file.json>`; no implicit aliases or
case normalization are allowed.

Validation rejects missing/extra fields, incompatible exact schema versions,
unknown registry references, duplicate IDs/coordinates/JSON keys, unsupported
source mappings, invalid memberships, nonfinite scores, missingness violations,
out-of-scope alpha/dataset values, unsafe source paths, absent provenance,
size/count/hash failures, symlinks and extra bundle files. Diagnostics identify
the field or record; CLI failures return exit code **2**.

Integrity hashes detect corruption; they do not authenticate a manifest rewritten
together with its data. Production consumers must obtain bundles from a trusted
producer commit, independently pin the manifest SHA-256, and review identity,
scientific scope and publication authority. A compatibility PASS is not
scientific validation or evidence of app deployment.

## Synthetic fixture and versions

[The synthetic v1 bundle](fixtures/synthetic-v1/manifest.json) contains four
invented coordinates: a call, a real zero with a tested non-call, an untested
finite HR, and an unsupported null. Every profile/target/tissue/dataset ID is
prefixed `SYNTHETIC_`; its zero commit and fixed epoch are fixture sentinels,
not a scientific release. Memberships are invented, not fitted GESD calls.

Recreate it in a new directory:

```bash
python integrations/generate_synthetic.py --output local/new-synthetic-bundle
python -m cardozo_ketamine_hr.integration validate local/new-synthetic-bundle
```

Synthetic data and adapted output compilations use the qualified
[CC BY-SA 4.0 data grant](../DATA_LICENSE.md); original schemas, software and
documentation use MIT. Restricted upstream terms remain applicable; exports
never confer rights to excluded sources.

Version 1 accepts exactly `1.0.0`. Consumers must explicitly upgrade for future
versions; incompatible semantics require a new major contract. Dataset-specific
identity namespaces and separately reviewed thin adapters can extend exchange
without modifying internal HR/GESD algorithms. See
[application integration](../docs/APPLICATION_INTEGRATION.md) for adoption
responsibilities. Neither production application currently consumes this interface.
