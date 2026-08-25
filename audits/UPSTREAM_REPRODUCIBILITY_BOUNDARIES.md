# Upstream reproducibility boundaries

Machine-readable record:
[`UPSTREAM_REPRODUCIBILITY_BOUNDARIES.csv`](UPSTREAM_REPRODUCIBILITY_BOUNDARIES.csv).

The compact repository reproduces the validated downstream analysis. It does
not claim that every historical source-acquisition or source-table construction
program was recovered.

## Earliest pooled-parent boundary

The only unrecovered producer required before the Full lane is the program that
assembled the 17,715-row × 45-column initial pooled-parent activity assertion
table. Full therefore begins at that immutable table, requires its exact
SHA-256 (`1F799CB884DEA1A3663763F4B87068E0DAA7C348D490F7730665F59CA9F57F2C`),
and then executes all seven recovered downstream pooled stages.

The missing producer is reported as a limitation. Its rules were not inferred
from the finished table and no substitute implementation was created.

## Other frozen-input boundaries

- Raw BioGPS/GNF1H acquisition and the exact historical expression-master
  producer are not reconstructed; the compact frozen expression inputs are
  validated by identity, dimensions, and content contracts.
- Raw-source construction of every ketamine-family and external reference
  profile is outside the compact Verify lane; selected profiles are versioned
  inputs with regression evidence.
- The projected common-RHR values are frozen comparative-scale inputs. Full
  checks pooled raw-HR equivalence before retaining those values and does not
  refit the underlying model.

These boundaries distinguish computational reproduction from end-to-end source
acquisition and from independent scientific validation.
