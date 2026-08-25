# References

This bibliography separates methodological precedent, external source-resource
citations, manual literature evidence, and software citations. The machine-
readable records are in [`CITATION.bib`](../CITATION.bib). DOI metadata and the
official resource links below were checked on 2026-08-25.

## Attribution boundary

The method papers below explain scientific ideas or procedures on which this
implementation builds. Citing them does **not** identify their authors as
authors of this repository's source code, as authors of any future manuscript,
or as endorsers of this release. Repository citation metadata is separate in
[`CITATION.cff`](../CITATION.cff). No manuscript citation is supplied here.

Likewise, citing a database documents provenance or an audited candidate
source. It does not state that the database is redistributed. The exact public
data boundary is documented in [`DATA_SOURCES.md`](DATA_SOURCES.md),
[`DATA_LICENSE.md`](../DATA_LICENSE.md), and
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

## Software release

Rosenn E. *Ketamine Historeceptomics*. Version 0.1.1. 2026.
[Repository](https://github.com/ericrosenn1/ketamine-historeceptomics).
BibTeX: `rosenn2026ketaminehistoreceptomics`. This is the software citation;
it does not assert or predict authorship of a scientific manuscript.

## Methodological basis

1. Shmelkov E, Grigoryan A, Swetnam J, Xin J, Tivon D, Shmelkov SV, Cardozo T.
   Historeceptomic fingerprints for drug-like compounds. *Frontiers in
   Physiology*. 2015;6:371.
   [doi:10.3389/fphys.2015.00371](https://doi.org/10.3389/fphys.2015.00371).
   BibTeX: `shmelkov2015historeceptomic`.
2. Cardozo T, Gupta P, Ni E, Young LM, Tivon D, Felsovalyi K. Data sources for
   in vivo molecular profiling of human phenotypes. *Wiley Interdisciplinary
   Reviews: Systems Biology and Medicine*. 2016;8(6):472–484.
   [doi:10.1002/wsbm.1354](https://doi.org/10.1002/wsbm.1354).
   BibTeX: `cardozo2016data`.
3. Cardozo T, Shmelkov E, Felsovalyi K, Swetnam J, Butler T, Malaspina D,
   Shmelkov SV. Chemistry-based molecular signature underlying the atypia of
   clozapine. *Translational Psychiatry*. 2017;7(2):e1036.
   [doi:10.1038/tp.2017.6](https://doi.org/10.1038/tp.2017.6).
   BibTeX: `cardozo2017clozapine`.
4. Kim EJ, Felsovalyi K, Young LM, Shmelkov SV, Grunebaum MF, Cardozo T.
   Molecular basis of atypicality of bupropion inferred from its receptor
   engagement in nervous system tissues. *Psychopharmacology*.
   2018;235(9):2643–2650.
   [doi:10.1007/s00213-018-4958-9](https://doi.org/10.1007/s00213-018-4958-9).
   BibTeX: `kim2018bupropion`.
5. Rosner B. Percentage points for a generalized ESD many-outlier procedure.
   *Technometrics*. 1983;25(2):165–172.
   [doi:10.1080/00401706.1983.10487848](https://doi.org/10.1080/00401706.1983.10487848).
   BibTeX: `rosner1983gesd`.

The first four papers provide historeceptomic and tissue-resolved receptor-
engagement context. Rosner is the statistical source for the generalized ESD
procedure. The repository's exact one-sided variant, finite-value rules,
candidate limit, thresholds, and tie handling remain implementation-specific
and are defined in [`METHODS.md`](METHODS.md).

## Database and expression-resource citations

- **ChEMBL:** Zdrazil B, et al. The ChEMBL Database in 2023: a drug discovery
  platform spanning multiple bioactivity data types and time periods. *Nucleic
  Acids Research*. 2024;52(D1):D1180–D1192.
  [doi:10.1093/nar/gkad1004](https://doi.org/10.1093/nar/gkad1004).
  Official resource: [ChEMBL](https://www.ebi.ac.uk/chembl/). BibTeX:
  `zdrazil2024chembl`.
- **PubChem:** Kim S, et al. PubChem 2025 update. *Nucleic Acids Research*.
  2025;53(D1):D1516–D1525.
  [doi:10.1093/nar/gkae1059](https://doi.org/10.1093/nar/gkae1059).
  Official [citation guidance](https://pubchem.ncbi.nlm.nih.gov/docs/citation-guidelines).
  BibTeX: `kim2025pubchem`.
- **PubChem BioAssay:** Wang Y, et al. PubChem BioAssay: 2017 update.
  *Nucleic Acids Research*. 2017;45(D1):D955–D963.
  [doi:10.1093/nar/gkw1118](https://doi.org/10.1093/nar/gkw1118).
  Official [BioAssay documentation](https://pubchem.ncbi.nlm.nih.gov/docs/bioassays).
  BibTeX: `wang2017pubchem_bioassay`.
- **BindingDB:** Liu T, et al. BindingDB in 2024: a FAIR knowledgebase of
  protein–small molecule binding data. *Nucleic Acids Research*.
  2025;53(D1):D1633–D1644.
  [doi:10.1093/nar/gkae1075](https://doi.org/10.1093/nar/gkae1075).
  Official [BindingDB information page](https://www.bindingdb.org/rwd/bind/info.jsp).
  BibTeX: `liu2025bindingdb`.
- **IUPHAR/BPS Guide to PHARMACOLOGY:** Harding SD, et al. The IUPHAR/BPS
  Guide to PHARMACOLOGY in 2026. *Nucleic Acids Research*.
  2026;54(D1):D1446–D1456.
  [doi:10.1093/nar/gkaf1067](https://doi.org/10.1093/nar/gkaf1067).
  Official [web-services and licensing page](https://www.guidetopharmacology.org/webServices.jsp).
  BibTeX: `harding2026gtopdb`.
- **NIMH Psychoactive Drug Screening Program (PDSP):** the live Ki Database
  asks users to cite Roth BL, Lopez E, Patel S, Kroeze WK. The multiplicity of
  serotonin receptors: uselessly diverse molecules or an embarrassment of
  riches? *The Neuroscientist*. 2000;6(4):252–262.
  [doi:10.1177/107385840000600408](https://doi.org/10.1177/107385840000600408).
  Official [PDSP Ki Database](https://pdsp.unc.edu/databases/kidb.php).
  BibTeX: `roth2000pdsp`.
- **BioGPS and the Human U133A/GNF1H Gene Atlas:** Su AI, et al. A gene atlas
  of the mouse and human protein-encoding transcriptomes. *PNAS*.
  2004;101(16):6062–6067.
  [doi:10.1073/pnas.0400782101](https://doi.org/10.1073/pnas.0400782101);
  Wu C, et al. BioGPS: an extensible and customizable portal for querying and
  organizing gene annotation resources. *Genome Biology*. 2009;10:R130.
  [doi:10.1186/gb-2009-10-11-r130](https://doi.org/10.1186/gb-2009-10-11-r130);
  Wu C, et al. BioGPS: building your own mash-up of gene annotations and
  expression profiles. *Nucleic Acids Research*. 2016;44(D1):D313–D316.
  [doi:10.1093/nar/gkv1104](https://doi.org/10.1093/nar/gkv1104).
  Official [BioGPS downloads](https://biogps.org/downloads/). BibTeX:
  `su2004geneatlas`, `wu2009biogps`, and `wu2016biogps`.
- **gcRMA preprocessing:** Wu Z, Irizarry RA, Gentleman R, Martinez-Murillo F,
  Spencer F. A model-based background adjustment for oligonucleotide
  expression arrays. *Journal of the American Statistical Association*.
  2004;99(468):909–917.
  [doi:10.1198/016214504000000683](https://doi.org/10.1198/016214504000000683).
  BibTeX: `wu2004gcrma`.
- **Therapeutic Target Database (TTD):** Zhang Y, et al. Therapeutic Target
  Database 2026: facilitating targeted therapies and precision medicine.
  *Nucleic Acids Research*. 2026;54(D1):D1692–D1701.
  [doi:10.1093/nar/gkaf1154](https://doi.org/10.1093/nar/gkaf1154).
  Official [TTD site](https://ttd.idrblab.net/). BibTeX: `zhang2026ttd`.

## Explicit manual-literature sources

These two publications are named explicitly because they contributed to the
historical manual-literature/provenance lane. No article text, PDF, or
publication-owned table is included in the public repository.

- Das J. Repurposing of drugs—the ketamine story. *Journal of Medicinal
  Chemistry*. 2020;63(22):13514–13525.
  [doi:10.1021/acs.jmedchem.0c01193](https://doi.org/10.1021/acs.jmedchem.0c01193).
  BibTeX: `das2020ketamine`.
- Sutherland JJ, Yonchev D, Fekete A, Urban L. A preclinical secondary
  pharmacology resource illuminates target–adverse drug reaction associations
  of marketed drugs. *Nature Communications*. 2023;14:4323.
  [doi:10.1038/s41467-023-40064-9](https://doi.org/10.1038/s41467-023-40064-9).
  BibTeX: `sutherland2023secondary`.

## Major scientific software

Exact versions are fixed in [`requirements-lock.txt`](../requirements-lock.txt).
Software remains subject to each upstream package's license.

| Package | Locked version | Primary citation |
|---|---:|---|
| NumPy | 2.5.1 | Harris CR, et al. *Nature*. 2020;585:357–362. [doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2); `harris2020numpy` |
| SciPy | 1.18.0 | Virtanen P, et al. *Nature Methods*. 2020;17:261–272. [doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2); `virtanen2020scipy` |
| pandas | 3.0.5 | McKinney W. *Proceedings of the 9th Python in Science Conference*. 2010:56–61. [doi:10.25080/Majora-92bf1922-00a](https://doi.org/10.25080/Majora-92bf1922-00a); software concept [doi:10.5281/zenodo.3509134](https://doi.org/10.5281/zenodo.3509134); `mckinney2010pandas`, `pandas305` |
| Matplotlib | 3.11.1 | Hunter JD. *Computing in Science & Engineering*. 2007;9(3):90–95. [doi:10.1109/MCSE.2007.55](https://doi.org/10.1109/MCSE.2007.55); `hunter2007matplotlib` |
| scikit-learn | 1.8.0 | Pedregosa F, et al. *Journal of Machine Learning Research*. 2011;12:2825–2830. [JMLR article](https://jmlr.org/papers/v12/pedregosa11a.html); `pedregosa2011scikitlearn` |
| PyArrow / Apache Arrow | 24.0.0 | [PyArrow 24.0.0 documentation](https://arrow.apache.org/docs/24.0/python/); `apachearrow2400` |

Other dependencies are pinned for reproducibility but are not listed here as
methodological citations. Their package metadata and upstream licenses remain
controlling.
