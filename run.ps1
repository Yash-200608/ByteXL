param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "mock", "api", "ui", "test", "eval", "seed", "demo", "stop")]
    [string]$Task = "demo",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Start-Window($Title, $Arguments) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='$Title'; `$env:PYTHONUTF8='1'; Set-Location '$PSScriptRoot'; & '$Py' $Arguments"
}

switch ($Task) {
    "setup" {
        if (-not (Test-Path $Py)) { py -3.11 -m venv .venv }
        & $Py -m pip install --upgrade pip
        & $Py -m pip install -r requirements.txt
        if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
    }
    "mock" { & $Py scripts/mock_ollama.py @Rest }
    "api" { & $Py -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 @Rest }
    "ui" { & $Py -m streamlit run ui/app.py --server.port 8501 @Rest }
    "test" { & $Py -m pytest -q @Rest }
    "eval" { & $Py scripts/eval.py @Rest }
    "seed" { & $Py scripts/seed.py @Rest }
    "demo" {
        $ollama = $false
        try { $ollama = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://localhost:11434/api/tags).StatusCode -eq 200 } catch {}
        if (-not $ollama) { Start-Window "ByteXL mock Ollama" "scripts/mock_ollama.py" }
        Start-Window "ByteXL API" "-m uvicorn app.api.main:app --host 127.0.0.1 --port 8000"
        Start-Window "ByteXL UI" "-m streamlit run ui/app.py --server.port 8501"
        Write-Host "Started. Open http://localhost:8501 (Ollama: $(if ($ollama) {'real'} else {'MOCK stand-in'}))"
    }
    "stop" {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { $_.CommandLine -match "mock_ollama|uvicorn app.api.main|streamlit run ui/app.py" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    }
}
