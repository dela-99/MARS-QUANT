$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location "C:\Users\RIDGE\MARS-QUANT"
$out = "C:\Users\RIDGE\MARS-QUANT\sizer_fix_session.log"
python run_session_v3.py --duration 1 --symbols XAUUSDm,EURUSDm,USDJPYm 2>&1 | Tee-Object -FilePath $out