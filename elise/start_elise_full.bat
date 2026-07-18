@echo off
setlocal
set SCRIPT_DIR=%~dp0
REM Full launcher: Signalling + FastAPI (Uni-Sign env for sign language) + optional UE.
REM Copies project-root index.html to SignallingWebServer\www when -EnableSignLanguageBackend is used.
if "%~1"=="" (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_elise.ps1" -AutoInstallMissing -StartUE -OpenUI -EnableSignLanguageBackend
) else (
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_elise.ps1" %*
)
endlocal
