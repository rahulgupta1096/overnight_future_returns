@echo off
cd /d "%~dp0"
python overnight_returns.py futures_input.csv --email rahulgupta1096@gmail.com
python overnight_returns.py futures_input.csv --email dianabgriffin11@gmail.com
pause
