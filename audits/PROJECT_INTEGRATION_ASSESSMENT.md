# Project integration assessment

Assessment date: **2026-10-31**. Scope: read-only inspection of the four current
repository default branches, public application interfaces, and existing
publication decisions before adding the public export interface. Private
repositories were neither modified nor made public.

## Scientific and publication baseline

The public computational baseline is **v0.1.1**, default-branch commit
`0390d9623ca5ce1326bfac542926f11704e8f952`. Its publication authority retains
**60 scientific reference outputs**, plus the class-membership registry, and
excludes **20 near-source inputs**. See [file decisions](../PUBLIC_RELEASE_FILE_DECISIONS.tsv),
[input size/hash requirements](../EXTERNAL_INPUT_MANIFEST.tsv),
[source snapshot hashes](SOURCE_SNAPSHOT_MANIFEST.tsv), and
[repository checksums](../SHA256SUMS.txt). The new interface reads approved
outputs; it does not recover or republish the excluded input tree.
The dedicated [reference preservation record](INTEGRATION_REFERENCE_CHECKSUMS.tsv)
compares the retained outputs with the v0.1.1 baseline.

MIT covers original software/documentation. Project contributions to the
approved analytical outputs are covered by the separate CC BY-SA 4.0 grant in
[DATA_LICENSE.md](../DATA_LICENSE.md), subject to preserved third-party terms.
The private development repositories do not provide a general public reuse
grant. Private evidence tables, code, manuscripts and upstream sources are not
included in this enhancement.

## Observed components and data flows

| Component | Verified loading/production boundary | Relationship to public outputs |
|---|---|---|
| Public computational repository | Accepted reference tables and figures; synthetic Smoke; Verify/Full require documented governed inputs | Versioned methods and approved selected numerical results |
| Private computational development repository | Frozen pharmacology/expression/profile authorities and recovered downstream scientific implementation | Scientific development lineage; its broader input inventory is not a public data grant |
| Ketamine Phenotype Explorer | `config.yaml` selects a local, pinned W1-W5 authority; `src/data_loader.py` verifies and loads `fingerprint_coordinates.csv` and `phenotype_evidence.csv` | Independently maintained membership/evidence projection; no loader fetching this public repository was found |
| Expression-State Historeceptomics Explorer | `scripts/build_local_data.py` reads a governed HR preview and the phenotype authority; `scripts/build_fingerprints.py` generates dataset-specific calls; `web/app.js` loads packaged `local/state.json` and source-qualified overlays | Independently packaged baseline and additional atlas/condition analyses; no public-computational export consumer was found |

The state application's phenotype import is an **existing source-verified
connection between the private applications' build inputs**. It does not
establish a deployed connection to this public repository.

## Shared concepts, with limits on equivalence

- All components distinguish HR values from sparse GESD membership and retain
  the primary **alpha 0.001** and sensitivity **alpha 0.0001** thresholds.
- The phenotype authority contains membership rows for four compound views;
  its pooled-parent ketamine subset contains the familiar **19/14 CNS calls**.
  It does not provide the full tested HR universe: absence from this table
  cannot be interpreted as a tested non-call.
- The state source verifies its original human **58-target, 77-tissue,
  4,466-coordinate** baseline and exact **19/14 CNS call identities** against
  its own governed authority. Other atlases and conditions are separately
  generated scientific scopes, with explicit ineligible/not-estimable cases.
- A read-only comparison of the governed state preview with all **59/38**
  publicly retained whole-body positive-call rows found matching source-native
  target/tissue labels. HR values differed by at most **4.931948893727167e-8**,
  consistent with different serialization precision. This is evidence of
  compatible selected coordinates, **not byte identity or equivalence of the
  full matrices**. No precision tolerance or accepted reference was changed.
- Compound display labels, source profile identities, anatomical labels,
  atlas identifiers and condition scopes differ across consumers. Their
  overlap does not authorize a new implicit mapping, a stereochemical merge,
  or transfer of calls to another expression dataset.

The inspected state preview is a separate governed source, rather than a
versioned download of the public release. Current application loaders therefore
do **not** demonstrate that both apps consume the same frozen files as this
repository. Full cross-repository numerical equivalence remains unestablished.

## Reusable interfaces already present

The computational repository already has file-level publication decisions,
exact external-input hashes, frozen output references, compound/tissue rosters,
and regression checks. The phenotype application has an explicit CSV contract,
conservative identity aliases, source-byte hashes and a pinned authority
manifest. The state application has versioned snapshot manifests, dataset/profile
metadata, missingness and GESD eligibility gates, and source-specific import
contracts. These are useful adoption points, but are not one shared schema.

## Public application verification and screenshots

Both launch links rendered their research interfaces in a fresh anonymous
headless Edge session on 2026-10-31. The phenotype app's source README still
describes invitation-only access; the observed public rendering is narrower
evidence of access at assessment time, not a guarantee of future availability.

- [Phenotype Explorer](https://ketamine-phenotype-explorer.streamlit.app/):
  four compound views, threshold/coordinate/phenotype selection, Sankey network,
  evidence filtering, source inspection and downloads. Its live interface
  identified the W1-W5 phenotype authority and showed structural checks passed.
- [Expression-State Explorer](https://huggingface.co/spaces/EricRosenn1/ketamine-state-historeceptomics):
  expression-atlas selection, supported dataset/condition comparisons,
  fingerprint/HR/evidence tables, anatomical and 2D/3D graph controls, provenance
  and exports. The public Space was running at revision
  `db982fa7c520017bb510c00568eaacabdd0cf726`. It is a **static research snapshot**;
  expression uploads are disabled there and belong to the local application.

The [screenshot record](../docs/figures/apps/README.md) identifies genuine
public-interface captures and their scope. Screenshots were reviewed for
public suitability; no private source file, account session, raw input table,
or unpublished authority was copied into the public repository. The default
state graph's **17 displayed evidence-linked coordinates** reflect its display
filter and must not replace the accepted **19 CNS calls**.

## Interface implemented by this enhancement

The versioned, file-based producer/validator described in
[APPLICATION_INTEGRATION.md](../docs/APPLICATION_INTEGRATION.md) exports approved
whole-body positive-call rows and validates synthetic/full-state contract
examples. It preserves source identities and provenance without recomputing
accepted scientific results. It deliberately does not promise a full HR
matrix, CNS matrix, evidence overlay, or operational application ingestion.

| Integration status | Connection |
|---|---|
| Existing and verified in inspected code | State build imports the independently maintained phenotype evidence authority |
| Compatible but separately maintained | Selected baseline identities, thresholds and public whole-body call coordinates; application-specific precision and labels require explicit review |
| Implemented here; ready for consumer evaluation | Public export command, versioned records/manifest, integrity and compatibility validation, synthetic example consumer |
| Proposed, not deployed | A private-app adapter consuming this repository's export with regression-tested identities, missingness and scope |

Further adoption requires a separate bounded change in each application. No
private production loader, source visibility, accepted numerical authority or
scientific interpretation was changed in this task.
