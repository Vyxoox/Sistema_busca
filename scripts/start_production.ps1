$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "app.log"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not $env:PORT) {
    $env:PORT = "8080"
}

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting SistemaBusca on port $env:PORT" | Out-File -FilePath $LogFile -Append -Encoding utf8
& $Python app.py *>> $LogFile
exit $LASTEXITCODE
