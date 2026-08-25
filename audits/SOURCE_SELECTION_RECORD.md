# Source snapshot selection record

Source resolution was performed read-only on 2026-08-24. Twenty-one selected
files were compared with their project-source copies before local workstation
paths were replaced with neutral aliases. The machine-readable
[`SOURCE_SNAPSHOT_MANIFEST.tsv`](SOURCE_SNAPSHOT_MANIFEST.tsv) retains both
hashes:

- `source_sha256` identifies the selected source file before path aliasing;
- `repo_sha256` identifies the file committed to this repository;
- `verification_status` states whether the copy is byte-identical or differs
  only because local provenance paths were aliased.

These columns are intentionally not interchangeable.

## Whole-body pooled-parent fingerprint

The specifically anticipated `KETAMINE_WHOLE_BODY_FINGERPRINT_REPLACEMENT.zip`
was not located in the searched project/download locations. The selected
validated alternative was the complete project package dated 2026-08-13, rather
than an unaccompanied later CSV:

- package SHA-256: `4390EA6400A11B7E5DB063CCFD0D8506FA482E2A2DD03CC5CBFFF6BAE4753C6A`;
- archive check: 28 of 28 members readable, with zero read failures;
- numerical input: 58 targets × 77 tissues = 4,466 finite coordinates;
- strict-CNS regression: 19 calls at α = 0.001 and 14 at α = 0.0001;
- whole-body result: 59 primary calls across 43 targets and 36 tissues, and
  38 sensitivity calls across 33 targets and 25 tissues.

The full-body Parquet and historical CSV had identical coordinate keys and a
maximum numerical difference of `7.105427357601002e-15`, below the recorded
`1e-12` serialization tolerance. Parquet remains the numerical input in this
repository. The unaccompanied later CSV had SHA-256
`C9678D4EEE5D869D82D7D32D20F52AFA950E8EB07D60B1697A17474A892A6275`
and the same 59 call keys, but it was not selected because it lacked the
package-level provenance and code record.

Several selected whole-body JSON/CSV derivatives contained local paths. Their
source and repository hashes therefore differ. For example:

| Repository file | Source SHA-256 | Repository SHA-256 |
|---|---|---|
| `results/reference/whole_body/KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p001.csv` | `F4080415A189842AB9698CEAA4A88F4804E3455AA8CE339016DF424807AA2002` | `ABB2AA0BC6E3343E0EEDA91CCA9B0699356C770542B9B7B1FF9976F86EEB9A0E` |
| `results/reference/whole_body/KETAMINE_WHOLE_BODY_FINGERPRINT_ALPHA_0p0001.csv` | `51A0E09A71869075D1C35DC1EEAA1E04171B22107B6654B90EDFF7CE22E7B649` | `F78C8D209F663C2C7AE077118E9CEF96C035DA6FD8D4F27CF4AB95031211C147` |
| `results/reference/whole_body/CNS_SMOKE_TEST.json` | `DCF09C95688C39C2B0E544BA4F886A5EFCC189A625524176BD3203944F847731` | `16941D78187F15FFACDDD6B89C641F7184F875E7C4704CE4DF53EA613BC05541` |
| `results/reference/whole_body/QC_RESULTS.json` | `BFA0155C3B89B16E124E25A23702F9129239281AAECDFB3436C30983AA34BC11` | `044B2EBE4FFCD2F85784877CCC09AC97AFCED428E1A082E7057090FD89107707` |

## Comparative closeout and Figure 4

The selected comparative numerical snapshot is
`Pooled_Parent_Ketamine_Final_Audit_And_Freeze_20260813_191547`; it supersedes
the incomplete earlier `...191351` candidate. Its compact package archive had SHA-256
`391949743D88D9C7A850D03422443D2F2264B5FFA744A63B5C92B824F701A1CC`;
96 of 96 members were readable.

The selected Figure 4 package is the final right-legend derivative dated
2026-08-21. Its archive had SHA-256
`1F28CFD31A9E859BC14B6A2E88D5853E8921CC9D07BC41205D54B95CCD6174B3`;
42 of 42 members were readable. The model is the frozen-reference EM-SVD PCA
with weighted-least-squares query projection: 25 external drugs define the
axes, 10 ketamine-family profiles are projected without refitting, and the
publication view displays the 25 references plus pooled-parent ketamine.

The final figure image is byte-identical to its selected source. Some source-
data and QC files differ at the byte level after path aliasing; both hashes are
retained in the snapshot manifest. Recorded numerical validation found zero
coordinate movement, refitting, or jitter.

The inherited reference EM-SVD fit reached the 300-iteration limit before its
update tolerance. Its frozen point estimate remains retained with a limitation;
this record does not relabel it as converged.

## Boundaries

- Whole-body and strict-CNS GESD use different candidate universes; membership
  differences are descriptive, not biological gain or loss.
- Local-path aliasing changes bytes but not the preserved numerical content.
- Hash identity establishes file identity, not redistribution permission.
- Manuscript materials were excluded from the public tree and were not selected
  as numerical inputs. Terminology review does not confer numerical authority.
