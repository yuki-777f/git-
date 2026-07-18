# A Simple Baseline / Spoken2Sign environment
# Officially recommended path: Docker image with Blender and SMPL-X rendering stack.

FROM rzuo/pose:sing_ISLR_smplx

WORKDIR /workspace/SLRT/Spoken2Sign

# Required runtime mounts when starting the container:
# - code: /workspace
# - datasets and 3D dictionaries: /data
# - SMPL-X add-ons and pretrained resources: /pretrained_models
#
# Example:
# docker run --gpus all `
#   -v C:/path/to/data:/data `
#   -v C:/path/to/SLRT:/workspace/SLRT `
#   -v C:/path/to/pretrained_models:/pretrained_models `
#   --name spoken2sign_smplx --ipc=host -it spoken2sign-reproduction:latest /bin/bash
