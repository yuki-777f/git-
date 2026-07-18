@echo off
setlocal

echo === Stop Elise Services ===
echo.

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%stop_ports.ps1"

echo.
echo [INFO] Stopping UE executable (myproject.exe) if running ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-Process -Name 'myproject' -ErrorAction SilentlyContinue; if ($p) { $p | Stop-Process -Force; Write-Output '[OK] myproject.exe stopped' } else { Write-Output '[OK] myproject.exe is not running' }"

echo.
echo Done.
endlocal
