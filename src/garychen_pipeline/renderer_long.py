from __future__ import annotations

import io
import math
import platform
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

from .config import ASSETS_DIR, CrawledSource, DesignTokens, EpisodeScript, VisualBeat
from .crawler import CHROME_APP_BIN
from .html_renderer import CAM_VIEWPORT_LONG, FONT_BOLD, build_long_beat_html
from .thumbnail_gen import render_studio_thumbnail

AVATAR_PNG = ASSETS_DIR / "avatar/garychen_avatar.png"


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()  # type: ignore[return-value]


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _ease_in_out_cubic(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return 4.0 * u * u * u if u < 0.5 else 1.0 - ((-2.0 * u + 2.0) ** 3) / 2.0


def extract_rgba_roi(png_bytes: bytes) -> tuple[int, int, int, int, np.ndarray, np.ndarray] | None:
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
    dx: int = 0,
    alpha_mul: float = 1.0,
):
    if roi_tuple is None or alpha_mul <= 0.001:
        return
    H, W, _ = canvas.shape
    y0, y1, x0, x1, rgb, a = roi_tuple
    ty0, ty1 = y0 + dy, y1 + dy
    tx0, tx1 = x0 + dx, x1 + dx
    sy0, sy1 = 0, y1 - y0
    sx0, sx1 = 0, x1 - x0
    if ty0 < 0:
        sy0 = -ty0
        ty0 = 0
    if ty1 > H:
        sy1 -= (ty1 - H)
        ty1 = H
    if tx0 < 0:
        sx0 = -tx0
        tx0 = 0
    if tx1 > W:
        sx1 -= (tx1 - W)
        tx1 = W
    if ty0 >= ty1 or sy0 >= sy1 or tx0 >= tx1 or sx0 >= sx1:
        return
    a_slice = a[sy0:sy1, sx0:sx1] * alpha_mul
    rgb_slice = rgb[sy0:sy1, sx0:sx1]
    dst = canvas[ty0:ty1, tx0:tx1]
    canvas[ty0:ty1, tx0:tx1] = (dst * (1.0 - a_slice) + rgb_slice * a_slice).astype(np.uint8)


def composite_horizontal_wipe(
    canvas: np.ndarray,
    roi_tuple: tuple[int, int, int, int, np.ndarray, np.ndarray] | None,
    progress: float,
):
    """60fps progressive left-to-right curve / arrow / scan-beam reveal with soft leading feather."""
    if roi_tuple is None or progress <= 0.001:
        return
    if progress >= 0.999:
        composite_roi(canvas, roi_tuple)
        return
    y0, y1, x0, x1, rgb, a = roi_tuple
    w = x1 - x0
    cut = int(round(w * max(0.0, min(1.0, progress))))
    if cut <= 1:
        return
    feather = min(22, cut)
    a_mod = a[:, :cut].copy()
    if feather > 2:
        ramp = np.linspace(1.0, 0.15, feather, dtype=np.float32).reshape(1, feather, 1)
        a_mod[:, cut - feather : cut] *= ramp
    dst = canvas[y0:y1, x0 : x0 + cut]
    canvas[y0:y1, x0 : x0 + cut] = (dst * (1.0 - a_mod) + rgb[:, :cut] * a_mod).astype(np.uint8)


def composite_typing_reveal(
    canvas: np.ndarray,
    roi_tuple: tuple[int, int, int, int, np.ndarray, np.ndarray] | None,
    progress: float,
    beat_sec: float,
):
    """
    60fps multi-line character-by-character typing reveal + blinking #EB8B1B terminal block cursor!
    Automatically detects horizontal text rows inside `roi_tuple` and types top-to-bottom, left-to-right.
    """
    if roi_tuple is None:
        return
    y0, y1, x0, x1, rgb, a = roi_tuple
    h, w, _ = rgb.shape
    row_has_ink = (a[:, :, 0].max(axis=1) > 0.08)

    # Segment into text line bands
    bands: list[tuple[int, int]] = []
    in_b = False
    bs = 0
    for r_i, val in enumerate(row_has_ink):
        if val and not in_b:
            bs = max(0, r_i - 2)
            in_b = True
        elif not val and in_b:
            if r_i - bs >= 6:
                bands.append((bs, min(h, r_i + 2)))
            in_b = False
    if in_b and h - bs >= 6:
        bands.append((bs, h))
    if not bands:
        bands = [(0, h)]

    n_bands = len(bands)
    p = max(0.0, min(1.0, progress))
    cursor_xy: tuple[int, int, int] | None = None

    for b_idx, (by0, by1) in enumerate(bands):
        b_start = b_idx / n_bands
        b_end = (b_idx + 1) / n_bands
        if p <= b_start:
            break
        local_p = min(1.0, (p - b_start) / max(1e-4, b_end - b_start))
        # Find ink x-extent for this line
        cols_ink = np.where(a[by0:by1, :, 0].max(axis=0) > 0.08)[0]
        lx0 = int(cols_ink[0]) if len(cols_ink) else 0
        lx1 = int(cols_ink[-1]) + 1 if len(cols_ink) else w
        cur_x = lx0 + int(round((lx1 - lx0) * local_p))
        if cur_x > 0:
            sub_a = a[by0:by1, :cur_x]
            sub_rgb = rgb[by0:by1, :cur_x]
            dst = canvas[y0 + by0 : y0 + by1, x0 : x0 + cur_x]
            canvas[y0 + by0 : y0 + by1, x0 : x0 + cur_x] = (dst * (1.0 - sub_a) + sub_rgb * sub_a).astype(np.uint8)
        cursor_xy = (x0 + cur_x + 4, y0 + by0 + 2, max(16, min(28, by1 - by0 - 4)))
        if local_p < 1.0:
            break

    # Draw crisp #EB8B1B block cursor (solid while typing, 2Hz blink after typing finishes)
    show_cursor = (p < 0.995) or (int(beat_sec * 2.2) % 2 == 0)
    if show_cursor and cursor_xy is not None:
        cx, cy, ch = cursor_xy
        H, W, _ = canvas.shape
        if 0 <= cx < W - 12 and 0 <= cy < H - ch:
            canvas[cy : cy + ch, cx : cx + 11] = (235, 139, 27)


def _make_macos_cursor_rgba() -> tuple[np.ndarray, np.ndarray]:
    im = Image.new("RGBA", (36, 44), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    poly = [(3, 2), (3, 33), (11, 25), (18, 39), (23, 36), (16, 23), (28, 23)]
    d.polygon(poly, fill=(255, 255, 255, 255), outline=(18, 18, 20, 255))
    arr = np.array(im, dtype=np.float32)
    return arr[:, :, :3], arr[:, :, 3:4] / 255.0


CURSOR_RGB, CURSOR_A = _make_macos_cursor_rgba()


def render_camera_viewport_60fps(
    canvas: np.ndarray,
    src_img_rgb: np.ndarray,
    viewport_rect: tuple[int, int, int, int],
    focus: list[float],
    beat_sec: float,
    beat_dur: float,
):
    """
    60fps Remotion Browser Camera Tour:
      - Smooth ease-in-out zoom `1.00x -> max_zoom` + pan toward `(fx, fy)` + gentle floating drift
      - Animated macOS pointer cursor gliding in from bottom-right + expanding #EB8B1B click ripple at `t ≈ 0.88s`!
    """
    vx, vy, vw, vh = viewport_rect
    sh, sw, _ = src_img_rgb.shape
    fx = float(focus[0]) if len(focus) >= 1 else 0.42
    fy = float(focus[1]) if len(focus) >= 2 else 0.36
    max_z = float(focus[2]) if len(focus) >= 3 else 1.32

    # Smooth zoom-in over first 2.4s, then slow continuous 60fps micro-pan so zero frames are static!
    z_prog = _ease_in_out_cubic(min(1.0, beat_sec / 2.4))
    drift_z = 0.035 * math.sin(max(0.0, beat_sec - 2.4) * 0.85)
    zoom = 1.0 + (max_z - 1.0) * z_prog + (drift_z if beat_sec > 2.4 else 0.0)

    cx_norm = 0.5 + (fx - 0.5) * z_prog + 0.022 * math.sin(beat_sec * 0.7)
    cy_norm = 0.42 + (fy - 0.42) * z_prog + 0.015 * math.cos(beat_sec * 0.6)

    crop_w = max(120, int(round(sw / zoom)))
    crop_h = max(90, int(round(crop_w * (vh / vw))))
    if crop_h > sh:
        crop_h = sh
        crop_w = int(round(crop_h * (vw / vh)))

    x0 = max(0, min(sw - crop_w, int(round(cx_norm * sw - crop_w / 2))))
    y0 = max(0, min(sh - crop_h, int(round(cy_norm * sh - crop_h / 2))))

    sub = Image.fromarray(src_img_rgb[y0 : y0 + crop_h, x0 : x0 + crop_w]).resize(
        (vw - 4, vh - 4), Image.Resampling.BILINEAR
    )
    canvas[vy + 2 : vy + vh - 2, vx + 2 : vx + vw - 2] = np.array(sub, dtype=np.uint8)

    # Cursor glide (0.15s -> 0.88s) + click ripple (0.88s -> 1.45s)
    c_u = _ease_in_out_cubic((beat_sec - 0.15) / 0.73)
    target_px = vx + int(vw * (0.48 + (fx - 0.5) * 0.25))
    target_py = vy + int(vh * (0.46 + (fy - 0.42) * 0.25))
    start_px, start_py = vx + int(vw * 0.86), vy + int(vh * 0.86)
    cur_px = int(round(start_px + (target_px - start_px) * c_u + 4.0 * math.sin(beat_sec * 1.6)))
    cur_py = int(round(start_py + (target_py - start_py) * c_u + 3.0 * math.cos(beat_sec * 1.4)))

    if 0.86 <= beat_sec <= 1.46:
        rp = (beat_sec - 0.86) / 0.60
        rad = int(10 + 46 * rp)
        alpha = int(235 * (1.0 - rp))
        ov = Image.new("RGBA", (rad * 2 + 8, rad * 2 + 8), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.ellipse((3, 3, rad * 2 + 5, rad * 2 + 5), outline=(235, 139, 27, alpha), width=3)
        r_arr = np.array(ov, dtype=np.float32)
        composite_roi(
            canvas,
            (
                cur_py - rad - 4,
                cur_py + rad + 4,
                cur_px - rad - 4,
                cur_px + rad + 4,
                r_arr[:, :, :3],
                r_arr[:, :, 3:4] / 255.0,
            ),
        )

    composite_roi(canvas, (cur_py, cur_py + 44, cur_px, cur_px + 36, CURSOR_RGB, CURSOR_A))


class GarychenLongRenderer:
    """
    V4 High-Density 60fps Remotion Compositor (1920x1080 @ 60fps):
      - Independent RGBA step spring physics (`+28px -> -2px -> 0px`)
      - 60fps progressive SVG curve/arrow wipes (`data-wipe="1"`)
      - 60fps live character-by-character typing + blinking #EB8B1B cursor (`data-typing="1"`)
      - 60fps smooth browser camera zoom & pan + macOS cursor glide & click ripple
      - Voice-reactive #EB8B1B studio ring around Gary's portrait in `avatar_mode`
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
        d.rounded_rectangle((px, 6, px + pw, 96), radius=14, fill=(9, 9, 9, 242))
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
        beats_by_id: dict[str, VisualBeat] = {b.beat_id: b for b in script.beats}
        orange_np = np.array(_hex_rgb(self.t.accent_orange_hex), dtype=np.uint8)
        bg_rgb_val = _hex_rgb(self.t.bg_stock_hex if script.avatar_mode else self.t.bg_tutorial_hex)

        # Precompute per-frame voice amplitude for subtle voice-reactive avatar ring in US Stocks
        audio_rms_per_f = np.zeros(total_frames, dtype=np.float32)
        try:
            ay, asr = sf.read(str(master_audio_wav), dtype="float32")
            if ay.ndim > 1:
                ay = ay.mean(axis=1)
            hop = max(1, int(asr / FPS))
            for fi in range(total_frames):
                seg = ay[fi * hop : (fi + 1) * hop]
                if len(seg):
                    audio_rms_per_f[fi] = min(1.0, float(np.sqrt(np.mean(seg * seg))) * 8.5)
        except Exception:
            pass

        avatar_roi = None
        avatar_ring_roi = None
        if script.avatar_mode and AVATAR_PNG.exists():
            av_im = Image.open(AVATAR_PNG).convert("RGBA").resize((216, 216), Image.Resampling.LANCZOS)
            av_arr = np.array(av_im, dtype=np.float32)
            avatar_roi = (820, 820 + 216, 1658, 1658 + 216, av_arr[:, :, :3], av_arr[:, :, 3:4] / 255.0)
            ring_im = Image.new("RGBA", (236, 236), (0, 0, 0, 0))
            rd = ImageDraw.Draw(ring_im)
            rd.ellipse((4, 4, 231, 231), outline=(235, 139, 27, 220), width=4)
            r_arr = np.array(ring_im, dtype=np.float32)
            avatar_ring_roi = (810, 810 + 236, 1648, 1648 + 236, r_arr[:, :, :3], r_arr[:, :, 3:4] / 255.0)

        render_studio_thumbnail(script, thumbnail_png)

        base_frames: dict[str, np.ndarray] = {}
        step_rois: dict[tuple[str, int], tuple[int, int, int, int, np.ndarray, np.ndarray] | None] = {}
        wipe_rois: dict[str, tuple[int, int, int, int, np.ndarray, np.ndarray] | None] = {}
        typing_rois: dict[str, tuple[int, int, int, int, np.ndarray, np.ndarray] | None] = {}
        cam_sources: dict[str, np.ndarray] = {}

        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        tmp_html_file = out_mp4.parent / "_render_stage_long_v4.html"
        launch_kwargs = {"headless": True}
        if Path(CHROME_APP_BIN).exists():
            launch_kwargs["executable_path"] = CHROME_APP_BIN

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs, args=["--allow-file-access-from-files"])
            page = browser.new_page(viewport={"width": W, "height": H, "device_scale_factor": 1})
            for beat in script.beats:
                # Preload high-res source screenshot for 60fps camera pan & zoom if `browser_ui_live_tour`
                if beat.layout_type == "browser_ui_live_tour":
                    cand_p = beat.screenshot_override
                    if not cand_p:
                        for sid in beat.source_ids:
                            s_obj = sources_by_id.get(sid)
                            if s_obj and s_obj.screenshot_path and Path(s_obj.screenshot_path).exists():
                                cand_p = s_obj.screenshot_path
                                break
                    if not cand_p:
                        cand_p = image_map.get(beat.beat_id, "")
                    if cand_p and Path(cand_p).exists():
                        cam_sources[beat.beat_id] = np.array(Image.open(cand_p).convert("RGB"), dtype=np.uint8)

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

                # 1. Opaque base frame (hide all data-step, data-wipe, data-typing)
                has_flags = page.evaluate(
                    """() => {
                        document.body.classList.remove('transparent-pass');
                        document.querySelectorAll('[data-step],[data-wipe],[data-typing]').forEach(el => { el.style.opacity = '0'; });
                        return {
                            wipe: document.querySelectorAll('[data-wipe]').length > 0,
                            typing: document.querySelectorAll('[data-typing]').length > 0
                        };
                    }"""
                )
                b_arr = np.array(Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB"), dtype=np.uint8)
                base_frames[beat.beat_id] = b_arr

                # 2. Independent step layers
                for s_i in range(n_steps):
                    page.evaluate(
                        """(targetStep) => {
                            document.body.classList.add('transparent-pass');
                            document.querySelectorAll('[data-wipe],[data-typing]').forEach(el => { el.style.opacity = '0'; });
                            document.querySelectorAll('[data-step]').forEach(el => {
                                el.style.opacity = (el.getAttribute('data-step') === String(targetStep)) ? '1' : '0';
                            });
                        }""",
                        s_i,
                    )
                    step_rois[(beat.beat_id, s_i)] = extract_rgba_roi(page.screenshot(type="png", omit_background=True))

                # 3. Dedicated 60fps wipe layer (`data-wipe`)
                if has_flags.get("wipe"):
                    page.evaluate(
                        """() => {
                            document.body.classList.add('transparent-pass');
                            document.querySelectorAll('[data-step],[data-typing]').forEach(el => { el.style.opacity = '0'; });
                            document.querySelectorAll('[data-wipe]').forEach(el => { el.style.opacity = '1'; });
                        }"""
                    )
                    wipe_rois[beat.beat_id] = extract_rgba_roi(page.screenshot(type="png", omit_background=True))

                # 4. Dedicated 60fps live-typing layer (`data-typing`)
                if has_flags.get("typing"):
                    page.evaluate(
                        """() => {
                            document.body.classList.add('transparent-pass');
                            document.querySelectorAll('[data-step],[data-wipe]').forEach(el => { el.style.opacity = '0'; });
                            document.querySelectorAll('[data-typing]').forEach(el => { el.style.opacity = '1'; });
                        }"""
                    )
                    typing_rois[beat.beat_id] = extract_rgba_roi(page.screenshot(type="png", omit_background=True))

            browser.close()
        tmp_html_file.unlink(missing_ok=True)

        # Precompute beat start/end times for smooth intra-beat 60fps progression
        beat_spans: dict[str, tuple[float, float]] = {}
        for c in line_cues:
            bid = c["beat_id"]
            if bid not in beat_spans:
                beat_spans[bid] = (c["start"], c["end"])
            else:
                beat_spans[bid] = (beat_spans[bid][0], max(beat_spans[bid][1], c["end"]))

        sub_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for c in line_cues:
            txt = c["text"]
            if txt and txt not in sub_cache:
                sub_cache[txt] = self._render_subtitle_band(txt)

        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "5600k", "-profile:v", "high"] if platform.system() == "Darwin" else [
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
                    beat_obj = beats_by_id[b_id]
                    step_age = f_idx - step_enter_f
                    beat_age = f_idx - beat_enter_f
                    beat_sec = beat_age / float(FPS)
                    b_s, b_e = beat_spans.get(b_id, (0.0, 6.0))
                    beat_dur = max(2.5, b_e - b_s)

                    frame = base_frames[b_id].copy()

                    # A. 60fps Browser Camera Pan & Zoom + Animated macOS Cursor Click
                    if b_id in cam_sources:
                        render_camera_viewport_60fps(
                            frame,
                            cam_sources[b_id],
                            CAM_VIEWPORT_LONG,
                            beat_obj.camera_focus,
                            beat_sec,
                            beat_dur,
                        )

                    # B. 60fps Progressive SVG Curve / Arrow / Scan-Beam Wipe (`data-wipe`)
                    if b_id in wipe_rois:
                        w_dur = 2.2 if beat_obj.layout_type in ("animated_growth_curve", "operating_leverage_chart") else 1.35
                        w_prog = _ease_in_out_cubic(min(1.0, max(0.0, (beat_sec - 0.12) / w_dur)))
                        composite_horizontal_wipe(frame, wipe_rois[b_id], w_prog)

                    # C. 60fps Live Character-by-Character Typing + Blinking #EB8B1B Cursor (`data-typing`)
                    if b_id in typing_rois:
                        t_prog = min(1.0, max(0.0, (beat_sec - 0.08) / 1.95))
                        composite_typing_reveal(frame, typing_rois[b_id], t_prog, beat_sec)

                    # D. Already-settled previous step layers + 22-frame Spring Entrance on active step `s_i`
                    float_dy = int(round(4.0 * math.sin(beat_sec * 1.6))) if beat_obj.layout_type == "concept_hero_split_3d" else 0
                    for prev_s in range(s_i):
                        dy_prev = float_dy if prev_s == 0 else 0
                        composite_roi(frame, step_rois.get((b_id, prev_s)), dy=dy_prev, alpha_mul=1.0)

                    if 0 <= step_age < 22:
                        u = step_age / 22.0
                        spring = 1.0 - math.exp(-6.5 * u) * math.cos(3.4 * u)
                        dy = int(round(28.0 * (1.0 - spring))) + (float_dy if s_i == 0 else 0)
                        a_mul = min(1.0, u / 0.20)
                        composite_roi(frame, step_rois.get((b_id, s_i)), dy=dy, alpha_mul=a_mul)
                    else:
                        composite_roi(frame, step_rois.get((b_id, s_i)), dy=(float_dy if s_i == 0 else 0), alpha_mul=1.0)

                    # E. US Stocks Avatar + Voice-Reactive #EB8B1B Studio Ring
                    if avatar_roi is not None:
                        if avatar_ring_roi is not None:
                            ring_a = 0.28 + 0.65 * float(audio_rms_per_f[f_idx])
                            composite_roi(frame, avatar_ring_roi, alpha_mul=ring_a)
                        composite_roi(frame, avatar_roi, alpha_mul=1.0)

                    # F. Crisp 7-frame stage entrance on beat boundary
                    if 0 <= beat_age < 7:
                        ba = (beat_age + 1) / 7.0
                        frame = (solid_bg * (1.0 - ba) + frame * ba).astype(np.uint8)

                    # G. Bottom Pill Subtitle
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
            raise RuntimeError(f"FFmpeg long V4 encode failed (rc={rc}): {stderr_out[-400:]}")
        err_log_path.unlink(missing_ok=True)
