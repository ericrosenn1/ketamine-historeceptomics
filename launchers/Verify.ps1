<#
.SYNOPSIS
Runs complete verification from the governed external authority tree.

.DESCRIPTION
Delegates to Run.ps1 in Verify mode and requires the 20 excluded inputs to be
supplied in a directory mirroring data/frozen. The Python lane validates every
file against EXTERNAL_INPUT_MANIFEST.tsv before numerical work.

.PARAMETER ExternalInputRoot
Directory mirroring data/frozen and containing all 20 manifest-listed inputs.

.PARAMETER OutputDir
Optional destination for Verify outputs.

.PARAMETER OpenOutput
Opens the completed output directory after success.

.EXAMPLE
.\Verify.ps1 -ExternalInputRoot 'D:\cardozo-inputs\data-frozen' -OpenOutput

.INPUTS
None. This script does not accept pipeline input.

.OUTPUTS
Writes regenerated analyses, regression QA, MANIFEST.tsv, and task_state.json.

.NOTES
SPDX-License-Identifier: MIT. Verify is not self-contained because governed near-source inputs are not redistributed.
#>
# SPDX-License-Identifier: MIT

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExternalInputRoot,
    [string]$OutputDir,
    [switch]$OpenOutput
)
& (Join-Path $PSScriptRoot 'Run.ps1') -Mode Verify -ExternalInputRoot $ExternalInputRoot -OutputDir $OutputDir -OpenOutput:$OpenOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
