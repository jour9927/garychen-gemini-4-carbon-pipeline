from __future__ import annotations

import math
import platform
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import ASSETS_DIR, CrawledSource, DesignTokens, EpisodeScript, ShortSceneSpec
from .renderer_long import FONT_BOLD, FONT_MED, _draw_glow_rect, _fit_image_rounded, _font, _hex_rgb, _smart_clip


class GarychenShortsRenderer:
    """
    Renders corresponding 1080x1920 @ 60fps YouTube Shorts traffic-funnel videos ("short是對應的長片的推流"):
      - Cohesive #262626 dark studio aesthetic + #EB8B1B amber accents matching the long-form episode
      - Top hook banner + real-time 60fps orange progress bar
      - Center PyTorch AI-generated visual card with Crawled Source Citation badge (`📎 資料來源：...`)
      - Safe-zone crisp #090909 subtitle pill (Y=1380..1485, clear of YouTube Shorts UI overlay)
      - Final Funnel CTA Scene displaying the Long Video Thumbnail + animated pointer to the bottom-left related video link!
    """

    def __init__(self, tokens: DesignTokens | None = None):
        self.t = tokens or DesignTokens()
        self.f_top = _font(FONT_BOLD, 28)
        self.f_h1 = _font(FONT_BOLD, 58)
        self.f_badge = _font(FONT_BOLD, 28)
        self.f_bullet = _font(FONT_MED, 34)
        self.f_src = _font(FONT_MED, 22)
        self.f_sub = _font(FONT_BOLD, 44)
        self.f_cta = _font(FONT_BOLD, 38)

    def render_short_state(
        self,
        script: EpisodeScript,
        s_scene: ShortSceneSpec,
        active_bullet_idx: int,
        subtitle_text: str,
        ai_img_path: str | None,
        long_thumb_path: Path | None,
        sources_by_id: dict[str, CrawledSource],
    ) -> Image.Image:
        W, H = self.t.short_width, self.t.short_height
        bg_rgb = _hex_rgb(self.t.bg_tutorial_hex)
        orange = _hex_rgb(self.t.accent_orange_hex)
        green = _hex_rgb(self.t.accent_green_hex)
        muted = _hex_rgb(self.t.text_secondary_hex)

        canvas = Image.new("RGBA", (W, H), (*bg_rgb, 255))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, W, 6), fill=(*_hex_rgb(self.t.top_bar_track_hex), 255))

        # 1. Top Channel + Hook Pill (Y=78..142)
        _draw_glow_rect(canvas, (70, 78, W - 70, 146), radius=34, fill_rgba=(20, 20, 22, 238), border_rgb=orange, border_w=2)
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((100, 100, 124, 124), fill=(*orange, 255))
        draw.text((142, 93), f"GARY CHEN｜{script.short_hook_banner}", font=self.f_top, fill=(255, 255, 255))

        # 2. Big Punchy Headline + Metric Highlight Badge (Y=185..345)
        hl_txt = _smart_clip(s_scene.headline, 18)
        hl_font = self.f_h1 if len(hl_txt) <= 13 else _font(FONT_BOLD, 46)
        self._center_text(draw, hl_txt, W // 2, 192, hl_font, (255, 255, 255))
        if s_scene.highlight_badge:
            bb = draw.textbbox((0, 0), s_scene.highlight_badge, font=self.f_badge)
            bw = (bb[2] - bb[0]) + 48
            bx = (W - bw) // 2
            draw.rounded_rectangle((bx, 276, bx + bw, 332), radius=28, fill=(*orange, 255))
            draw.text((bx + 24, 285), s_scene.highlight_badge, font=self.f_badge, fill=(18, 18, 18))

        # 3. Main Visual Card OR Final Long-Video Funnel Card (Y=365..955)
        cited = [sources_by_id[sid] for sid in s_scene.source_ids if sid in sources_by_id]
        if s_scene.is_cta and long_thumb_path and long_thumb_path.exists():
            _draw_glow_rect(canvas, (64, 365, W - 64, 965), radius=32, fill_rgba=(32, 32, 36, 255), border_rgb=orange, border_w=4, glow=True)
            thumb = _fit_image_rounded(str(long_thumb_path), W - 176, 490, radius=22)
            canvas.alpha_composite(thumb, (88, 392))
            draw = ImageDraw.Draw(canvas)
            self._center_text(draw, "✦ 完整長片已上線（含完整步驟與數據來源）", W // 2, 902, self.f_src, orange)
        else:
            _draw_glow_rect(canvas, (64, 365, W - 64, 955), radius=32, fill_rgba=(34, 34, 38, 255), border_rgb=orange, border_w=3, glow=True)
            art = _fit_image_rounded(ai_img_path, W - 168, 505, radius=24)
            canvas.alpha_composite(art, (84, 385))
            draw = ImageDraw.Draw(canvas)
            if cited:
                s0 = cited[0]
                src_str = f"● 公開資料來源：[{s0.source_id}] {s0.domain} · {_smart_clip(s0.title, 24)}"
                self._center_text(draw, src_str, W // 2, 906, self.f_src, muted)

        # 4. Stacked Takeaway Cards OR Funnel Pointer Box (Y=990..1340)
        if s_scene.is_cta:
            _draw_glow_rect(canvas, (64, 1000, W - 64, 1320), radius=28, fill_rgba=(28, 28, 32, 255), border_rgb=orange, border_w=3, glow=True)
            draw = ImageDraw.Draw(canvas)
            self._center_text(draw, "想直接照抄完整設定與架構？", W // 2, 1042, self.f_cta, (255, 255, 255))
            self._center_text(draw, _smart_clip(script.short_cta_target_title, 24), W // 2, 1118, self.f_bullet, orange)
            draw.rounded_rectangle((130, 1196, W - 130, 1282), radius=43, fill=(*orange, 255))
            self._center_text(draw, "↙ 點擊左下角「關聯影片」看完整版", W // 2, 1216, self.f_cta, (16, 16, 16))
        else:
            bullets = s_scene.bullet_points[:3]
            for idx_b, btxt in enumerate(bullets):
                by = 990 + idx_b * 112
                is_act = (idx_b == active_bullet_idx % max(1, len(bullets)))
                _draw_glow_rect(
                    canvas, (64, by, W - 64, by + 94), radius=22,
                    fill_rgba=(48, 48, 54, 255) if is_act else (36, 36, 40, 245),
                    border_rgb=orange if is_act else (68, 68, 74),
                    border_w=3 if is_act else 1, glow=is_act,
                )
                draw = ImageDraw.Draw(canvas)
                draw.ellipse((94, by + 23, 142, by + 71), fill=(*green, 255) if is_act else (*orange, 255))
                self._center_text(draw, "✓" if is_act else str(idx_b + 1), 118, by + 26, self.f_badge, (18, 18, 18))
                draw.text((168, by + 24), _smart_clip(btxt, 22), font=self.f_bullet, fill=(255, 255, 255))

        # 5. Safe-Zone Shorts Subtitle Pill (Y=1375..1480) with dynamic auto-fit font sizing
        if subtitle_text:
            draw = ImageDraw.Draw(canvas)
            sub_font = self.f_sub
            for candidate_sz in (44, 36, 30, 25):
                sub_font = _font(FONT_BOLD, candidate_sz)
                tb = draw.textbbox((0, 0), subtitle_text, font=sub_font)
                if (tb[2] - tb[0]) <= W - 150:
                    break
            tb = draw.textbbox((0, 0), subtitle_text, font=sub_font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            pw = min(996, max(320, tw + 72))
            px = (W - pw) // 2
            draw.rounded_rectangle((px, 1375, px + pw, 1482), radius=18, fill=(9, 9, 9, 245))
            self._center_text(draw, subtitle_text, W // 2, 1375 + (107 - th) // 2 - 4, sub_font, (255, 255, 255))

        return canvas.convert("RGB")

    @staticmethod
    def _center_text(draw: ImageDraw.ImageDraw, text: str, cx: int, y: int, font: ImageFont.FreeTypeFont, fill: tuple):
        bb = draw.textbbox((0, 0), text, font=font)
        draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=fill)

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
        W, H, FPS = self.t.short_width, self.t.short_height, self.t.fps
        total_frames = max(1, int(round(total_duration * FPS)))
        sources_by_id = {s.source_id: s for s in sources}
        scenes_by_id = {sc.scene_id: sc for sc in script.short_scenes}
        orange_np = np.array(_hex_rgb(self.t.accent_orange_hex), dtype=np.uint8)
        bg_np = np.array(_hex_rgb(self.t.bg_tutorial_hex), dtype=np.uint8)

        state_cache: dict[tuple[str, int, str], np.ndarray] = {}

        def get_state_arr(sc_id: str, step_idx: int, sub_txt: str) -> np.ndarray:
            key = (sc_id, step_idx, sub_txt)
            if key not in state_cache:
                sc = scenes_by_id[sc_id]
                im = self.render_short_state(
                    script=script,
                    s_scene=sc,
                    active_bullet_idx=step_idx,
                    subtitle_text=sub_txt,
                    ai_img_path=image_map.get(sc_id),
                    long_thumb_path=long_thumb_path,
                    sources_by_id=sources_by_id,
                )
                state_cache[key] = np.array(im, dtype=np.uint8)
            return state_cache[key]

        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "5000k", "-profile:v", "high"] if platform.system() == "Darwin" else [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high"
        ]
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-i", str(master_audio_wav),
            *vcodec,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
            "-shortest",
            "-movflags", "+faststart",
            str(out_mp4),
        ]

        cue_idx = 0
        n_cues = len(line_cues)
        current_sc_id = script.short_scenes[0].scene_id
        sc_start_frame = 0

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for f_idx in range(total_frames):
                t_sec = f_idx / FPS
                while cue_idx + 1 < n_cues and t_sec >= line_cues[cue_idx + 1]["start"] - 0.04:
                    cue_idx += 1
                cue = line_cues[cue_idx]
                sc_id = cue["scene_id"]
                if sc_id != current_sc_id:
                    current_sc_id = sc_id
                    sc_start_frame = f_idx

                in_speech = (cue["start"] - 0.04) <= t_sec <= (cue["end"] + 0.14)
                sub_txt = cue["text"] if in_speech else ""
                base_arr = get_state_arr(sc_id, int(cue.get("line_idx", 0)), sub_txt)

                sc_age = f_idx - sc_start_frame
                if sc_age < 16 and f_idx > 0:
                    alpha = 1.0 - math.pow(1.0 - (sc_age / 16.0), 3)
                    frame = (bg_np * (1.0 - alpha) + base_arr * alpha).astype(np.uint8)
                else:
                    frame = base_arr.copy()

                prog_w = max(4, int((f_idx + 1) / total_frames * W))
                frame[0:6, 0:prog_w] = orange_np
                proc.stdin.write(frame.tobytes())
        finally:
            proc.stdin.close()
            stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
            rc = proc.wait()
            if rc != 0:
                raise RuntimeError(f"FFmpeg short encode failed (rc={rc}): {stderr_out[-400:]}")
