$env:PYTHONIOENCODING = 'utf-8'
$ErrorActionPreference = 'Stop'
Set-Location "C:\Users\RIDGE\MARS-QUANT"

$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$out    = "C:\Users\RIDGE\MARS-QUANT\dashboard_screenshot.png"
$url    = "http://localhost:8765"

# Kill any prior chrome instances to keep output clean
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Streamlit renders via WebSocket after initial load — wait long enough for content
# Use Chrome DevTools Protocol to wait for network idle
& $chrome `
    --headless=new `
    --disable-gpu `
    --no-sandbox `
    --hide-scrollbars `
    --window-size=1600,4500 `
    --virtual-time-budget=60000 `
    --run-all-compositor-stages-before-draw `
    --disable-features=Translate `
    --screenshot=$out `
    $url

Write-Host "Done"
Get-ChildItem $out -ErrorAction SilentlyContinue | Select-Object FullName, Length, LastWriteTime