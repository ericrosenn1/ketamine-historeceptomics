<#
.SYNOPSIS
Runs the governed Full recovery and downstream verification lane.

.DESCRIPTION
Requires the recovered-stage activity, PDSP, project, and 20-file external
authority inputs, then delegates to Run.ps1. The lane writes derivative outputs
only and retains provenance-gated reuse and strict failure behavior.

.PARAMETER InitialActivityTable
Path to the governed initial activity assertion table.

.PARAMETER PdspWorkbook
Path to the governed PDSP Ki workbook.

.PARAMETER ProjectRoot
Path to the external historical project directory used by recovered stages.

.PARAMETER ExternalInputRoot
Directory mirroring data/frozen and containing all 20 files in EXTERNAL_INPUT_MANIFEST.tsv.

.PARAMETER ExpressionAuthority
Optional explicit directory containing the expression authority.

.PARAMETER OutputDir
Optional destination for Full-mode derivative outputs.

.PARAMETER OpenOutput
Opens the completed output directory after success.

.EXAMPLE
.\Full.ps1 -InitialActivityTable 'D:\inputs\activity.csv' -PdspWorkbook 'D:\inputs\pdsp.xlsx' -ProjectRoot 'D:\cardozo-project' -ExternalInputRoot 'D:\cardozo-inputs\data-frozen'

.INPUTS
None. This script does not accept pipeline input.

.OUTPUTS
Writes the Full-mode output tree, combined QA summary, manifest, and task state.

.NOTES
SPDX-License-Identifier: MIT. Full is not self-contained because governed source inputs are not redistributed.
#>
# SPDX-License-Identifier: MIT

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InitialActivityTable,
    [Parameter(Mandatory = $true)][string]$PdspWorkbook,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$ExternalInputRoot,
    [string]$ExpressionAuthority,
    [string]$OutputDir,
    [switch]$OpenOutput
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$parameters = @{
    Mode = 'Full'
    InitialActivityTable = $InitialActivityTable
    PdspWorkbook = $PdspWorkbook
    ProjectRoot = $ProjectRoot
    ExternalInputRoot = $ExternalInputRoot
    OpenOutput = $OpenOutput
}
if ($OutputDir) { $parameters.OutputDir = $OutputDir }
if ($ExpressionAuthority) { $parameters.ExpressionAuthority = $ExpressionAuthority }
& (Join-Path $PSScriptRoot 'Run.ps1') @parameters
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
