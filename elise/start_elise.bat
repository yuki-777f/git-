@echo off
setlocal
set SCRIPT_DIR=%~dp0
if "%~1"=="" (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_elise.ps1" -AutoInstallMissing -StartUE -OpenUI
) else (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_elise.ps1" %*
)
endlocal
