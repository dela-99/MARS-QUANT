@echo off
call C:\Users\mecha\anaconda3\Scripts\activate.bat
call conda activate trade_env
cd /d C:\Users\mecha\Documents\revision\trade\Quantitative-XAUUSD-Strategy\src\bots
python hyp_a_xgb_trading_bot_v1_paper.py
pause