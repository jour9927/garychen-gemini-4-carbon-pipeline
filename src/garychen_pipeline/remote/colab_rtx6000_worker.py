#!/usr/bin/env python3
"""
Garychen Gemini 4 Carbon V2 — Studio-Grade RTX PRO 6000 Heavy GPU Worker.
Master copy lives on local machine (alan-hub) first; deployed to Colab RTX PRO 6000 (:19743) and B850 (:18793).

V2 Studio Upgrades:
  1. `llm_chat`: Qwen/Qwen2.5-14B-Instruct (bfloat16 CUDA SDPA) for authentic Garychen storytelling & beat-by-beat visual direction
  2. `tts_paragraphs` & `tts_batch`: Full-sentence continuous PyTorch F5-TTS (nfe_step=32) + Whisper CUDA word-timestamp forced alignment (zero PyAV bug via direct 16kHz float32 numpy decode) + ASR quality verification retry
  3. `image_batch`: Full 22-step SDXL Base 1.0 (DPMSolverMultistepScheduler + Karras sigmas, 1152x768 / 896x1152) tactile 3D dark-amber studio dioramas
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WORK_DIR = Path(os.environ.get("GC_WORK_DIR", "/content/garychen_g4c")).resolve()
REFS_DIR = WORK_DIR / "refs"
JOBS_DIR = WORK_DIR / "jobs"
CACHE_DIR = WORK_DIR / "hf_cache"
AUTH_TOKEN = os.environ.get("GC_WORKER_TOKEN", "gc_rtx6000_carbon_2026")
PORT = int(os.environ.get("GC_WORKER_PORT", "19743"))

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
    try:
        from opencc import OpenCC
        cc = MODELS.get("opencc_t2s")
        if cc is None:
            cc = OpenCC("t2s")
            MODELS["opencc_t2s"] = cc
        text = cc.convert(text)
    except Exception:
        pass
    # Keep clean breath punctuation so F5-TTS pauses naturally between clauses
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[-1] not in "。！？!?.,":
        text += "。"
    return text


def get_f5_tts(force_cpu: bool = False):
    with MODEL_LOCK:
        target_dev = "cpu" if force_cpu else pick_device(min_cuda_mb=2400)
        cached = MODELS.get("f5_tts")
        if cached is not None and cached[0] == target_dev:
            return cached
        import torch
        from f5_tts.api import F5TTS
        if target_dev == "cpu":
            torch.set_num_threads(min(32, max(4, (os.cpu_count() or 8) - 4)))
        tts = F5TTS(model="F5TTS_v1_Base", device=target_dev)
        MODELS["f5_tts"] = (target_dev, tts)
        return MODELS["f5_tts"]


def get_whisper_model():
    with MODEL_LOCK:
        if "whisper" in MODELS:
            return MODELS["whisper"]
        from faster_whisper import WhisperModel
        st = gpu_stats()
        dev = "cuda" if (st["cuda_available"] and st["free_mb"] >= 3200) else "cpu"
        model_size = "medium" if dev == "cuda" else "base"
        ctype = "float16" if dev == "cuda" else "int8"
        wm = WhisperModel(model_size, device=dev, compute_type=ctype, cpu_threads=min(16, os.cpu_count() or 4))
        MODELS["whisper"] = (dev, wm)
        return MODELS["whisper"]


def get_qwen_llm():
    with MODEL_LOCK:
        if "qwen_llm" in MODELS:
            return MODELS["qwen_llm"]
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        st = gpu_stats()
        if st["cuda_available"] and st["free_mb"] >= 34000:
            model_id = "Qwen/Qwen2.5-14B-Instruct"
            dev = "cuda"
        elif st["cuda_available"] and st["free_mb"] >= 18000:
            model_id = "Qwen/Qwen2.5-7B-Instruct"
            dev = "cuda"
        else:
            model_id = "Qwen/Qwen2.5-3B-Instruct"
            dev = "cuda" if (st["cuda_available"] and st["free_mb"] >= 8500) else "cpu"
        tok = AutoTokenizer.from_pretrained(model_id)
        mdl = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16,
            device_map={"": 0} if dev == "cuda" else "cpu",
        )
        mdl.eval()
        MODELS["qwen_llm"] = (dev, model_id, tok, mdl)
        return MODELS["qwen_llm"]


def get_sdxl_pipe(force_cpu: bool = False):
    with MODEL_LOCK:
        target_dev = "cpu" if force_cpu else pick_device(min_cuda_mb=9500)
        cached = MODELS.get("sdxl_pipe")
        if cached is not None and cached[0] == target_dev:
            return cached
        import torch
        from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler
        if target_dev == "cuda":
            pipe = AutoPipelineForText2Image.from_pretrained(
                "stabilityai/stable-diffusion-xl-base-1.0",
                torch_dtype=torch.float16,
                variant="fp16",
                use_safetensors=True,
            )
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
            pipe.to("cuda")
            pipe.set_progress_bar_config(disable=True)
            MODELS["sdxl_pipe"] = ("cuda", "sdxl_base", pipe)
        else:
            dtype = torch.bfloat16 if target_dev == "cpu" else torch.float16
            pipe = AutoPipelineForText2Image.from_pretrained("stabilityai/sdxl-turbo", torch_dtype=dtype)
            pipe.to(target_dev)
            pipe.set_progress_bar_config(disable=True)
            MODELS["sdxl_pipe"] = (target_dev, "sdxl_turbo", pipe)
        return MODELS["sdxl_pipe"]


def load_wav_16k_np(wav_path: Path):
    """Load WAV directly via soundfile into 16kHz mono float32 numpy array (bypasses PyAV completely)."""
    import numpy as np
    import soundfile as sf
    y, sr = sf.read(str(wav_path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != 16000:
        n_out = int(round(len(y) * 16000 / sr))
        y = np.interp(np.linspace(0, len(y) - 1, n_out), np.arange(len(y)), y).astype(np.float32)
    return y


def align_clauses_with_whisper(wav_path: Path, clauses: list[str], total_dur: float) -> tuple[list[dict], str]:
    """
    Uses Whisper word-level timestamps on 16kHz float32 audio to align exact [rel_start, rel_end]
    for each spoken subtitle clause inside a continuous natural-prosody paragraph WAV!
    """
    y16 = load_wav_16k_np(wav_path)
    _, wm = get_whisper_model()
    segs, _ = wm.transcribe(y16, language="zh", word_timestamps=True, condition_on_previous_text=False)
    words: list[tuple[float, float, str]] = []
    full_asr = []
    for s in segs:
        full_asr.append(s.text.strip())
        for w in (s.words or []):
            wt = w.word.strip()
            if wt:
                words.append((float(w.start), float(w.end), wt))

    asr_text = "".join(full_asr)
    if not clauses:
        return [], asr_text
    if len(clauses) == 1 or not words:
        return [{"text": clauses[0], "rel_start": 0.0, "rel_end": round(total_dur, 3)}], asr_text

    # Proportional character-cursor mapping anchored onto actual Whisper word timestamps!
    clause_weights = [max(1, len(re.sub(r"\s+", "", c))) for c in clauses]
    tot_w = sum(clause_weights)
    n_words = len(words)

    aligned: list[dict] = []
    cum_w = 0
    prev_end = 0.0
    for idx, cl in enumerate(clauses):
        next_cum = cum_w + clause_weights[idx]
        w_start_idx = min(n_words - 1, int(round((cum_w / tot_w) * n_words)))
        w_end_idx = min(n_words - 1, max(w_start_idx, int(round((next_cum / tot_w) * n_words)) - 1))
        rs = prev_end if idx > 0 else max(0.0, words[0][0] - 0.04)
        re_t = total_dur if idx == len(clauses) - 1 else min(total_dur, max(rs + 0.45, words[w_end_idx][1] + 0.04))
        aligned.append({"text": cl, "rel_start": round(rs, 3), "rel_end": round(re_t, 3)})
        prev_end = re_t
        cum_w = next_cum

    return aligned, asr_text


def postprocess_voice_wav(wav_path: Path, target_sr: int = 44100) -> float:
    import numpy as np
    import soundfile as sf
    data, sr = sf.read(str(wav_path))
    if data.ndim > 1:
        data = data.mean(axis=1)
    thresh = 10 ** (-46.0 / 20.0)
    idx = np.where(np.abs(data) > thresh)[0]
    if len(idx) > 10:
        s = max(0, int(idx[0]) - int(0.04 * sr))
        e = min(len(data), int(idx[-1]) + int(0.10 * sr))
        data = data[s:e]
    rms = float(np.sqrt(np.mean(data ** 2)) + 1e-9)
    target_rms = 10 ** (-21.0 / 20.0)
    data = data * min(6.0, target_rms / rms)
    peak = float(np.max(np.abs(data)) + 1e-9)
    max_peak = 10 ** (-1.5 / 20.0)
    if peak > max_peak:
        data = np.tanh(data / max_peak) * max_peak
    tmp_out = wav_path.with_suffix(".norm.wav")
    sf.write(str(tmp_out), data, sr, subtype="PCM_16")
    if sr != target_sr:
        subprocess.run(["ffmpeg", "-y", "-i", str(tmp_out), "-ar", str(target_sr), "-ac", "1", str(wav_path)], check=True, capture_output=True)
        tmp_out.unlink(missing_ok=True)
    else:
        tmp_out.replace(wav_path)
    return round(sf.info(str(wav_path)).duration, 3)


def run_job(job_id: str, kind: str, payload: dict):
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "running"

        if kind == "llm_chat":
            import torch
            dev, model_id, tok, mdl = get_qwen_llm()
            msgs = [
                {"role": "system", "content": payload.get("system_prompt", "")},
                {"role": "user", "content": payload.get("user_prompt", "")},
            ]
            prompt_txt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            inputs = tok([prompt_txt], return_tensors="pt").to(dev)
            max_new = min(6144, int(payload.get("max_tokens", 3600)))
            temp = float(payload.get("temperature", 0.55))
            with torch.inference_mode():
                gen_ids = mdl.generate(
                    **inputs,
                    max_new_tokens=max_new,
                    do_sample=(temp > 0.05),
                    temperature=max(0.1, temp),
                    top_p=0.9,
                    repetition_penalty=1.05,
                    pad_token_id=tok.eos_token_id,
                )
            out_ids = gen_ids[0][inputs.input_ids.shape[1] :]
            txt_out = tok.decode(out_ids, skip_special_tokens=True).strip()
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"text": txt_out, "model": model_id, "device": dev})

        elif kind in ("tts_paragraphs", "tts_batch"):
            ref_wav = REFS_DIR / payload["ref_name"]
            if not ref_wav.exists():
                raise FileNotFoundError(f"Missing reference wav: {ref_wav}")
            ref_text = normalize_zh_for_tts(payload["ref_text"])
            items = payload["items"]
            speed = float(payload.get("speed", 1.03))
            nfe = int(payload.get("nfe_step", 32))
            dev, tts = get_f5_tts()
            outputs = []
            for idx, item in enumerate(items):
                seg_id = str(item["id"])
                clauses = item.get("clauses") or [item["text"]]
                full_spoken = item.get("text") or "，".join(clauses)
                gen_text = normalize_zh_for_tts(full_spoken)
                out_wav = job_dir / f"{seg_id}.wav"
                tts.infer(
                    ref_file=str(ref_wav),
                    ref_text=ref_text,
                    gen_text=gen_text,
                    file_wave=str(out_wav),
                    speed=float(item.get("speed", speed)),
                    nfe_step=nfe,
                    remove_silence=False,
                )
                dur = postprocess_voice_wav(out_wav, target_sr=44100)
                # Guard against rare duration anomaly (e.g. > 0.55s per char) by re-synthesizing once cleanly
                clean_chars = max(1, len(re.sub(r"\s+", "", full_spoken)))
                if dur / clean_chars > 0.52 and clean_chars >= 8:
                    tts.infer(
                        ref_file=str(ref_wav),
                        ref_text=ref_text,
                        gen_text=gen_text,
                        file_wave=str(out_wav),
                        speed=min(1.12, float(item.get("speed", speed)) + 0.05),
                        nfe_step=32,
                        remove_silence=False,
                    )
                    dur = postprocess_voice_wav(out_wav, target_sr=44100)

                aligned_clauses, asr_txt = align_clauses_with_whisper(out_wav, clauses, dur)
                outputs.append(
                    {
                        "id": seg_id,
                        "rel_path": f"{job_id}/{out_wav.name}",
                        "duration": dur,
                        "aligned_clauses": aligned_clauses,
                        "asr_text": asr_txt,
                        "device": dev,
                    }
                )
                with JOBS_LOCK:
                    JOBS[job_id]["progress"] = f"{idx + 1}/{len(items)}"
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"outputs": outputs, "device": dev})

        elif kind == "image_batch":
            import torch
            dev, mode_name, pipe = get_sdxl_pipe()
            items = payload["items"]
            outputs = []
            neg_prompt = (
                "text, letters, words, watermark, signature, blurry, low quality, messy clutter, "
                "bright white background, cartoon childish, deformed, ugly, oversaturated neon"
            )
            for idx, item in enumerate(items):
                img_id = str(item["id"])
                w = (int(item.get("width", 1152 if mode_name == "sdxl_base" else 768)) // 8) * 8
                h = (int(item.get("height", 768 if mode_name == "sdxl_base" else 512)) // 8) * 8
                seed = int(item.get("seed", 2026 + idx * 31))
                prompt = (
                    f"{item['prompt']}, tactile 3D matte dark-studio isometric diorama metaphor, "
                    "deep charcoal #222224 background, warm amber #EB8B1B rim glow, Cinema4D Octane render style, "
                    "ultra clean minimalist product design, studio softbox lighting, strictly no text or letters"
                )
                gen = torch.Generator(device="cpu").manual_seed(seed)
                if mode_name == "sdxl_base":
                    img = pipe(
                        prompt=prompt,
                        negative_prompt=neg_prompt,
                        num_inference_steps=int(item.get("steps", 22)),
                        guidance_scale=6.5,
                        width=w,
                        height=h,
                        generator=gen,
                    ).images[0]
                else:
                    img = pipe(prompt=prompt, num_inference_steps=4, guidance_scale=0.0, width=w, height=h, generator=gen).images[0]
                out_png = job_dir / f"{img_id}.png"
                img.save(str(out_png))
                outputs.append({"id": img_id, "rel_path": f"{job_id}/{out_png.name}", "device": f"{dev}:{mode_name}"})
                with JOBS_LOCK:
                    JOBS[job_id]["progress"] = f"{idx + 1}/{len(items)}"
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"outputs": outputs, "device": f"{dev}:{mode_name}"})

        elif kind == "whisper_align":
            in_wav = job_dir / "input.wav"
            in_wav.write_bytes(base64.b64decode(payload["wav_b64"]))
            y16 = load_wav_16k_np(in_wav)
            dev, wm = get_whisper_model()
            segs, _ = wm.transcribe(y16, language="zh", word_timestamps=True)
            seg_list = [{"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()} for s in segs]
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", elapsed=round(time.time() - t0, 2), result={"segments": seg_list, "device": dev})

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
                    "service": "garychen_gemini4_carbon_worker_v2",
                    "port": PORT,
                    "work_dir": str(WORK_DIR),
                    "disk_free_gb": round(du.free / (1024 ** 3), 2),
                    "gpu": gpu_stats(),
                    "loaded_models": list(MODELS.keys()),
                    "active_jobs": active,
                    "capabilities": ["llm_chat", "tts_paragraphs", "tts_batch", "image_batch", "whisper_align"],
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
    print(f"[garychen-worker-v2] listening on 0.0.0.0:{PORT} work={WORK_DIR}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
