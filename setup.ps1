# Setup grok-suite (Windows PowerShell)
#   PowerShell:  .\setup.ps1
#   kalau diblokir: powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe -m patchright install chromium
.venv\Scripts\python.exe -m camoufox fetch

Write-Host ""
Write-Host "Selesai. Contoh:"
Write-Host "  .venv\Scripts\python.exe grok.py harvest"
