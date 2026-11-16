@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py
    exit /b
)
where py >nul 2>nul
if %errorlevel%==0 (
    start "" pyw main.py
    exit /b
)
python main.py
pause