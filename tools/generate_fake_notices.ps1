param (
    [Parameter(Mandatory = $true)]
    [DateTime]$StartDate,

    [Parameter(Mandatory = $true)]
    [DateTime]$EndDate,

    [int]$MaxFiles = 30,

    [string]$OutputDir
)

<# 
Example Usage:
.\generate_fake_notices.ps1 -StartDate "2025-12-01" -EndDate "2025-12-30"
.\generate_fake_notices.ps1 -StartDate "2025-12-01" -EndDate "2025-12-30" -OutputDir ".\notices"
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

$count = 0
$current = $StartDate

while ($current -le $EndDate -and $count -lt $MaxFiles) {

    $mm   = $current.ToString("MM")
    $dd   = $current.ToString("dd")
    $yyyy = $current.ToString("yyyy")

    $fileName = "$mm-$dd-$yyyy-notice.yaml"
    $filePath = Join-Path $workingDir $fileName

    if (-not (Test-Path $filePath)) {
        $content = @"
id: "notice-$yyyy-$mm-$dd"
title: "QSnippet Updates - $mm/$dd/$yyyy"
message: |
  Test notice generated for $mm/$dd/$yyyy
"@

        $content | Set-Content -Path $filePath -Encoding UTF8
        Write-Host "Created $fileName"
        $count++
    }

    $current = $current.AddDays(1)
}

Write-Host "Done. Generated $count notice files in $workingDir"