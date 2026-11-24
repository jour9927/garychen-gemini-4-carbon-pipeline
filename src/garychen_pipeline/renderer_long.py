from __future__ import annotations

import math
import platform
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ASSETS_DIR, CrawledSource, DesignTokens, EpisodeScript, SceneSpec

FONT_BOLD = ASSETS_DIR / "fonts/NotoSansTC-Bold.otf"
FONT_MED = ASSETS_DIR / "fonts/NotoSansTC-Medium.otf"
FONT_MONO = ASSETS_DIR / "fonts/JetBrainsMono-Bold.ttf"
AVATAR_PNG = ASSETS_DIR / "avatar/garychen_avatar.png"


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()  # type: ignore[return-value]


def _smart_clip(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Avoid cutting inside an ASCII word
    if cut[-1].isascii() and cut[-1].isalnum() and text[max_chars].isascii() and text[max_chars].isalnum():
        last_sp = max(cut.rfind(" "), cut.rfind("/"), cut.rfind("-"), cut.rfind("："))
        if last_sp >= max_chars // 2:
            cut = cut[:last_sp]
    return cut.rstrip(" /-:：,，")


def _fit_image_rounded(img_path: str | None, w: int, h: int, radius: int = 22) -> Image.Image:
    if img_path and Path(img_path).exists():
        im = Image.open(img_path).convert("RGBA")
        # Center-crop aspect ratio
        ir = im.width / max(1, im.height)
        tr = w / max(1, h)
        if ir > tr:
            nw = int(im.height * tr)
            off = (im.width - nw) // 2
            im = im.crop((off, 0, off + nw, im.height))
        else:
            nh = int(im.width / tr)
            off = (im.height - nh) // 2
            im = im.crop((0, off, im.width, off + nh))
        im = im.resize((w, h), Image.Resampling.LANCZOS)
    else:
        im = Image.new("RGBA", (w, h), (44, 44, 48, 255))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def _draw_glow_rect(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    fill_rgba: tuple[int, int, int, int],
    border_rgb: tuple[int, int, int],
    border_w: int = 2,
    glow: bool = False,
):
    if glow:
        g_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(g_layer)
        pad = 8
        gd.rounded_rectangle(
            (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad),
            radius=radius + pad,
            outline=(*border_rgb, 115),
            width=10,
        )
        g_layer = g_layer.filter(ImageFilter.GaussianBlur(14))
        canvas.alpha_composite(g_layer)
    ov = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle(box, radius=radius, fill=fill_rgba, outline=(*border_rgb, 255), width=border_w)
    canvas.alpha_composite(ov)


class GarychenLongRenderer:
    """
    Renders pixel-faithful @garychenai 1920x1080 @ 60fps videos:
      - #262626 / #1E1E1E dark charcoal studio canvas
      - Top 4px #EB8B1B real-time progress bar
      - Top-left `01 / 06 章節名` header + Top-right Crawled Source Citation badge (`🌐 資料來源：...`)
      - 8 signature animated infographic + PyTorch AI illustration layouts with active-step focus synced to narration
      - #090909 bottom rounded subtitle pill (Y=922..1019)
      - Optional bottom-right circular studio avatar (for US stock / commentary mode)
    """

    def __init__(self, tokens: DesignTokens | None = None):
        self.t = tokens or DesignTokens()
        self.f_chap_num = _font(FONT_BOLD, 24)
        self.f_chap_txt = _font(FONT_MED, 23)
        self.f_src = _font(FONT_MED, 19)
        self.f_h1 = _font(FONT_BOLD, 48)
        self.f_h2 = _font(FONT_MED, 26)
        self.f_card_title = _font(FONT_BOLD, 31)
        self.f_card_sub = _font(FONT_MED, 22)
        self.f_badge = _font(FONT_BOLD, 21)
        self.f_mono = _font(FONT_MONO, 26)
        self.f_sub = _font(FONT_BOLD, 40)

    def render_scene_state(
        self,
        script: EpisodeScript,
        scene: SceneSpec,
        active_step_idx: int,
        subtitle_text: str,
        ai_img_path: str | None,
        sources_by_id: dict[str, CrawledSource],
    ) -> Image.Image:
        W, H = self.t.long_width, self.t.long_height
        bg_rgb = _hex_rgb(self.t.bg_stock_hex if script.avatar_mode else self.t.bg_tutorial_hex)
        orange = _hex_rgb(self.t.accent_orange_hex)
        green = _hex_rgb(self.t.accent_green_hex)
        red = _hex_rgb(self.t.accent_red_hex)
        muted = _hex_rgb(self.t.text_secondary_hex)

        canvas = Image.new("RGBA", (W, H), (*bg_rgb, 255))
        draw = ImageDraw.Draw(canvas)

        # 1. Top track bar background (fill is drawn per-frame at 60fps)
        draw.rectangle((0, 0, W, 4), fill=(*_hex_rgb(self.t.top_bar_track_hex), 255))

        # 2. Top-left chapter indicator: `01 / 06 章節標題`
        num_str = f"{scene.chapter_index:02d} / {scene.total_chapters:02d}"
        draw.text((32, 22), num_str, font=self.f_chap_num, fill=(*orange, 255))
        nb = draw.textbbox((32, 22), num_str, font=self.f_chap_num)
        draw.text((nb[2] + 14, 23), scene.chapter_title, font=self.f_chap_txt, fill=(*muted, 255))

        # 3. Top-right Crawled Source Citation Pill ("同時附上來源")
        cited_sources = [sources_by_id[sid] for sid in scene.source_ids if sid in sources_by_id]
        if cited_sources:
            s0 = cited_sources[0]
            date_part = f" · {s0.published_date}" if s0.published_date else ""
            src_label = f"來源 [{s0.source_id}] {s0.domain}{date_part}｜{_smart_clip(s0.title, 26)}"
            sb = draw.textbbox((0, 0), src_label, font=self.f_src)
            pw = (sb[2] - sb[0]) + 42
            px1 = W - pw - 32
            _draw_glow_rect(canvas, (px1, 18, W - 32, 56), radius=19, fill_rgba=(20, 20, 22, 230), border_rgb=(85, 85, 92), border_w=1)
            draw = ImageDraw.Draw(canvas)
            draw.ellipse((px1 + 14, 32, px1 + 24, 42), fill=(*orange, 255))
            draw.text((px1 + 32, 25), src_label, font=self.f_src, fill=(220, 220, 225, 255))

        # 4. Scene Main Content Area (Y = 85 .. 890)
        nodes = scene.nodes[:4] if scene.nodes else [{"label": scene.visual_title, "sub": scene.visual_subtitle, "tag": scene.badge_text}]
        focus_i = active_step_idx % max(1, len(nodes))
        lt = scene.layout_type

        if lt == "hero_comparison_cards":
            self._draw_centered_header(canvas, scene.visual_title, scene.visual_subtitle, y=110)
            n = min(3, len(nodes))
            cw, ch, gap = 380, 390, 56
            start_x = (W - (n * cw + (n - 1) * gap)) // 2
            cy = 275
            for i, nd in enumerate(nodes[:n]):
                x1 = start_x + i * (cw + gap)
                is_act = (i == focus_i)
                _draw_glow_rect(
                    canvas, (x1, cy, x1 + cw, cy + ch), radius=28,
                    fill_rgba=(48, 48, 52, 255) if is_act else (40, 40, 44, 240),
                    border_rgb=orange if is_act else (72, 72, 78),
                    border_w=3 if is_act else 2, glow=is_act,
                )
                if i == 0 and ai_img_path:
                    icon = _fit_image_rounded(ai_img_path, 160, 160, radius=32)
                    canvas.alpha_composite(icon, (x1 + (cw - 160) // 2, cy + 52))
                else:
                    self._draw_node_glyph(canvas, x1 + cw // 2, cy + 132, i + 1, active=is_act)
                d = ImageDraw.Draw(canvas)
                self._center_text(d, nd["label"], x1 + cw // 2, cy + 245, self.f_card_title, (255, 255, 255))
                self._center_text(d, nd["sub"][:18], x1 + cw // 2, cy + 302, self.f_card_sub, muted)
                if nd.get("tag"):
                    tag_col = orange if is_act else red
                    self._draw_pill_badge(canvas, x1 + cw - 150, cy - 20, nd["tag"], tag_col)

        elif lt == "split_ai_illustration_callout" or lt == "crawled_evidence_spotlight":
            # Left: structured animated flow / crawled facts; Right: PyTorch AI Illustration + glowing orange callout box (like UrFrDJ 150s!)
            d = ImageDraw.Draw(canvas)
            d.rectangle((96, 118, 104, 176), fill=(*orange, 255))
            d.text((124, 118), scene.visual_title, font=self.f_h1, fill=(255, 255, 255))
            if scene.visual_subtitle:
                d.text((124, 184), scene.visual_subtitle, font=self.f_h2, fill=(*muted, 255))

            for i, nd in enumerate(nodes[:3]):
                by = 265 + i * 165
                is_act = (i == focus_i)
                _draw_glow_rect(
                    canvas, (96, by, 880, by + 136), radius=22,
                    fill_rgba=(48, 48, 52, 255) if is_act else (38, 38, 42, 245),
                    border_rgb=orange if is_act else (68, 68, 74),
                    border_w=3 if is_act else 1, glow=is_act,
                )
                d = ImageDraw.Draw(canvas)
                d.ellipse((124, by + 38, 180, by + 94), fill=(*orange, 255) if is_act else (64, 64, 70, 255))
                self._center_text(d, str(i + 1), 152, by + 48, self.f_card_title, (20, 20, 20) if is_act else (230, 230, 230))
                d.text((206, by + 28), nd["label"], font=self.f_card_title, fill=(255, 255, 255))
                d.text((206, by + 76), nd["sub"][:26], font=self.f_card_sub, fill=(*muted, 255))
                if nd.get("tag"):
                    self._draw_pill_badge(canvas, 710, by + 44, nd["tag"][:12], orange if is_act else (70, 70, 78))

            # Right AI Illustration + Orange Callout Card
            _draw_glow_rect(canvas, (960, 120, 1824, 835), radius=28, fill_rgba=(34, 34, 38, 255), border_rgb=(68, 68, 74), border_w=2)
            art = _fit_image_rounded(ai_img_path, 816, 405, radius=22)
            canvas.alpha_composite(art, (984, 144))
            if scene.badge_text:
                self._draw_pill_badge(canvas, 1260, 526, scene.badge_text, orange, outline_only=False)
            _draw_glow_rect(canvas, (990, 590, 1794, 805), radius=20, fill_rgba=(28, 28, 30, 255), border_rgb=orange, border_w=2, glow=True)
            d = ImageDraw.Draw(canvas)
            ct = scene.callout_title or "公開資訊查證重點"
            cb = scene.callout_body or (cited_sources[0].key_facts[0][:44] if cited_sources and cited_sources[0].key_facts else scene.visual_subtitle)
            d.text((1022, 616), ct, font=self.f_card_title, fill=(*orange, 255))
            self._draw_wrapped(d, cb, 1022, 672, 740, self.f_card_sub, (235, 235, 240))
            if cited_sources:
                s0 = cited_sources[0]
                d.text((1022, 762), f"▸ 查證網址：{_smart_clip(s0.url, 58)}", font=self.f_src, fill=(*muted, 255))

        elif lt == "terminal_code_window":
            # Exact macOS dark terminal window (`aCvEYcz/frame_2s.jpg` & `280s.jpg`)
            _draw_glow_rect(canvas, (330, 120, 1590, 810), radius=24, fill_rgba=(28, 28, 30, 255), border_rgb=(75, 75, 82), border_w=2, glow=True)
            d = ImageDraw.Draw(canvas)
            d.line((330, 184, 1590, 184), fill=(62, 62, 68, 255), width=2)
            for idx_c, col in enumerate(((95, 95, 102), (95, 95, 102), (95, 95, 102))):
                cx = 374 + idx_c * 30
                d.ellipse((cx - 9, 144, cx + 9, 162), fill=(*col, 255))
            self._center_text(d, "garychen-agent — zsh", 960, 136, self.f_mono, (185, 185, 192))
            d.ellipse((392, 238, 414, 260), fill=(*orange, 255))
            d.text((434, 224), scene.visual_title, font=self.f_h1, fill=(255, 255, 255))

            for i, nd in enumerate(nodes[:3]):
                ry = 340 + i * 138
                is_act = (i == focus_i)
                _draw_glow_rect(
                    canvas, (410, ry, 1510, ry + 108), radius=18,
                    fill_rgba=(44, 44, 48, 255) if is_act else (34, 34, 38, 255),
                    border_rgb=orange if is_act else (62, 62, 68),
                    border_w=2, glow=is_act,
                )
                d = ImageDraw.Draw(canvas)
                d.text((442, ry + 20), f"$ {nd['label']}", font=self.f_mono, fill=(*orange, 255) if is_act else (235, 235, 240))
                d.text((442, ry + 62), f"└ {nd['sub'][:34]}", font=self.f_card_sub, fill=(*muted, 255))
                if nd.get("tag"):
                    self._draw_pill_badge(canvas, 1310, ry + 30, nd["tag"][:12], green if is_act else (72, 72, 78))

        elif lt == "step_pipeline_flow":
            # Exact numbered horizontal step pipeline + branching git/agent curve (`aCvEYcz/frame_140s.jpg`)
            self._draw_centered_header(canvas, scene.visual_title, scene.visual_subtitle, y=105)
            n = min(4, max(3, len(nodes)))
            used = nodes[:n]
            xs = [int(260 + i * (1400 / max(1, n - 1))) for i in range(n)]
            cy = 340
            d = ImageDraw.Draw(canvas)
            for i in range(n - 1):
                col = orange if i < focus_i else (95, 95, 102)
                d.line((xs[i] + 42, cy, xs[i + 1] - 42, cy), fill=(*col, 255), width=4)
                # Arrowhead
                ax = xs[i + 1] - 44
                d.polygon([(ax, cy), (ax - 14, cy - 8), (ax - 14, cy + 8)], fill=(*col, 255))

            for i, nd in enumerate(used):
                cx = xs[i]
                is_act = (i == focus_i)
                done = (i < focus_i)
                ring_col = orange if is_act else (green if done else (95, 95, 102))
                _draw_glow_rect(
                    canvas, (cx - 34, cy - 34, cx + 34, cy + 34), radius=34,
                    fill_rgba=(*orange, 255) if is_act else (38, 38, 42, 255),
                    border_rgb=ring_col, border_w=3, glow=is_act,
                )
                d = ImageDraw.Draw(canvas)
                lbl_num = "✓" if done else str(i + 1)
                self._center_text(d, lbl_num, cx, cy - 19, self.f_card_title, (20, 20, 20) if is_act else (255, 255, 255))

                _draw_glow_rect(
                    canvas, (cx - 145, cy + 62, cx + 145, cy + 230), radius=22,
                    fill_rgba=(48, 48, 54, 255) if is_act else (38, 38, 42, 240),
                    border_rgb=orange if is_act else (70, 70, 76),
                    border_w=3 if is_act else 1, glow=is_act,
                )
                d = ImageDraw.Draw(canvas)
                self._center_text(d, nd["label"][:11], cx, cy + 98, self.f_card_title, (255, 255, 255))
                self._center_text(d, nd["sub"][:14], cx, cy + 158, self.f_card_sub, muted)

            # Bottom callout bar with AI thumbnail
            _draw_glow_rect(canvas, (280, 640, 1640, 825), radius=22, fill_rgba=(32, 32, 36, 255), border_rgb=orange, border_w=2)
            if ai_img_path:
                thumb = _fit_image_rounded(ai_img_path, 220, 145, radius=16)
                canvas.alpha_composite(thumb, (304, 660))
            d = ImageDraw.Draw(canvas)
            d.text((555, 672), scene.callout_title or "關鍵自動化防線", font=self.f_card_title, fill=(*orange, 255))
            d.text((555, 730), (scene.callout_body or scene.visual_subtitle)[:42], font=self.f_card_sub, fill=(235, 235, 240))

        elif lt == "versus_debate_matrix":
            # Exact Pros vs Cons debate layout (`KWAvlqxNVAk/frame_800s.jpg`)
            d = ImageDraw.Draw(canvas)
            d.rectangle((110, 118, 118, 176), fill=(*orange, 255))
            d.text((140, 118), scene.visual_title, font=self.f_h1, fill=(255, 255, 255))

            left_title = nodes[0]["label"] if len(nodes) > 0 else "新架構優勢"
            right_title = nodes[1]["label"] if len(nodes) > 1 else "傳統做法痛點"

            _draw_glow_rect(canvas, (180, 245, 850, 685), radius=26, fill_rgba=(36, 44, 38, 245), border_rgb=green, border_w=2, glow=(focus_i % 2 == 0))
            _draw_glow_rect(canvas, (1070, 245, 1740, 685), radius=26, fill_rgba=(46, 36, 36, 245), border_rgb=red, border_w=2, glow=(focus_i % 2 == 1))
            _draw_glow_rect(canvas, (908, 415, 1012, 519), radius=52, fill_rgba=(32, 32, 36, 255), border_rgb=orange, border_w=3, glow=True)
            d = ImageDraw.Draw(canvas)
            self._center_text(d, "VS", 960, 446, self.f_card_title, (255, 255, 255))

            d.text((235, 285), left_title, font=self.f_h1, fill=(*green, 255))
            d.text((1125, 285), right_title, font=self.f_h1, fill=(*red, 255))
            for idx_b, nd in enumerate(nodes[:3]):
                d.text((235, 395 + idx_b * 78), f"●  {nd['sub'] or nd['label']}", font=self.f_card_sub, fill=(235, 235, 240))
                opp = nd.get("tag") or "人工維護成本高"
                d.text((1125, 395 + idx_b * 78), f"●  {opp}", font=self.f_card_sub, fill=(225, 210, 210))

            concl = scene.callout_body or scene.visual_subtitle or "不是額外負擔，而是規模化的關鍵訊號"
            self._center_text(d, concl[:30], 960, 745, self.f_card_title, (255, 255, 255))
            d.line((620, 808, 1300, 808), fill=(*orange, 255), width=4)

        elif lt == "checklist_architecture_box":
            # Exact orange-tabbed container with green checkmarks + AI illustration (`aCvEYcz/frame_80s.jpg`)
            _draw_glow_rect(canvas, (260, 195, 1660, 815), radius=28, fill_rgba=(36, 36, 40, 255), border_rgb=orange, border_w=3, glow=True)
            _draw_glow_rect(canvas, (320, 152, 650, 236), radius=42, fill_rgba=(38, 38, 42, 255), border_rgb=orange, border_w=3)
            d = ImageDraw.Draw(canvas)
            self._center_text(d, scene.visual_title[:10], 485, 172, self.f_card_title, orange)

            for i, nd in enumerate(nodes[:4]):
                ry = 285 + i * 116
                is_act = (i <= focus_i)
                d.ellipse((340, ry, 396, ry + 56), fill=(*green, 255) if is_act else (68, 68, 74, 255))
                self._center_text(d, "✓", 368, ry + 8, self.f_card_title, (18, 18, 18) if is_act else (180, 180, 185))
                d.text((428, ry + 2), nd["label"], font=self.f_card_title, fill=(255, 255, 255))
                d.text((428, ry + 44), nd["sub"][:24], font=self.f_card_sub, fill=(*muted, 255))

            d.line((1030, 265, 1030, 755), fill=(72, 72, 78, 255), width=2)
            art = _fit_image_rounded(ai_img_path, 510, 360, radius=24)
            canvas.alpha_composite(art, (1090, 275))
            d = ImageDraw.Draw(canvas)
            self._center_text(d, (scene.callout_body or scene.visual_subtitle)[:20], 1345, 675, self.f_card_title, (255, 255, 255))

        else:  # hub_spoke_ecosystem
            self._draw_centered_header(canvas, scene.visual_title, scene.visual_subtitle, y=96)
            cx, cy = 960, 445
            sat_coords = [(420, 340), (1500, 340), (480, 685), (1440, 685)]
            d = ImageDraw.Draw(canvas)
            for i, nd in enumerate(nodes[:4]):
                sx, sy = sat_coords[i]
                is_act = (i == focus_i)
                d.line((cx, cy, sx, sy), fill=(*orange, 255) if is_act else (95, 95, 102, 255), width=4 if is_act else 2)
                _draw_glow_rect(
                    canvas, (sx - 180, sy - 68, sx + 180, sy + 68), radius=22,
                    fill_rgba=(48, 48, 54, 255) if is_act else (38, 38, 42, 245),
                    border_rgb=orange if is_act else (72, 72, 78),
                    border_w=3 if is_act else 2, glow=is_act,
                )
                d = ImageDraw.Draw(canvas)
                self._center_text(d, nd["label"][:12], sx, sy - 42, self.f_card_title, (255, 255, 255))
                self._center_text(d, nd["sub"][:15], sx, sy + 12, self.f_card_sub, muted)

            # Central glowing hub with PyTorch AI visual
            _draw_glow_rect(canvas, (cx - 145, cy - 145, cx + 145, cy + 145), radius=36, fill_rgba=(30, 30, 34, 255), border_rgb=orange, border_w=4, glow=True)
            hub_art = _fit_image_rounded(ai_img_path, 254, 254, radius=28)
            canvas.alpha_composite(hub_art, (cx - 127, cy - 127))
            if scene.badge_text:
                self._draw_pill_badge(canvas, cx - 85, cy + 128, scene.badge_text, orange)

        # 5. Optional Studio Presenter Avatar (bottom-right, exact coordinates x=1630, y=790 from KWAvlqxNVAk)
        if script.avatar_mode and AVATAR_PNG.exists():
            av = Image.open(AVATAR_PNG).convert("RGBA").resize((230, 230), Image.Resampling.LANCZOS)
            canvas.alpha_composite(av, (1642, 804))

        # 6. Bottom Rounded Dark Subtitle Pill (`Y = 922 .. 1019`, fill `#090909`)
        if subtitle_text:
            d = ImageDraw.Draw(canvas)
            sub_font = self.f_sub
            tb = d.textbbox((0, 0), subtitle_text, font=sub_font)
            tw = tb[2] - tb[0]
            if tw > 1640:
                sub_font = _font(FONT_BOLD, 32)
                tb = d.textbbox((0, 0), subtitle_text, font=sub_font)
                tw = tb[2] - tb[0]
            pw = min(1780, max(360, tw + 84))
            px1 = (W - pw) // 2
            py1, py2 = 922, 1019
            d.rounded_rectangle((px1, py1, px1 + pw, py2), radius=16, fill=(9, 9, 9, 242))
            th = tb[3] - tb[1]
            self._center_text(d, subtitle_text, W // 2, py1 + (97 - th) // 2 - 4, sub_font, (255, 255, 255))

        return canvas.convert("RGB")

    def _draw_centered_header(self, canvas: Image.Image, title: str, sub: str, y: int):
        d = ImageDraw.Draw(canvas)
        self._center_text(d, title, self.t.long_width // 2, y, self.f_h1, (255, 255, 255))
        if sub:
            self._center_text(d, sub, self.t.long_width // 2, y + 66, self.f_h2, _hex_rgb(self.t.text_secondary_hex))

    @staticmethod
    def _center_text(draw: ImageDraw.ImageDraw, text: str, cx: int, y: int, font: ImageFont.FreeTypeFont, fill: tuple):
        bb = draw.textbbox((0, 0), text, font=font)
        w = bb[2] - bb[0]
        draw.text((cx - w // 2, y), text, font=font, fill=fill)

    @staticmethod
    def _draw_wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, max_w: int, font: ImageFont.FreeTypeFont, fill: tuple):
        line = ""
        cy = y
        for ch in text:
            test = line + ch
            bb = draw.textbbox((0, 0), test, font=font)
            if bb[2] - bb[0] > max_w and line:
                draw.text((x, cy), line, font=font, fill=fill)
                line = ch
                cy += 34
            else:
                line = test
        if line:
            draw.text((x, cy), line, font=font, fill=fill)

    def _draw_pill_badge(self, canvas: Image.Image, x: int, y: int, text: str, rgb: tuple[int, int, int], outline_only: bool = False):
        d = ImageDraw.Draw(canvas)
        bb = d.textbbox((0, 0), text, font=self.f_badge)
        pw = (bb[2] - bb[0]) + 34
        ph = 42
        fill = (28, 28, 32, 245) if outline_only else (*rgb, 255)
        txt_col = (*rgb, 255) if outline_only else (255, 255, 255, 255)
        d.rounded_rectangle((x, y, x + pw, y + ph), radius=21, fill=fill, outline=(*rgb, 255), width=2)
        d.text((x + 17, y + 7), text, font=self.f_badge, fill=txt_col)

    def _draw_node_glyph(self, canvas: Image.Image, cx: int, cy: int, num: int, active: bool):
        orange = _hex_rgb(self.t.accent_orange_hex)
        _draw_glow_rect(
            canvas, (cx - 64, cy - 64, cx + 64, cy + 64), radius=32,
            fill_rgba=(*orange, 35) if active else (56, 56, 62, 255),
            border_rgb=orange if active else (95, 95, 104),
            border_w=3, glow=active,
        )
        d = ImageDraw.Draw(canvas)
        self._center_text(d, f"0{num}", cx, cy - 22, self.f_h1, orange if active else (230, 230, 235))

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
        W, H, FPS = self.t.long_width, self.t.long_height, self.t.fps
        total_frames = max(1, int(round(total_duration * FPS)))
        sources_by_id = {s.source_id: s for s in sources}
        scenes_by_id = {sc.scene_id: sc for sc in script.scenes}
        orange_np = np.array(_hex_rgb(self.t.accent_orange_hex), dtype=np.uint8)
        bg_np = np.array(_hex_rgb(self.t.bg_stock_hex if script.avatar_mode else self.t.bg_tutorial_hex), dtype=np.uint8)

        # Build timeline intervals covering [0, total_frames)
        # Each cue belongs to a scene_id and line_idx
        state_cache: dict[tuple[str, int, str], np.ndarray] = {}

        def get_state_arr(sc_id: str, step_idx: int, sub_txt: str) -> np.ndarray:
            key = (sc_id, step_idx, sub_txt)
            if key not in state_cache:
                sc = scenes_by_id[sc_id]
                im = self.render_scene_state(
                    script=script,
                    scene=sc,
                    active_step_idx=step_idx,
                    subtitle_text=sub_txt,
                    ai_img_path=image_map.get(sc_id),
                    sources_by_id=sources_by_id,
                )
                state_cache[key] = np.array(im, dtype=np.uint8)
            return state_cache[key]

        # Save crisp 1920x1080 YouTube Thumbnail from Scene 1
        thumb_img = self.render_scene_state(
            script=script,
            scene=script.scenes[0],
            active_step_idx=0,
            subtitle_text="",
            ai_img_path=image_map.get(script.scenes[0].scene_id),
            sources_by_id=sources_by_id,
        )
        thumbnail_png.parent.mkdir(parents=True, exist_ok=True)
        thumb_img.save(str(thumbnail_png))

        # Hardware H.264 encoder on macOS (`h264_videotoolbox`), `libx264` on Linux
        vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "4500k", "-profile:v", "high"] if platform.system() == "Darwin" else [
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

        # Map each frame index to (scene_id, step_idx, subtitle_text, frames_into_scene)
        cue_idx = 0
        n_cues = len(line_cues)
        first_sc_id = script.scenes[0].scene_id
        current_sc_id = first_sc_id
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

                # Smooth 0.35s fade-in transition on scene switch
                sc_age = f_idx - sc_start_frame
                if sc_age < 21 and f_idx > 0:
                    alpha = 1.0 - math.pow(1.0 - (sc_age / 21.0), 3)
                    frame = (bg_np * (1.0 - alpha) + base_arr * alpha).astype(np.uint8)
                else:
                    frame = base_arr.copy()

                # Real-time 60fps top #EB8B1B progress bar
                prog_w = max(4, int((f_idx + 1) / total_frames * W))
                frame[0:4, 0:prog_w] = orange_np
                proc.stdin.write(frame.tobytes())
        finally:
            proc.stdin.close()
            stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
            rc = proc.wait()
            if rc != 0:
                raise RuntimeError(f"FFmpeg long encode failed (rc={rc}): {stderr_out[-400:]}")
