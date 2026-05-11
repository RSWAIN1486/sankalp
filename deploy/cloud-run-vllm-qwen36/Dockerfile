ARG VLLM_IMAGE=vllm/vllm-openai:v0.20.1
FROM ${VLLM_IMAGE}

ARG MODEL_ID=Qwen/Qwen3.6-27B-FP8
ENV MODEL_ID=${MODEL_ID}
ENV MODEL_DIR=/models/qwen3.6-27b-fp8
ENV HF_HOME=/models/.cache
ENV HUGGINGFACE_HUB_CACHE=/models/.cache/hub
ENV TRANSFORMERS_CACHE=/models/.cache/hub
ENV VLLM_NO_USAGE_STATS=1

RUN python3 -m pip install --no-cache-dir --upgrade huggingface_hub hf_xet && \
    python3 -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id=os.environ['MODEL_ID'], local_dir=os.environ['MODEL_DIR'], local_dir_use_symlinks=False, allow_patterns=['*.json','*.safetensors','*.model','*.txt','*.py','*.tiktoken','*.jinja','*.merges','*.vocab'])"

COPY start.sh /start.sh
RUN chmod +x /start.sh

ENTRYPOINT ["/start.sh"]
