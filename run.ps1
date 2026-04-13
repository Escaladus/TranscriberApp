$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonPath)) {
    Write-Error "Python virtual environment not found at $pythonPath"
    exit 1
}

$serverCommand = "Set-Location '$projectRoot'; & '$pythonPath' -m uvicorn app:app --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $serverCommand

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8000"
