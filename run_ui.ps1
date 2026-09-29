$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Set up .venv using the steps in README.md first.'
}
& $projectPython -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --server.headless true
