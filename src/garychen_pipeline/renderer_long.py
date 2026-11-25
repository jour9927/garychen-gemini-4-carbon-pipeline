from __future__ import annotations

import io
import math
import platform
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import ASSETS_DIR, CrawledSource, DesignTokens, EpisodeScript
from .crawler import CHROME_APP_BIN
from .html_renderer import FONT_BOLD, build_long_beat_html
from .thumbnail_gen import render_studio_thumbnail

AVATAR_PNG = ASSETS_DIR / "avatar/garychen_avatar.png"


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()  # type: ignore[return-value]


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def extract_rgba_roi(png_bytes: bytes) -> tuple[int, int, int, int, np.ndarray, np.ndarray] | None:
    """Extracts tight non-zero alpha bounding-box `(y0, y1, x0, x1, rgb_f32, alpha_f32)` for ultra-fast 60fps spring compositing."""
    arr = np.array(Image.open(io.BytesIO(png_bytes)).convert("RGBA"), dtype=np.uint8)
    mask = arr[:, :, 3] > 2
    if not np.any(mask):
        return None
    ys, xs = np.where(mask)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    sub = arr[y0:y1, x0:x1].astype(np.float32)
    return y0, y1, x0, x1, sub[:, :, :3], sub[:, :, 3:4] / 255.0


def composite_roi(
    canvas: np.ndarray,
    roi_tuple: tuple[int, int, int, int, np.ndarray, np.ndarray] | None,
    dy: int = 0,
    alpha_mul: float = 1.0,
):
    if roi_tuple is None or alpha_mul <= 0.001:
        return
    H, W, _ = canvas.shape
    y0, y1, x0, x1, rgb, a = roi_tuple
    ty0 = y0 + dy
    ty1 = y1 + dy
    sy0 = 0
    sy1 = y1 - y0
    if ty0 < 0:
        sy0 = -ty0
        ty0 = 0
    if ty1 > H:
        sy1 -= (ty1 - H)
        ty1 = H
    if ty0 >= ty1 or sy0 >= sy1:
        return
    a_slice = a[sy0:sy1] * alpha_mul
    rgb_slice = rgb[sy0:sy1]
    dst = canvas[ty0:ty1, x0:x1]
    canvas[ty0:ty1, x0:x1] = (dst * (1.0 - a_slice) + rgb_slice * a_slice).astype(np.uint8)


class GarychenLongRenderer:
    """
    V3 True Layer-Spring 1920x1080 @ 60fps Remotion Compositor:
      - Captures clean minimalist base layer (with exact-shape dashed ghost silhouettes) + independent RGBA step layers
      - Animates each step layer with real 60fps critically-damped spring physics (`+26px -> 0px` upward glide, zero crossfade double-text!)
      - Generates authentic @garychenai Studio Portrait + Gold/White Stroked YouTube Thumbnail
    """

    def __init__(self, tokens: DesignTokens | None = None):
        self.t = tokens or DesignTokens()

    def _render_subtitle_band(self, text: str) -> tuple[np.ndarray, np.ndarray]:
        W = self.t.long_width
        band_h = 104
        ov = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        font = _font(FONT_BOLD, 38)
        for sz in (38, 34, 30, 26):
            font = _font(FONT_BOLD, sz)
            tb = d.textbbox((0, 0), text, font=font)
            if (tb[2] - tb[0]) <= W - 240:
                break
        tb = d.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pw = min(1740, max(300, tw + 74))
        px = (W - pw) // 2
        d.rounded_rectangle((px, 6, px + pw, 96), radius=14, fill=(9, 9, 9, 240))
        d.text((W // 2 - tw // 2, 6 + (90 - th) // 2 - 4), text, font=font, fill=(255, 255, 255, 255))
        arr = np.array(ov, dtype=np.float32)
        return arr[:, :, :3], arr[:, :, 3:4] / 255.0

    def encode_video(
        self,
        script: EpisodeScript,
        line_cues: list[dict],
        master_audio_wav: Path,
        total_duration: float,
        image_map: dict[str, str],
        sources: list[CrawledSource],
        out_mp4: Path,
        thumbnail_png: Path,
    ):
        from playwright.sync_api import sync_playwright

        W, H, FPS = self.t.long_width, self.t.long_height, self.t.fps
        total_frames = max(1, int(round(total_duration * FPS)))
        sources_by_id = {s.source_id: s for s in sources}
        orange_np = np.array(_hex_rgb(self.t.accent_orange_hex), dtype=np.uint8)
        bg_rgb_val = _hex_rgb(self.t.bg_stock_hex if script.avatar_mode else self.t.bg_tutorial_hex)

        avatar_roi = None
        if script.avatar_mode and AVATAR_PNG.exists():
            av_im = Image.open(AVATAR_PNG).convert("RGBA").resize((218, 218), Image.Resampling.LANCZOS)
            av_arr = np.array(av_im, dtype=np.float32)
            avatar_roi = (818, 818 + 218, 1656, 1656 + 218, av_arr[:, :, :3], av_arr[:, :, 3:4] / 255.0)

        # Render authentic @garychenai Studio Portrait Thumbnail
        render_studio_thumbnail(script, thumbnail_png)

        base_frames: dict[str, np.ndarray] = {}
        step_rois: dict[tuple[str, int], tuple[int, int, int, int, np.ndarray, np.ndarray] | None] = {}
        settled_frames: dict[tuple[str, int], np.ndarray] = {}

        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        tmp_html_file = out_mp4.parent / "_render_stage_long_v3.html"
        launch_kwargs = {"headless": True}
        if Path(CHROME_APP_BIN).exists():
            launch_kwargs["executable_path"] = CHROME_APP_BIN

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs, args=["--allow-file-access-from-files"])
            page = browser.new_page(viewport={"width": W, "height": H, "device_scale_factor": 1})
            for beat in script.beats:
                html_doc, n_steps = build_long_beat_html(
                    script=script,
                    beat=beat,
                    ai_img_path=image_map.get(beat.beat_id),
                    sources_by_id=sources_by_id,
                    tokens=self.t,
                )
                tmp_html_file.write_text(html_doc, encoding="utf-8")
                page.goto(tmp_html_file.resolve().as_uri(), wait_until="load")
                page.evaluate("() => document.fonts.ready")

                # 1. Opaque base frame (ghost slots + header)
                page.evaluate(
                    """() => {
                        document.body.classList.remove('transparent-pass');
                        document.querySelectorAll('[data-step]').forEach(el => { el.style.opacity = '0'; });
                    }"""
                )
                base_im = Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB")
                b_arr = np.array(base_im, dtype=np.uint8)
                if avatar_roi is not None:
                    composite_roi(b_arr, avatar_roi, dy=0, alpha_mul=1.0)
                base_frames[beat.beat_id] = b_arr

                # 2. Independent transparent RGBA layer per progressive step
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
                    step_rois[(beat.beat_id, s_i)] = roi
                    composite_roi(running, roi, dy=0, alpha_mul=1.0)
                    if avatar_roi is not None:
                        composite_roi(running, avatar_roi, dy=0, alpha_mul=1.0)
                    settled_frames[(beat.beat_id, s_i)] = running.copy()

            browser.close()
        tmp_html_file.unlink(missing_ok=True)

        sub_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for c in line_cues:
            txt = c["text"]
            if txt and txt not in sub_cache:
                sub_cache[txt] = self._render_subtitle_band(txt)

        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "5200k", "-profile:v", "high"] if platform.system() == "Darwin" else [
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

                    # 20-frame (0.33s @ 60fps) Remotion Spring Entrance on the active step layer!
                    if 0 <= step_age < 20:
                        prev_canvas = base_frames[b_id].copy() if max_s == 0 else settled_frames[(b_id, max_s - 1)].copy()
                        u = step_age / 20.0
                        spring = 1.0 - math.exp(-6.8 * u) * math.cos(3.1 * u)
                        dy = int(round(26.0 * (1.0 - spring)))
                        a_mul = min(1.0, u / 0.22)
                        composite_roi(prev_canvas, step_rois.get((b_id, max_s)), dy=dy, alpha_mul=a_mul)
                        if avatar_roi is not None:
                            composite_roi(prev_canvas, avatar_roi, dy=0, alpha_mul=1.0)
                        frame = prev_canvas
                        # Clean 8-frame (0.13s) stage fade from dark matte on beat boundary (zero text overlap!)
                        if 0 <= beat_age < 8:
                            ba = (beat_age + 1) / 8.0
                            frame = (solid_bg * (1.0 - ba) + frame * ba).astype(np.uint8)
                    else:
                        frame = settled_frames[(b_id, max_s)].copy()

                    if (cue["start"] - 0.03) <= t_sec <= (cue["end"] + 0.14) and cue["text"] in sub_cache:
                        s_rgb, s_a = sub_cache[cue["text"]]
                        roi = frame[924:1028]
                        frame[924:1028] = (roi * (1.0 - s_a) + s_rgb * s_a).astype(np.uint8)

                    prog_w = max(3, int((f_idx + 1) / total_frames * W))
                    frame[0:3, 0:prog_w] = orange_np
                    proc.stdin.write(frame.tobytes())
            finally:
                proc.stdin.close()
                rc = proc.wait()
        if rc != 0:
            stderr_out = err_log_path.read_text(encoding="utf-8", errors="ignore")
            raise RuntimeError(f"FFmpeg long V3 encode failed (rc={rc}): {stderr_out[-400:]}")
        err_log_path.unlink(missing_ok=True)
