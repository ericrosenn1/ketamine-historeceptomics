# Synthetic historeceptomics demonstration

[Historeceptomics_Quickstart.ipynb](Historeceptomics_Quickstart.ipynb) explains
expression standardization, activity × expression HR scores, one-sided GESD
fingerprints, missing support, and fingerprint comparison. The saved outputs
were executed with Python 3.12 and the repository's scientific implementation.
All numbers are invented; this notebook is not a scientific result.

From a clean clone, run in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt -r requirements-notebook.txt
if ($LASTEXITCODE -ne 0) { throw 'Notebook dependency installation failed' }
.\.venv\Scripts\python.exe notebooks\execute.py
if ($LASTEXITCODE -ne 0) { throw 'Notebook execution failed' }
```

The runner uses the same interpreter as the command, creates a temporary kernel
specification, fails on any cell error, checks for a saved figure, and writes an
executed copy to `results/runs/Historeceptomics_Quickstart.executed.ipynb`.
Pass `--output` to choose a different destination. Source fixtures and the tracked
notebook are unchanged by the default command. No inputs are downloaded during
execution. Installing an interactive notebook UI is optional.

`fixtures/activity.csv` contains two fictional profiles and four fictional
targets. `fixtures/expression.csv` contains four fictional genes across 32
fictional tissues. The values were authored for teaching, without copying any
private project data or published measurements. The missing activity is
deliberate. Source code and prose are MIT; fixtures and embedded synthetic data
outputs use CC BY-SA 4.0 as described in [DATA_LICENSE.md](../DATA_LICENSE.md).

Full scientific reproduction is documented in the
[reproducibility guide](../docs/REPRODUCIBILITY.md).
