$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run the dependency setup in README.md first.' }
$taskPnpm = (Get-Command pnpm -ErrorAction Stop).Source
$taskBackend = Start-Process -FilePath $taskPython -ArgumentList @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
try {
    Write-Host 'Broadcast Copilot: http://127.0.0.1:5173'
    Write-Host 'Press Ctrl+C to stop both services.'
    & $taskPnpm dev
} finally {
    if (-not $taskBackend.HasExited) { Stop-Process -Id $taskBackend.Id }
}
