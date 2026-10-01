param([Parameter(Mandatory)][string]$VcVars)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ($VcVars -match '["\r\n%]') { throw 'Unsupported vcvars path characters.' }
$vcPath = (Resolve-Path -LiteralPath $VcVars).Path
$batchPath = Join-Path $root '.build/test-native.cmd'
$oldHarness = $env:USF_BRIDGE_HARNESS
@"
@echo off
call "$vcPath" >nul
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /I .build\firmware\src\mesh tests\native\bridge_harness.cpp .build\firmware\src\mesh\UsbSfBridge.cpp /Fe:.build\bridge_harness.exe /Fo:.build\
"@ | Set-Content -LiteralPath $batchPath
Push-Location -LiteralPath $root
try {
    & $batchPath
    if ($LASTEXITCODE) { throw 'C++ harness compilation failed.' }
    $env:USF_BRIDGE_HARNESS = Join-Path $root '.build/bridge_harness.exe'
    & .venv/Scripts/python.exe -m pytest -q
    if ($LASTEXITCODE) { throw 'Offline tests failed.' }
} finally {
    $env:USF_BRIDGE_HARNESS = $oldHarness
    Pop-Location
}
