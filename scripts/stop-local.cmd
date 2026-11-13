@echo off
rem Stops the TCC II prototype. Volumes (conversation state) are kept: no "down -v".
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if not defined TCC2_WSL_DISTRO set "TCC2_WSL_DISTRO=Ubuntu-24.04"
cd /d "%ROOT%" || exit /b 1
where docker >nul 2>&1
if %errorlevel%==0 (
  docker compose -f compose.demo.yaml down
) else (
  wsl.exe -d %TCC2_WSL_DISTRO% --cd "%ROOT%" -- docker compose -f compose.demo.yaml down
  taskkill /fi "WINDOWTITLE eq tcc2-wsl-keepalive*" /t /f >nul 2>&1
)
if errorlevel 1 (echo [erro] Falha ao parar os servicos. & exit /b 1)
echo Servicos parados. Volumes preservados.
exit /b 0
