from __future__ import annotations

from pathlib import Path

from .config import ASSETS_DIR, EpisodeScript
from .crawler import CHROME_APP_BIN
from .html_renderer import FONT_BOLD, FONT_MONO, app_squircle, esc, img_to_data_uri, svg_icon

PORTRAITS_DIR = ASSETS_DIR / "avatar/portraits"
FALLBACK_PORTRAIT = ASSETS_DIR / "avatar/gary_thumbnail_portrait.png"

BEARISH_KEYWORDS = ("跌", "崩", "殺", "恐慌", "泡沫", "剩", "腰斬", "危機", "錯殺", "風險", "暴跌", "回檔", "狂跌", "見頂")
POINTING_KEYWORDS = ("零", "免費", "$0", "神器", "新手", "全攻略", "實戰", "必學", "自動")


def _pick_real_portrait(script: EpisodeScript) -> tuple[Path, str]:
    """Selects authentic @garychenai real-photo portrait (`NAOH +` beanie) matching topic emotion & genre."""
    blob = f"{script.title} {script.thumbnail_line1} {script.thumbnail_line2}"
    if script.category == "us_stocks":
        if any(k in blob for k in BEARISH_KEYWORDS):
            p = PORTRAITS_DIR / "gary_bearish_mic.png"
            if p.exists():
                return p, "bearish_stocks"
        p = PORTRAITS_DIR / "gary_focused.png"
        if p.exists():
            return p, "bullish_stocks"
    else:
        if any(k in blob for k in POINTING_KEYWORDS):
            p = PORTRAITS_DIR / "gary_pointing.png"
            if p.exists():
                return p, "pointing_tutorial"
        p = PORTRAITS_DIR / "gary_expressive.png"
        if p.exists():
            return p, "expressive_tech"
    for cand in ("gary_pointing.png", "gary_focused.png"):
        cp = PORTRAITS_DIR / cand
        if cp.exists():
            return cp, "default"
    return FALLBACK_PORTRAIT, "default"


def _stock_mountain_svg(is_crash: bool) -> str:
    """Authentic jagged crash / rally area chart matching 78_KWAvlqxNVAk & 80_VbWh0Yhl_xM thumbnails."""
    if is_crash:
        pts = [
            (0, 80), (48, 42), (96, 95), (145, 70), (195, 138), (240, 118),
            (290, 178), (345, 162), (398, 224), (455, 205), (512, 268),
            (565, 248), (620, 318), (675, 296), (735, 355), (790, 392),
        ]
        stroke = "#EF4444"
        g_top, g_bot = "rgba(239,68,68,0.88)", "rgba(185,28,28,0.18)"
    else:
        pts = [
            (0, 375), (55, 352), (110, 365), (168, 312), (225, 328), (282, 268),
            (340, 282), (395, 215), (455, 228), (515, 158), (575, 174),
            (635, 108), (695, 122), (750, 62), (795, 44),
        ]
        stroke = "#22C55E"
        g_top, g_bot = "rgba(34,197,94,0.88)", "rgba(21,128,61,0.16)"

    poly_line = " ".join(f"{x},{y}" for x, y in pts)
    area_d = f"M 0,430 L " + " L ".join(f"{x},{y}" for x, y in pts) + f" L {pts[-1][0]},430 Z"
    return f"""
    <svg width="820" height="430" viewBox="0 0 820 430" style="position:absolute;left:0;bottom:0;z-index:4;overflow:visible;">
      <defs>
        <linearGradient id="stkGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="{stroke}" stop-opacity="0.92"/>
          <stop offset="75%" stop-color="{stroke}" stop-opacity="0.48"/>
          <stop offset="100%" stop-color="{stroke}" stop-opacity="0.08"/>
        </linearGradient>
      </defs>
      <path d="{area_d}" fill="url(#stkGrad)"/>
      <polyline points="{poly_line}" fill="none" stroke="{stroke}" stroke-width="6" stroke-linejoin="round" style="filter:drop-shadow(0 0 18px {g_top});"/>
    </svg>"""


def render_studio_thumbnail(script: EpisodeScript, out_png: Path):
    """
    V6 Studio @garychenai Thumbnail Engine (1920x1080):
      - Authentic multi-pose real Gary Chen (`NAOH +` beanie) portrait matched to topic sentiment
      - US Stocks: Pitch-dark studio + jagged red crash / green surge mountain chart + large official ticker brand badge
      - AI Agent / Tech: Pointing or expressive Gary + oversized high-contrast UI prop card & brand squircle
    """
    from playwright.sync_api import sync_playwright

    portrait_path, mode = _pick_real_portrait(script)
    portrait_uri = img_to_data_uri(str(portrait_path)) if portrait_path.exists() else ""
    b0 = script.beats[0]
    nodes = b0.nodes[:3]

    def _vis_units(s: str) -> float:
        return sum(0.56 if ch.isascii() else 1.0 for ch in s)

    max_u = max(_vis_units(script.thumbnail_line1), _vis_units(script.thumbnail_line2), 1.0)
    font_px = 148 if max_u <= 7.2 else (128 if max_u <= 8.8 else (110 if max_u <= 10.6 else 94))

    is_stocks = (script.category == "us_stocks")
    is_crash = (mode == "bearish_stocks")

    if is_stocks:
        bg_css = "radial-gradient(circle at 78% 36%, #2A1E1A 0%, #0D0D10 52%, #050507 100%)"
        line1_col = "#FF9500" if is_crash else "#FFC700"
        brand_ic = nodes[0].icon if nodes and nodes[0].icon not in ("trending_up", "dollar", "shield") else "nvidia"
        m0 = nodes[0].metric if nodes else ""
        m1 = nodes[1].metric if len(nodes) > 1 else b0.badge_text
        chart_layer = _stock_mountain_svg(is_crash=is_crash)
        prop_html = f"""
        <div style="position:absolute;left:530px;bottom:175px;z-index:8;display:flex;flex-direction:column;align-items:flex-start;gap:18px;">
          <div style="display:flex;align-items:center;gap:20px;background:rgba(18,18,22,0.92);border:2.5px solid {'#EF4444' if is_crash else '#22C55E'};padding:18px 32px;border-radius:24px;box-shadow:0 24px 56px rgba(0,0,0,0.8);">
            {svg_icon(brand_ic, 64)}
            <div>
              <div style="font-size:44px;font-weight:700;letter-spacing:-0.5px;line-height:1.05;">{esc(b0.badge_text or m1)}</div>
              <div style="font-size:24px;color:{'#F87171' if is_crash else '#4ADE80'};font-weight:700;margin-top:6px;">{esc(m0)} → {esc(m1)}</div>
            </div>
          </div>
        </div>"""
    else:
        bg_css = "radial-gradient(circle at 32% 45%, #3B3B42 0%, #202025 68%, #151518 100%)"
        line1_col = "#FFC700"
        chart_layer = ""
        chk_rows = "".join(
            f'<div style="display:flex;align-items:center;justify-content:space-between;padding:13px 18px;border-bottom:1px solid rgba(255,255,255,0.09);">'
            f'<span style="font-family:GaryMono,GarySans,monospace;font-size:30px;color:#F4F4F5;font-weight:700;">● {esc(nd.label[:14])}</span>'
            f'<span style="width:38px;height:38px;border-radius:50%;background:#22C55E;color:#09090B;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:24px;">✓</span></div>'
            for nd in nodes[:3]
        )
        hero_ic = next((nd.icon for nd in nodes if nd.icon not in ("dollar", "check", "trending_up")), (nodes[0].icon if nodes else "robot"))
        prop_html = f"""
        <div style="position:absolute;left:76px;bottom:68px;z-index:10;display:flex;align-items:center;gap:30px;">
          {app_squircle(hero_ic, 178, True)}
          <div style="width:650px;background:rgba(24,24,28,0.97);border:3px solid rgba(34,197,94,0.68);border-radius:28px;padding:24px 30px;box-shadow:0 28px 70px rgba(0,0,0,0.72);">
            {chk_rows}
            <div style="margin-top:18px;display:flex;align-items:center;justify-content:space-between;">
              <span style="background:#22C55E;color:#09090B;font-size:28px;font-weight:700;padding:8px 26px;border-radius:12px;display:inline-block;">{esc(b0.badge_text or "$0 免費開源")}</span>
              <span style="font-size:24px;color:#F59E0B;font-weight:700;">{esc(nodes[1].metric if len(nodes) > 1 else "")}</span>
            </div>
          </div>
        </div>"""

    portrait_h = 1045 if mode == "pointing_tutorial" else 1020
    html_doc = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>
      @font-face {{ font-family: 'GarySans'; src: url('file://{FONT_BOLD}') format('opentype'); font-weight: 700; }}
      @font-face {{ font-family: 'GaryMono'; src: url('file://{FONT_MONO}') format('truetype'); font-weight: 700; }}
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{
        width: 1920px; height: 1080px; overflow: hidden;
        background: {bg_css};
        font-family: 'GarySans', sans-serif; position: relative; color: #FFF;
      }}
      .big-stroke {{
        font-size: {font_px}px; font-weight: 700; line-height: 1.13; letter-spacing: -2px; white-space: nowrap;
        -webkit-text-stroke: 22px #09090B;
        paint-order: stroke fill;
        filter: drop-shadow(0 16px 26px rgba(0,0,0,0.82));
      }}
    </style></head><body>
      {chart_layer}
      {f'<img src="{portrait_uri}" style="position:absolute;right:0;bottom:0;height:{portrait_h}px;width:auto;z-index:6;filter:drop-shadow(-18px 8px 34px rgba(0,0,0,0.62));"/>' if portrait_uri else ''}
      <div style="position:absolute;left:76px;top:78px;z-index:12;max-width:1180px;">
        <div class="big-stroke" style="color:{line1_col};">{esc(script.thumbnail_line1)}</div>
        <div class="big-stroke" style="color:#FFFFFF;margin-top:8px;">{esc(script.thumbnail_line2)}</div>
      </div>
      {prop_html}
    </body></html>"""

    out_png.parent.mkdir(parents=True, exist_ok=True)
    tmp_html = out_png.parent / "_thumb_stage.html"
    tmp_html.write_text(html_doc, encoding="utf-8")
    launch_kwargs = {"headless": True}
    if Path(CHROME_APP_BIN).exists():
        launch_kwargs["executable_path"] = CHROME_APP_BIN
    with sync_playwright() as p:
        br = p.chromium.launch(**launch_kwargs, args=["--allow-file-access-from-files"])
        pg = br.new_page(viewport={"width": 1920, "height": 1080, "device_scale_factor": 1})
        pg.goto(tmp_html.resolve().as_uri(), wait_until="load")
        pg.evaluate("() => document.fonts.ready")
        pg.screenshot(path=str(out_png), type="png")
        br.close()
    tmp_html.unlink(missing_ok=True)
