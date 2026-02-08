$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $root "restart_helper.py"
$dist = $root
$build = Join-Path $root "build"
$spec = $root

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --noconsole `
  --name "ajpc_restart_helper" `
  --distpath $dist `
  --workpath $build `
  --specpath $spec `
  $src

if (Test-Path $build) { Remove-Item -Recurse -Force $build }
$specFile = Join-Path $root "ajpc_restart_helper.spec"
if (Test-Path $specFile) { Remove-Item -Force $specFile }

Write-Host "Built:" (Join-Path $root "ajpc_restart_helper.exe")
