#!/usr/bin/env bash
# Clean plain-text bootstrapper for Garychen Gemini 4 Carbon Heavy Worker on Colab RTX PRO 6000 (:19688)
set -euo pipefail

TOKEN="${GC_WORKER_TOKEN:-gc_rtx6000_carbon_2026}"
PORT="${GC_WORKER_PORT:-19688}"
REPO_RAW="${GC_REPO_RAW:-https://raw.githubusercontent.com/jour9927/garychen-gemini-4-carbon-pipeline/main}"

if [ -d "/local-scratch" ] && [ -w "/local-scratch" ]; then
  ROOT="/local-scratch/garychen_g4c"
else
  ROOT="/content/garychen_g4c"
fi

mkdir -p "$ROOT"/{bin,logs,refs,jobs,hf_cache,torch_cache}
if [ "$ROOT" != "/content/garychen_g4c" ] && [ ! -e "/content/garychen_g4c" ]; then
  ln -s "$ROOT" /content/garychen_g4c
fi

curl -fsSL "$REPO_RAW/src/garychen_pipeline/remote/colab_rtx6000_worker.py" -o "$ROOT/garychen_worker_19688.py"
chmod +x "$ROOT/garychen_worker_19688.py"

for f in gary_hook.wav gary_explainer.wav gary_warm.wav voice_manifest.json; do
  curl -fsSL "$REPO_RAW/assets/voice_refs/$f" -o "$ROOT/refs/$f"
done

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3 -m venv --system-site-packages "$ROOT/.venv"
fi

cat <<INST > "$ROOT/install_deps.sh"
#!/usr/bin/env bash
set -euo pipefail
export PIP_DISABLE_PIP_VERSION_CHECK=1
"$ROOT/.venv/bin/pip" install -q soundfile scipy pillow opencc-python-reimplemented faster-whisper diffusers transformers accelerate safetensors f5-tts
touch "$ROOT/.deps_ready"
INST
chmod +x "$ROOT/install_deps.sh"

pkill -f "garychen_worker_19688.py" || true
pkill -f "garychen_cf_19688" || true
sleep 0.4

if [ ! -f "$ROOT/.deps_ready" ]; then
  nohup bash "$ROOT/install_deps.sh" > "$ROOT/logs/install.log" 2>&1 < /dev/null &
fi

CF="$ROOT/bin/garychen_cf_19688"
if [ ! -x "$CF" ]; then
  if [ -x "/usr/local/bin/cloudflared" ]; then
    cp /usr/local/bin/cloudflared "$CF"
  else
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$CF"
  fi
  chmod +x "$CF"
fi

nohup "$ROOT/.venv/bin/python" -u "$ROOT/garychen_worker_19688.py" \
  --work-dir "$ROOT" --port "$PORT" --token "$TOKEN" \
  > "$ROOT/logs/worker.log" 2>&1 < /dev/null &

sleep 0.8
CF_LOG="$ROOT/logs/cf_19688.log"
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
{"url": "$URL", "port": $PORT, "work": "$ROOT"}
JSON
echo "GARYCHEN_RTX6000_READY=$URL"
