# Environment Setup Status

Date: 2026-07-20
Workspace: `C:\Users\Administrator\Desktop\Sign_language_AI`

## GitHub / Proxy

- GitHub remote `github` is configured as `https://github.com/yuki-777f/git-.git`.
- Clash/Mihomo proxy `127.0.0.1:7897` was verified for GitHub access.
- The project was pushed to GitHub successfully before model environment repair.

Temporary proxy for this PowerShell session:

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"
$env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:ALL_PROXY="socks5://127.0.0.1:7897"
```

## SEDS

Repository: `SEDS/`
Environment: `seds-reproduction`

Verified versions:

- Python: 3.10.20
- NumPy: 1.25.1
- Torch: 2.3.1+cu121
- Torchvision: 0.18.1+cu121

Status:

- `SEDS/requirements.txt` installs most packages on Windows.
- `xformers==0.0.22.post7` conflicts with the official README torch version because it requires `torch==2.1.0`.
- `xformers` was removed to keep the official SEDS torch stack.
- `python -m compileall SEDS` passed.

Windows-compatible requirements file:

- `member4_reproduction/environments/seds_requirements_no_xformers.txt`

Validation command:

```powershell
conda run -n seds-reproduction python -c "import numpy, torch, torchvision; print(numpy.__version__, torch.__version__, torchvision.__version__)"
conda run -n seds-reproduction python -m compileall SEDS
```

## Sign-IDD

Repository: `Sign-IDD/`
Environment: `sign-idd-reproduction`

Verified versions:

- Python: 3.10.20
- Torch: 2.4.1+cu121
- Torchvision: 0.19.1+cu121

Status:

- Official file is `Sign-IDD/requirement.txt`.
- It mixes pip packages with Conda/system packages such as `bzip2`, `ca-certificates`, `certifi`, and `python`.
- It also listed mismatched `torchvision==0.16.2+cu121`; for `torch==2.4.1`, `torchvision==0.19.1` was installed instead.
- Filtered Windows requirements installed successfully.
- `python -m compileall Sign-IDD` passed.

Windows-compatible requirements file:

- `member4_reproduction/environments/sign_idd_requirements_pip_windows.txt`

Validation command:

```powershell
conda run -n sign-idd-reproduction python -c "import torch, torchvision, numpy, pandas, yaml; print(torch.__version__, torchvision.__version__)"
conda run -n sign-idd-reproduction python -m compileall Sign-IDD
```

## Spoken2Sign / A Simple Baseline

Repository: `SLRT/Spoken2Sign/`
Docker image: `spoken2sign-reproduction:latest`
Base image: `rzuo/pose:sing_ISLR_smplx`

Status:

- Docker Desktop was installed with `winget`.
- WSL2 and Ubuntu were installed.
- Docker daemon initially returned `Docker Desktop is unable to start`; restarting Docker processes and WSL fixed it:

```powershell
Get-Process *docker* -ErrorAction SilentlyContinue | Stop-Process -Force
wsl --shutdown
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

- Pulling `rzuo/pose:sing_ISLR_smplx` completed.
- Local Docker image `spoken2sign-reproduction:latest` built successfully.
- `python -m compileall .` passed inside the container after removing AppleDouble files named `._*`.

Validation command:

```powershell
docker run --rm -v "${PWD}/SLRT:/workspace/SLRT" spoken2sign-reproduction:latest bash -lc "cd /workspace/SLRT/Spoken2Sign && find . -name '._*' -delete && python -m compileall ."
```

Remaining external resources:

- SEDS datasets, I3D features, RTM keypoints, `pretrain_signbert.pth`, and `ViT-B-32.pt`.
- Sign-IDD PHOENIX14T-compatible data and checkpoints.
- Spoken2Sign data, 3D dictionary, video IDs, SMPL/SMPLH/SMPL-X/MANO assets, and SMPL-X Blender add-ons.
