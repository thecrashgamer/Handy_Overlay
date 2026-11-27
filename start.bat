@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Phonebox einrichten ===

where python >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden. Bitte von python.org installieren und "Add Python to PATH" anhaken.
  pause
  exit /b 1
)

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
