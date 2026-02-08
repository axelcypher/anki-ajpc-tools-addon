$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $root "restart_helper.cs"
$out = Join-Path $root "ajpc_restart_helper.exe"
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not (Test-Path $csc)) {
  $csc = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
}
if (-not (Test-Path $csc)) {
  throw "csc.exe not found in .NET Framework directories."
}
if (-not (Test-Path $src)) {
  throw "Source file not found: $src"
}

& $csc `
  /nologo `
  /optimize+ `
  /target:winexe `
  /platform:anycpu `
  /out:$out `
  $src

if (-not (Test-Path $out)) {
  throw "Build failed: $out was not created."
}

Write-Host "Built native helper:" $out
