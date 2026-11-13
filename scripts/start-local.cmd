@echo off
rem Starts the TCC II prototype (backend A''-J v2 + web interface) with Docker Compose.
rem Uses Docker Desktop when "docker" is on PATH; otherwise Docker Engine inside WSL.
rem Usage (from any directory): .\scripts\start-local.cmd
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "COMPOSE_FILE_ARG=-f compose.demo.yaml"
if not defined TCC2_WSL_DISTRO set "TCC2_WSL_DISTRO=Ubuntu-24.04"
if not defined INTERFACE_PORT set "INTERFACE_PORT=8501"
cd /d "%ROOT%" || (echo [erro] Raiz do projeto nao encontrada: %ROOT% & exit /b 1)

if not exist "compose.demo.yaml" (echo [erro] compose.demo.yaml ausente em %ROOT% & exit /b 1)
if not exist ".env" (echo [erro] Arquivo .env ausente. Copie .env.example para .env e preencha OPENROUTER_API_KEY. & exit /b 1)
findstr /r /c:"^OPENROUTER_API_KEY=..*" ".env" >nul || (echo [erro] OPENROUTER_API_KEY vazio em .env. & exit /b 1)
findstr /r /c:"^POSTGRES_PASSWORD=..*" ".env" >nul || (echo [erro] POSTGRES_PASSWORD vazio em .env. Defina uma senha para o PostgreSQL dos checkpoints. & exit /b 1)
if not defined INDEX_DIR set "INDEX_DIR=.local\index"
if not exist "%INDEX_DIR%\chroma.sqlite3" (echo [erro] Indice Chroma ausente: %INDEX_DIR%\chroma.sqlite3. Veja README, secao Indice. & exit /b 1)

where docker >nul 2>&1
if %errorlevel%==0 (
  docker info >nul 2>&1 || (echo [erro] Docker instalado, mas o daemon nao responde. Inicie o Docker Desktop. & exit /b 1)
  echo Iniciando com Docker Desktop...
  docker compose %COMPOSE_FILE_ARG% up --build -d --wait --wait-timeout 300
  if errorlevel 1 goto :failed
  goto :ready
)

wsl.exe -d %TCC2_WSL_DISTRO% -- docker info >nul 2>&1
if errorlevel 1 (echo [erro] Docker nao encontrado no Windows nem na distro WSL %TCC2_WSL_DISTRO%. & exit /b 1)
echo Iniciando com Docker Engine no WSL (%TCC2_WSL_DISTRO%)...
rem WSL stops the distro, and its Docker daemon, when no session remains: keep one open.
tasklist /v /fi "WINDOWTITLE eq tcc2-wsl-keepalive*" | find "wsl.exe" >nul || start "tcc2-wsl-keepalive" /min wsl.exe -d %TCC2_WSL_DISTRO% -- sleep infinity <nul >nul 2>&1
wsl.exe -d %TCC2_WSL_DISTRO% --cd "%ROOT%" -- docker compose %COMPOSE_FILE_ARG% up --build -d --wait --wait-timeout 300
if errorlevel 1 goto :failed

:ready
echo.
echo Prototipo pronto (A''-J v2, Jev, politica v2).
echo Interface: http://127.0.0.1:%INTERFACE_PORT%
echo Para parar: .\scripts\stop-local.cmd
exit /b 0

:failed
echo [erro] Os servicos nao ficaram saudaveis. Veja: docker compose -f compose.demo.yaml ps  e  docker compose -f compose.demo.yaml logs backend
exit /b 1
