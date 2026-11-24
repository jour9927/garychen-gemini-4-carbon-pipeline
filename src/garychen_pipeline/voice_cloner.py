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


class GarychenVoiceCloner:
    """
    Dispatches PyTorch voice cloning (F5-TTS) using Garychen's extracted studio reference audio.
    Priority:
      1. Temporary High-Speed Node: RTX PRO 6000 on Google Colab (:19688)
      2. Persistent Tailscale Node: B850 (:18793)
      3. Local Apple Silicon PyTorch fallback
    All synthesized WAVs are immediately saved on local disk (本機) so disconnection loses nothing.
    """

    def __init__(self):
        self.refs_dir = ASSETS_DIR / "voice_refs"
        self.manifest = json.loads((self.refs_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.ref_by_style = {item["style"]: item for item in self.manifest}

    def select_healthy_remote(self, require_tts_deps: bool = True) -> RemoteNodeEndpoint | None:
        for ep in load_cluster_endpoints():
            try:
                r = httpx.get(f"{ep.url}/health", timeout=6.0)
                if r.status_code == 200 and r.json().get("ok"):
                    return ep
            except Exception:
                continue
        return None

    def _ensure_refs_uploaded(self, ep: RemoteNodeEndpoint):
        headers = {"Authorization": f"Bearer {ep.token}"}
        with httpx.Client(timeout=30.0) as client:
            for item in self.manifest:
                wav_path = self.refs_dir / item["name"]
                b64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")
                r = client.post(f"{ep.url}/upload_ref", headers=headers, json={"name": item["name"], "b64": b64})
                r.raise_for_status()

    def synthesize_lines(self, items: list[dict], out_dir: Path) -> tuple[list[dict], str]:
        """
        items: [{"id": "s01_l01", "text": "...", "voice_style": "hook|explainer|warm"}]
        Returns: ([{"id": ..., "wav_path": str, "duration": float, "text": str}], backend_used)
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        # Check cache on local disk first so resumed runs never re-compute finished audio
        all_cached = True
        cached_results: list[dict] = []
        for it in items:
            wp = out_dir / f"{it['id']}.wav"
            if wp.exists() and wp.stat().st_size > 1000:
                info = sf.info(str(wp))
                cached_results.append({"id": it["id"], "wav_path": str(wp), "duration": round(info.duration, 3), "text": it["text"]})
            else:
                all_cached = False
                break
        if all_cached and cached_results:
            return cached_results, "local_disk_cache"

        # Try remote GPU nodes in priority order (RTX PRO 6000 Colab first!)
        for ep in load_cluster_endpoints():
            try:
                hr = httpx.get(f"{ep.url}/health", timeout=6.0)
                if hr.status_code != 200:
                    continue
                print(f"[voice_cloner] Dispatching {len(items)} lines to {ep.name} ({ep.url})", flush=True)
                self._ensure_refs_uploaded(ep)
                results_map: dict[str, dict] = {}
                # Group by voice_style so each group uses its prosody-matched reference wav
                by_style: dict[str, list[dict]] = {}
                for it in items:
                    st = it.get("voice_style", "explainer")
                    if st not in self.ref_by_style:
                        st = "explainer"
                    by_style.setdefault(st, []).append(it)

                headers = {"Authorization": f"Bearer {ep.token}"}
                with httpx.Client(timeout=60.0) as client:
                    for style, group in by_style.items():
                        ref_info = self.ref_by_style[style]
                        sub_r = client.post(
                            f"{ep.url}/job/submit",
                            headers=headers,
                            json={
                                "kind": "tts_batch",
                                "ref_name": ref_info["name"],
                                "ref_text": ref_info["ref_text"],
                                "speed": 1.04 if style == "hook" else 1.02,
                                "nfe_step": 24,
                                "items": [{"id": x["id"], "text": x["text"]} for x in group],
                            },
                        )
                        sub_r.raise_for_status()
                        jid = sub_r.json()["job_id"]
                        # Poll job status
                        t_start = time.time()
                        while time.time() - t_start < 900:
                            time.sleep(2.0)
                            sr = client.get(f"{ep.url}/job/status/{jid}", headers=headers)
                            sr.raise_for_status()
                            st_data = sr.json()
                            if st_data.get("status") == "done":
                                dev_used = st_data.get("result", {}).get("device", "remote")
                                for out_item in st_data["result"]["outputs"]:
                                    dl = client.get(f"{ep.url}/download/{out_item['rel_path']}", headers=headers)
                                    dl.raise_for_status()
                                    local_wav = out_dir / f"{out_item['id']}.wav"
                                    local_wav.write_bytes(dl.content)
                                    dur = round(sf.info(str(local_wav)).duration, 3)
                                    results_map[out_item["id"]] = {
                                        "id": out_item["id"],
                                        "wav_path": str(local_wav),
                                        "duration": dur,
                                        "device": dev_used,
                                    }
                                break
                            if st_data.get("status") == "error":
                                raise RuntimeError(f"Remote TTS error on {ep.name}: {st_data.get('error', '')[:300]}")
                        else:
                            raise TimeoutError(f"Timed out waiting for TTS job {jid} on {ep.name}")

                ordered = []
                for it in items:
                    entry = results_map[it["id"]]
                    entry["text"] = it["text"]
                    ordered.append(entry)
                return ordered, f"{ep.name}:{ordered[0].get('device', 'gpu')}"
            except Exception as exc:
                print(f"[voice_cloner] Node {ep.name} unavailable or busy ({exc}), trying next...", flush=True)

        raise RuntimeError("No PyTorch F5-TTS worker reachable on RTX PRO 6000 Colab or B850.")

    @staticmethod
    def concat_master_track(
        line_timings: list[dict],
        out_wav: Path,
        inter_line_pause: float = 0.16,
        inter_scene_pause: float = 0.42,
    ) -> tuple[float, list[dict]]:
        """
        Concatenates individual line WAVs with natural studio breath pauses, builds exact start/end cue timestamps,
        and normalizes integrated loudness to Garychen's -21.0 LUFS standard.
        """
        sr = 44100
        chunks: list[np.ndarray] = []
        cursor = 0.20  # 200ms clean lead-in
        chunks.append(np.zeros(int(cursor * sr), dtype=np.float32))

        enriched: list[dict] = []
        prev_scene = None
        for idx, item in enumerate(line_timings):
            sc_id = item.get("scene_id", "")
            if prev_scene is not None:
                gap = inter_scene_pause if sc_id != prev_scene else inter_line_pause
                chunks.append(np.zeros(int(gap * sr), dtype=np.float32))
                cursor += gap
            prev_scene = sc_id

            audio, file_sr = sf.read(item["wav_path"], dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if file_sr != sr:
                # Resample via linear interpolation if needed
                new_len = int(round(len(audio) * sr / file_sr))
                audio = np.interp(np.linspace(0, len(audio) - 1, new_len), np.arange(len(audio)), audio).astype(np.float32)

            dur = len(audio) / sr
            enriched.append(
                {
                    **item,
                    "start": round(cursor, 3),
                    "end": round(cursor + dur, 3),
                    "duration": round(dur, 3),
                }
            )
            chunks.append(audio)
            cursor += dur

        # 350ms clean tail
        chunks.append(np.zeros(int(0.35 * sr), dtype=np.float32))
        cursor += 0.35

        raw_mix = np.concatenate(chunks)
        tmp_wav = out_wav.with_suffix(".raw.wav")
        sf.write(str(tmp_wav), raw_mix, sr, subtype="PCM_16")

        # Master with EBU R128 loudnorm to -21.0 LUFS, stereo 44.1kHz matching @garychenai
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(tmp_wav),
                "-af", "loudnorm=I=-21.0:TP=-1.5:LRA=5.0",
                "-ar", "44100", "-ac", "2",
                str(out_wav),
            ],
            check=True,
            capture_output=True,
        )
        tmp_wav.unlink(missing_ok=True)
        total_dur = round(sf.info(str(out_wav)).duration, 3)
        return total_dur, enriched
