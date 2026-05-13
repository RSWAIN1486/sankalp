# Qwen3.6 vLLM on AWS EC2 G6e

This runbook serves `Qwen/Qwen3.6-27B-FP8` through vLLM's OpenAI-compatible
`/v1` API on an AWS `g6e.4xlarge` instance.

Recommended first target:

- Instance: `g6e.4xlarge`
- GPU: `1x NVIDIA L40S`
- VRAM: `48 GB`
- System RAM: `128 GiB`
- Root/EBS volume: at least `250 GiB`
- AMI: AWS Deep Learning AMI GPU, Ubuntu preferred

The default compose config keeps the vision encoder enabled so Sankalp Computer Use can send
screenshots to the model. It starts with a conservative `MAX_MODEL_LEN=32768`. Raise context only
after the first endpoint is stable. Qwen thinking mode is disabled by default at the vLLM server
layer so OpenAI-compatible clients such as Sankalp receive normal `message.content`.

## Security Model

Prefer an SSH tunnel from your Mac to the EC2 instance. Then vLLM listens on the instance, but
Sankalp talks to `http://127.0.0.1:8000/v1` locally.

For the EC2 security group:

- Inbound SSH `22`: your home/public IP only
- Inbound vLLM `8000`: do not open to the world

If you skip the SSH tunnel and expose port `8000`, restrict it to your public IP `/32` and keep
`VLLM_API_KEY` enabled.

## EC2 Setup

SSH into the instance:

```sh
ssh -i /path/to/key.pem ubuntu@<EC2_PUBLIC_DNS_OR_IP>
```

Run the GPU host setup helper from the repo root if this is a fresh DLAMI instance:

```sh
bash scripts/setup_ec2_gpu.sh
source ~/.bashrc
```

The helper installs Miniconda into `~/miniconda3` when missing, runs `conda init bash`, accepts the
Anaconda Terms of Service for the default `pkgs/main` and `pkgs/r` channels, verifies `nvidia-smi`,
and checks Docker GPU access.

Verify the GPU:

```sh
nvidia-smi
```

If you used an AWS Deep Learning AMI, Docker and NVIDIA runtime are usually already available. Check:

```sh
docker --version
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If Docker is missing, install it:

```sh
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker
```

If `docker run --gpus all ... nvidia-smi` fails, install/configure NVIDIA Container Toolkit before
starting vLLM.

## Deploy vLLM

Clone or copy this repo to the EC2 instance, then:

```sh
cd /path/to/sankalp/deploy/aws-ec2-vllm-qwen36
cp .env.example .env
```

Edit `.env`:

```sh
nano .env
```

Set:

```text
HF_TOKEN=<your Hugging Face token>
VLLM_API_KEY=<a long random API key>
VLLM_IMAGE=vllm/vllm-openai:latest
MAX_MODEL_LEN=32768
```

If the container restarts immediately with a CUDA error like `unsupported display driver / cuda driver combination`,
the pinned image and host NVIDIA driver are out of sync. On newer driver branches such as `580.x`, prefer a newer
`VLLM_IMAGE` instead of an older pinned tag.

Start the server:

```sh
docker compose up -d
docker compose logs -f vllm
```

The first start downloads the model into `~/.cache/huggingface`. On later starts, the model loads
from that local cache.

## Test On EC2

```sh
source .env

curl -sS http://127.0.0.1:8000/v1/models \
  -H "Authorization: Bearer ${VLLM_API_KEY}"

curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer ${VLLM_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-27B-FP8",
    "messages": [{"role": "user", "content": "Reply with exactly: hello"}],
    "max_tokens": 16,
    "temperature": 0
  }'
```

## Connect From Your Mac

Recommended tunnel:

```sh
ssh -i /path/to/key.pem -N -L 8000:127.0.0.1:8000 ubuntu@<EC2_PUBLIC_DNS_OR_IP>
```

Keep that terminal open. Then test from your Mac:

```sh
curl -sS http://127.0.0.1:8000/v1/models \
  -H "Authorization: Bearer <VLLM_API_KEY>"
```

In Sankalp Settings -> Provider:

- Provider: `OpenAI-compatible endpoint`
- Base URL: `http://127.0.0.1:8000/v1`
- Model: `Qwen/Qwen3.6-27B-FP8`
- API key: the value of `VLLM_API_KEY`

## Context Tuning

Use this progression:

1. `MAX_MODEL_LEN=32768`: first stable vision-capable target on `g6e.4xlarge`
2. `MAX_MODEL_LEN=65536`: try after basic chat and screenshot prompts work
3. `MAX_MODEL_LEN=131072`: only if VRAM still has headroom

Restart after changing `.env`:

```sh
docker compose down
docker compose up -d
docker compose logs -f vllm
```

If you hit OOM:

- Lower `MAX_MODEL_LEN`
- Keep `MAX_NUM_SEQS=1`
- For text-only usage, add `--language-model-only` to `docker-compose.yml`; this disables
  vision/screenshot input and can free memory
- If responses return `content: null` with only a `reasoning` field, restart with the current
  compose file so `--default-chat-template-kwargs '{"enable_thinking": false}'` is active

## Operations

Stop serving but keep the instance:

```sh
docker compose down
```

Stop the EC2 instance when done to avoid compute charges. The Hugging Face cache persists on EBS,
so the next start avoids re-downloading the model.

For Spot instances, expect interruption risk. Keep the setup in this directory and the model cache
on persistent EBS if you want fast recovery.
