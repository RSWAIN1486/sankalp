#!/usr/bin/env bash
set -euo pipefail

MINICONDA_HOME="${MINICONDA_HOME:-$HOME/miniconda3}"
MINICONDA_INSTALLER="${TMPDIR:-/tmp}/Miniconda3-latest-Linux-x86_64.sh"
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"

log() {
  printf '\n==> %s\n' "$*"
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

install_miniconda() {
  if [ -x "$MINICONDA_HOME/bin/conda" ]; then
    log "Miniconda already installed at $MINICONDA_HOME"
  else
    log "Installing Miniconda to $MINICONDA_HOME"
    if has_command curl; then
      curl -fsSL "$MINICONDA_URL" -o "$MINICONDA_INSTALLER"
    elif has_command wget; then
      wget -O "$MINICONDA_INSTALLER" "$MINICONDA_URL"
    else
      echo "curl or wget is required to download Miniconda." >&2
      exit 1
    fi

    bash "$MINICONDA_INSTALLER" -b -p "$MINICONDA_HOME"
  fi

  log "Initializing conda for bash"
  "$MINICONDA_HOME/bin/conda" init bash

  log "Accepting Anaconda Terms of Service for default channels"
  "$MINICONDA_HOME/bin/conda" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main || true
  "$MINICONDA_HOME/bin/conda" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r || true

  log "Conda version"
  "$MINICONDA_HOME/bin/conda" --version
}

verify_gpu() {
  if has_command nvidia-smi; then
    log "NVIDIA GPU"
    nvidia-smi
  else
    log "nvidia-smi not found. Use a GPU DLAMI or install NVIDIA drivers before running vLLM."
  fi
}

verify_docker() {
  if ! has_command docker; then
    log "Docker not found. Installing Docker."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    log "Added $USER to docker group. Log out/in or run 'newgrp docker' before using Docker without sudo."
    return
  fi

  log "Docker version"
  docker --version

  log "Testing NVIDIA container runtime"
  if docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi; then
    log "NVIDIA container runtime is working"
  else
    log "Docker is installed, but GPU container runtime test failed. Check NVIDIA Container Toolkit."
  fi
}

main() {
  install_miniconda
  verify_gpu
  verify_docker

  cat <<EOF

EC2 GPU setup checks complete.

Open a new shell, or run:

  source ~/.bashrc

Then verify:

  conda --version
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
  docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

EOF
}

main "$@"
