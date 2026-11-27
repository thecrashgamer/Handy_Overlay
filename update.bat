@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden. Bitte zuerst start.bat ausfuehren oder Python installieren.
  pause
  exit /b 1
)
python update.py %*
echo.
pause
