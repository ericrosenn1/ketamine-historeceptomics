# Synthetic public fixtures

These files are invented test data. They contain no measurements copied from
ChEMBL, PubChem, PDSP, BioGPS/GNF1H, IUPHAR/BPS, BindingDB, a publication, or a
private project resource. They exercise schemas, missingness, censored bounds,
fingerprint metrics, and deterministic multivariate code; they are not
scientific evidence and must not be combined with the retained ketamine results.

`smoke_profiles.csv` supplies four fictional compounds over three fictional
target–tissue features. `smoke_activity.csv` and `smoke_expression.csv` show the
minimal activity/expression schemas used to test exact values, a right-censored
affinity boundary, within-target expression values, and one unsupported
coordinate. Expected values are simple enough to audit by inspection.

The fixtures collectively replace 20 near-source frozen inputs that are not
redistributed in the public release. Exact external-input schemas, original
hashes, and acquisition routing are documented in
[`docs/DATA_SOURCES.md`](../../docs/DATA_SOURCES.md),
[`docs/FULL_MODE.md`](../../docs/FULL_MODE.md), and
[`CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv`](../../CURRENT_ANALYSIS_AUTHORITY_MANIFEST.csv).

SPDX-License-Identifier: MIT
