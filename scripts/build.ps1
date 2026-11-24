# Build the portable CamDesk app with Nuitka.
#
#   .\scripts\build.ps1            -> dist\CamDesk\CamDesk.exe (folder build: fast start, no unpacking)
#   .\scripts\build.ps1 -Zip       -> also dist\CamDesk-<version>-win64.zip
#   .\scripts\build.ps1 -Installer -> also dist\CamDesk-Setup-<version>.exe (install wizard)
#   .\scripts\build.ps1 -Installer -SkipBuild   -> only re-pack the existing dist\CamDesk
#
# Needs: uv, and a C compiler (Visual Studio Build Tools with C++; Nuitka finds it).
# -Installer also needs Inno Setup 6 (winget install JRSoftware.InnoSetup).
# The first build compiles everything and takes a while; later builds reuse Nuitka's cache.
param([switch]$Zip, [switch]$Installer, [switch]$SkipBuild)

# "Continue", not "Stop": Nuitka prints progress on stderr, and Windows PowerShell 5.1 turns
# any stderr line from a native program into a terminating error under "Stop" (the first build
# "failed" that way after Nuitka had actually finished). Success is checked via $LASTEXITCODE.
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

$version = (Select-String -Path "src\camdesk\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
if ($SkipBuild) {
    if (-not (Test-Path dist\CamDesk\CamDesk.exe)) { throw "-SkipBuild: dist\CamDesk\CamDesk.exe not found" }
    Write-Host "Skipping the Nuitka build; packaging the existing dist\CamDesk ..."
} else {
Write-Host "Building CamDesk $version ..."

uv run python -m nuitka `
    --standalone `
    --assume-yes-for-downloads `
    --msvc=latest `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --windows-icon-from-ico=src\camdesk\resources\app.ico `
    --include-package=camdesk `
    --include-package-data=camdesk `
    --include-package=av `
    --include-module=keyring.backends.Windows `
    --nofollow-import-to=pytest `
    --nofollow-import-to=tests `
    --product-name=CamDesk `
    --file-description="CamDesk - IP Webcam desktop controller" `
    --product-version=$version `
    --file-version=$version `
    --output-dir=dist `
    --output-filename=CamDesk.exe `
    --remove-output `
    scripts\camdesk_entry.py
if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed ($LASTEXITCODE)" }

# Nuitka names the folder after the entry script; give it a friendly name.
if (Test-Path dist\CamDesk) { Remove-Item -Recurse -Force dist\CamDesk }
Rename-Item dist\camdesk_entry.dist CamDesk

$size = (Get-ChildItem -Recurse dist\CamDesk | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Built dist\CamDesk\CamDesk.exe  ({0:N0} MB folder)" -f $size)

# Smoke test the packaged app (fake camera, own temp data folder): starts, shows video,
# saves a snapshot, exits cleanly. Catches modules Nuitka missed, like av._cyutil once was.
$smokeHome = Join-Path $env:TEMP "camdesk-build-smoke"
if (Test-Path $smokeHome) { Remove-Item -Recurse -Force $smokeHome }
$env:CAMDESK_HOME = $smokeHome
$proc = Start-Process -FilePath dist\CamDesk\CamDesk.exe -ArgumentList "--fake", "--smoke-test" -PassThru -Wait
Remove-Item Env:\CAMDESK_HOME
$smokeLog = Join-Path $smokeHome "appdata\logs\camdesk.log"
if ($proc.ExitCode -ne 0) {
    if (Test-Path $smokeLog) { Get-Content $smokeLog -Tail 20 }
    throw "Smoke test FAILED (exit $($proc.ExitCode)) - see the log above"
}
Write-Host "Smoke test passed (fake camera: video + snapshot)"
Remove-Item -Recurse -Force $smokeHome
}

if ($Installer) {
    $iscc = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 not found - run: winget install JRSoftware.InnoSetup" }
    & $iscc /Q "/DAppVersion=$version" scripts\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed ($LASTEXITCODE)" }
    $setup = "dist\CamDesk-Setup-$version.exe"
    Write-Host ("Installer: {0}  ({1:N0} MB)" -f $setup, ((Get-Item $setup).Length / 1MB))
}

if ($Zip) {
    $zipPath = "dist\CamDesk-$version-win64.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath }
    Compress-Archive -Path dist\CamDesk -DestinationPath $zipPath
    Write-Host ("Zipped: {0}  ({1:N0} MB)" -f $zipPath, ((Get-Item $zipPath).Length / 1MB))
}
