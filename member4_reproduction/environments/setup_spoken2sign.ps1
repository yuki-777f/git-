param(
    [string]$RepoPath = "SLRT",
    [string]$DataPath = "C:/path/to/data",
    [string]$PretrainedPath = "C:/path/to/pretrained_models"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $RepoPath)) {
    git clone https://github.com/FangyunWei/SLRT.git $RepoPath
}

docker pull rzuo/pose:sing_ISLR_smplx
docker build -f "member4_reproduction/environments/spoken2sign.Dockerfile" -t spoken2sign-reproduction:latest .

Write-Host "Docker image is ready. Start it with:"
Write-Host "docker run --gpus all -v ${DataPath}:/data -v ${PWD}/${RepoPath}:/workspace/SLRT -v ${PretrainedPath}:/pretrained_models --name spoken2sign_smplx --ipc=host -it spoken2sign-reproduction:latest /bin/bash"
Write-Host "Inside container: cd /workspace/SLRT/Spoken2Sign && python -m compileall ."
