from __future__ import annotations

import io
import math
import platform
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .config import CrawledSource, DesignTokens, EpisodeScript
from .crawler import CHROME_APP_BIN
from .html_renderer import FONT_BOLD, build_short_beat_html
from .renderer_long import _font, _hex_rgb


class GarychenShortsRenderer:
    """
    V2 Remotion-Grade 1080x1920 @ 60fps Corresponding Funnel Shorts Renderer:
      - Fast 6–8 progressive vertical HTML5/CSS3/SVG beats (changing visual state every ~2.5s)
      - Embeds real crawled dark-mode webpage screenshots + 22-step SDXL 3D dioramas
      - Safe-zone crisp #090909 subtitle pill (Y=1380..1490) + final Long-Video Related Link Funnel CTA!
    """

    def __init__(self, tokens: DesignTokens | None = None):
        self.t = tokens or DesignTokens()

    def _render_subtitle_band(self, text: str) -> tuple[np.ndarray, np.ndarray]:
        W = self.t.short_width
        band_h = 120
        ov = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        font = _font(FONT_BOLD, 44)
        for sz in (44, 38, 32, 27):
            font = _font(FONT_BOLD, sz)
            tb = d.textbbox((0, 0), text, font=font)
            if (tb[2] - tb[0]) <= W - 140:
                break
        tb = d.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pw = min(996, max(320, tw + 74))
        px = (W - pw) // 2
        d.rounded_rectangle((px, 6, px + pw, 112), radius=18, fill=(9, 9, 9, 245))
        d.text((W // 2 - tw // 2, 6 + (106 - th) // 2 - 4), text, font=font, fill=(255, 255, 255, 255))
        arr = np.array(ov, dtype=np.float32)
        return arr[:, :, :3], arr[:, :, 3:4] / 255.0

    def encode_short(
        self,
        script: EpisodeScript,
        line_cues: list[dict],
        master_audio_wav: Path,
        total_duration: float,
        image_map: dict[str, str],
        long_thumb_path: Path | None,
        sources: list[CrawledSource],
        out_mp4: Path,
    ):
        from playwright.sync_api import sync_playwright

        W, H, FPS = self.t.short_width, self.t.short_height, self.t.fps
        total_frames = max(1, int(round(total_duration * FPS)))
        sources_by_id = {s.source_id: s for s in sources}
        sbeats_by_id = {b.beat_id: b for b in script.short_beats}
        orange_np = np.array(_hex_rgb(self.t.accent_orange_hex), dtype=np.uint8)

        needed_states: list[tuple[str, int]] = []
        seen_st: set[tuple[str, int]] = set()
        for c in line_cues:
            st = (c["beat_id"], int(c.get("step_idx", 0)))
            if st not in seen_st:
                seen_st.add(st)
                needed_states.append(st)

        state_frames: dict[tuple[str, int], np.ndarray] = {}
        launch_kwargs = {"headless": True}
        if Path(CHROME_APP_BIN).exists():
            launch_kwargs["executable_path"] = CHROME_APP_BIN

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": W, "height": H, "device_scale_factor": 1})
            for beat_id, step_i in needed_states:
                sb = sbeats_by_id[beat_id]
                html_doc = build_short_beat_html(
                    script=script,
                    sbeat=sb,
                    step_idx=step_i,
                    ai_img_path=image_map.get(beat_id),
                    long_thumb_path=long_thumb_path,
                    sources_by_id=sources_by_id,
                    tokens=self.t,
                )
                page.set_content(html_doc, wait_until="load")
                im = Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB")
                state_frames[(beat_id, step_i)] = np.array(im, dtype=np.uint8)
            browser.close()

        sub_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for c in line_cues:
            txt = c["text"]
            if txt and txt not in sub_cache:
                sub_cache[txt] = self._render_subtitle_band(txt)

        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "5500k", "-profile:v", "high"] if platform.system() == "Darwin" else [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-profile:v", "high"
        ]
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-i", str(master_audio_wav),
            *vcodec,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-shortest", "-movflags", "+faststart",
            str(out_mp4),
        ]

        cue_idx = 0
        n_cues = len(line_cues)
        prev_key = (line_cues[0]["beat_id"], int(line_cues[0].get("step_idx", 0)))
        cur_key = prev_key
        transition_start_f = -999

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for f_idx in range(total_frames):
                t_sec = f_idx / FPS
                while cue_idx + 1 < n_cues and t_sec >= line_cues[cue_idx + 1]["start"] - 0.03:
                    cue_idx += 1
                cue = line_cues[cue_idx]
                next_key = (cue["beat_id"], int(cue.get("step_idx", 0)))
                if next_key != cur_key:
                    prev_key = cur_key
                    cur_key = next_key
                    transition_start_f = f_idx

                target_arr = state_frames[cur_key]
                age = f_idx - transition_start_f
                if 0 <= age < 12:
                    alpha = 1.0 - math.pow(1.0 - (age / 12.0), 3)
                    frame = (state_frames[prev_key] * (1.0 - alpha) + target_arr * alpha).astype(np.uint8)
                else:
                    frame = target_arr.copy()

                if (cue["start"] - 0.03) <= t_sec <= (cue["end"] + 0.12) and cue["text"] in sub_cache:
                    s_rgb, s_a = sub_cache[cue["text"]]
                    roi = frame[1374:1494]
                    frame[1374:1494] = (roi * (1.0 - s_a) + s_rgb * s_a).astype(np.uint8)

                prog_w = max(4, int((f_idx + 1) / total_frames * W))
                frame[0:6, 0:prog_w] = orange_np
                proc.stdin.write(frame.tobytes())
        finally:
            proc.stdin.close()
            stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
            rc = proc.wait()
            if rc != 0:
                raise RuntimeError(f"FFmpeg short V2 encode failed (rc={rc}): {stderr_out[-400:]}")
