$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'dist/index.html'))) {
    throw 'Run pnpm build before starting the production preview.'
}
Write-Host 'Production preview: http://127.0.0.1:8080 (Ctrl+C stops it)'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m backend.serve
