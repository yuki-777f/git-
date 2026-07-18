# Member 4 model reproduction environments

This directory keeps the three model environments independent, matching the PDF requirement that each model can be configured and validated separately.

## Directory Layout

Clone the official repositories as siblings under the workspace root:

```text
Sign_language_AI/
  SEDS/
  SLRT/
    Spoken2Sign/
  Sign-IDD/
  member4_reproduction/
    environments/
```

## Quick Setup Scripts

Run these from the workspace root in PowerShell. They create or build the environment and then run `python -m compileall .` inside the cloned official repository.

```powershell
./member4_reproduction/environments/setup_seds.ps1
./member4_reproduction/environments/setup_spoken2sign.ps1 -DataPath C:/path/to/data -PretrainedPath C:/path/to/pretrained_models
./member4_reproduction/environments/setup_sign_idd.ps1
```

The scripts clone the official repository only when the target folder is missing. They do not download datasets, model weights, SMPL assets, or private resources.

## 1. SEDS

Official repository: https://github.com/longtaojiang/SEDS

Independent environment file: `seds_environment.yml`

```powershell
conda env create -f member4_reproduction/environments/seds_environment.yml
conda activate seds-reproduction
git clone https://github.com/longtaojiang/SEDS.git
Set-Location SEDS
pip install -r requirements.txt
python -m compileall .
```

Validation priority:

```powershell
bash scripts/eval_csl.sh
# or, when CSL data is not ready:
bash scripts/eval_ph.sh
```

Expected resources:

- `datasets/CSL/I3D_features`
- `datasets/CSL/RTMpose`
- `ckpts/pretrain_signbert.pth`
- `modules/ViT-B-32.pt`

## 2. A Simple Baseline / Spoken2Sign

Official repository: https://github.com/FangyunWei/SLRT/tree/main/Spoken2Sign

Independent environment file: `spoken2sign.Dockerfile`

Docker is the preferred independent environment because the model depends on Blender, SMPL-X resources, and rendering tools.

```powershell
git clone https://github.com/FangyunWei/SLRT.git
docker pull rzuo/pose:sing_ISLR_smplx
docker build -f member4_reproduction/environments/spoken2sign.Dockerfile -t spoken2sign-reproduction:latest .
docker run --gpus all `
  -v C:/path/to/data:/data `
  -v ${PWD}/SLRT:/workspace/SLRT `
  -v C:/path/to/pretrained_models:/pretrained_models `
  --name spoken2sign_smplx --ipc=host -it spoken2sign-reproduction:latest /bin/bash
```

Inside the container:

```bash
cd /workspace/SLRT/Spoken2Sign
python -m compileall .
# Then run the official minimal generation and rendering commands after 3D dictionary,
# video IDs, SMPL/SMPLH/SMPL-X/MANO, and add-ons are placed correctly.
```

Required external resources:

- PHOENIX-2014T / CSL-Daily / WLASL / MSASL as needed
- 3D dictionary and video IDs
- SMPL, SMPLH, SMPL-X, MANO models under the official expected data layout
- SMPL-X Blender add-on under `/pretrained_models`

## 3. Sign-IDD

Official repository: https://github.com/NaVi-start/Sign-IDD

Independent environment file: `sign_idd_environment.yml`

```powershell
conda env create -f member4_reproduction/environments/sign_idd_environment.yml
conda activate sign-idd-reproduction
git clone https://github.com/NaVi-start/Sign-IDD.git
Set-Location Sign-IDD
if (Test-Path requirements.txt) { pip install -r requirements.txt } elseif (Test-Path requirement.txt) { pip install -r requirement.txt } else { Write-Error "No requirement file found" }
python -m compileall .
```

Validation priority:

```powershell
python __main__.py test ./Configs/Sign-IDD.yaml
# If no checkpoint is available, run a small training smoke test instead:
python __main__.py train ./Configs/Sign-IDD.yaml
```

Expected resources:

- PHOENIX14T-compatible data
- Official checkpoint if available
- `Configs/Sign-IDD.yaml` adjusted to local dataset/checkpoint paths

## Verification Record

For each model, save the following in `04_evaluation_template.md` or a copied experiment log:

- environment name
- Python, PyTorch, CUDA versions
- complete install command log
- `python -m compileall .` result
- demo, evaluation, or minimal inference command
- checkpoint, dataset path, runtime, and metrics
