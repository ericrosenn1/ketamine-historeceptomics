# Computational methods

## Study representation

Historeceptomics in this study combines selected compound-target pharmacology
with tissue-specific target expression. The resulting HR-score matrix describes
the numerical target × anatomy representation available for a compound. A
historeceptomic fingerprint is the sparse subset of target-anatomy pairs called
from that matrix as upper-tail HR outliers by generalized extreme Studentized
deviate (GESD) testing. The HR-score matrix is therefore the numerical input to
fingerprint construction, not the fingerprint itself.

Fingerprint-derived analyses are the principal manuscript-facing analyses.
Analyses of continuous HR values are retained as exploratory secondary
analyses. The two representations are generated, compared, and reported
separately.

## Public execution boundary

The scientific methods below describe the accepted analysis, not the contents
of the synthetic Smoke fixtures. This public repository retains 60 accepted
reference-output files and one cleared class-membership table. The 20
near-source numerical inputs needed to execute the accepted analysis are not
redistributed; Verify and Full read them only from a caller-supplied directory
and validate every file against
[`EXTERNAL_INPUT_MANIFEST.tsv`](../EXTERNAL_INPUT_MANIFEST.tsv) before
computation. Smoke uses invented fixtures to test implementation contracts and
does not regenerate ketamine results.

Public input routing does not change the selected values, formulas, thresholds,
missingness rules, fixed projections, coordinates, or regression tolerances
described here.

## 1. Compound identity

Compound names are normalized for Unicode typography, dash variants,
whitespace, and case, but identity-bearing punctuation and stereochemical
qualifiers are preserved. A record is resolved only through an explicitly
configured alias or source-specific rule in [`configs/compounds.yaml`](../configs/compounds.yaml).
Ambiguous or unknown labels remain unresolved rather than being merged.

The following identities remain separate:

- ketamine with unspecified stereochemistry;
- the pooled-parent ketamine analysis profile;
- chemically confirmed racemic ketamine;
- S-ketamine (esketamine);
- R-ketamine (arketamine);
- specified hydroxynorketamine stereoisomers;
- generic or unspecified-isomer metabolite aggregates.

The pooled-parent profile is therefore not interpreted as a confirmed racemate,
and racemate activity is never assigned to an isolated enantiomer.

## 2. Pharmacological activity

The manuscript source inventory comprises ChEMBL, PubChem BioAssay, the NIMH
PDSP Ki Database, IUPHAR/BPS Guide to PHARMACOLOGY, BindingDB, and primary
literature. These names describe the historical candidate/provenance landscape;
they do not imply that every resource supplied a selected retained value or
that database exports are redistributed. The selected public execution boundary
starts from governed, hash-validated activity inputs as described in
[`PROVENANCE.md`](PROVENANCE.md) and [`DATA_SOURCES.md`](DATA_SOURCES.md).

Eligible positive quantitative source values are converted to molar units and
expressed as `pActivity = -log10(activity in mol/L)`. Original concentration
relation operators are retained as provenance: an observation such as
`Ki > 10,000 nM` remains a censored concentration boundary and is not converted
into an exact value. Because the negative logarithm reverses numerical order,
the transformed boundary is interpreted together with its original operator,
not as an uncensored pActivity measurement.
Zero, negative, nonnumeric, and unsupported values do not become numerical
pActivity observations.

For each exact-protein target, selection follows the recovered rules:

1. use measured human evidence when available;
2. otherwise use measured mammalian nonhuman evidence;
3. within that species stratum, prefer exact measurements over censored measurements;
4. apply endpoint priority in this order: Ki, then Kd, then IC50, then EC50/AC50, then other standardized quantitative potency;
5. for exact observations, retain the strongest selected activity (maximum pActivity, equivalent to minimum molar concentration);
6. for censored observations, retain the appropriate reported boundary and its direction.

Modeled, assigned, non-mammalian, unresolved-species, and otherwise excluded
records remain available for accounting but are not silently substituted for a
measured selected value. The final pooled-parent activity input contains 76
selected targets: 40 exact and 36 censored `Ki > 10,000 nM` values.

## 3. Target harmonization

Target mapping is restricted to exact canonical protein identifiers and gene
symbols represented in the versioned feature dictionary. Generic receptor or
complex measurements are not decomposed into individual subunits. For example,
a generic NMDA-receptor record is not assigned to GRIN subunits without an exact
source mapping. Protein, receptor-complex, and family-grain records therefore
remain distinct.

## 4. Tissue expression

The manuscript records the expression source as the human BioGPS GeneAtlas
U133A/GNF1H GCRMA panel. Probe mappings incompatible with an exact gene were
excluded, compatible probes were summarized within gene, and seven
cancer/fetal/stem samples were excluded to form the governed 77-tissue panel.
The public repository can verify the accepted standardized values and their
downstream use, but it does not redistribute the raw atlas or recover a
raw-download-to-expression-master producer. The manuscript-level probe and
sample-processing description is therefore provenance, not a newly claimed
public execution lane.

Expression is standardized separately within each gene over the full 77-tissue
panel using the sample standard deviation (`ddof = 1`):

```text
expression_Z(gene, tissue)
  = [expression(gene, tissue) - mean_tissues(expression_gene)]
    / sample_SD_tissues(expression_gene)
```

Of the 76 selected pooled-parent activity targets, 58 have expression profiles
that satisfy the exact-protein feature contract. The remaining unsupported
targets are not imputed or filled with zero. The governed external input set
contains the frozen standardized expression values needed for Verify; the raw
BioGPS acquisition and the exact producer of the historical expression master
are outside the public repository boundary.

The strict-CNS panel is the configured 18-tissue subset of those 77-panel
z-scores. It is not re-standardized within the CNS subset.

## 5. HR-score calculation

For every supported target-anatomy pair:

```text
HR(target, tissue)
  = selected pActivity(target) × expression_Z(target, tissue)
```

This calculation produces the full numerical HR-score matrix for a compound;
unsupported coordinates remain missing. The whole-body HR-score matrix
contains 58 targets × 77 tissues = 4,466 finite coordinates. The strict-CNS
HR-score matrix is the exact 18-tissue subset defined in
[`configs/tissues_cns18.yaml`](../configs/tissues_cns18.yaml), giving 58 × 18 =
1,044 finite coordinates.

HR is a constructed score. Its sign and magnitude do not independently encode
agonism, antagonism, therapeutic benefit, adverse effects, tissue exposure, or
causal biological effect. Activity relation and source fields remain available
upstream so that exact and censored inputs are not conflated.

## 6. Historeceptomic fingerprint construction

Fingerprints are constructed with a one-sided upper-tail Rosner-style GESD
procedure applied to the finite, signed values in an HR-score matrix. At each
step:

1. calculate the mean and sample standard deviation of the active values;
2. identify the largest standardized upper deviation;
3. calculate the GESD critical value for the current sample size and α;
4. remove that candidate for the next iteration;
5. retain calls through the last iteration where the test statistic exceeds the critical value.

The maximum number of candidates is:

```text
r_max = floor(0.10 × number of finite tested coordinates)
```

The resulting historeceptomic fingerprint is the sparse set of selected
target-anatomy coordinates. The primary threshold is α = 0.001. The stricter
sensitivity threshold is α = 0.0001. Source order deterministically resolves
exact ties. The strict-CNS pooled-parent fingerprints contain 19 primary and 14
sensitivity calls. Whole-body testing contains 59 primary and 38 sensitivity
calls.

Because the strict-CNS and whole-body tests use different candidate universes,
their membership differences are descriptive and are not interpreted as
biological gain or loss.

## 7. Sparse fingerprint comparisons

For cross-compound analysis at each α threshold, fingerprint membership is
encoded in a compound × target-anatomy fingerprint-call matrix:

- `1`: a called target-anatomy pair;
- `0`: a tested target-anatomy pair that was not called;
- missing: a coordinate that was not supported or tested for that compound.

The fingerprint-call matrix represents sparse call membership; it is not the
numerical HR-score matrix. Pairwise sparse comparisons operate on these
fingerprint calls and report call counts, intersection and union sizes, Jaccard
similarity, overlap coefficient, target and tissue overlap, and signed sparse
cosine similarity. A jointly tested Jaccard measure is also reported to
separate call-set similarity from unequal feature support. Ordinary call-set
Jaccard uses every called coordinate in either profile; jointly tested Jaccard
first restricts both call sets to coordinates tested in both profiles. For both
measures, two empty call sets have Jaccard similarity 1 by convention.

Support-aware sparse fingerprint PCA is calculated from the 0/1/missing
fingerprint-call matrix independently at α = 0.001 and α = 0.0001. These
fingerprint-derived outputs are the principal multivariate results represented
for manuscript use. A feature must be observed in at least two profiles and
vary over its observed values. Retained features are mean-centered without
variance scaling. Missing coordinates are initialized from feature means and
updated by iterative rank-two SVD while observed cells remain fixed. The
accepted implementation uses a 300-iteration maximum and retains
iteration-limit point estimates with an explicit nonconvergence limitation
rather than silently changing the model.

## 8. Ketamine-family and external-drug comparisons

The ketamine-family set contains 10 compound profiles: pooled-parent ketamine,
confirmed racemate, S-ketamine, R-ketamine, one unspecified-isomer
hydroxyketamine aggregate, and five additional metabolite profiles. The family
analysis contains all 45 unordered pairs.

The external comparison contains 25 psychoactive reference drugs listed in
[`configs/reference_drugs.yaml`](../configs/reference_drugs.yaml). Combined with
the 10 ketamine-family profiles, the global analysis contains 35 profiles and
all 595 unordered pairs.

Thirty profiles are stored in the main strict-CNS profile table and five
additional metabolite profiles are added from the separate compact metabolite
inputs. The potential strict-CNS comparison grid contains 76 targets × 18
tissues = 1,368 coordinates, but support varies by compound and each pair is
evaluated on its matched finite intersection. The pooled-parent common-scale
profile contains 1,026 coordinates (57 targets × 18 tissues) after pooled-only
GRIN3B coordinates are excluded from cross-profile support. Its original
1,044-coordinate, 58-target strict-CNS universe is retained for the
pooled-parent GESD fingerprint.

## 9. Exploratory continuous comparisons

Continuous cross-profile analyses use the frozen `common_rhr` representation,
not raw HR directly. Raw HR is projected through the weighted empirical
cumulative distribution encoded in the frozen common-scale model: tied knot
values use their weighted mid-rank, values between knots use the corresponding
weighted cumulative boundary, and the resulting percentile is transformed by
the standard normal inverse CDF after clipping to `[1e-6, 1 - 1e-6]`. This
rank-based projection is fixed; it is not refit during Verify or Full.

Pairwise common-RHR calculations use only matched finite coordinates and report
signed and absolute differences, root-mean-square and Euclidean distances,
cosine similarity, Pearson and Spearman correlations when estimable, and
feature-support overlap. The recorded overlap gate requires at least 20 matched
features spanning at least two targets. Pairs below that gate remain in the
output with their denominators and limitation state. These analyses operate on
numerical HR-derived values rather than fingerprint calls and are not
fingerprint analyses.

Exploratory multivariate outputs include missingness-aware EM-SVD PCA,
complete-case PCA, target-level variants, PCoA, weighted metric MDS, and
average-linkage clustering. Low-rank or insufficient-data cases remain
`NOT_ESTIMABLE` rather than being forced into numerical results.

The fixed-reference PCA fits the 25 external profiles and projects the 10
ketamine-family profiles by weighted least squares. The projected family
profiles do not refit the reference axes. Some inherited EM-SVD fits reached the specified
300-iteration limit before the update tolerance; their frozen point estimates
are retained with an explicit limitation rather than changing the method.

Drug-class membership is descriptive and many-to-many, not a mutually
exclusive pharmacological classification. The frozen registry contains 84
memberships across 14 contexts and 27 identities, including status-only entries
that do not enter numerical models. Global RMS ordination and clustering use
the complete finite 21-profile subset of the 35-profile comparison; the 14
excluded profiles are named in the subset audit.

## 10. Missing-data handling

Missingness is preserved at each stage. Unsupported pharmacological targets,
targets without compatible expression, and compound-feature combinations that
were not tested remain missing. Zero is introduced only for a tested non-call
in a fingerprint-call matrix. This call matrix is distinct from the numerical
HR-score matrix. Pairwise common-RHR statistics are calculated only on matched
observed coordinates, and their denominators are reported.

## 11. Manuscript literature mapping

### CNS phenotype mapping

The manuscript evaluates 400 prespecified combinations formed from 20 CNS
target-tissue pairs and 20 phenotype definitions. Searches used PubMed/NCBI
E-utilities and Europe PMC, with Crossref and OpenAlex for discovery and
metadata reconciliation and PubMed Central or publisher/DOI records for source
inspection where available. Queries combined target/receptor aliases,
compatible anatomy terms, and phenotype-specific terms.

A relationship was retained only when semantic review found a primary source
jointly supporting the target, compatible anatomy, and requested phenotype.
Mammalian evidence was eligible. Reviews could support discovery but did not
replace a qualifying primary source. Initially unsupported cells received a
second search with expanded terms. Retrieval failure or rate limiting was
recorded as an access limitation, not as evidence of biological absence.

The manuscript Sankey links compounds to α = 0.001 fingerprint target-tissue
pairs and those pairs to retained phenotype relationships. Link width counts
distinct compound-pair-phenotype paths; it is not an effect-size or
evidence-strength scale.

### Neuropsychiatric pathology mapping

The pathology universe contains the 19 pooled-parent α = 0.001 CNS fingerprint
pairs crossed with six disease groups: major depressive disorder, bipolar
disorder, anxiety, post-traumatic stress disorder, substance use disorder, and
alcohol use disorder (114 combinations). Search routes and semantic review
followed the same general source systems while adding disease synonyms,
disease-model terms, transcriptomic/proteomic/receptor-binding terms, and
compatible subregional anatomy.

Definitive source-level adjudication retained 20 relationships: 6 exact-direct,
13 hierarchical-direct, and 1 orthogonal. Exact and hierarchical direct classes
require joint target-anatomy-disease evidence in one qualifying source;
orthogonal evidence requires separately supported target-disease and
anatomy-disease legs under the governed rule. Incompatible exposure/behavior
models, null target findings, unresolved broader anatomy, and inaccessible
insufficient evidence were not accepted. The retained disease counts are MDD 3,
bipolar disorder 3, anxiety 2, SUD 5, AUD 7, and PTSD 0.

### Reproducibility boundary

These literature mappings and their manuscript figures are documented
scientific analyses but are not executed by Smoke, Verify, or Full. Their
complete source records, final adjudication authorities, redistribution
decisions, governed builders, and validation fixtures are absent from the
public release. Their explicit statuses are recorded in
[`ANALYSIS_REPRODUCIBILITY_MATRIX.csv`](../ANALYSIS_REPRODUCIBILITY_MATRIX.csv).
Selected continuous HR-score correspondences discussed with pathology remain
secondary and must not be presented as fingerprint calls.

## 12. Validation

The implementation is tested at the identity, target, activity, expression,
HR, fingerprint, pairwise, multivariate, fixed-reference, and resource-control
levels. Verify mode regenerates the downstream tables and figures from the
manifest-valid external inputs and compares them with the retained versioned
references. Comparisons require matching schemas, keys, missingness,
text/status values, call sets, dimensions, and rosters; numerical comparisons
use the recorded absolute tolerances.

The publication Figure 4 is a visual derivative of fixed PCA coordinates. Its
25 external-drug points and pooled-parent ketamine point are not refit, moved,
or jittered during rendering.

Data-resource acquisition and terms are documented in
[`DATA_SOURCES.md`](DATA_SOURCES.md); methodological citations are in
[`REFERENCES.md`](REFERENCES.md).
