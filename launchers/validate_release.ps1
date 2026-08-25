<#
.SYNOPSIS
Runs the release-validation alias for the external-input Verify lane.

.DESCRIPTION
Forwards to run_reproduction.ps1 in Verify mode. A manifest-valid external
directory is mandatory because the 20 governed scientific inputs are not
redistributed in the public repository.

.PARAMETER ExternalInputRoot
Directory mirroring data/frozen and containing all 20 files in EXTERNAL_INPUT_MANIFEST.tsv.

.PARAMETER OutputDir
Optional destination for validation outputs.

.PARAMETER OpenOutput
Opens the completed output directory after success.

.EXAMPLE
.\validate_release.ps1 -ExternalInputRoot 'D:\cardozo-inputs\data-frozen'

.INPUTS
None. This script does not accept pipeline input.

.OUTPUTS
Writes the Verify output tree and forwards its concise terminal validation summary.

.NOTES
SPDX-License-Identifier: MIT. This alias retains strict Verify failure semantics.
#>
# SPDX-License-Identifier: MIT

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExternalInputRoot,
    [string]$OutputDir,
    [switch]$OpenOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$parameters = @{
    Mode = 'Verify'
    ExternalInputRoot = $ExternalInputRoot
    OpenOutput = $OpenOutput
}
if ($OutputDir) { $parameters.OutputDir = $OutputDir }
& (Join-Path $PSScriptRoot 'run_reproduction.ps1') @parameters
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
