from __future__ import annotations

from pathlib import Path

from .config import ASSETS_DIR, EpisodeScript
from .crawler import CHROME_APP_BIN
from .html_renderer import FONT_BOLD, FONT_MONO, app_squircle, esc, img_to_data_uri

PORTRAIT_CUTOUT = ASSETS_DIR / "avatar/gary_thumbnail_portrait.png"


def render_studio_thumbnail(script: EpisodeScript, out_png: Path):
    """
    Renders an authentic @garychenai high-CTR YouTube thumbnail (1920x1080) matching `ref_thumbnails_grid.jpg`:
      - Right side: Studio portrait cutout of Gary Chen in his signature dark knit beanie
      - Left side: Massive 148px bold 2-line stacked headline (#FFC700 Gold + #FFFFFF White) with thick #000000 stroke
      - Bottom-left: Crisp floating UI card (GitHub checks or verified financial KPIs + brand squircles)
    """
    from playwright.sync_api import sync_playwright

    portrait_uri = img_to_data_uri(str(PORTRAIT_CUTOUT)) if PORTRAIT_CUTOUT.exists() else ""
    b0 = script.beats[0]
    nodes = b0.nodes[:3]

    if script.category == "us_stocks":
        mini_rows = "".join(
            f'<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 18px;background:#222226;border-radius:12px;">'
            f'<span style="font-size:24px;color:#D4D4D8;font-weight:700;">{esc(nd.label[:10])}</span>'
            f'<span style="font-size:28px;color:#4ADE80;font-weight:700;">{esc(nd.metric)}</span></div>'
            for nd in nodes[:2]
        )
        card_html = f"""
        <div style="width:680px;background:rgba(26,26,30,0.95);border:2.5px solid #EB8B1B;border-radius:24px;padding:24px 28px;box-shadow:0 24px 60px rgba(0,0,0,0.65);display:flex;flex-direction:column;gap:14px;">
          {mini_rows}
        </div>"""
    else:
        chk_rows = "".join(
            f'<div style="display:flex;align-items:center;justify-content:space-between;padding:9px 14px;border-bottom:1px solid rgba(255,255,255,0.08);">'
            f'<span style="font-family:GaryMono,GarySans,monospace;font-size:24px;color:#F4F4F5;">● {esc(nd.label[:18])}</span>'
            f'<span style="width:30px;height:30px;border-radius:50%;background:#22C55E;color:#09090B;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:20px;">✓</span></div>'
            for nd in nodes[:3]
        )
        card_html = f"""
        <div style="display:flex;align-items:center;gap:26px;">
          {app_squircle(nodes[0].icon, 138, True)}
          <div style="width:520px;background:rgba(28,28,32,0.96);border:2px solid rgba(34,197,94,0.55);border-radius:22px;padding:18px 22px;box-shadow:0 24px 60px rgba(0,0,0,0.65);">
            {chk_rows}
            <div style="margin-top:14px;"><span style="background:#238636;color:#FFF;font-size:21px;font-weight:700;padding:7px 20px;border-radius:9px;display:inline-block;">{esc(b0.badge_text or "免費開源實戰")}</span></div>
          </div>
        </div>"""

    def _vis_units(s: str) -> float:
        return sum(0.56 if ch.isascii() else 1.0 for ch in s)

    max_u = max(_vis_units(script.thumbnail_line1), _vis_units(script.thumbnail_line2), 1.0)
    font_px = 144 if max_u <= 7.2 else (124 if max_u <= 8.8 else (106 if max_u <= 10.6 else 92))

    html_doc = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>
      @font-face {{ font-family: 'GarySans'; src: url('file://{FONT_BOLD}') format('opentype'); font-weight: 700; }}
      @font-face {{ font-family: 'GaryMono'; src: url('file://{FONT_MONO}') format('truetype'); font-weight: 700; }}
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{
        width: 1920px; height: 1080px; overflow: hidden;
        background: radial-gradient(circle at 32% 45%, #38383E 0%, #1F1F23 70%, #161619 100%);
        font-family: 'GarySans', sans-serif; position: relative; color: #FFF;
      }}
      .big-stroke {{
        font-size: {font_px}px; font-weight: 700; line-height: 1.14; letter-spacing: -2px; white-space: nowrap;
        -webkit-text-stroke: 20px #09090B;
        paint-order: stroke fill;
        filter: drop-shadow(0 14px 22px rgba(0,0,0,0.72));
      }}
    </style></head><body>
      {f'<img src="{portrait_uri}" style="position:absolute;right:0;bottom:0;height:1015px;width:auto;z-index:5;"/>' if portrait_uri else ''}
      <div style="position:absolute;left:84px;top:96px;z-index:10;max-width:1140px;">
        <div class="big-stroke" style="color:#FFC700;">{esc(script.thumbnail_line1)}</div>
        <div class="big-stroke" style="color:#FFFFFF;margin-top:8px;">{esc(script.thumbnail_line2)}</div>
      </div>
      <div style="position:absolute;left:88px;bottom:86px;z-index:10;">
        {card_html}
      </div>
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
