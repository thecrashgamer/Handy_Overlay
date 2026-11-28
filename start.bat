@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Phonebox einrichten ===

python --version >nul 2>nul
if not errorlevel 1 goto python_ok

echo Python wurde nicht gefunden.
set "ANTWORT="
set /p ANTWORT="Python 3.12 jetzt automatisch installieren? (j/n): "
if /i "%ANTWORT%"=="j" goto python_install
if /i "%ANTWORT%"=="y" goto python_install
if /i "%ANTWORT%"=="ja" goto python_install
if /i "%ANTWORT%"=="yes" goto python_install
echo Abgebrochen. Bitte Python von python.org installieren und "Add Python to PATH" anhaken.
pause
exit /b 1

:python_install
where winget >nul 2>nul
if errorlevel 1 (
  echo winget ist nicht verfuegbar. Bitte Python von python.org installieren und "Add Python to PATH" anhaken.
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo Die Python-Installation ist fehlgeschlagen.
  pause
  exit /b 1
)
for /f "delims=" %%p in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')"') do set "PATH=%%p;%PATH%"
python --version >nul 2>nul
if errorlevel 1 (
  echo Python ist installiert, wird in diesem Fenster aber noch nicht gefunden.
  echo Bitte dieses Fenster schliessen und start.bat noch einmal starten.
  pause
  exit /b 1
)

:python_ok
for /f "delims=" %%v in ('python --version') do echo Gefunden: %%v

echo Installiere Pakete ...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Installation fehlgeschlagen.
  pause
  exit /b 1
)

for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set PYW=%%i

echo Richte Autostart ein ...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Phonebox.lnk'); $s.TargetPath='%PYW%'; $s.Arguments='server.py'; $s.WorkingDirectory='%~dp0'; $s.Save()"

echo Starte den Server ...
start "" "%PYW%" server.py

echo.
echo Fertig. Der Server laeuft jetzt unsichtbar im Hintergrund.
echo.
echo Am PC:    http://localhost:8000
echo Am Handy: eine dieser Adressen (verschluesselt, Port 8443):
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } | ForEach-Object { '  https://' + $_.IPAddress + ':8443' }"
echo.
echo Beim ersten Mal am Handy: Adresse + /zertifikat oeffnen und die Anleitung befolgen.
echo (Die Warnung "nicht privat" einmal bestaetigen, dann das Zertifikat installieren.)
echo Fragt die Windows-Firewall nach, bitte "Private Netzwerke" erlauben.
pause
