@echo off
setlocal

set SCRIPT_DIR=%~dp0

echo === Restart Elise Services ===
echo.
echo [1/2] Stopping existing services...
call "%SCRIPT_DIR%stop_elise.bat"
if errorlevel 1 (
    echo [WARN] stop_elise.bat returned an error. Continue anyway.
)

echo.
echo [INFO] Waiting 2 seconds for ports to release...
timeout /t 2 /nobreak >nul

echo.
echo [2/2] Starting services...
call "%SCRIPT_DIR%start_elise.bat"
if errorlevel 1 (
    echo [ERROR] start_elise.bat returned an error.
    endlocal
    exit /b 1
)

echo.
echo Restart done.
endlocal
