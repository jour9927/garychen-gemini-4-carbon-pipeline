#!/usr/bin/env bash
# Clean plain-text bootstrapper for Garychen Gemini 4 Carbon V3 Heavy Worker on Colab RTX PRO 6000 (:19743)
set -euo pipefail

TOKEN="${GC_WORKER_TOKEN:-gc_rtx6000_carbon_2026}"
PORT="${GC_WORKER_PORT:-19743}"
REPO_SHA="${GC_REPO_SHA:-main}"
REPO_RAW="https://raw.githubusercontent.com/jour9927/garychen-gemini-4-carbon-pipeline/${REPO_SHA}"

# Pick mount with maximum free space (/content NVMe SSD when plenty free, else /local-scratch or /dev/shm)
ROOT=$(python3 -c "
import os, shutil
from pathlib import Path
cands = [Path('/content'), Path('/local-scratch'), Path('/dev/shm'), Path('/tmp')]
best = max([p for p in cands if p.exists() and os.access(p, os.W_OK)], key=lambda p: shutil.disk_usage(str(p)).free)
print(best / 'garychen_g4c')
")

mkdir -p "$ROOT"/{bin,logs,refs,jobs,hf_cache,torch_cache,tmp,pip_cache}
export TMPDIR="$ROOT/tmp"
export PIP_CACHE_DIR="$ROOT/pip_cache"
export HF_HOME="$ROOT/hf_cache"
export TORCH_HOME="$ROOT/torch_cache"

curl -fsSL "$REPO_RAW/src/garychen_pipeline/remote/colab_rtx6000_worker.py" -o "$ROOT/garychen_worker_19743.py"
chmod +x "$ROOT/garychen_worker_19743.py"

for f in gary_hook.wav gary_explainer.wav gary_warm.wav voice_manifest.json; do
  curl -fsSL "$REPO_RAW/assets/voice_refs/$f" -o "$ROOT/refs/$f"
done

pkill -9 -f "[g]arychen_worker_19743.py" || true
pkill -9 -f "[g]arychen_cf_19743" || true
sleep 0.5

if [ ! -f "$ROOT/.deps_ready_v3" ]; then
  cat <<INST > "$ROOT/install_deps.sh"
#!/usr/bin/env bash
set -euo pipefail
export TMPDIR="$ROOT/tmp"
export PIP_CACHE_DIR="$ROOT/pip_cache"
export PIP_DISABLE_PIP_VERSION_CHECK=1
python3 -m pip install -q --no-cache-dir soundfile opencc-python-reimplemented faster-whisper f5-tts
touch "$ROOT/.deps_ready_v3"
INST
  chmod +x "$ROOT/install_deps.sh"
  nohup bash "$ROOT/install_deps.sh" > "$ROOT/logs/install.log" 2>&1 < /dev/null &
fi

CF="/usr/local/bin/garychen_cf_19743"
if [ ! -x "$CF" ]; then
  if [ -x "/usr/local/bin/cloudflared" ]; then
    cp /usr/local/bin/cloudflared "$CF"
  else
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$CF"
  fi
  chmod +x "$CF"
fi

NVIDIA_LIBS=$(python3 -c "import glob, site; sp=site.getsitepackages()[0]; print(':'.join(glob.glob(sp+'/nvidia/*/lib') + glob.glob(sp+'/torch/lib')))" 2>/dev/null || true)
export LD_LIBRARY_PATH="${NVIDIA_LIBS}:/usr/local/nvidia/lib64:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"

nohup python3 -u "$ROOT/garychen_worker_19743.py" \
  --work-dir "$ROOT" --port "$PORT" --token "$TOKEN" \
  > "$ROOT/logs/worker.log" 2>&1 < /dev/null &

sleep 0.8
CF_LOG="$ROOT/logs/cf_19743.log"
: > "$CF_LOG"
nohup "$CF" tunnel --protocol http2 --no-autoupdate --url "http://127.0.0.1:$PORT" \
  > "$CF_LOG" 2>&1 < /dev/null &

URL=""
for _ in $(seq 1 50); do
  sleep 0.5
  M=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG" | head -n 1 || true)
  if [ -n "$M" ] && grep -q "Registered" "$CF_LOG"; then
    URL="$M"
    break
  elif [ -n "$M" ]; then
    URL="$M"
  fi
done

cat <<JSON > "$ROOT/ready.json"
{"url": "$URL", "port": $PORT, "token": "$TOKEN", "work": "$ROOT"}
JSON
echo "GARYCHEN_V3_READY={\"url\": \"$URL\", \"port\": $PORT, \"token\": \"$TOKEN\", \"work\": \"$ROOT\"}"
