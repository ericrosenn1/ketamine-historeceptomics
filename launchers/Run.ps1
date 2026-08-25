<#
.SYNOPSIS
Runs a Cardozo ketamine historeceptomics Smoke, Verify, or Full lane.

.DESCRIPTION
Selects Python, fixes numerical libraries to one thread, performs dependency
preflight checks, and invokes the portable workflow. Smoke is self-contained.
Verify and Full require a manifest-valid external directory mirroring the
redistribution-excluded data/frozen tree.

.PARAMETER Mode
Execution lane: Smoke, Verify, or Full. The default is Verify.

.PARAMETER OutputDir
Optional output directory. A timestamped results/runs directory is used when omitted.

.PARAMETER InitialActivityTable
Governed initial activity assertion table required by Full mode.

.PARAMETER PdspWorkbook
Governed PDSP Ki workbook required by Full mode.

.PARAMETER ProjectRoot
External historical project directory required by Full mode.

.PARAMETER ExpressionAuthority
Optional explicit expression-authority directory for Full mode.

.PARAMETER ExternalInputRoot
Directory mirroring data/frozen and containing the 20 files in
EXTERNAL_INPUT_MANIFEST.tsv. Required by Verify and Full modes.

.PARAMETER OpenOutput
Opens the completed output directory after a successful run.

.EXAMPLE
.\Run.ps1 -Mode Smoke -OpenOutput

.EXAMPLE
.\Run.ps1 -Mode Verify -ExternalInputRoot 'D:\cardozo-inputs\data-frozen'

.INPUTS
None. This script does not accept pipeline input.

.OUTPUTS
Writes a mode-specific output tree, task_state.json, QA summaries, and a concise terminal summary.

.NOTES
SPDX-License-Identifier: MIT. Verify and Full are external-input lanes; Smoke is the public self-contained lane.
#>
# SPDX-License-Identifier: MIT

[CmdletBinding()]
param(
    [ValidateSet('Smoke', 'Verify', 'Full')]
    [string]$Mode = 'Verify',
    [string]$OutputDir,
    [string]$InitialActivityTable,
    [string]$PdspWorkbook,
    [string]$ProjectRoot,
    [string]$ExpressionAuthority,
    [string]$ExternalInputRoot,
    [switch]$OpenOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPrefix = @()
if ($env:CARDOZO_HR_PYTHON) {
    $python = $env:CARDOZO_HR_PYTHON
} elseif (Test-Path (Join-Path $repoRoot '.venv\Scripts\python.exe')) {
    $python = Join-Path $repoRoot '.venv\Scripts\python.exe'
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = 'py'
    $pythonPrefix = @('-3.12')
} else {
    $python = 'python'
}
if (-not $OutputDir) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $OutputDir = Join-Path $repoRoot "results\runs\$($Mode.ToLower())_$stamp"
}

$env:PYTHONPATH = Join-Path $repoRoot 'src'
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$arguments = @('-m', 'cardozo_ketamine_hr.portable', '--mode', $Mode, '--output-dir', $OutputDir)
if ($InitialActivityTable) { $arguments += @('--initial-activity-table', $InitialActivityTable) }
if ($PdspWorkbook) { $arguments += @('--pdsp-workbook', $PdspWorkbook) }
if ($ProjectRoot) { $arguments += @('--project-root', $ProjectRoot) }
if ($ExpressionAuthority) { $arguments += @('--expression-authority', $ExpressionAuthority) }
if ($ExternalInputRoot) { $arguments += @('--external-input-root', $ExternalInputRoot) }

Write-Host "Cardozo ketamine historeceptomics: $Mode"
Write-Host "Python: $python"
Write-Host "PowerShell: $($PSVersionTable.PSVersion)"
Write-Host "Output: $OutputDir"
if ($ExternalInputRoot) { Write-Host "External inputs: $ExternalInputRoot" }
try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git is required but was not found on PATH.'
    }
    if ($Mode -eq 'Full') {
        if (-not $InitialActivityTable -or -not (Test-Path -LiteralPath $InitialActivityTable -PathType Leaf)) {
            throw 'Full requires an existing -InitialActivityTable file.'
        }
        if (-not $PdspWorkbook -or -not (Test-Path -LiteralPath $PdspWorkbook -PathType Leaf)) {
            throw 'Full requires an existing -PdspWorkbook file.'
        }
        if (-not $ProjectRoot -or -not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
            throw 'Full requires an existing -ProjectRoot directory containing the versioned external inputs.'
        }
        if ($ExpressionAuthority -and -not (Test-Path -LiteralPath $ExpressionAuthority -PathType Container)) {
            throw '-ExpressionAuthority must be an existing directory when supplied.'
        }
    }
    if ($Mode -in @('Verify', 'Full')) {
        if (-not $ExternalInputRoot -or -not (Test-Path -LiteralPath $ExternalInputRoot -PathType Container)) {
            throw "$Mode requires an existing -ExternalInputRoot directory mirroring data/frozen."
        }
    }
    & git --version
    if ($LASTEXITCODE -ne 0) { throw 'git --version failed.' }
    & $python @pythonPrefix -c 'import joblib, matplotlib, numpy, openpyxl, pandas, PIL, psutil, pyarrow, pypdf, scipy, sklearn, yaml; print("Python dependency preflight: PASS")'
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency preflight failed.' }
    & $python @pythonPrefix @arguments
    if ($LASTEXITCODE -ne 0) { throw "$Mode returned exit code $LASTEXITCODE." }
} catch {
    Write-Host 'FAILED STAGE: portable reproduction' -ForegroundColor Red
    Write-Host "COMMAND: $python $($arguments -join ' ')" -ForegroundColor Red
    $inputPath = if ($ExternalInputRoot) { $ExternalInputRoot } else { Join-Path $repoRoot 'data\fixtures' }
    Write-Host "INPUT PATH: $inputPath" -ForegroundColor Red
    Write-Host "OUTPUT PATH: $OutputDir" -ForegroundColor Red
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "RECOVERY ACTION: inspect $OutputDir\task_state.json and the mode-specific QA CSV files; correct the reported cause, then rerun this command." -ForegroundColor Red
    exit 1
}

Write-Host "PASS: $Mode completed"
Write-Host "State: $OutputDir\task_state.json"
Write-Host "Manifest: $OutputDir\MANIFEST.tsv"
if ($OpenOutput) { Invoke-Item -LiteralPath $OutputDir }
