param(
    [switch]$InstallDeps,
    [switch]$AutoInstallMissing,
    [switch]$StartUE,
    [switch]$OpenUI,
    # 为手语识别（/sign_to_text）在启动后端前注入 UNISIGN_* 环境变量，并与数字人共用同一套启动流程
    [switch]$EnableSignLanguageBackend,
    [string]$UniSignRoot = "",
    [string]$UniSignFinetune = "",
    [string]$UniSignDevice = "cpu",
    [string]$UniSignMaxLength = "256"
)

$ErrorActionPreference = "Stop"

function Assert-FileExists {
    param(
        [string]$Path,
        [string]$Name
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing required file: $Name (`"$Path`")"
    }
}

function Start-NewTerminal {
    param(
        [string]$Title,
        [string]$Command
    )
    $args = @(
        "-NoExit",
        "-Command",
        "`$host.ui.RawUI.WindowTitle='$Title'; $Command"
    )
    Start-Process -FilePath "powershell.exe" -ArgumentList $args | Out-Null
}

function Test-PortInUse {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        return ($null -ne $conn)
    }
    catch {
        return $false
    }
}

function Wait-BackendHttpReady {
    param(
        [string]$Uri = "http://127.0.0.1:8000/",
        [int]$TimeoutSec = 45,
        [int]$PerRequestMs = 3000
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $req = [System.Net.HttpWebRequest]::Create($Uri)
            $req.Method = "GET"
            $req.Timeout = $PerRequestMs
            $req.UserAgent = "EliseLauncher/1.0"
            $resp = $req.GetResponse()
            $code = [int]$resp.StatusCode
            $resp.Close()
            if ($code -ge 200 -and $code -lt 300) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

function Wait-PortListening {
    param(
        [int]$Port,
        [int]$TimeoutSec = 20
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortInUse -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Wait-StreamerConnected {
    param(
        [string]$LogPath,
        [int]$TimeoutSec = 20
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $LogPath) {
            try {
                $latest = Get-Content -LiteralPath $LogPath -Tail 200 -ErrorAction Stop
                if ($latest -match "New streamer connection|Registered new streamer") {
                    return $true
                }
            }
            catch {
                # keep waiting
            }
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SignallingDir = Join-Path $ProjectRoot "SignallingWebServer"
$WindowsDir = Join-Path $ProjectRoot "Windows"

$MainPy = Join-Path $ProjectRoot "main.py"
$Lexicon = Join-Path $ProjectRoot "lexicon.json"
$ReqFile = Join-Path $ProjectRoot "requirements.txt"
$RuntimeReqFile = Join-Path $ProjectRoot "requirements.runtime.txt"
$SignallingEntry = Join-Path $SignallingDir "dist\index.js"
$SignallingConfig = Join-Path $SignallingDir "config.json"
$SignallingLog = Join-Path $SignallingDir ("logs\\server-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$FrontendElise = Join-Path $SignallingDir "www\elise.html"
$FrontendIndex = Join-Path $SignallingDir "www\index.html"
$ProjectIndex = Join-Path $ProjectRoot "index.html"
$UEExe = Join-Path $WindowsDir "myproject.exe"

Write-Host "=== Elise Launcher ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

Assert-FileExists -Path $MainPy -Name "main.py"
Assert-FileExists -Path $Lexicon -Name "lexicon.json"
Assert-FileExists -Path $SignallingEntry -Name "SignallingWebServer/dist/index.js"
Assert-FileExists -Path $SignallingConfig -Name "SignallingWebServer/config.json"
Assert-FileExists -Path $FrontendElise -Name "SignallingWebServer/www/elise.html"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python not found in PATH."
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "node not found in PATH."
}

$PythonReqToUse = $ReqFile
if (Test-Path -LiteralPath $RuntimeReqFile) {
    $PythonReqToUse = $RuntimeReqFile
}

$NodeModules = Join-Path $SignallingDir "node_modules"

$PyCheckCode = "import importlib.util,sys;mods=['fastapi','uvicorn','multipart','pythonosc','openai','websocket'];missing=[m for m in mods if importlib.util.find_spec(m) is None];print(','.join(missing));sys.exit(1 if missing else 0)"
$MissingPyModules = @()
& python -c $PyCheckCode | ForEach-Object {
    if ($_ -and $_.Trim() -ne "") {
        $MissingPyModules = $_.Split(",")
    }
}
$PythonDepsMissing = ($LASTEXITCODE -ne 0)
$NodeDepsMissing = (-not (Test-Path -LiteralPath $NodeModules))
if (-not $NodeDepsMissing) {
    Push-Location $SignallingDir
    try {
        & node -e "require.resolve('express'); require.resolve('commander')"
        $NodeDepsMissing = ($LASTEXITCODE -ne 0)
    }
    finally {
        Pop-Location
    }
}

$ShouldInstallDeps = $InstallDeps -or ($AutoInstallMissing -and ($PythonDepsMissing -or $NodeDepsMissing))

if ($ShouldInstallDeps) {
    if ($InstallDeps -or $PythonDepsMissing) {
        Write-Host "[1/2] Installing Python dependencies..." -ForegroundColor Yellow
        if ($PythonDepsMissing -and $MissingPyModules.Count -gt 0) {
            Write-Host ("Missing Python modules: " + ($MissingPyModules -join ", "))
        }
        & python -m pip install -r $PythonReqToUse
        if ($LASTEXITCODE -ne 0) {
            throw "Python dependency install failed. File: $PythonReqToUse"
        }
    }
    else {
        Write-Host "[1/2] Python dependencies already present, skipping install."
    }

    if ($InstallDeps -or $NodeDepsMissing) {
        if ($NodeDepsMissing) {
            Write-Host "[2/2] Installing SignallingWebServer dependencies..." -ForegroundColor Yellow
            Push-Location $SignallingDir
            try {
                & npm install
                if ($LASTEXITCODE -ne 0) {
                    throw "npm install failed in SignallingWebServer."
                }
            }
            finally {
                Pop-Location
            }
        }
        else {
            Write-Host "[2/2] node_modules exists, skipping npm install."
        }
    }
    else {
        Write-Host "[2/2] Node dependencies already present, skipping install."
    }
}
elseif ($AutoInstallMissing) {
    Write-Host "[Deps] Dependencies look good, no install needed."
}

$SignallingPortsBusy = (Test-PortInUse -Port 8080) -or (Test-PortInUse -Port 8888) -or (Test-PortInUse -Port 8889)
if ($SignallingPortsBusy) {
    Write-Warning "Detected port in use (8080/8888/8889). Skip launching SignallingWebServer to avoid conflict."
    Write-Warning "If you want a fresh start, close old signalling/node processes first."
}
else {
    Write-Host "[Start] SignallingWebServer" -ForegroundColor Green
    Start-NewTerminal -Title "Elise-Signalling" -Command "Set-Location -LiteralPath '$SignallingDir'; node .\dist\index.js"
    if (Wait-PortListening -Port 8080 -TimeoutSec 20) {
        Write-Host "[Ready] SignallingWebServer is listening on 8080"
    }
    else {
        Write-Warning "SignallingWebServer did not become ready on port 8080 within timeout."
    }
}

if ($EnableSignLanguageBackend -and (Test-Path -LiteralPath $ProjectIndex)) {
    Write-Host "[Deploy] Copy combined UI to SignallingWebServer/www/index.html" -ForegroundColor Yellow
    Copy-Item -LiteralPath $ProjectIndex -Destination $FrontendIndex -Force
}

$BackendCommand = "`$env:PYTHONUNBUFFERED='1'; Set-Location -LiteralPath '$ProjectRoot'; python .\main.py"
if ($EnableSignLanguageBackend) {
    $ResolvedUniRoot = if ($UniSignRoot) { $UniSignRoot } else { Join-Path (Split-Path -Parent $ProjectRoot) "Uni-Sign-main" }
    $ResolvedUniFinetune = if ($UniSignFinetune) { $UniSignFinetune } else { Join-Path $ResolvedUniRoot "out\stage3_finetuning\best_checkpoint.pth" }
    Write-Host "[Sign] UNISIGN_ROOT=$ResolvedUniRoot" -ForegroundColor DarkCyan
    Write-Host "[Sign] UNISIGN_FINETUNE=$ResolvedUniFinetune" -ForegroundColor DarkCyan
    $BackendCommand = "`$env:PYTHONUNBUFFERED='1'; `$env:UNISIGN_ROOT='$ResolvedUniRoot'; `$env:UNISIGN_FINETUNE='$ResolvedUniFinetune'; `$env:UNISIGN_DEVICE='$UniSignDevice'; `$env:UNISIGN_MAX_LENGTH='$UniSignMaxLength'; Set-Location -LiteralPath '$ProjectRoot'; python .\main.py"
}

Write-Host "[Start] FastAPI backend" -ForegroundColor Green
Start-NewTerminal -Title "Elise-Backend" -Command $BackendCommand
if (Wait-PortListening -Port 8000 -TimeoutSec 20) {
    Write-Host "[Ready] FastAPI backend is listening on 8000"
}
else {
    Write-Warning "FastAPI backend did not become ready on port 8000 within timeout."
}

if ($StartUE) {
    if (Test-Path -LiteralPath $UEExe) {
        Write-Host "[Start] UE executable" -ForegroundColor Green
        $UEArgs = @(
            "-PixelStreamingURL=ws://127.0.0.1:8888",
            "-PixelStreamingIP=127.0.0.1",
            "-PixelStreamingPort=8888",
            "-AudioMixer",
            "-Windowed",
            "-log"
        )
        $UEProc = Start-Process -FilePath $UEExe -WorkingDirectory $WindowsDir -ArgumentList $UEArgs -PassThru
        Start-Sleep -Seconds 3
        if (Get-Process -Id $UEProc.Id -ErrorAction SilentlyContinue) {
            Write-Host ("[Ready] UE is running (PID " + $UEProc.Id + ")")
        }
        else {
            Write-Warning "UE exited early. Try manual launch in terminal:"
            Write-Warning ".\Windows\myproject.exe -PixelStreamingURL=ws://127.0.0.1:8888 -PixelStreamingIP=127.0.0.1 -PixelStreamingPort=8888 -AudioMixer -Windowed -log"
        }

        if (Wait-StreamerConnected -LogPath $SignallingLog -TimeoutSec 20) {
            Write-Host "[Ready] Streamer registered to SignallingWebServer"
        }
        else {
            Write-Warning "No streamer registration detected in signalling log."
            Write-Warning "This usually means UE build does not start Pixel Streaming runtime."
        }
    }
    else {
        Write-Warning "UE executable not found: $UEExe"
    }
}

if ($OpenUI) {
    Write-Host "[Wait] Backend HTTP health (GET /) ..." -ForegroundColor Yellow
    if (Wait-BackendHttpReady -Uri "http://127.0.0.1:8000/" -TimeoutSec 45 -PerRequestMs 3000) {
        Write-Host "[Ready] Backend responded on GET http://127.0.0.1:8000/" -ForegroundColor Green
    }
    else {
        Write-Warning "Backend did not return success on GET / within 45s. Opening browser anyway."
    }

    Write-Host "[Start] Open UI page" -ForegroundColor Green
    $uiUrl = if ($EnableSignLanguageBackend -and (Test-Path -LiteralPath $FrontendIndex)) {
        "http://127.0.0.1:8080/index.html"
    }
    elseif (Test-Path -LiteralPath $FrontendIndex) {
        "http://127.0.0.1:8080/index.html"
    }
    else {
        "http://127.0.0.1:8080/elise.html"
    }
    Start-Process $uiUrl | Out-Null
}

Write-Host ""
Write-Host "Launch commands have been sent." -ForegroundColor Cyan
if ($EnableSignLanguageBackend -and (Test-Path -LiteralPath $FrontendIndex)) {
    Write-Host "UI:      http://127.0.0.1:8080/index.html  (手语 + 数字人)"
}
else {
    Write-Host "UI:      http://127.0.0.1:8080/index.html  (若不存在则使用 elise.html)"
}
Write-Host "Backend: http://127.0.0.1:8000/"
Write-Host ""
Write-Host "First run command:"
Write-Host "powershell -ExecutionPolicy Bypass -File .\start_elise.ps1 -InstallDeps -StartUE -OpenUI"
Write-Host "Auto mode command:"
Write-Host "powershell -ExecutionPolicy Bypass -File .\start_elise.ps1 -AutoInstallMissing -StartUE -OpenUI"
