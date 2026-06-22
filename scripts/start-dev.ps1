# start-dev.ps1 — open backend and frontend in separate terminals

$root    = $PSScriptRoot
$python  = "C:\Users\kimme\anaconda3\python.exe"
$nodeDir = "C:\Program Files\nodejs"

# Backend — FastAPI on port 8000
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Write-Host 'Backend starting on port 8000...' -ForegroundColor Cyan; " +
    "cd '$root'; " +
    "& '$python' -m uvicorn backend.main:app --reload --port 8000"
)

Start-Sleep -Milliseconds 800

# Frontend — Next.js on port 3001
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Write-Host 'Frontend starting on port 3001...' -ForegroundColor Green; " +
    "cd '$root\frontend'; " +
    '$env:PATH = $env:PATH + ";" + ' + "'$nodeDir'; " +
    "npm run dev -- -p 3001"
)

Write-Host ""
Write-Host "Started:" -ForegroundColor White
Write-Host "  Backend  -> http://127.0.0.1:8000/health" -ForegroundColor Cyan
Write-Host "  Frontend -> http://localhost:3001/coupon" -ForegroundColor Green
Write-Host ""
Write-Host "Close the two new terminal windows to stop the servers." -ForegroundColor DarkGray
