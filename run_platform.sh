#!/usr/bin/env bash
set -euo pipefail

export MODEL_PATH="${MODEL_PATH:-/home/chuanhaoyang/proiect_pratice_of_cnn/MMRSG-UNet-main/model/epoch_241.pth}"
export LLM_BASE_URL="${LLM_BASE_URL:-https://api.deepseek.com}"
export LLM_MODEL="${LLM_MODEL:-deepseek-v4-flash}"

if [[ -z "${LLM_API_KEY:-${DEEPSEEK_API_KEY:-}}" ]]; then
  echo "DeepSeek key is empty. Set LLM_API_KEY or DEEPSEEK_API_KEY before starting."
fi

cd /home/chuanhaoyang/proiect_pratice_of_cnn/MMRSG-UNet-main
uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --reload

