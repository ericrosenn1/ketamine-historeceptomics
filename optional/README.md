# Analyses outside the current release

Version 0.1.1 covers the ketamine historeceptomics computational core: governed
activity/expression integration, HR-score matrices, GESD fingerprints,
ketamine-family and external-drug comparisons, sparse and continuous
multivariate derivatives, whole-body fingerprints, and the fixed-coordinate
Figure 4 output.

The current manuscript, **_Historeceptomic Profiling of Ketamine, Its
Enantiomers, and Metabolites_** by Eric Rosenn and Timothy Cardozo, also
contains downstream interpretation analyses that are not executable from this
public release:

- the literature search and semantic adjudication of 400 predefined CNS
  target-tissue-phenotype combinations;
- compound-pair-phenotype path assembly and Sankey rendering;
- the literature search and definitive adjudication of 114 predefined
  target-tissue-disease combinations, with 20 retained relationships;
- pathology matrix construction and rendering; and
- manuscript assembly, narrative interpretation, and literature-derived
  tables.

These analyses are not imported or required by Smoke, Verify, Full, tests, or
public CI. No manuscript draft is committed or used as a numerical input. The
working manuscript title and authors are documented as scientific identity, not
as an assertion of journal, DOI, date, or publication status.

The private project tree contains literature-search summaries and historical
figure packages, but the alignment audit did not identify a single current,
portable, redistribution-approved package containing all source records,
search dictionaries, adjudication ledgers, build scripts, manifests, licensing
decisions, and validation evidence needed to reproduce the manuscript's final
phenotype and pathology outputs. Historical pathology figure packages also
predate the definitive 20-relationship source audit. They are therefore not
promoted or silently substituted here.

Future inclusion of an optional analysis requires its own explicit scope,
source and citation record, file-level redistribution decisions, governed input
contract, tests, numerical validation, interpretation limits, and scientific
approval. Restricted sources cannot be added merely because the core software
is MIT-licensed.

The explicit status of each manuscript analysis is recorded in
[`ANALYSIS_REPRODUCIBILITY_MATRIX.csv`](../ANALYSIS_REPRODUCIBILITY_MATRIX.csv).
In literature mapping, a documented not-found result means that no qualifying
source was found under the recorded protocol; it is not evidence of biological
absence.

Nothing in this directory expands the causal or biological interpretation of
the retained results. Historeceptomic outputs remain observational,
construction-dependent representations.
