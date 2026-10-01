param(
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$PlatformioCore
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = (Resolve-Path -LiteralPath (Join-Path $projectRoot '.build')).Path
$coreRoot = (Resolve-Path -LiteralPath $PlatformioCore).Path
if ((Test-Path 'Q:\') -or (Test-Path 'R:\')) { throw 'Q: and R: must be unused for short build paths.' }
$oldCore = $env:PLATFORMIO_CORE_DIR
$mappedProject = $false
$mappedCore = $false
try {
    subst Q: $buildRoot
    if ($LASTEXITCODE) { throw 'Cannot map project drive.' }
    $mappedProject = $true
    subst R: $coreRoot
    if ($LASTEXITCODE) { throw 'Cannot map toolchain drive.' }
    $mappedCore = $true
    $env:PLATFORMIO_CORE_DIR = 'R:\'
    & $Python -m platformio run --project-dir Q:\firmware -e tbeam-s3-core -j 12 *> (Join-Path $buildRoot 'firmware-build.log')
    if ($LASTEXITCODE) { throw "Build failed; inspect .build/firmware-build.log (exit $LASTEXITCODE)." }
    $binary = Join-Path $buildRoot 'firmware/.pio/build/tbeam-s3-core/firmware-tbeam-s3-core-2.7.26.bin'
    $bytes = (Get-Item -LiteralPath $binary).Length
    $budget = 0x250000
    Write-Output "App bytes: $bytes; historical partition budget: $budget; remaining: $($budget - $bytes)"
    if ($bytes -gt $budget) { throw 'App exceeds the historical device partition. Do not flash.' }
    Get-FileHash -LiteralPath $binary -Algorithm SHA256
} finally {
    $env:PLATFORMIO_CORE_DIR = $oldCore
    if ($mappedCore) { subst R: /D }
    if ($mappedProject) { subst Q: /D }
}
