<#
.SYNOPSIS
Provides the stable public entry point for repository reproduction lanes.

.DESCRIPTION
Forwards explicitly supplied parameters to Run.ps1, which performs strict
preflight, execution, validation, and terminal reporting. Verify and Full must
receive a directory mirroring the excluded data/frozen input tree.

.PARAMETER Mode
Execution lane: Smoke, Verify, or Full. The default is Verify.

.PARAMETER OutputDir
Optional destination for generated outputs.

.PARAMETER InitialActivityTable
Governed initial activity assertion table required by Full mode.

.PARAMETER PdspWorkbook
Governed PDSP Ki workbook required by Full mode.

.PARAMETER ProjectRoot
External historical project directory required by Full mode.

.PARAMETER ExpressionAuthority
Optional explicit expression-authority directory for Full mode.

.PARAMETER ExternalInputRoot
Directory mirroring data/frozen and containing all 20 manifest-listed excluded inputs; required by Verify and Full.

.PARAMETER OpenOutput
Opens the completed output directory after success.

.EXAMPLE
.\run_reproduction.ps1 -Mode Smoke

.EXAMPLE
.\run_reproduction.ps1 -Mode Verify -ExternalInputRoot 'D:\cardozo-inputs\data-frozen' -OpenOutput

.INPUTS
None. This script does not accept pipeline input.

.OUTPUTS
Forwards Run.ps1 terminal output and writes the selected lane's validated output tree.

.NOTES
SPDX-License-Identifier: MIT. Run.ps1 enforces all mode-specific required inputs.
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
& (Join-Path $PSScriptRoot 'Run.ps1') @PSBoundParameters
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
