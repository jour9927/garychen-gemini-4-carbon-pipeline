#!/usr/bin/env python3
"""
Garychen Gemini 4 Carbon — Isolated RTX PRO 6000 / GPU Heavy Worker.
Master copy lives on local machine (alan-hub) first; deployed to Colab RTX PRO 6000 (:19688) and B850 (:18790).

Capabilities:
  - PyTorch Voice Cloning TTS (`f5-tts` F5TTS_v1_Base with Traditional->Simplified pinyin normalization + Taiwan Mandarin ref voice)
  - PyTorch AI Image Generation (`diffusers` SDXL-Turbo / Flux spot & card illustrations + transparent RGBA prop cutouts)
  - Faster-Whisper ASR word/segment timestamp alignment
  - VRAM-aware adaptive device selection (`cuda` when free VRAM suffices, automatic 48-core `cpu` bfloat16/float32 fallback so co-tenant GPU jobs are never disrupted)
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

WORK_DIR = Path(os.environ.get("GC_WORK_DIR", "/content/garychen_g4c")).resolve()
REFS_DIR = WORK_DIR / "refs"
JOBS_DIR = WORK_DIR / "jobs"
CACHE_DIR = WORK_DIR / "hf_cache"
AUTH_TOKEN = os.environ.get("GC_WORKER_TOKEN", "gc_rtx6000_carbon_token")
PORT = int(os.environ.get("GC_WORKER_PORT", "19688"))

os.environ.setdefault("HF_HOME", str(CACHE_DIR))
os.environ.setdefault("TORCH_HOME", str(WORK_DIR / "torch_cache"))

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
MODEL_LOCK = threading.Lock()
MODELS: dict[str, object] = {}


def gpu_stats() -> dict:
    info = {"cuda_available": False, "gpu_name": "cpu", "total_mb": 0, "free_mb": 0, "cpus": os.cpu_count() or 4}
    try:
        import torch
        if torch.cuda.is_available():
            free_b, tot_b = torch.cuda.mem_get_info(0)
            info.update(
                cuda_available=True,
                gpu_name=torch.cuda.get_device_name(0),
                total_mb=int(tot_b // (1024 * 1024)),
                free_mb=int(free_b // (1024 * 1024)),
            )
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            info.update(cuda_available=False, gpu_name="Apple Silicon MPS", total_mb=36864, free_mb=24576)
    except Exception:
        pass
    return info


def pick_device(min_cuda_mb: int) -> str:
    import torch
    st = gpu_stats()
    if st["cuda_available"] and st["free_mb"] >= min_cuda_mb:
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    torch.set_num_threads(min(32, max(4, (os.cpu_count() or 8) - 4)))
    return "cpu"


def normalize_zh_for_tts(text: str) -> str:
    """Convert Traditional Chinese to Simplified only for F5-TTS pinyin frontend accuracy while keeping English spacing."""
    try:
        from opencc import OpenCC
        cc = MODELS.get("opencc_t2s")
        if cc is None:
            cc = OpenCC("t2s")
            MODELS["opencc_t2s"] = cc
        text = cc.convert(text)
    except Exception:
        pass
    return text.strip()


def get_f5_tts(force_cpu: bool = False):
    with MODEL_LOCK:
        target_dev = "cpu" if force_cpu else pick_device(min_cuda_mb=2400)
        cached = MODELS.get("f5_tts")
        if cached is not None and cached[0] == target_dev:
            return cached
        from f5_tts.api import F5TTS
        import torch
        if target_dev == "cpu":
            torch.set_num_threads(min(32, max(4, (os.cpu_count() or 8) - 4)))
        tts = F5TTS(model="F5TTS_v1_Base", device=target_dev)
        MODELS["f5_tts"] = (target_dev, tts)
        return MODELS["f5_tts"]


def get_image_pipe(force_cpu: bool = False):
    with MODEL_LOCK:
        target_dev = "cpu" if force_cpu else pick_device(min_cuda_mb=7200)
        cached = MODELS.get("sdxl_turbo")
        if cached is not None and cached[0] == target_dev:
            return cached
        import torch
        from diffusers import AutoPipelineForText2Image
        dtype = torch.float16 if target_dev in ("cuda", "mps") else torch.bfloat16
        if target_dev == "cpu":
            torch.set_num_threads(min(32, max(4, (os.cpu_count() or 8) - 4)))
        pipe = AutoPipelineForText2Image.from_pretrained(
            "stabilityai/sdxl-turbo",
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
        )
        pipe.to(target_dev)
        pipe.set_progress_bar_config(disable=True)
        MODELS["sdxl_turbo"] = (target_dev, pipe)
        return MODELS["sdxl_turbo"]


def get_whisper_model():
    with MODEL_LOCK:
        if "whisper" in MODELS:
            return MODELS["whisper"]
        from faster_whisper import WhisperModel
        st = gpu_stats()
        dev = "cuda" if (st["cuda_available"] and st["free_mb"] >= 2800) else "cpu"
        ctype = "float16" if dev == "cuda" else "int8"
        wm = WhisperModel("base", device=dev, compute_type=ctype, cpu_threads=min(16, os.cpu_count() or 4))
        MODELS["whisper"] = (dev, wm)
        return MODELS["whisper"]


def get_qwen_llm():
    with MODEL_LOCK:
        if "qwen_llm" in MODELS:
            return MODELS["qwen_llm"]
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        st = gpu_stats()
        model_id = "Qwen/Qwen2.5-7B-Instruct" if (st["cuda_available"] and st["free_mb"] >= 18000) else "Qwen/Qwen2.5-3B-Instruct"
        dev = "cuda" if (st["cuda_available"] and st["free_mb"] >= 9000) else "cpu"
        dtype = torch.bfloat16
        tok = AutoTokenizer.from_pretrained(model_id)
        mdl = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype, device_map={"": 0} if dev == "cuda" else "cpu")
        mdl.eval()
        MODELS["qwen_llm"] = (dev, model_id, tok, mdl)
        return MODELS["qwen_llm"]


def postprocess_voice_wav(wav_path: Path, target_sr: int = 44100):
    """Trim leading/trailing dead air and normalize to Garychen's signature -21 LUFS crisp studio profile."""
    import numpy as np
    import soundfile as sf
    data, sr = sf.read(str(wav_path))
    if data.ndim > 1:
        data = data.mean(axis=1)
    # Trim edges below -48 dBFS
    thresh = 10 ** (-48.0 / 20.0)
    idx = np.where(np.abs(data) > thresh)[0]
    if len(idx) > 10:
        pad = int(0.05 * sr)
        s = max(0, int(idx[0]) - pad)
        e = min(len(data), int(idx[-1]) + int(0.12 * sr))
        data = data[s:e]
    # RMS normalize to ~ -21 dBFS with soft peak limiter at -1.5 dBFS
    rms = float(np.sqrt(np.mean(data ** 2)) + 1e-9)
    target_rms = 10 ** (-21.0 / 20.0)
    gain = min(6.0, target_rms / rms)
    data = data * gain
    peak = float(np.max(np.abs(data)) + 1e-9)
    max_peak = 10 ** (-1.5 / 20.0)
    if peak > max_peak:
        data = np.tanh(data / max_peak) * max_peak
    tmp_out = wav_path.with_suffix(".norm.wav")
    sf.write(str(tmp_out), data, sr, subtype="PCM_16")
    if sr != target_sr:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_out), "-ar", str(target_sr), "-ac", "1", str(wav_path)],
            check=True,
            capture_output=True,
        )
        tmp_out.unlink(missing_ok=True)
    else:
        tmp_out.replace(wav_path)
    info = sf.info(str(wav_path))
    return round(info.duration, 3)


def run_job(job_id: str, kind: str, payload: dict):
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "running"

        if kind == "tts_batch":
            ref_name = payload["ref_name"]
            ref_wav = REFS_DIR / ref_name
            if not ref_wav.exists():
                raise FileNotFoundError(f"Missing reference wav: {ref_wav}")
            ref_text = normalize_zh_for_tts(payload["ref_text"])
            items = payload["items"]
            speed = float(payload.get("speed", 1.03))
            nfe = int(payload.get("nfe_step", 24))
            force_cpu = bool(payload.get("force_cpu", False))
            dev, tts = get_f5_tts(force_cpu=force_cpu)
            outputs = []
            for idx, item in enumerate(items):
                seg_id = str(item["id"])
                gen_text = normalize_zh_for_tts(item["text"])
                out_wav = job_dir / f"{seg_id}.wav"
                try:
                    tts.infer(
                        ref_file=str(ref_wav),
                        ref_text=ref_text,
                        gen_text=gen_text,
                        file_wave=str(out_wav),
                        speed=float(item.get("speed", speed)),
                        nfe_step=nfe,
                        remove_silence=False,
                    )
                except RuntimeError as err:
                    if "out of memory" in str(err).lower() and dev == "cuda":
                        import torch
                        torch.cuda.empty_cache()
                        dev, tts = get_f5_tts(force_cpu=True)
                        tts.infer(
                            ref_file=str(ref_wav),
                            ref_text=ref_text,
                            gen_text=gen_text,
                            file_wave=str(out_wav),
                            speed=float(item.get("speed", speed)),
                            nfe_step=max(16, nfe),
                            remove_silence=False,
                        )
                    else:
                        raise
                dur = postprocess_voice_wav(out_wav, target_sr=44100)
                outputs.append({"id": seg_id, "rel_path": f"{job_id}/{out_wav.name}", "duration": dur, "device": dev})
                with JOBS_LOCK:
                    JOBS[job_id]["progress"] = f"{idx + 1}/{len(items)}"
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"outputs": outputs, "device": dev})

        elif kind == "image_batch":
            import torch
            force_cpu = bool(payload.get("force_cpu", False))
            dev, pipe = get_image_pipe(force_cpu=force_cpu)
            items = payload["items"]
            outputs = []
            for idx, item in enumerate(items):
                img_id = str(item["id"])
                w = (int(item.get("width", 768)) // 8) * 8
                h = (int(item.get("height", 512)) // 8) * 8
                seed = int(item.get("seed", 2026 + idx * 17))
                prompt = (
                    f"{item['prompt']}, sleek modern dark-mode tech editorial 3D render illustration, "
                    "warm amber #EB8B1B rim lighting, dark charcoal studio aesthetic, crisp clean geometry, "
                    "high contrast, strictly no text, no watermark, no letters"
                )
                gen = torch.Generator(device="cpu").manual_seed(seed)
                try:
                    img = pipe(
                        prompt=prompt,
                        num_inference_steps=int(item.get("steps", 4)),
                        guidance_scale=0.0,
                        width=w,
                        height=h,
                        generator=gen,
                    ).images[0]
                except RuntimeError as err:
                    if "out of memory" in str(err).lower() and dev == "cuda":
                        torch.cuda.empty_cache()
                        dev, pipe = get_image_pipe(force_cpu=True)
                        img = pipe(
                            prompt=prompt,
                            num_inference_steps=4,
                            guidance_scale=0.0,
                            width=min(w, 640),
                            height=min(h, 512),
                            generator=gen,
                        ).images[0]
                    else:
                        raise
                if item.get("target_size"):
                    tw, th = item["target_size"]
                    img = img.resize((int(tw), int(th)))
                out_png = job_dir / f"{img_id}.png"
                img.save(str(out_png))
                outputs.append({"id": img_id, "rel_path": f"{job_id}/{out_png.name}", "device": dev})
                with JOBS_LOCK:
                    JOBS[job_id]["progress"] = f"{idx + 1}/{len(items)}"
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"outputs": outputs, "device": dev})

        elif kind == "whisper_align":
            wav_b64 = payload["wav_b64"]
            in_wav = job_dir / "input.wav"
            in_wav.write_bytes(base64.b64decode(wav_b64))
            dev, wm = get_whisper_model()
            segs, _ = wm.transcribe(str(in_wav), language="zh", word_timestamps=True)
            seg_list = []
            for s in segs:
                seg_list.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()})
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"segments": seg_list, "device": dev})

        elif kind == "llm_chat":
            import torch
            dev, model_id, tok, mdl = get_qwen_llm()
            msgs = [
                {"role": "system", "content": payload.get("system_prompt", "")},
                {"role": "user", "content": payload.get("user_prompt", "")},
            ]
            prompt_txt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            inputs = tok([prompt_txt], return_tensors="pt").to(dev)
            max_new = min(4096, int(payload.get("max_tokens", 3200)))
            temp = float(payload.get("temperature", 0.55))
            with torch.inference_mode():
                gen_ids = mdl.generate(
                    **inputs,
                    max_new_tokens=max_new,
                    do_sample=(temp > 0.05),
                    temperature=max(0.1, temp),
                    top_p=0.9,
                    pad_token_id=tok.eos_token_id,
                )
            out_ids = gen_ids[0][inputs.input_ids.shape[1] :]
            txt_out = tok.decode(out_ids, skip_special_tokens=True).strip()
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"text": txt_out, "model": model_id, "device": dev})

        else:
            raise ValueError(f"Unsupported job kind: {kind}")

    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", elapsed=round(time.time() - t0, 2), error=f"{exc}\n{traceback.format_exc()}")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _send_json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if self.headers.get("Authorization", "") == f"Bearer {AUTH_TOKEN}":
            return True
        self._send_json(401, {"ok": False, "error": "unauthorized"})
        return False

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            du = shutil.disk_usage(str(WORK_DIR))
            with JOBS_LOCK:
                active = [k for k, v in JOBS.items() if v.get("status") in ("queued", "running")]
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "garychen_gemini4_carbon_worker",
                    "port": PORT,
                    "work_dir": str(WORK_DIR),
                    "disk_free_gb": round(du.free / (1024 ** 3), 2),
                    "gpu": gpu_stats(),
                    "loaded_models": list(MODELS.keys()),
                    "active_jobs": active,
                },
            )
            return
        if not self._authorized():
            return
        if u.path.startswith("/job/status/"):
            jid = u.path.split("/job/status/", 1)[1]
            with JOBS_LOCK:
                info = dict(JOBS.get(jid) or {})
            self._send_json(200 if info else 404, info or {"ok": False, "error": "not_found"})
            return
        if u.path.startswith("/download/"):
            rel = u.path.split("/download/", 1)[1].lstrip("/")
            target = (JOBS_DIR / rel).resolve()
            if JOBS_DIR.resolve() not in target.parents or not target.exists():
                self._send_json(404, {"ok": False, "error": "file_not_found"})
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send_json(404, {"ok": False, "error": "unknown_route"})

    def do_POST(self):
        if not self._authorized():
            return
        n = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(n).decode("utf-8") if n > 0 else "{}")
        if self.path == "/upload_ref":
            name = Path(payload["name"]).name
            REFS_DIR.mkdir(parents=True, exist_ok=True)
            data = base64.b64decode(payload["b64"])
            (REFS_DIR / name).write_bytes(data)
            self._send_json(200, {"ok": True, "name": name, "bytes": len(data)})
            return
        if self.path == "/job/submit":
            jid = payload.get("job_id") or f"gc_{uuid.uuid4().hex[:10]}"
            kind = payload["kind"]
            with JOBS_LOCK:
                JOBS[jid] = {"job_id": jid, "kind": kind, "status": "queued", "progress": "0", "submitted_at": time.time()}
            threading.Thread(target=run_job, args=(jid, kind, payload), daemon=True).start()
            self._send_json(200, {"ok": True, "job_id": jid, "status": "queued"})
            return
        self._send_json(404, {"ok": False, "error": "unknown_post_route"})


def main():
    global WORK_DIR, REFS_DIR, JOBS_DIR, CACHE_DIR, AUTH_TOKEN, PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default=str(WORK_DIR))
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--token", default=AUTH_TOKEN)
    args = ap.parse_args()
    WORK_DIR = Path(args.work_dir).resolve()
    REFS_DIR = WORK_DIR / "refs"
    JOBS_DIR = WORK_DIR / "jobs"
    CACHE_DIR = WORK_DIR / "hf_cache"
    PORT = args.port
    AUTH_TOKEN = args.token
    for d in (WORK_DIR, REFS_DIR, JOBS_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    print(f"[garychen-worker] listening on 0.0.0.0:{PORT} work={WORK_DIR}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
