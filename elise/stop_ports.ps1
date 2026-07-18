$ErrorActionPreference = "Continue"

function Get-NetstatListenPids([int]$Port) {
    $set = New-Object "System.Collections.Generic.HashSet[int]"
    foreach ($line in (& netstat.exe -ano 2>$null)) {
        if ($line -notmatch "LISTENING") { continue }
        if ($line -notmatch ":${Port}\s") { continue }
        if ($line -match "LISTENING\s+(\d+)\s*$") {
            [void]$set.Add([int]$Matches[1])
        }
    }
    return @($set)
}

function Stop-OneListenerPid([int]$procId, [int]$port) {
    if ($procId -le 0) { return $false }
    if ($procId -eq 4) {
        Write-Host "[WARN] Port $port appears bound to System (PID 4), often http.sys. Do NOT kill PID 4."
        Write-Host "       Admin CMD: netsh http show urlacl   (look for :$port)"
        Write-Host ("       Example (admin): netsh http delete urlacl url=http://+:{0}/" -f $port)
        return $false
    }

    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    $name = if ($p) { $p.ProcessName } else { "?" }
    Write-Host "[INFO] Port $port try stop PID=$procId Name=$name"

    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "[OK] Stop-Process PID $procId"
        return $true
    }
    catch {
        Write-Host "[WARN] Stop-Process PID ${procId}: $($_.Exception.Message)"
    }

    $tc = Start-Process -FilePath "taskkill.exe" -ArgumentList @("/F", "/PID", "$procId") -Wait -PassThru -WindowStyle Hidden
    if ($tc.ExitCode -eq 0) {
        Write-Host "[OK] taskkill /F /PID $procId"
        return $true
    }
    if ($tc.ExitCode -eq 128) {
        Write-Host "[INFO] taskkill 128: PID $procId not found (stale PID or already exited)."
    }
    else {
        Write-Host "[WARN] taskkill PID $procId exit=$($tc.ExitCode) — try Administrator or close the app window."
    }
    return $false
}

# Uvicorn --reload can leave Get-NetTCPConnection / netstat OwningProcess pointing at an exited parent PID
# while the child still holds the socket. Find likely Elise backend Python by command line.
function Get-EliseBackendPythonPids {
    $out = New-Object "System.Collections.Generic.HashSet[int]"
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^(python|pythonw)(\.exe)?$'
    } | ForEach-Object {
        $cl = $_.CommandLine
        if (-not $cl) { return }
        if ($cl -notmatch '(?i)[\\/]elise[\\/]') { return }
        if ($cl -match '(?i)main\.py' -or ($cl -match '(?i)uvicorn' -and $cl -match '8000')) {
            [void]$out.Add([int]$_.ProcessId)
        }
    }
    return @($out)
}

$ports = @(8000, 8080, 8888, 8889)

foreach ($port in $ports) {
    Write-Host "[INFO] Checking port $port ..."

    $ids = New-Object "System.Collections.Generic.HashSet[int]"
    $gnc = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($c in @($gnc)) {
        if ($c.OwningProcess) { [void]$ids.Add([int]$c.OwningProcess) }
    }
    foreach ($n in (Get-NetstatListenPids $port)) {
        [void]$ids.Add($n)
    }

    if ($ids.Count -eq 0) {
        Write-Host "[OK] No listener on port $port"
        continue
    }

    Write-Host "[INFO] Port $port candidate PIDs: $($ids -join ', ') (Get-NetTCPConnection + netstat -ano)"

    foreach ($procId in ($ids | Sort-Object)) {
        [void](Stop-OneListenerPid -procId $procId -port $port)
    }

    Start-Sleep -Milliseconds 800
    $stillGnc = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    $stillNet = Get-NetstatListenPids $port
    if (-not $stillGnc -and $stillNet.Count -eq 0) {
        Write-Host "[OK] Port $port is now free."
        continue
    }

    if ($port -eq 8000) {
        $extra = Get-EliseBackendPythonPids
        $extra = $extra | Where-Object { -not $ids.Contains($_) }
        if ($extra.Count -gt 0) {
            Write-Host "[INFO] Port 8000 still busy; fallback PIDs (Elise Python cmdline): $($extra -join ', ')"
            foreach ($procId in ($extra | Sort-Object)) {
                [void](Stop-OneListenerPid -procId $procId -port $port)
            }
            Start-Sleep -Milliseconds 800
            $stillGnc = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
            $stillNet = Get-NetstatListenPids $port
        }
    }

    if (-not $stillGnc -and $stillNet.Count -eq 0) {
        Write-Host "[OK] Port $port is now free."
    }
    else {
        Write-Host "[WARN] Port $port still LISTENING. Compare: Get-NetTCPConnection vs netstat -ano"
        Write-Host ('       CMD: netstat -ano | findstr ":{0}"' -f $port)
        if ($port -eq 8000) {
            Write-Host "       If OwningProcess is stale (uvicorn --reload), avoid ELISE_RELOAD=1 or kill python above."
        }
    }
}
