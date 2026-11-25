from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

from .config import ASSETS_DIR, RemoteNodeEndpoint, load_cluster_endpoints
from .sfx import synthesize_sfx
from .tts_normalizer import to_spoken_tts_text


class GarychenVoiceCloner:
    """
    V3 Studio Bilingual Voice Cloner:
      - Decouples `display_clauses` (crisp `$1,305 億`, `211,995 ★`, `CI/CD`) from `spoken_clauses`
        (`一千三百零五億美金`, `二十一萬兩千顆星`, `C I C D`) so F5-TTS pronounces every number & English term like real Gary Chen!
      - Synthesizes full continuous paragraphs at `nfe_step=48` (`sway_sampling_coef=-1.0`) on RTX PRO 6000 Blackwell
        and aligns exact word-level timestamps back onto `display_clauses` via Whisper!
      - Applies 15ms cosine micro-fades, subtle -29 dBFS motion SFX synced to 60fps spring reveals, and Shure-SM7B warm EQ (-20.5 LUFS).
    """

    def __init__(self):
        self.refs_dir = ASSETS_DIR / "voice_refs"
        self.manifest = json.loads((self.refs_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.ref_by_style = {item["style"]: item for item in self.manifest}

    def _ensure_refs_uploaded(self, ep: RemoteNodeEndpoint):
        headers = {"Authorization": f"Bearer {ep.token}"}
        with httpx.Client(timeout=30.0) as client:
            for item in self.manifest:
                wav_path = self.refs_dir / item["name"]
                b64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")
                r = client.post(f"{ep.url}/upload_ref", headers=headers, json={"name": item["name"], "b64": b64})
                r.raise_for_status()

    def synthesize_beats(self, beat_items: list[dict], out_dir: Path) -> tuple[list[dict], str]:
        """
        beat_items: [{"id": "beat_01", "clauses": [...], "spoken_clauses": [...], "voice_style": "hook|explainer|warm", "sfx_cue": "pop"}]
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        meta_cache_file = out_dir / "alignment_manifest.json"
        if meta_cache_file.exists():
            cached_list = json.loads(meta_cache_file.read_text(encoding="utf-8"))
            if len(cached_list) == len(beat_items) and all(Path(x["wav_path"]).exists() for x in cached_list):
                return cached_list, "local_disk_cache"

        healthy_eps: list[tuple[int, RemoteNodeEndpoint, list[str]]] = []
        for ep in load_cluster_endpoints():
            try:
                hr = httpx.get(f"{ep.url}/health", timeout=5.0)
                if hr.status_code != 200:
                    continue
                hj = hr.json()
                gpu = hj.get("gpu") or {}
                has_fast_cuda = bool(gpu.get("cuda_available") and int(gpu.get("free_mb", 0)) >= 2400)
                rank = 0 if ("colab" in ep.name and has_fast_cuda) else (1 if has_fast_cuda else (2 if "mps" in ep.name else 3))
                healthy_eps.append((rank, ep, hj.get("capabilities") or []))
            except Exception:
                pass
        healthy_eps.sort(key=lambda t: t[0])

        for _, ep, caps in healthy_eps:
            try:
                job_kind = "tts_paragraphs" if "tts_paragraphs" in caps else "tts_batch"
                print(f"[voice_cloner] Dispatching {len(beat_items)} bilingual paragraph beats ({job_kind}) to {ep.name}", flush=True)
                self._ensure_refs_uploaded(ep)

                by_style: dict[str, list[dict]] = {}
                for it in beat_items:
                    st = it.get("voice_style", "explainer")
                    if st not in self.ref_by_style:
                        st = "explainer"
                    by_style.setdefault(st, []).append(it)

                results_map: dict[str, dict] = {}
                headers = {"Authorization": f"Bearer {ep.token}"}
                with httpx.Client(timeout=60.0) as client:
                    for style, group in by_style.items():
                        ref_info = self.ref_by_style[style]
                        payload_items = []
                        for x in group:
                            disp_cl = x["clauses"]
                            spok_cl = x.get("spoken_clauses") or [to_spoken_tts_text(c) for c in disp_cl]
                            payload_items.append(
                                {
                                    "id": x["id"],
                                    "clauses": disp_cl,
                                    "spoken_clauses": spok_cl,
                                    "text": "，".join(spok_cl),
                                }
                            )
                        sub_r = client.post(
                            f"{ep.url}/job/submit",
                            headers=headers,
                            json={
                                "kind": job_kind,
                                "ref_name": ref_info["name"],
                                "ref_text": ref_info["ref_text"],
                                "speed": 1.03 if style == "hook" else 1.01,
                                "nfe_step": 48,
                                "items": payload_items,
                            },
                        )
                        sub_r.raise_for_status()
                        jid = sub_r.json()["job_id"]
                        t_start = time.time()
                        while time.time() - t_start < 1200:
                            time.sleep(2.0)
                            sr = client.get(f"{ep.url}/job/status/{jid}", headers=headers)
                            sr.raise_for_status()
                            st_data = sr.json()
                            if st_data.get("status") == "done":
                                dev_used = st_data.get("result", {}).get("device", "cuda")
                                for out_item in st_data["result"]["outputs"]:
                                    dl = client.get(f"{ep.url}/download/{out_item['rel_path']}", headers=headers)
                                    dl.raise_for_status()
                                    local_wav = out_dir / f"{out_item['id']}.wav"
                                    local_wav.write_bytes(dl.content)
                                    dur = round(sf.info(str(local_wav)).duration, 3)
                                    aligned = out_item.get("aligned_clauses")
                                    orig_cl = next(g["clauses"] for g in group if g["id"] == out_item["id"])
                                    if not aligned or len(aligned) != len(orig_cl):
                                        aligned = self._proportional_fallback_align(orig_cl, dur)
                                    else:
                                        # Ensure display text is always exact crisp Traditional Chinese display string
                                        for ci, disp_s in enumerate(orig_cl):
                                            aligned[ci]["text"] = disp_s
                                    results_map[out_item["id"]] = {
                                        "id": out_item["id"],
                                        "wav_path": str(local_wav),
                                        "duration": dur,
                                        "aligned_clauses": aligned,
                                        "device": dev_used,
                                    }
                                break
                            if st_data.get("status") == "error":
                                raise RuntimeError(f"Remote TTS error on {ep.name}: {st_data.get('error', '')[:320]}")
                        else:
                            raise TimeoutError(f"Timed out waiting for TTS job {jid}")

                ordered: list[dict] = []
                for it in beat_items:
                    r_entry = results_map[it["id"]]
                    r_entry["sfx_cue"] = it.get("sfx_cue", "pop")
                    ordered.append(r_entry)
                meta_cache_file.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
                return ordered, f"{ep.name}:{ordered[0].get('device', 'cuda')}"
            except Exception as exc:
                print(f"[voice_cloner] Node {ep.name} failed ({exc}), trying next...", flush=True)

        raise RuntimeError("No PyTorch F5-TTS worker reachable.")

    @staticmethod
    def _proportional_fallback_align(clauses: list[str], total_dur: float) -> list[dict]:
        weights = [max(1, len(c)) for c in clauses]
        tot = sum(weights)
        cur = 0.0
        out = []
        for i, c in enumerate(clauses):
            d = total_dur * (weights[i] / tot)
            end = total_dur if i == len(clauses) - 1 else cur + d
            out.append({"text": c, "rel_start": round(cur, 3), "rel_end": round(end, 3)})
            cur = end
        return out

    @staticmethod
    def _apply_cosine_fade(audio: np.ndarray, sr: int, fade_ms: float = 16.0) -> np.ndarray:
        n = min(len(audio) // 4, int(sr * fade_ms / 1000.0))
        if n <= 4:
            return audio
        out = audio.copy()
        ramp = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n, dtype=np.float32)))
        out[:n] *= ramp
        out[-n:] *= ramp[::-1]
        return out

    @classmethod
    def build_master_timeline(
        cls,
        beat_results: list[dict],
        out_wav: Path,
        inter_beat_pause: float = 0.25,
        chapter_pause: float = 0.44,
    ) -> tuple[float, list[dict]]:
        sr = 44100
        voice_chunks: list[np.ndarray] = []
        sfx_events: list[tuple[int, str]] = []
        cues: list[dict] = []

        cursor = 0.18
        voice_chunks.append(np.zeros(int(cursor * sr), dtype=np.float32))

        for b_idx, br in enumerate(beat_results):
            if b_idx > 0:
                gap = chapter_pause if br.get("sfx_cue") == "whoosh" else inter_beat_pause
                voice_chunks.append(np.zeros(int(gap * sr), dtype=np.float32))
                cursor += gap

            beat_start = cursor
            sfx_kind = br.get("sfx_cue", "pop")
            if sfx_kind and sfx_kind != "none":
                sfx_events.append((max(0, int((beat_start - 0.02) * sr)), sfx_kind))

            audio, file_sr = sf.read(br["wav_path"], dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if file_sr != sr:
                n_len = int(round(len(audio) * sr / file_sr))
                audio = np.interp(np.linspace(0, len(audio) - 1, n_len), np.arange(len(audio)), audio).astype(np.float32)

            audio = cls._apply_cosine_fade(audio, sr, fade_ms=16.0)
            dur = len(audio) / sr
            aligned = br.get("aligned_clauses") or []
            for s_idx, cl in enumerate(aligned):
                c_start = beat_start + float(cl["rel_start"])
                c_end = beat_start + min(dur, float(cl["rel_end"]))
                cues.append(
                    {
                        "beat_id": br["id"],
                        "step_idx": s_idx,
                        "start": round(c_start, 3),
                        "end": round(c_end, 3),
                        "text": cl["text"],
                    }
                )
                if s_idx > 0:
                    sfx_events.append((int(c_start * sr), "terminal" if sfx_kind == "terminal" else "pop"))

            voice_chunks.append(audio)
            cursor += dur

        voice_chunks.append(np.zeros(int(0.45 * sr), dtype=np.float32))
        voice_track = np.concatenate(voice_chunks)

        sfx_bed = np.zeros_like(voice_track)
        for sample_pos, skind in sfx_events:
            clip = synthesize_sfx(skind, sr=sr) * 0.72
            if len(clip) == 0 or sample_pos >= len(sfx_bed):
                continue
            end_pos = min(len(sfx_bed), sample_pos + len(clip))
            sfx_bed[sample_pos:end_pos] += clip[: end_pos - sample_pos]

        mixed = np.clip(voice_track + sfx_bed, -0.98, 0.98)
        tmp_wav = out_wav.with_suffix(".raw.wav")
        sf.write(str(tmp_wav), mixed, sr, subtype="PCM_16")

        # Studio Shure-SM7B warm baritone EQ + -20.5 LUFS loudness mastering matching @garychenai
        af_chain = (
            "highpass=f=75,"
            "equalizer=f=175:t=q:w=1.1:g=1.4,"
            "equalizer=f=3500:t=q:w=1.4:g=0.9,"
            "loudnorm=I=-20.5:TP=-1.5:LRA=5.5"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_wav), "-af", af_chain, "-ar", "44100", "-ac", "2", str(out_wav)],
            check=True,
            capture_output=True,
        )
        tmp_wav.unlink(missing_ok=True)
        total_dur = round(sf.info(str(out_wav)).duration, 3)
        return total_dur, cues
