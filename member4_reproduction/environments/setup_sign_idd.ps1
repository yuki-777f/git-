param(
    [string]$RepoPath = "Sign-IDD"
)

$ErrorActionPreference = "Stop"

conda env create -f "member4_reproduction/environments/sign_idd_environment.yml"
conda run -n sign-idd-reproduction python --version

if (-not (Test-Path $RepoPath)) {
    git clone https://github.com/NaVi-start/Sign-IDD.git $RepoPath
}

Push-Location $RepoPath
if (Test-Path "requirements.txt") {
    conda run -n sign-idd-reproduction pip install -r requirements.txt
} elseif (Test-Path "requirement.txt") {
    conda run -n sign-idd-reproduction pip install -r requirement.txt
} else {
    throw "No requirements.txt or requirement.txt found in $RepoPath"
}
conda run -n sign-idd-reproduction python -m compileall .
Pop-Location

Write-Host "Sign-IDD environment is ready. Activate with: conda activate sign-idd-reproduction"
