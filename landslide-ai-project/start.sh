#!/usr/bin/env bash
# GROSEN: Automated Command Center Startup for macOS / Linux

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python 3 was not found on your system PATH."
    exit 1
fi

echo "========================================================================"
echo "   GROSEN - NEYVELI LIGNITE CORP SECTOR 4 GIS COMMAND CENTER"
echo "========================================================================"
echo ""

echo "[1/3] Starting FastAPI backend on port 8000..."
$PYTHON_CMD -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload &
SERVER_PID=$!

cleanup() {
    echo ""
    echo "[SHUTDOWN] Stopping background server (PID: $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

echo "[2/3] Waiting 2 seconds for server initialization..."
sleep 2

echo "[3/3] Launching frontend in default web browser..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://127.0.0.1:8000/"
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://127.0.0.1:8000/" &>/dev/null || true
else
    $PYTHON_CMD -m webbrowser "http://127.0.0.1:8000/" || true
fi

echo ""
echo "========================================================================"
echo "   GROSEN Command Center Active: ws://127.0.0.1:8000/ws"
echo "   Press Ctrl+C to stop server."
echo "========================================================================"
wait $SERVER_PID
