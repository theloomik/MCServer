<#
.SYNOPSIS
    Builds MCServer: icon conversion -> PyInstaller -> Inno Setup installer
.PARAMETER Version
    App version string (default: 1.0.0)
.EXAMPLE
    .\build.ps1
    .\build.ps1 -Version 1.2.0
#>
param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step([string]$msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Ok([string]$msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Fail([string]$msg) { Write-Host "    ERR $msg" -ForegroundColor Red; exit 1 }

# ── 0. Prerequisites ──────────────────────────────────────────────────────────
Step "Checking prerequisites"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail "Python not found in PATH" }
Ok "Python $(python --version)"

python -m pip show pyinstaller -q 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Installing pyinstaller..." -ForegroundColor Yellow
    python -m pip install pyinstaller -q
}
Ok "pyinstaller"

python -m pip show pillow -q 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Installing pillow..." -ForegroundColor Yellow
    python -m pip install pillow -q
}
Ok "pillow"

$ISSCPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$ISCC = $ISSCPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ISCC) { Fail "Inno Setup 6 not found. Install from https://jrsoftware.org/isdl.php" }
Ok "Inno Setup at $ISCC"

# ── 1. Convert icon.jpg -> icon.ico ──────────────────────────────────────────
Step "Converting icon.jpg to icon.ico"

$iconPy = @'
from PIL import Image
img = Image.open("icon.jpg").convert("RGBA")
img.save("icon.ico", format="ICO", sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
print("icon.ico written")
'@

$tmpPy = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), ".py")
Set-Content -Path $tmpPy -Value $iconPy -Encoding utf8
python $tmpPy
$iconExitCode = $LASTEXITCODE
Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue
if ($iconExitCode -ne 0) { Fail "Icon conversion failed" }
Ok "icon.ico created"

# ── 2. PyInstaller ────────────────────────────────────────────────────────────
Step "Building with PyInstaller (onedir mode)"

if (Test-Path "dist\MCServer") {
    Remove-Item -Recurse -Force "dist\MCServer"
    Write-Host "    Cleaned old dist\MCServer" -ForegroundColor DarkGray
}

python -m PyInstaller MCServer.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed (see output above)" }
if (-not (Test-Path "dist\MCServer\MCServer.exe")) { Fail "MCServer.exe missing from dist\MCServer" }
Ok "dist\MCServer\MCServer.exe ready"

# ── 3. Inno Setup ─────────────────────────────────────────────────────────────
Step "Compiling installer with Inno Setup (v$Version)"

New-Item -ItemType Directory -Force "dist\installer" | Out-Null
$env:APP_VERSION = $Version

& $ISCC "installer\setup.iss" "/DHAS_ICON"
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup compilation failed" }

$Installer = "dist\installer\MCServer_Setup_v$Version.exe"
if (-not (Test-Path $Installer)) { Fail "Installer not found: $Installer" }

$SizeMB = [Math]::Round((Get-Item $Installer).Length / 1MB, 1)

Write-Host "`n=== Build complete ===" -ForegroundColor Green
Write-Host "    $Installer  ($SizeMB MB)" -ForegroundColor White
