param([int]$Port = 8501, [switch]$Stop)

$ErrorActionPreference = "Stop"
if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    Write-Host "Tailscale is not installed. Install it from https://tailscale.com/download and sign in, then run this again."
    exit 1
}
if ($Stop) {
    tailscale funnel --https=443 off
    Write-Host "Public link turned off."
    exit 0
}
try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port" -TimeoutSec 5 | Out-Null }
catch { Write-Host "PERRY is not running on port $Port. Start it first with .\run.ps1 demo"; exit 1 }
try { $h = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 10 } catch { $h = $null }
if (-not $h -or -not $h.models.vision_available -or ($h.models.installed -contains "mock-ollama:stand-in")) {
    Write-Host "Warning: the real Ollama models are not running here, so visitors will see fallback answers." -ForegroundColor Yellow
}
tailscale funnel --bg $Port
Write-Host ""
tailscale funnel status
Write-Host "Share the https://...ts.net link above. Keep this laptop awake and online. Turn it off with: .\deploy\share.ps1 -Stop"
