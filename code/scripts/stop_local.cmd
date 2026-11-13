@echo off
rem LEGADO: launcher operacional anterior ao prototipo do TCC II (para o container de API antigo).
rem Para o prototipo atual (A''-J v2, interface Bisco), use scripts\start-local.cmd na raiz do repositorio.
rem Stops the UI and the API container started by start_local.cmd, from this checkout.
setlocal
set "SCRIPT="
for /f "usebackq delims=" %%P in (`wsl.exe -d Ubuntu-24.04 -u root -- wslpath -a "%~dp0stop_local.sh"`) do set "SCRIPT=%%P"
if not defined SCRIPT exit /b 1
wsl.exe -d Ubuntu-24.04 -u root -- bash "%SCRIPT%"
