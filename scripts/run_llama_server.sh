#!/usr/bin/env bash
# ==============================================================================
# Translator Memory Engine - Local LLM Server Launcher
# ==============================================================================
# This script starts the local llama-server (llama.cpp) with parameters highly
# optimized for Intel i5-11300H (4 Cores / 8 Threads, AVX2/VNNI support).
#
# By default, it automatically downloads the optimal Qwen-2.5 model from Hugging Face!
#
# Usage:
#   ./scripts/run_llama_server.sh
# ==============================================================================

# Ensure llama-server is installed or in PATH
if ! command -v llama-server &> /dev/null; then
    echo "❌ Error: 'llama-server' not found in PATH."
    echo "Please install llama.cpp (e.g. via homebrew, or compile from source) or use Ollama."
    exit 1
fi

HF_REPO="Qwen/Qwen2.5-1.5B-Instruct-GGUF"
HF_FILE="qwen2.5-1.5b-instruct-q4_k_m.gguf"

echo "🚀 Starting Local LLM Verification Server (llama-server)..."
echo "----------------------------------------------------------------------"
echo "HF Repo: $HF_REPO"
echo "HF File: $HF_FILE (Will automatically download and cache if missing!)"
echo "Host:    127.0.0.1:8080"
echo "Threads: 4 (Optimized for 4 Physical Cores on i5-11300H)"
echo "Context: 2048 (Safe for Micro-Batching)"
echo "----------------------------------------------------------------------"

# Execution with optimized parameters for CPU
# -c 2048: Micro-batching chunk_size=10 only requires ~400-600 tokens max.
# -t 4: Match physical cores exactly to prevent hyper-threading cache thrashing.
# --parallel 1: Only handle one request at a time to prevent RAM/CPU spikes.
# --hf-repo & --hf-file: Tell llama-server to seamlessly pull from huggingface.

exec llama-server \
    --hf-repo "$HF_REPO" \
    --hf-file "$HF_FILE" \
    --host "127.0.0.1" \
    --port 8080 \
    --ctx-size 2048 \
    --threads 4 \
    --parallel 1
