$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location "C:\Users\RIDGE\MARS-QUANT"
python ground_truth.py