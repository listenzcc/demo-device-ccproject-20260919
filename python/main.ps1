param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw "Python was not found on PATH. Install Python 3 and try again."
}

if ($Python.Name -eq "py.exe") {
    & $Python.Source -3 (Join-Path $PSScriptRoot "main.py") --host $HostAddress --port $Port
} else {
    & $Python.Source (Join-Path $PSScriptRoot "main.py") --host $HostAddress --port $Port
}
exit $LASTEXITCODE