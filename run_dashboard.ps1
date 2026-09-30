$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location "C:\Users\RIDGE\MARS-QUANT"
streamlit run dashboard.py --server.headless true --server.port 8765 --browser.gatherUsageStats false