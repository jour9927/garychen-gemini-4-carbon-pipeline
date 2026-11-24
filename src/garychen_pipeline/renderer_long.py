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

AVATAR_PNG = ASSETS_DIR / "avatar/garychen_avatar.png"


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()  # type: ignore[return-value]


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class GarychenLongRenderer:
    """
    V2 Remotion-Grade 1920x1080 @ 60fps Renderer:
      - Renders all 14 authentic @garychenai HTML5 + CSS3 + Inline SVG templates via headless Chromium
      - Animates progressive step reveals (0 -> 1 -> 2 -> 3) smoothly at 60fps synced to Whisper clause timestamps
      - Overlays crisp #090909 rounded subtitle pill (Y=922..1019) & top 4px #EB8B1B real-time progress bar
    """

    def __init__(self, tokens: DesignTokens | None = None):
        self.t = tokens or DesignTokens()

    def _render_subtitle_band(self, text: str) -> tuple[np.ndarray, np.ndarray]:
        """Pre-renders only the subtitle band rows [916..1026] as (rgb, alpha_float) for ultra-fast 60fps compositing."""
        W = self.t.long_width
        band_h = 110
        ov = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        font = _font(FONT_BOLD, 40)
        for sz in (40, 35, 30, 26):
            font = _font(FONT_BOLD, sz)
            tb = d.textbbox((0, 0), text, font=font)
            if (tb[2] - tb[0]) <= W - 200:
                break
        tb = d.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pw = min(1780, max(340, tw + 82))
        px = (W - pw) // 2
        d.rounded_rectangle((px, 6, px + pw, 103), radius=16, fill=(9, 9, 9, 242))
        d.text((W // 2 - tw // 2, 6 + (97 - th) // 2 - 4), text, font=font, fill=(255, 255, 255, 255))
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
        beats_by_id = {b.beat_id: b for b in script.beats}
        orange_np = np.array(_hex_rgb(self.t.accent_orange_hex), dtype=np.uint8)
        bg_np = np.array(_hex_rgb(self.t.bg_stock_hex if script.avatar_mode else self.t.bg_tutorial_hex), dtype=np.uint8)

        # Preload optional avatar RGBA
        avatar_im = None
        if script.avatar_mode and AVATAR_PNG.exists():
            avatar_im = Image.open(AVATAR_PNG).convert("RGBA").resize((226, 226), Image.Resampling.LANCZOS)

        # Collect unique (beat_id, step_idx) states needed across timeline
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
                beat = beats_by_id[beat_id]
                html_doc = build_long_beat_html(
                    script=script,
                    beat=beat,
                    step_idx=step_i,
                    ai_img_path=image_map.get(beat_id),
                    sources_by_id=sources_by_id,
                    tokens=self.t,
                )
                page.set_content(html_doc, wait_until="load")
                png_bytes = page.screenshot(type="png")
                im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                if avatar_im is not None:
                    im.alpha_composite(avatar_im, (1648, 810))
                state_frames[(beat_id, step_i)] = np.array(im.convert("RGB"), dtype=np.uint8)

            # Render crisp thumbnail from Beat 1 at full reveal
            b0 = script.beats[0]
            thumb_html = build_long_beat_html(
                script=script,
                beat=b0,
                step_idx=max(1, len(b0.nodes) - 1),
                ai_img_path=image_map.get(b0.beat_id),
                sources_by_id=sources_by_id,
                tokens=self.t,
            )
            page.set_content(thumb_html, wait_until="load")
            t_im = Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGBA")
            if avatar_im is not None:
                t_im.alpha_composite(avatar_im, (1648, 810))
            thumbnail_png.parent.mkdir(parents=True, exist_ok=True)
            t_im.convert("RGB").save(str(thumbnail_png))
            browser.close()

        sub_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for c in line_cues:
            txt = c["text"]
            if txt and txt not in sub_cache:
                sub_cache[txt] = self._render_subtitle_band(txt)

        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "5200k", "-profile:v", "high"] if platform.system() == "Darwin" else [
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
        is_beat_switch = False

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
                    is_beat_switch = (next_key[0] != cur_key[0])
                    prev_key = cur_key
                    cur_key = next_key
                    transition_start_f = f_idx

                target_arr = state_frames[cur_key]
                age = f_idx - transition_start_f
                trans_len = 16 if is_beat_switch else 11
                if 0 <= age < trans_len:
                    alpha = 1.0 - math.pow(1.0 - (age / float(trans_len)), 3)
                    src_arr = bg_np if (is_beat_switch and f_idx < 16) else state_frames[prev_key]
                    frame = (src_arr * (1.0 - alpha) + target_arr * alpha).astype(np.uint8)
                else:
                    frame = target_arr.copy()

                # Composite subtitle pill cleanly on rows [916:1026]
                if (cue["start"] - 0.03) <= t_sec <= (cue["end"] + 0.12) and cue["text"] in sub_cache:
                    s_rgb, s_a = sub_cache[cue["text"]]
                    roi = frame[916:1026]
                    frame[916:1026] = (roi * (1.0 - s_a) + s_rgb * s_a).astype(np.uint8)

                prog_w = max(4, int((f_idx + 1) / total_frames * W))
                frame[0:4, 0:prog_w] = orange_np
                proc.stdin.write(frame.tobytes())
        finally:
            proc.stdin.close()
            stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
            rc = proc.wait()
            if rc != 0:
                raise RuntimeError(f"FFmpeg long V2 encode failed (rc={rc}): {stderr_out[-400:]}")
