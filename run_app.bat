@echo off
rem Launch CUCM MACD Tool (no console window).
rem Uses the REAL Python directly, because the bare "pythonw" on PATH is the
rem Microsoft Store stub ("Python was not found") which shadows the real one.
cd /d "%~dp0"

set "PYW=%LocalAppData%\Python\bin\pythonw.exe"
if exist "%PYW%" goto run
set "PYW=%LocalAppData%\Python\pythoncore-3.14-64\pythonw.exe"
if exist "%PYW%" goto run
start "" pyw "%~dp0macd_app.py"
exit /b

:run
start "" "%PYW%" "%~dp0macd_app.py"
