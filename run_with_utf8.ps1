$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$out = "C:\Users\RIDGE\MARS-QUANT\live_session_$(Get-Date -Format yyyyMMdd_HHmmss).log"
Set-Location "C:\Users\RIDGE\MARS-QUANT"
python run_session_v3.py --duration 5 --symbols XAUUSDm 2>&1 | Tee-Object -FilePath $out
Write-Host "Log saved to: $out"