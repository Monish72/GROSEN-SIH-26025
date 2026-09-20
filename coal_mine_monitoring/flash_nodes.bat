@echo off
title GROSEN - Reflash Sensor Nodes
color 0A
setlocal enabledelayedexpansion

echo ========================================================================
echo    GROSEN - SENSOR NODE REFLASH UTILITY
echo ========================================================================
echo.
echo Please connect the Sensor Node ESP32 you wish to flash via USB cable.
echo.
echo [1] Flash Sensor Node 1 (NODE_ID = 1)
echo [2] Flash Sensor Node 2 (NODE_ID = 2)
echo [3] Exit
echo.
set /p choice="Enter choice (1, 2, or 3): "

if "%choice%"=="1" (
    set NID=1
    echo.
    echo [CONFIG] Configuring firmware for Sensor Node 1 (NODE_ID = 1)...
    powershell -Command "(Get-Content 'sensor_node\src\config.h') -replace '#define NODE_ID\s+[0-9]+', '#define NODE_ID             1' | Set-Content 'sensor_node\src\config.h'"
) else if "%choice%"=="2" (
    set NID=2
    echo.
    echo [CONFIG] Configuring firmware for Sensor Node 2 (NODE_ID = 2)...
    powershell -Command "(Get-Content 'sensor_node\src\config.h') -replace '#define NODE_ID\s+[0-9]+', '#define NODE_ID             2' | Set-Content 'sensor_node\src\config.h'"
) else (
    echo Exiting.
    exit /b 0
)

echo.
echo [PORT] Freeing USB COM port for flashing...
taskkill /F /IM python.exe >nul 2>nul
timeout /t 2 /nobreak >nul

echo.
echo [FLASH] Compiling and uploading firmware to Node %NID% via PlatformIO...
cd sensor_node
python -m platformio run --target upload
if %errorlevel% neq 0 (
    echo.
    echo [FAIL] Upload failed!
    echo Check that:
    echo  1. The ESP32 is securely plugged in via USB.
    echo  2. If it gets stuck on 'Connecting.....', hold down the 'BOOT' button on the ESP32.
    cd ..
    pause
    exit /b 1
)

echo.
echo ========================================================================
echo [SUCCESS] GROSEN Sensor Node %NID% successfully flashed with 100kHz I2C firmware!
echo ========================================================================
cd ..
echo.
echo Next Steps:
echo 1. Disconnect Node %NID% and reconnect to charger (or leave on USB).
echo 2. If you want to flash the other node, re-run this script and choose the other number.
echo 3. When both nodes are powered, plug the Gateway back into your laptop and run start.bat!
echo.
pause
