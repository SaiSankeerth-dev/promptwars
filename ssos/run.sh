#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║   SSOS NeuralStadium — Starting Demo...             ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""

if ! docker info >/dev/null 2>&1; then
  echo "  [ERROR] Docker is not running. Please start Docker and retry."
  exit 1
fi

echo "  [1/3] Building services..."
docker compose -f docker-compose.demo.yml build --quiet

echo ""
echo "  [2/3] Starting SSOS..."
docker compose -f docker-compose.demo.yml up -d

echo ""
echo "  [3/3] Waiting for services..."
sleep 8

echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║   ✅  SSOS IS RUNNING                               ║"
echo "  ╠══════════════════════════════════════════════════════╣"
echo "  ║   🏟️  Open: ssos/dashboard/public/index.html        ║"
echo "  ║   📡  API:  http://localhost:8000                   ║"
echo "  ║   🧠  ML:   http://localhost:8001                   ║"
echo "  ║   🗺️  Nav:  http://localhost:8002                   ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Stop with: docker compose -f docker-compose.demo.yml down"
echo ""

# Auto-open dashboard on macOS/Linux
if command -v open >/dev/null 2>&1; then
  open dashboard/public/index.html
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open dashboard/public/index.html
fi
