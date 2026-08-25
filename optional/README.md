# Analyses outside the current release

Version 0.1.1 covers the ketamine historeceptomics computational core: governed
activity/expression integration, HR-score matrices, GESD fingerprints,
ketamine-family and external-drug comparisons, sparse and continuous
multivariate derivatives, whole-body fingerprints, and the fixed-coordinate
Figure 4 output.

It does not include the complete source and numerical packages for:

- receptor-tissue-effect literature mapping;
- pathology or phenotype integration;
- manuscript assembly or production;
- other downstream biological interpretation workflows.

These analyses are not imported or required by Smoke, Verify, Full, tests, or
public CI. No manuscript draft is committed or used as a numerical input, and
the public documentation does not infer a manuscript title or author list.

Future inclusion of an optional analysis requires its own explicit scope,
source and citation record, file-level redistribution decisions, governed input
contract, tests, numerical validation, interpretation limits, and scientific
approval. Restricted sources cannot be added merely because the core software
is MIT-licensed.

Nothing in this directory expands the causal or biological interpretation of
the retained results. Historeceptomic outputs remain observational,
construction-dependent representations.
