@echo off
rem LEGADO: launcher operacional anterior ao prototipo do TCC II (exige o container de API antigo).
rem Para o prototipo atual (A''-J v2, interface Bisco), use scripts\start-local.cmd na raiz do repositorio.
rem Starts API and UI in WSL from this checkout. Keep this window open while using the system;
rem Ctrl+C ends only the keepalive.
setlocal
set "SCRIPT="
for /f "usebackq delims=" %%P in (`wsl.exe -d Ubuntu-24.04 -u root -- wslpath -a "%~dp0start_local.sh"`) do set "SCRIPT=%%P"
if not defined SCRIPT exit /b 1
wsl.exe -d Ubuntu-24.04 -u root -- bash "%SCRIPT%"
if errorlevel 1 exit /b 1
start "" http://127.0.0.1:8501
wsl.exe -d Ubuntu-24.04 -u root -- sleep infinity
