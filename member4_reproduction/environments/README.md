# Member 4 model reproduction environments

This directory keeps the three model environments independent, matching the PDF requirement that each model can be configured and validated separately.

See `environment_status.md` for the latest verified Windows setup status.

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

## Proxy Used During Setup

GitHub and Docker access used the local Clash/Mihomo proxy shown below:

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"
$env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:ALL_PROXY="socks5://127.0.0.1:7897"
```

## 1. SEDS

Official repository: https://github.com/longtaojiang/SEDS

Independent environment file: `seds_environment.yml`
Windows-compatible pip file: `seds_requirements_no_xformers.txt`

```powershell
conda env create -f member4_reproduction/environments/seds_environment.yml
conda activate seds-reproduction
git clone https://github.com/longtaojiang/SEDS.git
pip install -r member4_reproduction/environments/seds_requirements_no_xformers.txt
pip install numpy==1.25.1 Pillow==9.5.0 fsspec==2024.12.0 MarkupSafe==2.1.5
python -m compileall SEDS
```

`xformers==0.0.22.post7` is intentionally excluded on Windows because it requires `torch==2.1.0`, while the official SEDS README specifies `torch==2.3.1+cu121` and `torchvision==0.18.1+cu121`.

Validation priority after datasets and checkpoints are ready:

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
Base Docker image: `rzuo/pose:sing_ISLR_smplx`

```powershell
git clone https://github.com/FangyunWei/SLRT.git
docker pull rzuo/pose:sing_ISLR_smplx
docker build -f member4_reproduction/environments/spoken2sign.Dockerfile -t spoken2sign-reproduction:latest .
docker run --rm -v "${PWD}/SLRT:/workspace/SLRT" spoken2sign-reproduction:latest bash -lc "cd /workspace/SLRT/Spoken2Sign && find . -name '._*' -delete && python -m compileall ."
```

To run an interactive container after data/model resources are ready:

```powershell
docker run --gpus all `
  -v C:/path/to/data:/data `
  -v ${PWD}/SLRT:/workspace/SLRT `
  -v C:/path/to/pretrained_models:/pretrained_models `
  --name spoken2sign_smplx --ipc=host -it spoken2sign-reproduction:latest /bin/bash
```

Required external resources:

- PHOENIX-2014T / CSL-Daily / WLASL / MSASL as needed
- 3D dictionary and video IDs
- SMPL, SMPLH, SMPL-X, MANO models under the official expected data layout
- SMPL-X Blender add-on under `/pretrained_models`

## 3. Sign-IDD

Official repository: https://github.com/NaVi-start/Sign-IDD

Independent environment file: `sign_idd_environment.yml`
Windows-compatible pip file: `sign_idd_requirements_pip_windows.txt`

```powershell
conda env create -f member4_reproduction/environments/sign_idd_environment.yml
conda activate sign-idd-reproduction
git clone https://github.com/NaVi-start/Sign-IDD.git
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121
pip install -r member4_reproduction/environments/sign_idd_requirements_pip_windows.txt
python -m compileall Sign-IDD
```

`Sign-IDD/requirement.txt` mixes pip packages with Conda/system packages. The Windows-compatible file excludes `bzip2`, `ca-certificates`, `certifi`, `python`, `torch`, and `torchvision`, then installs the PyTorch pair separately.

Validation priority after datasets and checkpoints are ready:

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
