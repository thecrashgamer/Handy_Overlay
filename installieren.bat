@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Phonebox: alles installieren ===
echo.

rem --- 1. Python pruefen (der Windows-Store-Platzhalter zaehlt nicht) ---
python --version >nul 2>nul
if not errorlevel 1 goto python_ok

echo Python wurde nicht gefunden. Installiere Python 3.12 ...
where winget >nul 2>nul
if errorlevel 1 (
  echo.
  echo winget ist nicht verfuegbar. Bitte Python von https://www.python.org/downloads/ installieren
  echo und dabei "Add python.exe to PATH" anhaken. Danach diese Datei erneut starten.
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo Die Python-Installation ist fehlgeschlagen.
  pause
  exit /b 1
)

rem --- PATH in dieser Sitzung aktualisieren ---
for /f "delims=" %%p in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')"') do set "PATH=%%p;%PATH%"

python --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python ist installiert, wird aber in diesem Fenster noch nicht gefunden.
  echo Bitte dieses Fenster schliessen und installieren.bat noch einmal starten.
  pause
  exit /b 1
)

:python_ok
for /f "delims=" %%v in ('python --version') do echo Gefunden: %%v
echo.

rem --- 2. pip aktualisieren und Pakete installieren ---
echo Aktualisiere pip ...
python -m pip install --upgrade pip
echo.
echo Installiere Pakete aus requirements.txt ...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Die Installation der Pakete ist fehlgeschlagen.
  pause
  exit /b 1
)

rem --- 3. Autostart einrichten und Server starten ---
echo.
echo Alles installiert. Richte Autostart ein und starte den Server ...
echo.
call "%~dp0start.bat"
