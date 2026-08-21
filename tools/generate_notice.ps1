param (
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$Title,

    [string]$Message = "Notes for this release.",

    [string]$OutputDir
)

<#
Example Usage:
.\generate_notice.ps1 -Version "0.0.7"
.\generate_notice.ps1 -Version "0.0.7" -Title "QSnippet 0.0.7" -Message "- Added X`n- Fixed Y" -OutputDir ".\notices"
#>

$ErrorActionPreference = "Stop"

# Resolve output directory
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $workingDir = Get-Location
} else {
    $workingDir = Resolve-Path $OutputDir -ErrorAction SilentlyContinue
    if (-not $workingDir) {
        $workingDir = New-Item -ItemType Directory -Path $OutputDir -Force
    }
}

if ([string]::IsNullOrWhiteSpace($Title)) {
    $Title = "QSnippet $Version"
}

$fileName = "v$Version-notice.yaml"
$filePath = Join-Path $workingDir $fileName

if (Test-Path $filePath) {
    throw "Notice already exists: $filePath"
}

$indentedMessage = ($Message -split "`n" | ForEach-Object { "  $_" }) -join "`n"

$content = @"
id: "v$Version"
title: "$Title"
message: |
$indentedMessage
"@

$content | Set-Content -Path $filePath -Encoding UTF8
Write-Host "Created $fileName in $workingDir"
