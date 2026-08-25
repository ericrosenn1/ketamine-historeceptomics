<#
.SYNOPSIS
Runs the self-contained public Smoke lane.

.DESCRIPTION
Delegates to Run.ps1 in Smoke mode. The lane uses synthetic fixtures and
retained public reference metadata; it does not require excluded scientific inputs.

.PARAMETER OutputDir
Optional destination for Smoke outputs.

.PARAMETER OpenOutput
Opens the completed output directory after success.

.EXAMPLE
.\Smoke.ps1 -OpenOutput

.INPUTS
None. This script does not accept pipeline input.

.OUTPUTS
Writes synthetic Smoke analyses, QA_SUMMARY.csv, MANIFEST.tsv, and task_state.json.

.NOTES
SPDX-License-Identifier: MIT. This is the release's self-contained public execution lane.
#>
# SPDX-License-Identifier: MIT

[CmdletBinding()]
param([string]$OutputDir, [switch]$OpenOutput)
& (Join-Path $PSScriptRoot 'Run.ps1') -Mode Smoke -OutputDir $OutputDir -OpenOutput:$OpenOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
