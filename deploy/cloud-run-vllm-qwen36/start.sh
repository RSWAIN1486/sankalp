#!/usr/bin/env bash
set -euo pipefail

: "${PORT:=8000}"
: "${MODEL_DIR:=/models/qwen3.6-27b-fp8}"
: "${SERVED_MODEL_NAME:=Qwen/Qwen3.6-27B-FP8}"
: "${MAX_MODEL_LEN:=65536}"
: "${GPU_MEMORY_UTILIZATION:=0.86}"
: "${MAX_NUM_SEQS:=2}"
: "${MAX_NUM_BATCHED_TOKENS:=8192}"
: "${KV_CACHE_DTYPE:=auto}"
: "${LIMIT_MM_PER_PROMPT:={\"image\":4}}"
: "${UVICORN_LOG_LEVEL:=info}"

args=(
  "${MODEL_DIR}"
  --host "0.0.0.0"
  --port "${PORT}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --trust-remote-code
  --dtype "auto"
  --max-model-len "${MAX_MODEL_LEN}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
  --max-num-seqs "${MAX_NUM_SEQS}"
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}"
  --kv-cache-dtype "${KV_CACHE_DTYPE}"
  --enable-prefix-caching
  --reasoning-parser "qwen3"
  --limit-mm-per-prompt "${LIMIT_MM_PER_PROMPT}"
  --uvicorn-log-level "${UVICORN_LOG_LEVEL}"
)

if [[ -n "${VLLM_API_KEY:-}" ]]; then
  args+=(--api-key "${VLLM_API_KEY}")
fi

if [[ "${ENABLE_AUTO_TOOL_CHOICE:-0}" == "1" ]]; then
  args+=(--enable-auto-tool-choice --tool-call-parser "qwen3_coder")
fi

if [[ "${LANGUAGE_MODEL_ONLY:-0}" == "1" ]]; then
  args+=(--language-model-only)
fi

if [[ -n "${EXTRA_VLLM_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${EXTRA_VLLM_ARGS})
  args+=("${extra_args[@]}")
fi

exec vllm serve "${args[@]}"
