param(
    [string]$RepoPath = "SEDS"
)

$ErrorActionPreference = "Stop"

conda env create -f "member4_reproduction/environments/seds_environment.yml"
conda run -n seds-reproduction python --version

if (-not (Test-Path $RepoPath)) {
    git clone https://github.com/longtaojiang/SEDS.git $RepoPath
}

Push-Location $RepoPath
conda run -n seds-reproduction pip install -r requirements.txt
conda run -n seds-reproduction python -m compileall .
Pop-Location

Write-Host "SEDS environment is ready. Activate with: conda activate seds-reproduction"
