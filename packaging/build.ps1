<#
Build the Windows installer locally.
  .\packaging\build.ps1            # PyInstaller folder build, then installer if Inno Setup is installed
Requires: pip install -r requirements.txt -r requirements-build.txt
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$version = (python -c "import sys; sys.path.insert(0,'src'); import immersion_app; print(immersion_app.__version__)").Trim()
Write-Host "Building Language Immersion Tools $version"

python -m PyInstaller packaging/immersion.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (Test-Path $iscc) {
    & $iscc "/DAppVersion=$version" packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer: dist\LanguageImmersionTools-Setup-$version.exe"
} else {
    Write-Host "Inno Setup not found; skipped installer. Folder build is in dist\LanguageImmersionTools"
}
