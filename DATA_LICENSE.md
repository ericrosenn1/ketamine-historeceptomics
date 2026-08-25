# Data and output licensing

## Separate software and data grants

The repository [MIT License](LICENSE) applies only to original software and
original documentation. It does **not** apply to scientific data, synthetic CSV
data, retained analytical outputs, upstream database content, or published
measurements.

For clarity, `data/fixtures/README.md` is original documentation and is covered
by MIT. The three CSV files described by that README are synthetic test data,
not documentation; they are covered by the data/output grant below.

## Project-authored data and outputs

To the extent copyright or related rights are held in the project-created
selection, arrangement, annotations, and expression of the following public
files, those contributions are made available under the
[Creative Commons Attribution-ShareAlike 4.0 International license
(CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/):

- `data/fixtures/*.csv` — wholly invented test fixtures, not scientific
  measurements;
- `data/frozen/metadata/class_membership.csv` — project-authored descriptive
  analysis metadata; and
- `results/reference/**` — 60 project-generated, non-substitutive analytical
  reference outputs.

Use of a factual datum that is not protected by copyright may not require a
copyright license, but attribution, database rights, contract terms, privacy,
and other laws can still apply. This notice does not waive those obligations.
When sharing an adapted compilation, identify the repository release, preserve
the provenance and limitations notices, indicate modifications, link to
CC BY-SA 4.0, and apply the license's ShareAlike requirements to covered
adapted material. The machine-readable repository citation is in
[`CITATION.cff`](CITATION.cff).

## Excluded and third-party material

The public release excludes 20 near-source frozen files. These include compact
selected-activity, BioGPS/GNF1H expression, HR, call, feature-dictionary,
metabolite-profile, and external-profile inputs. They are absent and no public
license is offered for them. The public synthetic fixtures exercise compatible
minimal schemas but do not reproduce, encode, or substitute for those values.

No license is granted here to any third-party database, source workbook,
publication text, literature-derived table, trademark, or other upstream
resource. In particular, this grant does not replace or weaken ChEMBL,
PubChem-contributor, BindingDB, IUPHAR/BPS, PDSP, BioGPS/GNF1H, TTD, publisher,
or other source-specific terms. Inclusion of a project-generated analytical
output does not transfer ownership of an upstream resource or authorize
reconstruction and redistribution of an excluded source table.

[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) records source-specific
notices and official terms links. [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)
documents acquisition boundaries and schemas.

## File-level authority

[`PUBLIC_RELEASE_FILE_DECISIONS.tsv`](PUBLIC_RELEASE_FILE_DECISIONS.tsv) is the
file-level publication authority: 20 near-source files are excluded/replaced
for testing by synthetic fixtures, `data/frozen/metadata/class_membership.csv`
is retained, and all 60 `results/reference/**` files are retained. The source-
era inventory and hashes remain in [`DATA_MANIFEST.csv`](DATA_MANIFEST.csv).
If a broad statement elsewhere conflicts with the file-level decision table,
the narrower per-path decision controls.

## No warranty

The data and outputs are provided without warranty. Provider terms can change,
and this notice is not legal advice. Before adding or redistributing any
external-source content, recheck the current provider terms, preserve
record-level provenance, and obtain any permissions required for the intended
use.
