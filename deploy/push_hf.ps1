param([Parameter(Mandatory = $true)][string]$Space)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tmp = Join-Path $env:TEMP "perry-hf-space"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
New-Item -ItemType Directory $tmp | Out-Null

Push-Location $root
git archive HEAD | tar -x -C $tmp
Pop-Location

$header = @'
---
title: PERRY - Your Personal Health Assistant
emoji: 🩺
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

'@
$readme = Join-Path $tmp "README.md"
Set-Content -Path $readme -Value ($header + (Get-Content -Raw $readme)) -Encoding utf8

Push-Location $tmp
git init -q -b main
git add -A
git commit -q -m "PERRY cloud demo"
git push --force "https://huggingface.co/spaces/$Space" main
Pop-Location
Write-Host "Pushed. The Space builds in 10-20 minutes: https://huggingface.co/spaces/$Space"
