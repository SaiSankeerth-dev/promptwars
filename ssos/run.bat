@echo off
setlocal

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   SSOS NeuralStadium — Starting Demo...             ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: Check Docker
docker info >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Docker is not running. Please start Docker Desktop and retry.
    pause
    exit /b 1
)

echo  [1/3] Pulling base images and building services...
docker compose -f docker-compose.demo.yml build --quiet

echo.
echo  [2/3] Starting SSOS services...
docker compose -f docker-compose.demo.yml up -d

echo.
echo  [3/3] Waiting for services to be ready...
timeout /t 8 /nobreak >nul

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   ✅  SSOS IS RUNNING                               ║
echo  ╠══════════════════════════════════════════════════════╣
echo  ║   🏟️  Mission Control Dashboard:                    ║
echo  ║       Open: ssos/dashboard/public/index.html        ║
echo  ║                                                      ║
echo  ║   📡  API Gateway:   http://localhost:8000          ║
echo  ║   🧠  ML Inference:  http://localhost:8001          ║
echo  ║   🛡️  CrushGuard:   http://localhost:8001/api/v1/crushguard/alerts
echo  ║   🗺️  Routing:       http://localhost:8002          ║
echo  ║   🤖  Digital Twin:  http://localhost:8005          ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
echo  To stop:  docker compose -f docker-compose.demo.yml down
echo.

start "" "dashboard\public\index.html"

endlocal
