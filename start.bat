@echo off
title GROSEN - Mine Subsidence AI Early Warning System
echo ========================================================================
echo    GROSEN - NEYVELI LIGNITE CORP SECTOR 4 GIS COMMAND CENTER
echo ========================================================================
echo.

set "PROJ_DIR=%~dp0landslide-ai-project"
cd /d "%PROJ_DIR%"

echo [1/3] Starting FastAPI backend on port 8000...
start "GROSEN Backend" /d "%PROJ_DIR%" cmd /k "cd /d "%PROJ_DIR%" && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload --app-dir "%PROJ_DIR%""

echo [2/3] Waiting 2 seconds for server initialization...
timeout /t 2 /nobreak >nul

echo [3/3] Launching frontend in default web browser...
start http://127.0.0.1:8000/

echo.
echo ========================================================================
echo    GROSEN Command Center Active: ws://127.0.0.1:8000/ws
echo ========================================================================
