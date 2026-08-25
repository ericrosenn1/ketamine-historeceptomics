# Third-party notices

The repository's MIT license covers original software and original
documentation only. It does not license upstream databases, publication
content, scientific data, or the retained analytical outputs. Data/output
terms are stated in [`DATA_LICENSE.md`](DATA_LICENSE.md). Provider links and
terms below were checked on 2026-08-25 and may change.

## What is and is not redistributed

Twenty near-source frozen paths are excluded from the public release and are
functionally replaced for Smoke testing by three wholly invented CSV fixtures.
The only retained `data/frozen/**` file is the project-authored descriptive
metadata table `data/frozen/metadata/class_membership.csv`. The 60 files under
`results/reference/**` are project-generated, non-substitutive analytical
references; they are not raw database exports. The exact per-path authority is
[`PUBLIC_RELEASE_FILE_DECISIONS.tsv`](PUBLIC_RELEASE_FILE_DECISIONS.tsv).

The Markdown file `data/fixtures/README.md` is original documentation covered
by MIT. The synthetic CSV fixture content is data and is governed by the
CC BY-SA 4.0 data/output notice, not by MIT. None of the fixture values was
copied from an external source, and the fixtures are not scientific evidence.

## Pharmacology and target resources

- **ChEMBL.** The [official ChEMBL site](https://www.ebi.ac.uk/chembl/)
  identifies ChEMBL data as CC BY-SA 3.0; general
  [EMBL-EBI terms](https://www.ebi.ac.uk/about/terms-of-use/) also apply. No
  ChEMBL row, selected value, or database extract is included in the public
  input set.
- **PubChem and PubChem BioAssay.** PubChem aggregates records submitted by
  many contributors. Its [data-source documentation](https://pubchem.ncbi.nlm.nih.gov/docs/data-sources)
  and [BioAssay documentation](https://pubchem.ncbi.nlm.nih.gov/docs/bioassays)
  require source-aware provenance; reuse conditions can be contributor-
  specific. No PubChem or BioAssay row, selected value, or bulk collection is
  included in the public input set.
- **BindingDB.** The official
  [BindingDB information page](https://www.bindingdb.org/rwd/bind/info.jsp)
  labels BindingDB-curated data CC BY 3.0, while the current primary paper
  describes CC BY 4.0; ChEMBL-derived records retain ChEMBL's CC BY-SA 3.0
  conditions. No BindingDB-sourced selected value or extract was identified in
  the governed 81-path inventory, so no BindingDB content is redistributed.
  Resolve source- and release-specific terms before any future inclusion.
- **IUPHAR/BPS Guide to PHARMACOLOGY.** Its official
  [web-services page](https://www.guidetopharmacology.org/webServices.jsp)
  states that the database is under ODbL and its contents under CC BY-SA 4.0.
  No GtoPdb database extract is included. A resource name in historical
  provenance is not itself a retained database record.
- **NIMH Psychoactive Drug Screening Program (PDSP).** The live
  [PDSP Ki Database page](https://pdsp.unc.edu/databases/kidb.php) describes the
  database as a public-domain resource. The exact project workbook, compact
  selected measurements, and source records are nevertheless excluded because
  they are governed external inputs and can mix source-specific provenance.
  Full mode requires an authorized local workbook and does not copy it into
  Git.
- **Therapeutic Target Database (TTD).** TTD appeared in historical
  source-summary/candidate-source material. No TTD extract is included and no
  blanket redistribution permission was established for the historical
  content. Consult the [official TTD site](https://ttd.idrblab.net/) and current
  terms before acquisition.

## Expression resources

- **BioGPS Human U133A/GNF1H Gene Atlas, GSE1133, averaged gcRMA.** The source
  is available from [BioGPS downloads](https://biogps.org/downloads/).
  [BioGPS terms](https://biogps.org/terms/) address access, notices, and
  third-party content but do not provide a sufficiently explicit grant for
  redistributing this project's exact processed GNF1H/gcRMA tables. The
  77-tissue expression table, standardized values, feature dictionary, and
  expression-derived near-source HR/profile inputs are therefore excluded.
- **GTEx and Allen Human Brain Atlas (AHBA).** No GTEx or AHBA file, field,
  selected value, or source lane was identified in the governed 81-path
  inventory. Neither resource contributes content to this public release.

## Publications and manual literature

No article text, literature PDF, supplementary table, manuscript, or
correspondence is redistributed. Exact literature-derived values in excluded
near-source tables remain excluded. The two explicit manual-literature sources
and the methodological papers are cited in
[`docs/REFERENCES.md`](docs/REFERENCES.md) and
[`CITATION.bib`](CITATION.bib). Citation does not grant rights in publication
content and does not imply author endorsement.

## Retained project outputs

`data/frozen/metadata/class_membership.csv` and `results/reference/**` were
retained as project-authored metadata and non-substitutive analytical outputs.
Their inclusion does not relicense, transfer ownership of, or waive any right
in an upstream resource. Users must not treat a derived numerical result as a
source database record or use this notice to infer permission for the excluded
inputs.

## Scientific software

The environment uses third-party Python packages, each under its own upstream
license. Exact versions are pinned in
[`requirements-lock.txt`](requirements-lock.txt). Major scientific citations
for NumPy, SciPy, pandas, Matplotlib, scikit-learn, and PyArrow are in
[`docs/REFERENCES.md`](docs/REFERENCES.md); citation does not replace package
license compliance.

## Names, marks, and warranties

Names, logos, trademarks, and publication content remain the property of their
respective owners. No third-party logo is included. Nothing in this notice is a
warranty that an upstream provider's terms will remain unchanged or that a
specific downstream use is permitted. Recheck the current provider terms and
preserve record-level attribution before any new acquisition or redistribution.
