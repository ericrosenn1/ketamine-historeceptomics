# Data sources, schemas, and public boundary

This page records the external resources that informed the historical analysis,
the schemas used at the reproducible boundary, and what is actually present in
the public repository. It is a provenance statement, not permission to copy an
upstream database. Provider terms and links were checked on 2026-08-25 and may
change.

## Public-release inventory

The source-era inventory contains 81 governed paths. The public release applies
the following deterministic file-level decision:

| Path rule | Count | Public decision | Reason |
|---|---:|---|---|
| `data/frozen/core/**` | 8 | Excluded; public Smoke uses synthetic fixtures | Near-source selected activity, BioGPS/GNF1H expression, HR values, missing-expression accounting, or fingerprint calls encode source observations too closely for redistribution without a clearer rights basis. |
| `data/frozen/e7/**` | 6 | Excluded; public Smoke uses synthetic fixtures | Frozen metabolite profiles, calls, and identity accounting inherit mixed pharmacology/expression/manual-literature provenance. |
| `data/frozen/metadata/feature_dictionary.parquet` | 1 | Excluded; public Smoke uses synthetic fixtures | Exact target–tissue feature content derives from the governed expression mapping. |
| `data/frozen/profiles/**` | 5 | Excluded; public Smoke uses synthetic fixtures | The long profiles, call tables, external profiles, and pairwise input inherit mixed external-source values. |
| `data/frozen/metadata/class_membership.csv` | 1 | Retained | Project-authored descriptive analysis metadata; it contains no assay or expression measurement. |
| `results/reference/**` | 60 | Retained | Project-generated, non-substitutive analytical reference outputs selected for inspection and regression comparison; they are not raw database exports. |

Thus, **20 near-source frozen files are absent**, one project metadata file and
60 analytical reference files are retained, and three invented CSV fixtures
stand in for the excluded input classes during public tests. The fixtures are
not one-for-one data replacements and cannot reproduce the accepted research
results. [`PUBLIC_RELEASE_FILE_DECISIONS.tsv`](../PUBLIC_RELEASE_FILE_DECISIONS.tsv)
is the file-level publication authority; [`DATA_MANIFEST.csv`](../DATA_MANIFEST.csv)
preserves the governed source-era path and hash inventory.

The public scientific-data footprint is therefore:

- `data/fixtures/smoke_activity.csv`, `smoke_expression.csv`, and
  `smoke_profiles.csv`: wholly invented test values;
- `data/frozen/metadata/class_membership.csv`: descriptive class membership
  with columns `class_id`, `class_label`, `drug`, `notes`,
  `numeric_profile_expected`, and `status_only`;
- `results/reference/**`: 60 accepted tables, JSON checks, and figures that
  report project analyses but do not provide the excluded source-level input
  tables.

No raw database export, source workbook, literature PDF, manuscript,
correspondence, credential, or captured software environment is distributed.

## External-input boundary

The earliest recovered pooled-parent boundary is a 17,715-row × 45-column
activity assertion table with SHA-256
`1F799CB884DEA1A3663763F4B87068E0DAA7C348D490F7730665F59CA9F57F2C`.
The program that originally assembled this table from raw pharmacology sources
was not recovered. Consequently, neither the private workflow nor this public
release claims a raw-database-to-activity-table reconstruction.

Authorized holders can run Full mode by supplying three local resources:

1. the exact initial activity assertion CSV;
2. the governed PDSP Ki workbook used by the recovered pipeline; and
3. the governed project source directory containing the required expression
   and lineage resources.

These resources stay outside Git. The Full launcher accepts explicit paths,
hashes the supplied files, executes the recovered downstream stages in a
derivative run directory, and fails closed if required hashes, schemas,
missingness, or numerical gates do not match. See [`FULL_MODE.md`](FULL_MODE.md).
The retained `results/reference/**` files are comparison targets, not a way to
reverse-engineer or substitute for the excluded inputs.

Public Smoke mode begins instead with synthetic schemas. It demonstrates code
behavior only and must not be presented as a scientific reproduction of the
ketamine results.

## Source-resource register

### Pharmacology and target resources

| Resource | Historical role | Official acquisition and current terms | Public content decision |
|---|---|---|---|
| ChEMBL | Candidate/source pharmacology and source provenance | Obtain releases or use web services from [ChEMBL](https://www.ebi.ac.uk/chembl/). The official site identifies ChEMBL data as [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); general [EMBL-EBI terms](https://www.ebi.ac.uk/about/terms-of-use/) also apply. | No ChEMBL row, selected value, or database extract is retained in the public input set. |
| PubChem and PubChem BioAssay | Compound/assay identifiers, contributed assay records, and provenance | Use official [data-source](https://pubchem.ncbi.nlm.nih.gov/docs/data-sources), [BioAssay](https://pubchem.ncbi.nlm.nih.gov/docs/bioassays), and [download](https://pubchem.ncbi.nlm.nih.gov/docs/downloads) documentation. PubChem aggregates depositor content; licensing and reuse conditions remain contributor-specific and must be checked at the contributing source. | No PubChem or BioAssay row, selected value, or bulk collection is retained in the public input set. |
| BindingDB | Audited candidate source in the wider source landscape | Use the official [BindingDB information page](https://www.bindingdb.org/rwd/bind/info.jsp). That page labels BindingDB-curated data CC BY 3.0, whereas the 2025 primary paper describes CC BY 4.0; its ChEMBL-derived subset remains subject to ChEMBL CC BY-SA 3.0. Resolve the applicable record-level source and current term before reuse. | A path/content audit found no BindingDB-sourced selected value or database extract in the 81-path governed inventory. Nothing from BindingDB is redistributed. |
| IUPHAR/BPS Guide to PHARMACOLOGY | Candidate target/pharmacology provenance | The official [web-services page](https://www.guidetopharmacology.org/webServices.jsp) states that the database is offered under ODbL and its contents under CC BY-SA 4.0. Current access requirements, including registration or API keys, must be checked at acquisition time. | No GtoPdb database extract is retained. A historical source name does not itself establish that selected public data came from GtoPdb. |
| NIMH PDSP Ki Database | Pharmacology, species, endpoint, and censored-relation evidence | The live [PDSP Ki Database page](https://pdsp.unc.edu/databases/kidb.php) provides search/CSV access and describes the Ki database as a public-domain resource. The project used a dated local workbook; that exact workbook and its provenance remain governed external inputs. | The workbook and all compact selected PDSP values are excluded. Full mode requires an authorized local copy. |
| Therapeutic Target Database (TTD) | Historical source-summary/candidate-target context | Acquire only through the official [TTD site](https://ttd.idrblab.net/), record the release and terms in force, and cite the current primary paper. No blanket redistribution permission was established for the historical project content. | No TTD database extract is retained; conservative exclusion applies. |
| Manual literature | Individual pharmacology evidence and provenance review | Acquire articles from their publishers or lawful repositories by DOI. Copyright and supplementary-data terms are publication-specific. The two explicit sources are listed in [`REFERENCES.md`](REFERENCES.md). | Exact literature-derived values, article text, PDFs, and tables are excluded. |

### Human expression resources

The historical expression profile was identified as the BioGPS Human
U133A/GNF1H Gene Atlas, GEO series GSE1133, averaged gcRMA dataset. The source
atlas and preprocessing method should be cited separately: the Gene Atlas,
BioGPS portal papers, and gcRMA paper are listed in
[`REFERENCES.md`](REFERENCES.md).

- Official acquisition: [BioGPS downloads](https://biogps.org/downloads/).
- Terms: [BioGPS terms of use](https://biogps.org/terms/). Those terms permit
  access and use, require preservation of notices, and acknowledge third-party
  content, but do not provide a sufficiently explicit redistribution grant for
  this project's exact processed GNF1H/gcRMA tables. The public release therefore
  excludes those tables.
- Historical transformation: an averaged gcRMA expression matrix was mapped
  from probe/gene records to compatible exact-protein targets, reduced to a
  governed 77-tissue panel after seven cancer/fetal/stem samples were excluded,
  and standardized within each gene using sample standard deviation
  (`ddof = 1`). That tissue selection, target mapping, and standardization are
  project transformations, not claims about the source atlas. The manuscript
  records compatible-probe aggregation, but the public release does not recover
  or claim a raw-download-to-expression-master producer.

The resulting 58-target × 77-tissue expression table, its 18-tissue strict-CNS
subset, the target–tissue feature dictionary, and all near-source HR/profile
inputs are absent from the public release.

### Manuscript literature-mapping resources

The manuscript's CNS phenotype and neuropsychiatric pathology mappings used
[PubMed/NCBI](https://pubmed.ncbi.nlm.nih.gov/), [Europe
PMC](https://europepmc.org/), PubMed Central, [Crossref](https://www.crossref.org/),
[OpenAlex](https://openalex.org/), and publisher/DOI records. PubMed/Europe PMC
and publisher records supported source inspection; Crossref and OpenAlex also
supported discovery and metadata reconciliation. Citation chaining from
relevant reviews could identify candidates, but a review did not replace a
qualifying primary source.

These are external discovery and evidence systems, not redistributed database
inputs. The public repository does not contain article text, PDFs, the complete
query/cache tree, qualifying-source extracts, final adjudication packages, or
the governed builders for the 400-cell phenotype map and 114-cell pathology
map. Source-specific terms and article copyright continue to apply. A
documented not-found or access-limited search result is not evidence of
biological absence.

### Explicit absence findings

- **GTEx:** no GTEx file, field, selected value, or source lane was identified
  in the governed 81-path inventory.
- **Allen Human Brain Atlas (AHBA):** no AHBA file, field, selected value, or
  source lane was identified in the governed 81-path inventory.
- **BindingDB:** no BindingDB-sourced selected value or extract was identified,
  as noted above.

These are repository-content findings, not statements that the resources are
scientifically irrelevant. An unavailable or excluded source is not a negative
scientific observation.

## Input schema contracts

The original 45-column activity assertion table is governed by exact hash and
the recovered upstream scripts. Its substantive record grain includes compound
identity, source record, target identity and target grain, endpoint, species,
numerical value and unit, relation/censoring operator, and source/publication
provenance. Do not flatten exact proteins, receptor complexes, receptor
families, or ambiguous targets into one interchangeable target class.

The downstream selected-activity contract includes at minimum:

```text
canonical_target_id
final_selected_pActivity_v4
final_activity_relation_operator_v4
final_activity_is_bounded_v4
```

The expression contract includes:

```text
canonical_target_id
tissue_id
tissue_label
expression_z
```

The long comparison-profile contract includes:

```text
drug
feature_id
target
tissue
raw_hr
common_rhr
call_alpha001
call_alpha0001
```

The three public fixture CSVs implement exactly these minimal contracts with
fictional identifiers (`SMOKE_*`, `SYNTHETIC_*`). One missing expression value
and one censored activity boundary are deliberate. They test missingness and
relation handling; they are not measurements and must never be merged with the
retained reference results.

## Acquisition rules for an authorized rebuild

1. Acquire each source directly from its official provider or an authorized
   governed snapshot; do not scrape a republished compilation when provenance
   is available at the original source.
2. Record provider, release/snapshot date, download URL or accession, file
   format, byte size, SHA-256, license/terms URL, and contributor-level terms.
3. Preserve compound identity, target grain, endpoint, species, units,
   relation operators, censoring, and missingness. Do not zero-fill or silently
   convert a boundary into an exact measurement.
4. Do not substitute a live database release for the frozen snapshot and call
   the result a reproduction. A current-source rebuild is a new derivative and
   requires scientific reconciliation and its own provenance.
5. Treat retrieval failure as unavailable evidence, never as a negative
   observation.

Primary citations and verified DOI links are maintained in
[`REFERENCES.md`](REFERENCES.md) and [`CITATION.bib`](../CITATION.bib).
