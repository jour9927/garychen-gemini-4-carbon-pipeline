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
from .renderer_long import _font, _hex_rgb, composite_roi, extract_rgba_roi


class GarychenShortsRenderer:
    """
    V3 True Layer-Spring 1080x1920 @ 60fps Traffic-Funnel Shorts Compositor:
      - Renders 8 vertical scenes with independent transparent RGBA step layers
      - Animates 60fps spring entrances (`+28px -> 0px`) synced to Whisper clause timestamps
      - Ends with Long-Video Thumbnail + Animated Bottom-Left Related Video CTA
    """

    def __init__(self, tokens: DesignTokens | None = None):
        self.t = tokens or DesignTokens()

    def _render_subtitle_band(self, text: str) -> tuple[np.ndarray, np.ndarray]:
        W = self.t.short_width
        band_h = 118
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
        pw = min(996, max(310, tw + 74))
        px = (W - pw) // 2
        d.rounded_rectangle((px, 6, px + pw, 110), radius=16, fill=(9, 9, 9, 244))
        d.text((W // 2 - tw // 2, 6 + (104 - th) // 2 - 4), text, font=font, fill=(255, 255, 255, 255))
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
        orange_np = np.array(_hex_rgb(self.t.accent_orange_hex), dtype=np.uint8)
        bg_rgb_val = _hex_rgb(self.t.bg_stock_hex if script.avatar_mode else self.t.bg_tutorial_hex)

        base_frames: dict[str, np.ndarray] = {}
        step_rois: dict[tuple[str, int], tuple[int, int, int, int, np.ndarray, np.ndarray] | None] = {}
        settled_frames: dict[tuple[str, int], np.ndarray] = {}

        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        tmp_html_file = out_mp4.parent / "_render_stage_short_v3.html"
        launch_kwargs = {"headless": True}
        if Path(CHROME_APP_BIN).exists():
            launch_kwargs["executable_path"] = CHROME_APP_BIN

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs, args=["--allow-file-access-from-files"])
            page = browser.new_page(viewport={"width": W, "height": H, "device_scale_factor": 1})
            for sb in script.short_beats:
                html_doc, n_steps = build_short_beat_html(
                    script=script,
                    sbeat=sb,
                    ai_img_path=image_map.get(sb.beat_id),
                    long_thumb_path=long_thumb_path,
                    sources_by_id=sources_by_id,
                    tokens=self.t,
                )
                tmp_html_file.write_text(html_doc, encoding="utf-8")
                page.goto(tmp_html_file.resolve().as_uri(), wait_until="load")
                page.evaluate("() => document.fonts.ready")

                page.evaluate(
                    """() => {
                        document.body.classList.remove('transparent-pass');
                        document.querySelectorAll('[data-step]').forEach(el => { el.style.opacity = '0'; });
                    }"""
                )
                b_arr = np.array(Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB"), dtype=np.uint8)
                base_frames[sb.beat_id] = b_arr

                running = b_arr.copy()
                for s_i in range(n_steps):
                    page.evaluate(
                        """(targetStep) => {
                            document.body.classList.add('transparent-pass');
                            document.querySelectorAll('[data-step]').forEach(el => {
                                el.style.opacity = (el.getAttribute('data-step') === String(targetStep)) ? '1' : '0';
                            });
                        }""",
                        s_i,
                    )
                    roi = extract_rgba_roi(page.screenshot(type="png", omit_background=True))
                    step_rois[(sb.beat_id, s_i)] = roi
                    composite_roi(running, roi, dy=0, alpha_mul=1.0)
                    settled_frames[(sb.beat_id, s_i)] = running.copy()
            browser.close()
        tmp_html_file.unlink(missing_ok=True)

        sub_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for c in line_cues:
            txt = c["text"]
            if txt and txt not in sub_cache:
                sub_cache[txt] = self._render_subtitle_band(txt)

        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "5500k", "-profile:v", "high"] if platform.system() == "Darwin" else [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-profile:v", "high"
        ]
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
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
        cur_key = (line_cues[0]["beat_id"], int(line_cues[0].get("step_idx", 0)))
        step_enter_f = 0
        beat_enter_f = 0
        solid_bg = np.empty((H, W, 3), dtype=np.uint8)
        solid_bg[:] = bg_rgb_val

        err_log_path = out_mp4.with_suffix(".ffmpeg.log")
        with open(err_log_path, "w", encoding="utf-8") as err_fh:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err_fh)
            assert proc.stdin is not None
            try:
                for f_idx in range(total_frames):
                    t_sec = f_idx / FPS
                    while cue_idx + 1 < n_cues and t_sec >= line_cues[cue_idx + 1]["start"] - 0.02:
                        cue_idx += 1
                    cue = line_cues[cue_idx]
                    next_key = (cue["beat_id"], int(cue.get("step_idx", 0)))
                    if next_key != cur_key:
                        if next_key[0] != cur_key[0]:
                            beat_enter_f = f_idx
                        cur_key = next_key
                        step_enter_f = f_idx

                    b_id, s_i = cur_key
                    max_s = s_i
                    while (b_id, max_s) not in settled_frames and max_s > 0:
                        max_s -= 1

                    step_age = f_idx - step_enter_f
                    beat_age = f_idx - beat_enter_f

                    if 0 <= step_age < 18:
                        prev_canvas = base_frames[b_id].copy() if max_s == 0 else settled_frames[(b_id, max_s - 1)].copy()
                        u = step_age / 18.0
                        spring = 1.0 - math.exp(-6.8 * u) * math.cos(3.1 * u)
                        dy = int(round(28.0 * (1.0 - spring)))
                        a_mul = min(1.0, u / 0.22)
                        composite_roi(prev_canvas, step_rois.get((b_id, max_s)), dy=dy, alpha_mul=a_mul)
                        frame = prev_canvas
                        if 0 <= beat_age < 7:
                            ba = (beat_age + 1) / 7.0
                            frame = (solid_bg * (1.0 - ba) + frame * ba).astype(np.uint8)
                    else:
                        frame = settled_frames[(b_id, max_s)].copy()

                    if (cue["start"] - 0.03) <= t_sec <= (cue["end"] + 0.14) and cue["text"] in sub_cache:
                        s_rgb, s_a = sub_cache[cue["text"]]
                        roi = frame[1410:1528]
                        frame[1410:1528] = (roi * (1.0 - s_a) + s_rgb * s_a).astype(np.uint8)

                    prog_w = max(4, int((f_idx + 1) / total_frames * W))
                    frame[0:5, 0:prog_w] = orange_np
                    proc.stdin.write(frame.tobytes())
            finally:
                proc.stdin.close()
                rc = proc.wait()
        if rc != 0:
            stderr_out = err_log_path.read_text(encoding="utf-8", errors="ignore")
            raise RuntimeError(f"FFmpeg short V3 encode failed (rc={rc}): {stderr_out[-400:]}")
        err_log_path.unlink(missing_ok=True)
