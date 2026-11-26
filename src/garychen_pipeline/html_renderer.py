from __future__ import annotations

import base64
import html
import json
import math
from pathlib import Path
from typing import Any

from .config import ASSETS_DIR, CrawledSource, DesignTokens, EpisodeScript, ShortBeatSpec, VisualBeat

FONT_BOLD = (ASSETS_DIR / "fonts/NotoSansTC-Bold.otf").resolve()
FONT_MED = (ASSETS_DIR / "fonts/NotoSansTC-Medium.otf").resolve()
FONT_MONO = (ASSETS_DIR / "fonts/JetBrainsMono-Bold.ttf").resolve()
BRAND_JSON = (ASSETS_DIR / "brand_svgs/brand_icons.json").resolve()

BRAND_LIB: dict[str, dict[str, str]] = (
    json.loads(BRAND_JSON.read_text(encoding="utf-8")) if BRAND_JSON.exists() else {}
)

BRAND_ALIASES: dict[str, str] = {
    "nvda": "nvidia",
    "msft": "microsoft",
    "googl": "google",
    "alphabet": "google",
    "codex": "openai",
    "operator": "openai",
    "gpt": "openai",
    "browser-use": "playwright",
    "browser_use": "playwright",
    "agent": "robot",
    "bot": "robot",
    "postgres": "postgresql",
    "ts": "typescript",
    "twitter": "x",
    "gcal": "calendar",
}

STROKE_ICON_SVGS: dict[str, str] = {
    "terminal": '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    "code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "globe": '<circle cx="12" cy="12" r="9.5"/><line x1="2.5" y1="12" x2="21.5" y2="12"/><path d="M12 2.5a14.5 14.5 0 0 1 4 9.5 14.5 14.5 0 0 1-4 9.5 14.5 14.5 0 0 1-4-9.5 14.5 14.5 0 0 1 4-9.5z"/>',
    "cpu": '<rect x="5" y="5" width="14" height="14" rx="2.5"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="2" x2="9" y2="5"/><line x1="15" y1="2" x2="15" y2="5"/><line x1="9" y1="19" x2="9" y2="22"/><line x1="15" y1="19" x2="15" y2="22"/>',
    "shield": '<path d="M12 21s7.5-3.8 7.5-9.5V5.2L12 2.5 4.5 5.2v6.3C4.5 17.2 12 21 12 21z"/><polyline points="9 12 11 14 15.2 9.8"/>',
    "check": '<path d="M21 11.5a9 9 0 1 1-5.3-8.2"/><polyline points="21 4.5 12 13.5 9 10.5"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="8" ry="2.8"/><path d="M20 12c0 1.5-3.6 2.8-8 2.8S4 13.5 4 12"/><path d="M4 5.5v13c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8v-13"/>',
    "trending_up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "dollar": '<line x1="12" y1="2" x2="12" y2="22"/><path d="M16.5 6H9.8a3.2 3.2 0 0 0 0 6.4h4.4a3.2 3.2 0 0 1 0 6.4H6.5"/>',
    "layers": '<polygon points="12 3 3 7.5 12 12 21 7.5 12 3"/><polyline points="3 16.5 12 21 21 16.5"/><polyline points="3 12 12 16.5 21 12"/>',
    "zap": '<polygon points="13 2.5 4 13.5 12 13.5 11 21.5 20 10.5 12 10.5 13 2.5"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2.2"/><path d="M8 11V7.5a4 4 0 0 1 8 0V11"/>',
    "users": '<circle cx="12" cy="8.5" r="3.8"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/>',
    "play": '<polygon points="6 4 19 12 6 20 6 4"/>',
    "aws": '<path d="M4 16c4.5 3 11.5 3 16 0"/><polyline points="17 14 20 16 18 19"/><path d="M7 11l3-6 3 6M8 9h4M15 5l2 6 2-6"/>',
    "sparkles": '<path d="M12 3l1.8 5.6a2 2 0 0 0 1.3 1.3L20.7 12l-5.6 1.8a2 2 0 0 0-1.3 1.3L12 20.7l-1.8-5.6a2 2 0 0 0-1.3-1.3L3.3 12l5.6-1.8a2 2 0 0 0 1.3-1.3L12 3z"/>',
}

CAM_VIEWPORT_LONG = (68, 138, 1140, 684)  # Enlarged V6 viewport (+46% area) on 1920x1080 canvas
CAM_VIEWPORT_SHORT = (70, 310, 940, 560)  # (x, y, w, h) on 1080x1920 canvas


def _resolve_icon_key(name: str) -> str:
    k = (name or "sparkles").strip().lower()
    return BRAND_ALIASES.get(k, k)


def svg_icon(name: str, size: int = 30, color: str | None = None) -> str:
    key = _resolve_icon_key(name)
    if key in BRAND_LIB:
        entry = BRAND_LIB[key]
        fg = color or entry.get("fg", "#EB8B1B")
        if "custom_svg" in entry:
            return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" style="display:block;flex-shrink:0;">{entry["custom_svg"]}</svg>'
        return (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="{fg}" stroke="none" '
            f'style="display:block;flex-shrink:0;"><path d="{entry["path"]}"/></svg>'
        )
    fg = color or "#EB8B1B"
    body = STROKE_ICON_SVGS.get(key, STROKE_ICON_SVGS["sparkles"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{fg}" '
        f'stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" style="color:{fg};display:block;flex-shrink:0;">{body}</svg>'
    )


def app_squircle(icon_name: str, size: int = 92, glow: bool = False) -> str:
    key = _resolve_icon_key(icon_name)
    if key in BRAND_LIB:
        bg = BRAND_LIB[key].get("bg", "#2A2A2E")
        fg = BRAND_LIB[key].get("fg", "#FFFFFF")
    else:
        bg, fg = "#2B2B30", "#EB8B1B"
    border = "2.2px solid #EB8B1B" if glow else "1.4px solid rgba(255,255,255,0.14)"
    sh = "0 0 38px rgba(235,139,27,0.40), 0 14px 30px rgba(0,0,0,0.48)" if glow else "0 14px 28px rgba(0,0,0,0.40)"
    rad = int(round(size * 0.25))
    icon_color = None if key in BRAND_LIB else fg
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:{rad}px;background:{bg};border:{border};'
        f'box-shadow:{sh};display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
        f'{svg_icon(key, int(size * 0.54), icon_color)}</div>'
    )


def img_to_data_uri(path_str: str | None) -> str:
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.exists():
        return ""
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def esc(s: str) -> str:
    return html.escape(str(s or ""))


def _human_silhouette_svg(filled: bool = False, height: int = 195) -> str:
    w = int(round(height * 0.44))
    if filled:
        return (
            f'<svg width="{w}" height="{height}" viewBox="0 0 84 190" style="filter:drop-shadow(0 0 24px rgba(235,139,27,0.55));display:block;">'
            f'<circle cx="42" cy="28" r="19" fill="#EB8B1B"/>'
            f'<path d="M18 68 C18 54 66 54 66 68 L72 122 C72 128 63 128 61 121 L57 86 L54 180 C54 186 44 186 44 180 L42 132 L40 180 C40 186 30 186 30 180 L27 86 L23 121 C21 128 12 128 12 122 Z" fill="#EB8B1B"/>'
            f'</svg>'
        )
    return (
        f'<svg width="{w}" height="{height}" viewBox="0 0 84 190" style="opacity:0.62;display:block;">'
        f'<circle cx="42" cy="28" r="18" fill="none" stroke="#D4D4D8" stroke-width="2.6"/>'
        f'<path d="M18 68 C18 54 66 54 66 68 L72 122 C72 128 63 128 61 121 L57 86 L54 180 C54 186 44 186 44 180 L42 132 L40 180 C40 186 30 186 30 180 L27 86 L23 121 C21 128 12 128 12 122 Z" fill="none" stroke="#D4D4D8" stroke-width="2.6" stroke-linejoin="round"/>'
        f'</svg>'
    )


def _smooth_svg_path(pts: list[tuple[float, float]]) -> str:
    if not pts:
        return ""
    if len(pts) == 1:
        return f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
    d = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        cx1 = x0 + (x1 - x0) * 0.45
        cx2 = x0 + (x1 - x0) * 0.55
        d.append(f"C {cx1:.1f} {y0:.1f}, {cx2:.1f} {y1:.1f}, {x1:.1f} {y1:.1f}")
    return " ".join(d)


def _pipeline_bar_html(steps: list[str], active_idx: int) -> str:
    if not steps or active_idx < 0:
        return ""
    items = []
    for i, lbl in enumerate(steps[:5]):
        is_act = (i == active_idx)
        is_done = (i < active_idx)
        dot_bg = "#EB8B1B" if is_act else ("#22C55E" if is_done else "#323236")
        dot_fg = "#121214" if (is_act or is_done) else "#A1A1AA"
        pill_style = (
            "background:rgba(235,139,27,0.16);border:1.5px solid #EB8B1B;color:#FFFFFF;box-shadow:0 0 22px rgba(235,139,27,0.25);"
            if is_act
            else ("background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);color:#A1A1AA;" if not is_done else "background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.30);color:#D4D4D8;")
        )
        items.append(
            f'<div style="display:flex;align-items:center;gap:9px;padding:6px 15px;border-radius:999px;font-size:15px;font-weight:700;{pill_style}">'
            f'<span style="width:21px;height:21px;border-radius:50%;background:{dot_bg};color:{dot_fg};font-size:13px;display:inline-flex;align-items:center;justify-content:center;">{"✓" if is_done else i+1}</span>'
            f'<span>{esc(lbl[:8])}</span></div>'
        )
        if i < len(steps[:5]) - 1:
            line_col = "#EB8B1B" if i < active_idx else "rgba(255,255,255,0.12)"
            items.append(f'<div style="width:28px;height:2px;background:{line_col};"></div>')
    return (
        f'<div class="base-only" style="position:absolute;top:24px;left:0;right:0;display:flex;justify-content:center;align-items:center;z-index:14;">'
        f'{"".join(items)}</div>'
    )


def base_css(bg_hex: str, width: int, height: int) -> str:
    return f"""
    @font-face {{ font-family: 'GarySans'; src: url('file://{FONT_MED}') format('opentype'); font-weight: 500; }}
    @font-face {{ font-family: 'GarySans'; src: url('file://{FONT_BOLD}') format('opentype'); font-weight: 700; }}
    @font-face {{ font-family: 'GaryMono'; src: url('file://{FONT_MONO}') format('truetype'); font-weight: 700; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      width: {width}px; height: {height}px; overflow: hidden;
      background: {bg_hex};
      color: #FFFFFF;
      font-family: 'GarySans', -apple-system, sans-serif;
      -webkit-font-smoothing: antialiased;
      position: relative;
    }}
    body.transparent-pass {{ background: transparent !important; }}
    body.transparent-pass .base-only {{ opacity: 0 !important; }}
    .mono {{ font-family: 'GaryMono', 'GarySans', monospace; }}
    .chap-crumb {{
      position: absolute; top: 20px; left: 28px;
      display: flex; align-items: baseline; gap: 10px; font-size: 16px; z-index: 15;
    }}
    .chap-crumb .num {{ color: #EB8B1B; font-weight: 700; letter-spacing: 0.4px; }}
    .chap-crumb .lbl {{ color: #8A8A93; font-weight: 500; }}
    .stage {{
      position: absolute; top: 72px; left: 56px; right: 56px; bottom: 146px;
      display: flex; flex-direction: column; justify-content: center; align-items: center;
    }}
    .stage-zoom-lg {{
      transform: scale(1.28); transform-origin: center center;
      display: flex; flex-direction: column; justify-content: center; align-items: center;
    }}
    .stage-zoom-md {{
      transform: scale(1.16); transform-origin: center center;
      display: flex; flex-direction: column; justify-content: center; align-items: center;
    }}
    .ghost {{
      border: 1.8px dashed rgba(255,255,255,0.13);
      background: rgba(255,255,255,0.012);
      border-radius: 22px;
    }}
    .slot-wrap {{ position: relative; }}
    .slot-wrap > .ghost {{ position: absolute; inset: 0; pointer-events: none; }}
    .glass-card {{
      background: linear-gradient(180deg, rgba(48,48,52,0.97) 0%, rgba(36,36,40,0.97) 100%);
      border: 1.2px solid rgba(255,255,255,0.10);
      border-radius: 22px;
      box-shadow: 0 18px 42px rgba(0,0,0,0.44);
    }}
    .glass-card.orange-glow {{
      border: 2px solid #EB8B1B;
      box-shadow: 0 0 34px rgba(235,139,27,0.24), 0 18px 42px rgba(0,0,0,0.46);
    }}
    .pill {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 14px; border-radius: 999px; font-size: 16px; font-weight: 700;
    }}
    .pill-orange {{ background: rgba(235,139,27,0.16); color: #F59E0B; border: 1.4px solid rgba(235,139,27,0.65); }}
    .pill-orange-solid {{ background: #EB8B1B; color: #141414; }}
    .pill-green {{ background: rgba(34,197,94,0.14); color: #4ADE80; border: 1.2px solid rgba(34,197,94,0.52); }}
    .pill-red {{ background: rgba(239,68,68,0.15); color: #F87171; border: 1.2px solid rgba(239,68,68,0.52); }}
    .pill-muted {{ background: rgba(255,255,255,0.07); color: #A1A1AA; border: 1px solid rgba(255,255,255,0.11); }}
    .cite-badge {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 16px; border-radius: 999px;
      background: rgba(20,20,23,0.90); border: 1px solid rgba(255,255,255,0.11);
      font-size: 15px; color: #A1A1AA; margin-top: 18px;
    }}
    .cite-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #EB8B1B; }}
    .bar-title {{
      display: flex; align-items: center; gap: 16px; align-self: flex-start; margin-bottom: 30px;
    }}
    .bar-line {{ width: 5px; height: 38px; background: #EB8B1B; border-radius: 3px; }}
    .feathered-3d {{
      -webkit-mask-image: radial-gradient(ellipse 80% 78% at 50% 50%, #000 52%, transparent 98%);
      mask-image: radial-gradient(ellipse 80% 78% at 50% 50%, #000 52%, transparent 98%);
    }}
    """


def _cite_pill(s0: CrawledSource | None) -> str:
    return ""


def _hud_cite_pill(s0: CrawledSource | None) -> str:
    if not s0:
        return ""
    dt_p = f" · {esc(s0.published_date)}" if s0.published_date else ""
    return (
        f'<div class="cite-badge" style="margin:0;padding:5px 15px;font-size:14px;background:rgba(16,16,19,0.88);">'
        f'<span class="cite-dot"></span><span>公開來源：{esc(s0.domain)}{dt_p}｜{esc(s0.title[:40])}</span></div>'
    )


def _build_chart_svg(
    points: list[list[Any]],
    secondary: list[list[Any]] | None = None,
    width: int = 1140,
    height: int = 370,
    dual_label: str = "",
) -> str:
    if len(points) < 2:
        points = [["FY23", 270, "$270 億"], ["FY24", 609, "$609 億"], ["FY25", 1305, "$1,305 億"], ["FY26", 2159, "$2,159 億"]]
    vals = [float(p[1]) for p in points]
    vmin, vmax = min(vals), max(vals)
    span = max(1e-3, vmax - vmin)
    pad_x, pad_top, pad_bot = 95, 58, 66
    usable_w = width - 2 * pad_x
    usable_h = height - pad_top - pad_bot

    coords: list[tuple[float, float]] = []
    for idx, v in enumerate(vals):
        x = pad_x + (idx / max(1, len(vals) - 1)) * usable_w
        y = pad_top + usable_h * (1.0 - (v - vmin) / span * 0.86 - 0.08)
        coords.append((x, y))

    main_d = _smooth_svg_path(coords)
    sec_svg = ""
    if secondary and len(secondary) >= 2:
        svals = [float(p[1]) for p in secondary]
        smin, smax = min(svals), max(svals)
        sspan = max(1e-3, smax - smin)
        scoords = []
        for idx, sv in enumerate(svals):
            sx = pad_x + (idx / max(1, len(svals) - 1)) * usable_w
            sy = pad_top + usable_h * (1.0 - (sv - smin) / sspan * 0.52 - 0.06)
            scoords.append((sx, sy))
        sec_d = _smooth_svg_path(scoords)
        lx, ly = scoords[-1]
        slbl = str(secondary[-1][2]) if len(secondary[-1]) >= 3 else f"{secondary[-1][1]}%"
        sec_svg = (
            f'<path d="{sec_d}" fill="none" stroke="#E4E4E7" stroke-width="3.4" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="6.5" fill="#FFFFFF"/>'
            f'<text x="{lx:.1f}" y="{min(height - 38, ly + 30):.1f}" fill="#E4E4E7" font-size="20" font-weight="700" text-anchor="end">營益率 {esc(slbl)}</text>'
        )
        if dual_label:
            sec_svg += (
                f'<rect x="{pad_x + 12}" y="{pad_top - 4}" width="166" height="34" rx="17" fill="rgba(235,139,27,0.18)" stroke="#EB8B1B" stroke-width="1.4"/>'
                f'<text x="{pad_x + 95}" y="{pad_top + 19}" fill="#F59E0B" font-size="18" font-weight="700" text-anchor="middle">{esc(dual_label)}</text>'
            )

    dots_and_labels = []
    for idx, (pt, (cx, cy)) in enumerate(zip(points, coords)):
        xlbl = str(pt[0])
        vlbl = str(pt[2]) if len(pt) >= 3 else str(pt[1])
        is_end = (idx == len(points) - 1)
        is_start = (idx == 0)
        dots_and_labels.append(
            f'<text x="{cx:.1f}" y="{height - 18}" fill="#9CA3AF" font-size="18" font-weight="700" text-anchor="middle">{esc(xlbl)}</text>'
        )
        if is_start or is_end or idx == len(points) - 2:
            col = "#EB8B1B" if is_end else "#E4E4E7"
            r = 8 if is_end else 5.5
            dots_and_labels.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{col}"/>'
                f'<text x="{cx:.1f}" y="{cy - 18:.1f}" fill="{col}" font-size="{"24" if is_end else "18"}" font-weight="700" text-anchor="middle">{esc(vlbl)}</text>'
            )

    mid_x, mid_y = coords[len(coords) // 2]
    return f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="overflow:visible;">
      <defs>
        <radialGradient id="amberFlare" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#FFB84D" stop-opacity="0.55"/>
          <stop offset="45%" stop-color="#EB8B1B" stop-opacity="0.18"/>
          <stop offset="100%" stop-color="#EB8B1B" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <line class="base-only" x1="{pad_x - 20}" y1="{height - pad_bot}" x2="{width - pad_x + 20}" y2="{height - pad_bot}" stroke="rgba(255,255,255,0.18)" stroke-width="1.8"/>
      <line class="base-only" x1="{pad_x - 20}" y1="{pad_top - 10}" x2="{pad_x - 20}" y2="{height - pad_bot}" stroke="rgba(255,255,255,0.14)" stroke-width="1.5"/>
      <g data-wipe="1">
        <circle cx="{mid_x:.1f}" cy="{mid_y:.1f}" r="95" fill="url(#amberFlare)"/>
        <path d="{main_d}" fill="none" stroke="rgba(235,139,27,0.28)" stroke-width="14" stroke-linecap="round"/>
        <path d="{main_d}" fill="none" stroke="#EB8B1B" stroke-width="5" stroke-linecap="round"/>
        {sec_svg}
        {''.join(dots_and_labels)}
      </g>
    </svg>"""


def build_long_beat_html(
    script: EpisodeScript,
    beat: VisualBeat,
    ai_img_path: str | None,
    sources_by_id: dict[str, CrawledSource],
    tokens: DesignTokens,
) -> tuple[str, int]:
    """
    Renders V4 1920x1080 Remotion stage with:
      - `base-only` skeleton + top workflow pipeline bar
      - `data-step="0..n-1"` independent RGBA spring layers
      - `data-typing="1"` live 60fps typing lines
      - `data-wipe="1"` progressive 60fps SVG curve/arrow wipes
      - `#cam-viewport` live 60fps camera pan+zoom + cursor click slot
    """
    bg_hex = tokens.bg_stock_hex if script.avatar_mode else tokens.bg_tutorial_hex
    cited = [sources_by_id[sid] for sid in beat.source_ids if sid in sources_by_id]
    s0 = cited[0] if cited else None
    nodes = beat.nodes[:4]
    while len(nodes) < 3:
        from .config import VisualNode
        nodes.append(VisualNode(label=beat.visual_title or "關鍵重點", sub=beat.clauses[-1][:20], icon="sparkles"))
    n_clauses = max(1, len(beat.clauses))
    lt = beat.layout_type
    ai_uri = img_to_data_uri(ai_img_path)

    crumb_html = ""
    if beat.chapter_index >= 2:
        crumb_html = (
            f'<div class="chap-crumb base-only">'
            f'<span class="num">{beat.chapter_index:02d} / {beat.total_chapters:02d}</span>'
            f'<span class="lbl">{esc(beat.chapter_title)}</span></div>'
        )
    pipe_html = _pipeline_bar_html(beat.pipeline_steps, beat.active_pipeline_idx)

    def step_of(idx: int) -> int:
        return min(n_clauses - 1, idx)

    stage_inner = ""

    # 1. CLAUDE CLI / TERMINAL LIVE TYPING DIALOG (aCvEYcz t=3s..9s)
    if lt == "claude_chat_dialog":
        cmds = beat.code_lines if beat.code_lines else [n.label for n in nodes]
        rows = []
        for i, nd in enumerate(nodes[:3]):
            line_main = cmds[i] if i < len(cmds) else nd.label
            typing_attr = 'data-typing="1"' if i == 0 else f'data-step="{step_of(i)}"'
            rows.append(
                f'<div {typing_attr} style="display:flex;flex-direction:column;gap:8px;">'
                f'<div style="display:flex;align-items:center;gap:12px;font-size:23px;font-weight:700;">'
                f'<span style="width:10px;height:10px;border-radius:50%;background:#EB8B1B;flex-shrink:0;"></span>'
                f'<span class="mono">{esc(line_main[:46])}</span></div>'
                f'<div style="color:#A1A1AA;font-size:19px;padding-left:22px;">└ {esc(nd.sub or nd.label)}</div>'
                + (
                    f'<div style="margin-left:22px;margin-top:4px;background:#1D1D20;border:1px solid rgba(235,139,27,0.35);border-radius:10px;padding:9px 16px;font-size:18px;color:#F4F4F5;" class="mono">&gt; {esc(nd.tag)}</div>'
                    if nd.tag
                    else ""
                )
                + "</div>"
            )
        stage_inner = f"""
        <div class="glass-card base-only" style="width:750px;min-height:450px;position:absolute;"></div>
        <div style="width:750px;min-height:450px;border-radius:22px;overflow:hidden;position:relative;">
          <div class="base-only" style="height:46px;background:#1E1E22;border-bottom:1px solid rgba(255,255,255,0.08);display:flex;align-items:center;justify-content:space-between;padding:0 20px;">
            <div style="display:flex;gap:8px;">
              <span style="width:11px;height:11px;border-radius:50%;background:#EF4444;opacity:0.75;"></span>
              <span style="width:11px;height:11px;border-radius:50%;background:#F59E0B;opacity:0.75;"></span>
              <span style="width:11px;height:11px;border-radius:50%;background:#22C55E;opacity:0.75;"></span>
            </div>
            <span class="mono" style="font-size:16px;color:#A1A1AA;">claude — agent terminal</span>
            <span style="width:42px;"></span>
          </div>
          <div style="padding:32px 38px;display:flex;flex-direction:column;gap:24px;">
            {''.join(rows)}
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 2. SLASH-COMMAND LIVE PROMPT BAR (08_pstack tile 3!)
    elif lt == "slash_command_prompt_bar":
        prompt_line = beat.code_lines[0] if beat.code_lines else f"{nodes[0].label}：{nodes[0].sub}"
        slash_cmd = beat.badge_text if beat.badge_text.startswith("/") else f"/{nodes[0].icon}"
        stage_inner = f"""
        <div class="base-only" style="margin-bottom:36px;">
          <span class="pill pill-orange" style="font-size:24px;padding:9px 28px;" class="mono">{esc(slash_cmd)}</span>
        </div>
        <div style="display:flex;align-items:center;gap:24px;position:relative;">
          <div class="base-only" style="width:68px;height:68px;border-radius:50%;border:2px solid rgba(255,255,255,0.28);background:#2B2B30;display:flex;align-items:center;justify-content:center;">
            {svg_icon("users", 32, "#E4E4E7")}
          </div>
          <div class="glass-card base-only" style="width:820px;height:88px;"></div>
          <div style="width:820px;height:88px;margin-left:-844px;padding:0 28px;display:flex;align-items:center;justify-content:space-between;position:relative;">
            <div data-typing="1" class="mono" style="font-size:24px;color:#FFFFFF;font-weight:700;">&gt; {esc(prompt_line[:38])}</div>
            <span data-step="{step_of(0)}" class="pill pill-red" style="position:absolute;top:-16px;right:22px;font-size:15px;">{esc(nodes[0].tag or "原本痛點")}</span>
          </div>
        </div>
        <div data-wipe="1" style="margin:22px 0;color:#EB8B1B;font-size:28px;font-weight:700;">↓ AI Agent 結構化拆解</div>
        <div style="display:flex;gap:24px;">
          {''.join(
              f'<div class="slot-wrap" style="width:430px;height:122px;"><div class="ghost base-only"></div>'
              f'<div data-step="{step_of(i+1)}" class="glass-card {"orange-glow" if i==0 else ""}" style="width:430px;height:122px;padding:20px 24px;display:flex;align-items:center;gap:18px;">'
              f'{app_squircle(nd.icon, 68, i==0)}'
              f'<div><div style="font-size:22px;font-weight:700;">{esc(nd.label)}</div>'
              f'<div style="font-size:16px;color:#A1A1AA;margin-top:4px;">{esc(nd.sub[:24])}</div></div></div></div>'
              for i, nd in enumerate(nodes[1:3])
          )}
        </div>"""

    # 3. VS CODE LIVE SYNTAX TYPING + AI ROBOT + APP/TEST PREVIEW (08_pstack tiles 4 & 7!)
    elif lt == "code_editor_live_preview":
        code_lns = beat.code_lines[:4] if beat.code_lines else [
            "from browser_use import Agent",
            "agent = Agent(task='自動擷取報表與比對', llm=llm)",
            "result = await agent.run()",
        ]
        code_html = "".join(
            f'<div style="display:flex;gap:16px;font-size:19px;line-height:1.75;" class="mono">'
            f'<span style="color:#52525B;user-select:none;">{idx+1}</span>'
            f'<span style="color:{"#F59E0B" if idx==0 else ("#93C5FD" if idx==1 else "#E4E4E7")};">{esc(ln[:46])}</span></div>'
            for idx, ln in enumerate(code_lns)
        )
        right_rows = "".join(
            f'<div data-step="{step_of(i+1)}" style="display:flex;align-items:center;justify-content:space-between;padding:12px 18px;background:#232327;border-radius:12px;border:1px solid rgba(255,255,255,0.08);">'
            f'<span style="font-size:19px;font-weight:700;">{esc(nd.label)}</span>'
            f'<span class="pill pill-green" style="font-size:15px;">✓ {esc(nd.tag or nd.metric or "通過")}</span></div>'
            for i, nd in enumerate(nodes[:3])
        )
        stage_inner = f"""
        <div class="base-only" style="margin-bottom:26px;">
          <span class="pill pill-orange" style="font-size:21px;padding:7px 24px;">{esc(beat.visual_title)}</span>
        </div>
        <div style="display:flex;align-items:center;gap:28px;">
          <div style="position:relative;width:620px;height:340px;">
            <div class="glass-card base-only" style="position:absolute;inset:0;background:#1B1B1F;"></div>
            <div class="base-only" style="position:relative;height:44px;background:#242429;border-radius:22px 22px 0 0;border-bottom:1px solid rgba(255,255,255,0.08);display:flex;align-items:center;padding:0 20px;gap:10px;">
              {svg_icon("python", 20)}
              <span class="mono" style="font-size:16px;color:#D4D4D8;">agent_workflow.py</span>
            </div>
            <div data-typing="1" style="position:relative;padding:24px 26px;">{code_html}</div>
          </div>

          <div style="display:flex;flex-direction:column;align-items:center;gap:10px;">
            <div data-step="{step_of(0)}">{app_squircle("robot", 82, True)}</div>
            <svg width="90" height="28" viewBox="0 0 90 28"><g data-wipe="1"><line x1="4" y1="14" x2="76" y2="14" stroke="#EB8B1B" stroke-width="3.5"/><polygon points="74,6 88,14 74,22" fill="#EB8B1B"/></g></svg>
          </div>

          <div class="slot-wrap" style="width:500px;height:340px;">
            <div class="ghost base-only"></div>
            <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:500px;height:340px;padding:24px 26px;display:flex;flex-direction:column;justify-content:space-between;">
              <div style="display:flex;align-items:center;justify-content:space-between;">
                <span style="font-size:21px;font-weight:700;color:#4ADE80;">● 實戰自動執行結果</span>
                <span class="pill pill-orange" style="font-size:14px;">{esc(beat.badge_text)}</span>
              </div>
              <div style="display:flex;flex-direction:column;gap:12px;">{right_rows}</div>
            </div>
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 4. APP SQUIRCLES + PRICE STRIKETHROUGH (UrFrDJ t=9s..18s)
    elif lt == "app_squircles_strikethrough":
        comp_icons = [("claude", "Claude Code"), ("openai", "Operator"), ("zapier", "Zapier")]
        comp_items = [
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:10px;opacity:0.48;filter:grayscale(0.8);">'
            f'{app_squircle(ic_k, 76, False)}'
            f'<span style="font-size:16px;color:#A1A1AA;">{ic_lbl}</span>'
            f'<span class="pill pill-red" style="font-size:14px;">$20–$200/月</span></div>'
            for ic_k, ic_lbl in comp_icons
        ]
        hero_nd = nodes[0]
        hero_badge = beat.badge_text or "$0 / 月"
        stage_inner = f"""
        <div data-step="{step_of(0)}" style="display:flex;gap:52px;margin-bottom:44px;">{''.join(comp_items)}</div>
        <div style="display:flex;align-items:center;gap:46px;">
          <div data-step="{step_of(1)}" style="font-size:38px;font-weight:700;color:#EF4444;text-decoration:line-through;opacity:0.88;">$20–$200</div>
          <div class="slot-wrap" style="width:140px;height:140px;">
            <div class="ghost base-only" style="border-radius:35px;"></div>
            <div data-step="{step_of(1)}">{app_squircle(hero_nd.icon, 140, True)}</div>
          </div>
          <div data-step="{step_of(2)}" style="font-size:50px;font-weight:700;color:#4ADE80;">{esc(hero_badge)}</div>
        </div>
        <div data-step="{step_of(2)}" style="margin-top:30px;display:flex;flex-direction:column;align-items:center;">
          <span class="pill pill-muted" style="font-size:21px;padding:8px 26px;color:#FFFFFF;">{esc(beat.visual_title or hero_nd.label)}</span>
          {_cite_pill(s0)}
        </div>"""

    # 5. ECOSYSTEM HUB WITH 60FPS GROWING SVG ARROWS (UrFrDJ t=27s & 82_google tile 5)
    elif lt == "ecosystem_node_graph":
        hero_nd = nodes[0]
        children = nodes[1:4] if len(nodes) > 1 else nodes[:3]
        while len(children) < 3:
            children.append(nodes[-1])
        child_cols = []
        for idx_ch, ch in enumerate(children[:3]):
            st = step_of(idx_ch + 1)
            tag_pill = f'<span class="pill pill-orange" style="font-size:15px;margin-top:6px;">{esc(ch.tag or ch.metric)}</span>' if (ch.tag or ch.metric) else ""
            child_cols.append(
                f'<div style="display:flex;flex-direction:column;align-items:center;width:250px;">'
                f'<div class="slot-wrap" style="width:90px;height:90px;">'
                f'<div class="ghost base-only" style="border-radius:22px;"></div>'
                f'<div data-step="{st}">{app_squircle(ch.icon, 90, False)}</div></div>'
                f'<div data-step="{st}" style="text-align:center;margin-top:12px;">'
                f'<div style="font-size:22px;font-weight:700;">{esc(ch.label)}</div>'
                f'<div style="font-size:16px;color:#9CA3AF;margin-top:4px;">{esc(ch.sub[:20])}</div>'
                f'{tag_pill}</div></div>'
            )
        stage_inner = f"""
        <div class="base-only" style="font-size:30px;font-weight:700;color:#E4E4E7;margin-bottom:22px;">{esc(beat.visual_title)}</div>
        <div style="position:relative;width:1000px;min-height:475px;display:flex;flex-direction:column;align-items:center;">
          <div data-step="{step_of(0)}" style="z-index:5;display:flex;flex-direction:column;align-items:center;">
            {app_squircle(hero_nd.icon, 110, True)}
            <span style="font-size:22px;font-weight:700;margin-top:10px;color:#EB8B1B;">{esc(hero_nd.label)}</span>
          </div>
          <svg width="860" height="106" viewBox="0 0 860 106" style="margin-top:4px;overflow:visible;">
            <line class="base-only" x1="430" y1="0" x2="145" y2="98" stroke="rgba(255,255,255,0.10)" stroke-width="2" stroke-dasharray="6 6"/>
            <line class="base-only" x1="430" y1="0" x2="430" y2="98" stroke="rgba(255,255,255,0.10)" stroke-width="2" stroke-dasharray="6 6"/>
            <line class="base-only" x1="430" y1="0" x2="715" y2="98" stroke="rgba(255,255,255,0.10)" stroke-width="2" stroke-dasharray="6 6"/>
            <g data-wipe="1">
              <line x1="430" y1="0" x2="145" y2="98" stroke="#EB8B1B" stroke-width="3.2"/>
              <line x1="430" y1="0" x2="430" y2="98" stroke="#EB8B1B" stroke-width="3.2"/>
              <line x1="430" y1="0" x2="715" y2="98" stroke="#EB8B1B" stroke-width="3.2"/>
            </g>
          </svg>
          <div style="display:flex;justify-content:space-between;width:860px;margin-top:4px;">
            {''.join(child_cols)}
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 6. PROTAGONIST GARY APP FLOW WITH 60FPS GROWING ARROWS (aCvEYcz t=48s)
    elif lt == "protagonist_app_flow":
        flow_nodes = nodes[:3]
        stage_inner = f"""
        <div class="base-only" style="display:flex;flex-direction:column;align-items:center;margin-bottom:34px;">
          <div style="font-size:34px;font-weight:700;">{esc(beat.visual_title)}</div>
        </div>
        <div style="display:flex;align-items:center;gap:24px;">
          <div data-step="{step_of(0)}" style="display:flex;align-items:center;gap:18px;">
            <div style="display:flex;flex-direction:column;align-items:center;gap:8px;">
              <div style="width:76px;height:76px;border-radius:50%;border:2.5px solid #EB8B1B;display:flex;align-items:center;justify-content:center;background:rgba(235,139,27,0.12);">
                {svg_icon("users", 34, "#FFFFFF")}
              </div>
              <span style="font-size:17px;font-weight:700;">Gary</span>
            </div>
            <div class="glass-card" style="width:240px;padding:22px 20px;border-radius:24px;position:relative;">
              <span class="pill pill-orange" style="position:absolute;top:-13px;right:14px;font-size:13px;">v1.0</span>
              <div style="font-size:20px;font-weight:700;margin-bottom:12px;">{esc(flow_nodes[0].label)}</div>
              <div style="font-size:15px;color:#A1A1AA;line-height:1.65;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:10px;">
                {esc(flow_nodes[0].sub)}
              </div>
              <div style="font-size:16px;font-weight:700;color:#EB8B1B;margin-top:10px;">{esc(flow_nodes[0].tag or "自動觸發")}</div>
            </div>
          </div>

          <svg width="56" height="24" viewBox="0 0 56 24"><g data-wipe="1"><line x1="2" y1="12" x2="44" y2="12" stroke="#EB8B1B" stroke-width="3.2"/><polygon points="42,5 54,12 42,19" fill="#EB8B1B"/></g></svg>
          <div class="slot-wrap" style="width:118px;height:126px;">
            <div class="ghost base-only" style="border-radius:26px;"></div>
            <div data-step="{step_of(1)}" style="display:flex;flex-direction:column;align-items:center;gap:10px;">
              {app_squircle(flow_nodes[1].icon, 92, True)}
              <span style="font-size:17px;font-weight:700;">{esc(flow_nodes[1].label[:11])}</span>
            </div>
          </div>

          <svg width="56" height="24" viewBox="0 0 56 24"><g data-wipe="1"><line x1="2" y1="12" x2="44" y2="12" stroke="#EB8B1B" stroke-width="3.2"/><polygon points="42,5 54,12 42,19" fill="#EB8B1B"/></g></svg>
          <div class="slot-wrap" style="width:118px;height:126px;">
            <div class="ghost base-only" style="border-radius:26px;"></div>
            <div data-step="{step_of(2)}" style="display:flex;flex-direction:column;align-items:center;gap:10px;">
              {app_squircle(flow_nodes[2].icon, 92, False)}
              <span style="font-size:17px;font-weight:700;">{esc(flow_nodes[2].label[:11])}</span>
            </div>
          </div>

          <div data-step="{step_of(3)}" style="display:flex;align-items:center;gap:16px;">
            <span style="font-size:30px;color:#22C55E;font-weight:700;">→</span>
            <div class="glass-card orange-glow" style="padding:20px 24px;max-width:295px;">
              <div style="font-size:19px;font-weight:700;color:#4ADE80;">✓ {esc(beat.callout_title)}</div>
              <div style="font-size:16px;color:#E4E4E7;margin-top:6px;line-height:1.45;">{esc(beat.callout_body[:36])}</div>
            </div>
          </div>
        </div>"""

    # 7. COMPACT 4-STEP HORIZONTAL AGENDA (UrFrDJ t=48s)
    elif lt == "agenda_four_steps":
        boxes = []
        for i in range(4):
            nd = nodes[i] if i < len(nodes) else nodes[-1]
            st = step_of(i)
            boxes.append(
                f'<div class="slot-wrap" style="width:236px;height:164px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:236px;height:164px;padding:18px 20px;display:flex;flex-direction:column;justify-content:space-between;align-items:center;">'
                f'<span style="align-self:flex-start;font-size:15px;color:#EB8B1B;font-weight:700;">STEP 0{i+1}</span>'
                f'{svg_icon(nd.icon, 36, "#EB8B1B")}'
                f'<span style="font-size:21px;font-weight:700;">{esc(nd.label[:9])}</span>'
                f'</div></div>'
            )
            if i < 3:
                boxes.append('<span data-wipe="1" style="font-size:26px;color:#EB8B1B;font-weight:700;">→</span>')
        stage_inner = f"""
        <div class="base-only" style="margin-bottom:32px;"><span class="pill pill-orange" style="font-size:18px;">◎ 今天這集實戰路線</span></div>
        <div style="display:flex;align-items:center;gap:18px;">{''.join(boxes)}</div>"""

    # 8. GITHUB PR LIST + BLAST-RADIUS RADAR (08_pstack tile 5!)
    elif lt in ("github_pr_blast_radius", "github_pr_checks_card", "feature_pill_matrix"):
        pr_rows_src = (s0.pr_or_issue_items[:5] if (s0 and s0.pr_or_issue_items) else [])
        if len(pr_rows_src) < 4:
            pr_rows_src = [f"#{2401+i} {nd.label} — {nd.sub[:16]}" for i, nd in enumerate(nodes[:4])]
        pr_html = []
        for idx_p, pr_txt in enumerate(pr_rows_src[:5]):
            hl = (idx_p in (0, 2))
            border_c = "#EB8B1B" if hl else "rgba(34,197,94,0.35)"
            pr_html.append(
                f'<div data-step="{step_of(min(idx_p, 2))}" style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-radius:10px;background:#222226;border:1.4px solid {border_c};">'
                f'<div style="display:flex;align-items:center;gap:10px;font-size:16px;" class="mono">'
                f'{svg_icon("git", 18, "#4ADE80")}'
                f'<span style="color:#F4F4F5;">{esc(pr_txt[:34])}</span></div>'
                f'<span class="pill pill-green" style="font-size:13px;padding:2px 10px;">Open ✓</span></div>'
            )
        stage_inner = f"""
        <div class="base-only" style="display:flex;align-items:center;gap:14px;margin-bottom:24px;">
          <span class="pill pill-orange">{esc(beat.badge_text or "自動防線")}</span>
          <span style="font-size:28px;font-weight:700;">{esc(beat.visual_title)}</span>
        </div>
        <div style="display:flex;align-items:center;gap:56px;">
          <div class="glass-card base-only" style="width:520px;height:380px;position:absolute;"></div>
          <div style="width:520px;height:380px;padding:24px 26px;display:flex;flex-direction:column;gap:12px;position:relative;">
            <div class="base-only" style="display:flex;align-items:center;gap:10px;font-size:20px;font-weight:700;margin-bottom:4px;">
              {svg_icon("github", 24, "#FFFFFF")} <span>Pull requests &amp; Checks</span>
            </div>
            {''.join(pr_html)}
          </div>

          <svg width="120" height="220" viewBox="0 0 120 220" style="overflow:visible;">
            <g data-wipe="1">
              <line x1="0" y1="60" x2="120" y2="110" stroke="#EB8B1B" stroke-width="2.4" opacity="0.85"/>
              <line x1="0" y1="150" x2="120" y2="110" stroke="#EB8B1B" stroke-width="2.4" opacity="0.85"/>
            </g>
          </svg>

          <div data-step="{step_of(2)}" style="position:relative;width:300px;height:300px;display:flex;align-items:center;justify-content:center;">
            <div style="position:absolute;width:290px;height:290px;border-radius:50%;border:1.5px solid rgba(255,255,255,0.12);"></div>
            <div style="position:absolute;width:205px;height:205px;border-radius:50%;border:1.5px solid rgba(34,197,94,0.28);background:rgba(34,197,94,0.05);"></div>
            <div style="position:absolute;width:120px;height:120px;border-radius:50%;border:2px solid rgba(34,197,94,0.55);background:rgba(34,197,94,0.12);"></div>
            <div style="width:54px;height:54px;border-radius:14px;background:#22C55E;color:#09090B;font-size:30px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 0 30px rgba(34,197,94,0.6);">✓</div>
            <span class="pill pill-green" style="position:absolute;top:12px;right:-24px;">{esc(beat.callout_title or "自動把關通過")}</span>
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 9. MULTI-AGENT SWARM ROBOT GRID (08_pstack tile 6!)
    elif lt == "swarm_subagents_grid":
        sub_bots = "".join(
            f'<div data-step="{step_of(min(2, 1 + i // 4))}" style="display:flex;flex-direction:column;align-items:center;gap:8px;">'
            f'{app_squircle("robot", 74, i in (0, 5))}'
            f'<span style="font-size:14px;color:#A1A1AA;" class="mono">Agent #{i+1}</span></div>'
            for i in range(8)
        )
        stage_inner = f"""
        <div class="base-only" style="margin-bottom:28px;">
          <span class="pill pill-orange" style="font-size:22px;padding:8px 26px;">{esc(beat.visual_title)}</span>
        </div>
        <div style="display:flex;align-items:center;gap:42px;">
          <div data-step="{step_of(0)}" class="glass-card orange-glow" style="width:280px;height:290px;padding:26px;display:flex;flex-direction:column;align-items:center;justify-content:space-between;">
            {app_squircle("robot", 98, True)}
            <div style="text-align:center;">
              <div style="font-size:23px;font-weight:700;">{esc(nodes[0].label)}</div>
              <div style="font-size:16px;color:#A1A1AA;margin-top:6px;">{esc(nodes[0].sub[:22])}</div>
            </div>
            <span class="pill pill-green">{esc(nodes[0].tag or "主控調度")}</span>
          </div>

          <svg width="74" height="28" viewBox="0 0 74 28"><g data-wipe="1"><line x1="2" y1="14" x2="60" y2="14" stroke="#EB8B1B" stroke-width="3.5"/><polygon points="58,6 72,14 58,22" fill="#EB8B1B"/></g></svg>

          <div style="position:relative;width:620px;height:310px;">
            <div class="glass-card base-only" style="position:absolute;inset:0;"></div>
            <span class="pill pill-muted base-only" style="position:absolute;top:-15px;right:24px;">{esc(beat.badge_text or "平行分工")}</span>
            <div style="position:relative;height:100%;padding:34px 36px;display:grid;grid-template-columns:repeat(4, 1fr);gap:22px;align-items:center;justify-items:center;">
              {sub_bots}
            </div>
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 10. LIVE DARK SCREENSHOT / WEBM TOUR WITH 60FPS CAMERA ZOOM & CURSOR SLOT
    elif lt == "browser_ui_live_tour":
        vx, vy, vw, vh = CAM_VIEWPORT_LONG
        callouts = []
        for i, nd in enumerate(nodes[:3]):
            st = step_of(i)
            callouts.append(
                f'<div class="slot-wrap" style="width:580px;height:132px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:580px;height:132px;padding:22px 26px;display:flex;align-items:center;gap:20px;">'
                f'<span style="width:44px;height:44px;border-radius:50%;background:#EB8B1B;color:#141414;font-weight:700;font-size:22px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">{i+1}</span>'
                f'<div><div style="font-size:26px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:19px;color:#A1A1AA;margin-top:6px;">{esc(nd.sub[:26])}</div></div></div></div>'
            )
        stage_inner = f"""
        <div class="base-only" style="position:fixed;left:{vx}px;top:{vy-42}px;width:{vw}px;height:42px;background:#1D1D22;border:1.5px solid rgba(255,255,255,0.16);border-bottom:none;border-radius:18px 18px 0 0;display:flex;align-items:center;padding:0 20px;gap:9px;">
          <span style="width:11px;height:11px;border-radius:50%;background:#EF4444;"></span>
          <span style="width:11px;height:11px;border-radius:50%;background:#F59E0B;"></span>
          <span style="width:11px;height:11px;border-radius:50%;background:#22C55E;"></span>
          <span class="mono" style="margin-left:14px;font-size:16px;color:#9CA3AF;">{esc(s0.url[:68] if s0 else beat.visual_title)}</span>
        </div>
        <div class="base-only" style="position:fixed;left:{vx}px;top:{vy}px;width:{vw}px;height:{vh}px;border:1.5px solid rgba(255,255,255,0.16);border-radius:0 0 18px 18px;box-shadow:0 28px 70px rgba(0,0,0,0.65);background:#141418;"></div>
        <div style="position:fixed;left:{vx + vw + 42}px;top:{vy + 14}px;width:590px;display:flex;flex-direction:column;gap:22px;">
          <div class="base-only" style="font-size:36px;font-weight:700;margin-bottom:6px;">{esc(beat.visual_title)}</div>
          {''.join(callouts)}
        </div>"""

    # 11. BEFORE VS AFTER STAMP WORKFLOW CARD (UrFrDJ t=884s)
    elif lt == "before_after_workflow_card":
        l_nd = nodes[0]
        r_nd = nodes[1] if len(nodes) > 1 else nodes[0]
        stage_inner = f"""
        <div style="display:flex;align-items:center;gap:38px;">
          <div data-step="{step_of(0)}" class="glass-card" style="width:460px;height:390px;padding:34px;display:flex;flex-direction:column;justify-content:space-between;position:relative;">
            <div style="display:flex;align-items:center;gap:12px;font-size:28px;font-weight:700;color:#E4E4E7;">
              {svg_icon("lock", 28, "#A1A1AA")} <span>以前：{esc(l_nd.label[:11])}</span>
            </div>
            <div style="font-size:21px;color:#A1A1AA;line-height:1.68;">{esc(l_nd.sub)}</div>
            <div style="align-self:flex-end;transform:rotate(-9deg);border:3px solid #EF4444;color:#F87171;background:rgba(239,68,68,0.15);padding:6px 22px;border-radius:8px;font-size:26px;font-weight:700;">
              {esc(l_nd.tag or "手動繁瑣")}
            </div>
          </div>
          <svg width="64" height="28" viewBox="0 0 64 28"><g data-wipe="1"><line x1="2" y1="14" x2="50" y2="14" stroke="#EB8B1B" stroke-width="3.6"/><polygon points="48,6 62,14 48,22" fill="#EB8B1B"/></g></svg>
          <div class="slot-wrap" style="width:460px;height:390px;">
            <div class="ghost base-only"></div>
            <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:460px;height:390px;padding:34px;display:flex;flex-direction:column;justify-content:space-between;">
              <div style="display:flex;align-items:center;gap:12px;font-size:28px;font-weight:700;color:#FFFFFF;">
                {svg_icon("zap", 28, "#4ADE80")} <span>現在：{esc(r_nd.label[:11])}</span>
              </div>
              <div style="display:flex;align-items:center;justify-content:center;gap:20px;">
                {app_squircle(r_nd.icon, 82, True)}
                <span style="color:#4ADE80;font-size:24px;font-weight:700;">— ✓ —</span>
                {app_squircle(nodes[-1].icon, 82, False)}
              </div>
              <div style="text-align:center;"><span class="pill pill-green" style="font-size:19px;padding:7px 24px;">{esc(r_nd.tag or "全自動完成")}</span></div>
            </div>
          </div>
        </div>"""

    # 12. SUBTLE EDITORIAL ILLUSTRATION + INSIGHT CARDS (08_pstack tile 9)
    elif lt == "concept_hero_split_3d":
        pills_col = []
        for i, nd in enumerate(nodes[:3]):
            st = step_of(i)
            is_bad = (nd.trend == "down")
            p_cls = "pill-red" if is_bad else ("pill-green" if i == 0 else "pill-orange")
            sym = "✕" if is_bad else "✓"
            pills_col.append(
                f'<div class="slot-wrap" style="width:520px;height:102px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card" style="width:520px;height:102px;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;">'
                f'<div style="display:flex;align-items:center;gap:16px;">'
                f'<span class="pill {p_cls}" style="padding:5px 12px;">{sym}</span>'
                f'<div><div style="font-size:22px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:16px;color:#A1A1AA;margin-top:3px;">{esc(nd.sub[:26])}</div></div></div>'
                + (f'<span class="mono" style="font-size:18px;color:#EB8B1B;">{esc(nd.tag)}</span>' if nd.tag else "")
                + '</div></div>'
            )
        art_block = (
            f'<img src="{ai_uri}" class="feathered-3d" style="width:560px;height:390px;object-fit:cover;display:block;"/>'
            if ai_uri
            else f'<div style="width:420px;height:340px;display:flex;align-items:center;justify-content:center;">{app_squircle(nodes[0].icon, 160, True)}</div>'
        )
        stage_inner = f"""
        <div style="display:flex;align-items:center;gap:56px;">
          <div style="display:flex;flex-direction:column;gap:18px;">
            <div class="bar-title base-only" style="margin-bottom:10px;"><div class="bar-line"></div><span style="font-size:34px;font-weight:700;">{esc(beat.visual_title)}</span></div>
            {''.join(pills_col)}
          </div>
          <div data-step="{step_of(0)}">{art_block}</div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 13. 60FPS ANIMATED MULTI-YEAR GROWTH CURVE (82_google tile 2!)
    elif lt == "animated_growth_curve":
        chart_svg = _build_chart_svg(beat.chart_points, None, width=1160, height=370)
        stage_inner = f"""
        <div class="base-only" style="font-size:40px;font-weight:700;margin-bottom:16px;">{esc(beat.visual_title)}</div>
        <div style="position:relative;">{chart_svg}</div>
        <div data-step="{step_of(1)}" style="display:flex;gap:28px;margin-top:12px;">
          <span class="pill pill-muted" style="font-size:18px;padding:7px 20px;">{esc(nodes[0].label)}：{esc(nodes[0].sub[:18])}</span>
          <span class="pill pill-orange" style="font-size:18px;padding:7px 20px;">{esc(beat.badge_text)}｜{esc(beat.callout_body[:24])}</span>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 14. 60FPS DUAL OPERATING LEVERAGE CHART (82_google tile 7!)
    elif lt == "operating_leverage_chart":
        chart_svg = _build_chart_svg(
            beat.chart_points,
            beat.secondary_chart_points,
            width=1160,
            height=370,
            dual_label="營運槓桿效應",
        )
        stage_inner = f"""
        <div class="base-only" style="font-size:40px;font-weight:700;margin-bottom:16px;">{esc(beat.visual_title)}</div>
        <div style="position:relative;">{chart_svg}</div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 15. SECOND-LEVEL THINKING CROWD SILHOUETTE (82_google tile 6!)
    elif lt == "second_level_thinking_crowd":
        crowd_figs = "".join(_human_silhouette_svg(False, 195) for _ in range(4))
        hero_fig = _human_silhouette_svg(True, 195)
        stage_inner = f"""
        <div class="base-only" style="text-align:center;margin-bottom:32px;">
          <div style="font-size:56px;font-weight:700;letter-spacing:1px;">第二層思考</div>
          <div style="font-size:24px;color:#A1A1AA;margin-top:6px;">Second-Level Thinking</div>
        </div>
        <div style="display:flex;align-items:center;gap:54px;">
          <div data-step="{step_of(0)}" class="glass-card" style="width:360px;padding:24px;border-color:rgba(239,68,68,0.4);">
            <div style="font-size:17px;color:#F87171;font-weight:700;">華爾街第一層直覺</div>
            <div style="font-size:23px;font-weight:700;margin-top:8px;">{esc(nodes[0].label)}</div>
            <div style="font-size:17px;color:#A1A1AA;margin-top:6px;line-height:1.5;">{esc(nodes[0].sub)}</div>
          </div>

          <div style="display:flex;align-items:flex-end;gap:18px;">
            <div data-step="{step_of(0)}" style="display:flex;gap:14px;">{crowd_figs}</div>
            <div data-step="{step_of(1)}" style="margin-left:14px;">{hero_fig}</div>
          </div>

          <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:380px;padding:24px;">
            <div style="font-size:17px;color:#EB8B1B;font-weight:700;">第二層底層邏輯</div>
            <div style="font-size:23px;font-weight:700;margin-top:8px;">{esc(nodes[1].label)}</div>
            <div style="font-size:17px;color:#E4E4E7;margin-top:6px;line-height:1.5;">{esc(nodes[1].sub)}</div>
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 16. MOAT SHIELD ARCHITECTURE (82_google tile 11!)
    elif lt == "moat_shield_architecture":
        moat_cards = []
        for i in range(4):
            nd = nodes[i] if i < len(nodes) else nodes[-1]
            moat_cards.append(
                f'<div data-step="{step_of(min(2, (i+1)//2))}" class="glass-card" style="width:270px;padding:18px 22px;display:flex;align-items:center;gap:14px;">'
                f'{app_squircle(nd.icon, 56, i == 0)}'
                f'<div><div style="font-size:20px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:15px;color:#A1A1AA;margin-top:3px;">{esc(nd.sub[:18])}</div></div></div>'
            )
        stage_inner = f"""
        <div class="base-only" style="font-size:38px;font-weight:700;margin-bottom:28px;">{esc(beat.visual_title)}</div>
        <div style="display:flex;align-items:center;gap:42px;">
          <div style="display:flex;flex-direction:column;gap:24px;">{moat_cards[0]}{moat_cards[1]}</div>
          <div data-step="{step_of(0)}" style="position:relative;width:230px;height:260px;display:flex;align-items:center;justify-content:center;">
            <svg width="220" height="250" viewBox="0 0 220 250" style="filter:drop-shadow(0 0 36px rgba(235,139,27,0.45));">
              <path d="M110 14 L196 52 V124 C196 182 156 220 110 238 C64 220 24 182 24 124 V52 Z" fill="#232327" stroke="#EB8B1B" stroke-width="5"/>
              <path d="M110 34 L176 64 V122 C176 168 144 198 110 214 V34 Z" fill="rgba(235,139,27,0.22)"/>
            </svg>
            <div style="position:absolute;font-size:22px;font-weight:700;color:#FFFFFF;text-align:center;">{esc(beat.badge_text)}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:24px;">{moat_cards[2]}{moat_cards[3]}</div>
        </div>
        <div data-step="{step_of(2)}" style="margin-top:22px;color:#F59E0B;font-size:20px;font-weight:700;">↓ {esc(beat.callout_body)}</div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 17. US STOCKS: NEGATIVE-SPACE BIG STATEMENT WITH CONTEXT PILLS (never empty!)
    elif lt == "stocks_big_statement":
        headline = beat.visual_title if len(beat.visual_title) >= 6 else (beat.badge_text or beat.visual_title)
        sub_pills = "".join(
            f'<div data-step="{step_of(min(n_clauses - 1, i + 1))}" class="glass-card {"orange-glow" if i == 0 else ""}" style="padding:20px 28px;min-width:340px;display:flex;align-items:center;gap:18px;">'
            f'{app_squircle(nd.icon, 64, i == 0)}'
            f'<div><div style="font-size:22px;font-weight:700;">{esc(nd.label)}</div>'
            f'<div style="font-size:18px;color:#EB8B1B;font-weight:700;margin-top:4px;">{esc(nd.metric or nd.tag or nd.sub[:14])}</div></div></div>'
            for i, nd in enumerate(nodes[:3])
        )
        stage_inner = f"""
        <div style="display:flex;flex-direction:column;gap:42px;max-width:1360px;">
          <div data-step="{step_of(0)}" style="display:flex;align-items:center;gap:28px;">
            <div style="width:8px;height:96px;background:#EB8B1B;border-radius:4px;flex-shrink:0;"></div>
            <div>
              <div style="font-size:68px;font-weight:700;letter-spacing:-0.8px;line-height:1.15;">{esc(headline)}</div>
              <div data-step="{step_of(1)}" style="font-size:28px;color:#D4D4D8;margin-top:14px;">{esc(beat.callout_body or beat.visual_subtitle)}</div>
            </div>
          </div>
          <div style="display:flex;gap:26px;">{sub_pills}</div>
        </div>"""

    # 18. US STOCKS: COMPACT ASYMMETRIC KPI / VALUATION CARDS (KWAvlqx t=15s, 449s, 697s, 883s)
    elif lt in ("stocks_kpi_asymmetric", "stocks_valuation_scenarios"):
        n_c = min(3, max(2, len(nodes)))
        cards = []
        for i, nd in enumerate(nodes[:n_c]):
            st = step_of(i)
            is_down = (nd.trend == "down")
            p_cls = "pill-red" if is_down else "pill-green"
            arr = "▼ " if is_down else "▲ "
            cards.append(
                f'<div class="slot-wrap" style="width:415px;height:240px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:415px;height:240px;padding:28px 30px;display:flex;flex-direction:column;justify-content:space-between;">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                f'<span style="font-size:20px;color:#A1A1AA;font-weight:500;">{esc(nd.label)}</span>'
                f'{svg_icon(nd.icon, 24)}</div>'
                f'<div style="font-size:54px;font-weight:700;letter-spacing:-1px;color:#FFFFFF;">{esc(nd.metric)}</div>'
                f'<div><span class="pill {p_cls}">{arr}{esc(nd.sub[:21])}</span></div>'
                f'</div></div>'
            )
        stage_inner = f"""
        <div style="width:1340px;">
          <div class="bar-title base-only">
            <div class="bar-line"></div>
            <span style="font-size:36px;font-weight:700;">{esc(beat.visual_title)}</span>
          </div>
          <div style="display:flex;gap:32px;">{''.join(cards)}</div>
          <div data-step="{step_of(n_c - 1)}">{_cite_pill(s0)}</div>
        </div>"""

    # 19. US STOCKS: BORDERLESS MINIMALIST FOUR PILLARS (KWAvlqx t=201s, 387s, 1193s)
    else:
        cols = []
        n_p = min(4, max(3, len(nodes)))
        for i in range(n_p):
            nd = nodes[i] if i < len(nodes) else nodes[-1]
            st = step_of(i)
            cols.append(
                f'<div data-step="{st}" style="flex:1;display:flex;flex-direction:column;align-items:center;text-align:center;padding:0 16px;">'
                f'{app_squircle(nd.icon, 68, i == 0)}'
                f'<div style="font-size:24px;font-weight:700;margin-top:18px;">{esc(nd.label)}</div>'
                + (f'<div style="font-size:18px;color:#EB8B1B;font-weight:700;margin-top:6px;">{esc(nd.tag or nd.metric)}</div>' if (nd.tag or nd.metric) else "")
                + f'<div style="font-size:17px;color:#9CA3AF;margin-top:8px;line-height:1.5;">{esc(nd.sub[:28])}</div>'
                f'</div>'
            )
        stage_inner = f"""
        <div style="width:1420px;">
          <div class="bar-title base-only">
            <div class="bar-line"></div>
            <span style="font-size:36px;font-weight:700;">{esc(beat.visual_title)}</span>
          </div>
          <div style="display:flex;gap:26px;margin-top:18px;">{''.join(cols)}</div>
          <div data-step="{step_of(2)}" style="text-align:center;margin-top:28px;">{_cite_pill(s0)}</div>
        </div>"""

    wide_layouts = {
        "stocks_kpi_asymmetric", "stocks_valuation_scenarios", "stocks_four_pillars",
        "stocks_big_statement", "second_level_thinking_crowd", "protagonist_app_flow",
        "code_editor_live_preview", "animated_growth_curve", "operating_leverage_chart",
        "concept_hero_split_3d",
    }
    if lt == "browser_ui_live_tour":
        wrapped_stage = stage_inner
    elif lt in wide_layouts:
        wrapped_stage = f'<div class="stage-zoom-md">{stage_inner}</div>'
    else:
        wrapped_stage = f'<div class="stage-zoom-lg">{stage_inner}</div>'

    hud_cite = (
        f'<div data-step="{step_of(2)}" style="position:fixed;left:48px;bottom:14px;z-index:16;">{_hud_cite_pill(s0)}</div>'
        if s0 else ""
    )

    doc = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>{base_css(bg_hex, tokens.long_width, tokens.long_height)}</style></head>
    <body>
      {crumb_html}
      {pipe_html}
      <div class="stage">{wrapped_stage}</div>
      {hud_cite}
    </body></html>"""
    return doc, n_clauses


def build_short_beat_html(
    script: EpisodeScript,
    sbeat: ShortBeatSpec,
    ai_img_path: str | None,
    long_thumb_path: Path | None,
    sources_by_id: dict[str, CrawledSource],
    tokens: DesignTokens,
) -> tuple[str, int]:
    """
    V4 Pure-Remotion 1080x1920 Vertical Motion-Graphics Builder:
      - ZERO generic AI photo boxes! Every vertical frame uses authentic @garychenai dark Remotion cards,
        official brand squircles, live 60fps typing (`data-typing`), 60fps curve wipes (`data-wipe`),
        60fps browser zoom (`CAM_VIEWPORT_SHORT`), and portrait-thumbnail Related Video funnel CTA!
    """
    bg_hex = tokens.bg_stock_hex if script.avatar_mode else tokens.bg_tutorial_hex
    cited = [sources_by_id[sid] for sid in sbeat.source_ids if sid in sources_by_id]
    s0 = cited[0] if cited else None
    thumb_uri = img_to_data_uri(str(long_thumb_path)) if (long_thumb_path and long_thumb_path.exists()) else ""
    n_clauses = max(1, len(sbeat.clauses))
    nodes = sbeat.nodes[:3]
    while len(nodes) < 3:
        from .config import VisualNode
        nodes.append(VisualNode(label=sbeat.headline, sub=sbeat.clauses[-1][:18], icon="zap"))

    def step_of(i: int) -> int:
        return min(n_clauses - 1, i)

    slt = sbeat.layout_type

    if sbeat.is_cta or slt == "short_funnel_cta":
        body_inner = f"""
        <div class="base-only" style="text-align:center;">
          <div style="font-size:56px;font-weight:700;line-height:1.2;">{esc(sbeat.headline)}</div>
          <div style="margin-top:16px;"><span class="pill pill-orange-solid" style="font-size:25px;padding:8px 28px;">完整深度長片已上線</span></div>
        </div>
        <div data-step="{step_of(0)}" class="glass-card orange-glow" style="width:920px;padding:18px;margin-top:34px;">
          {f'<img src="{thumb_uri}" style="width:100%;height:500px;object-fit:cover;border-radius:16px;display:block;"/>' if thumb_uri else ''}
        </div>
        <div data-step="{step_of(1)}" class="glass-card" style="width:920px;padding:30px;margin-top:28px;text-align:center;">
          <div style="font-size:28px;font-weight:700;color:#E4E4E7;">《{esc(script.short_cta_target_title[:24])}》</div>
          <div style="margin-top:22px;background:#EB8B1B;color:#141414;font-size:34px;font-weight:700;padding:18px 30px;border-radius:999px;">
            ↙ 點擊左下角「關聯影片」看完整版
          </div>
        </div>"""

    elif slt in ("short_squircles_hook", "short_shock_metric_hero"):
        body_inner = f"""
        <div class="base-only" style="text-align:center;margin-bottom:28px;">
          <div style="font-size:58px;font-weight:700;line-height:1.18;">{esc(sbeat.headline)}</div>
          <div style="font-size:26px;color:#A1A1AA;margin-top:12px;">{esc(sbeat.sub_caption)}</div>
        </div>
        <div data-step="{step_of(0)}" style="display:flex;gap:38px;margin-bottom:36px;">
          {app_squircle("claude" if not script.avatar_mode else "microsoft", 96, False)}
          {app_squircle("openai" if not script.avatar_mode else "meta", 96, False)}
          {app_squircle("zapier" if not script.avatar_mode else "google", 96, False)}
        </div>
        <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:900px;padding:40px 36px;display:flex;flex-direction:column;align-items:center;gap:20px;">
          {app_squircle(nodes[0].icon, 146, True)}
          <div style="font-size:74px;font-weight:700;color:#4ADE80;letter-spacing:-1px;">{esc(sbeat.highlight_badge or nodes[0].metric)}</div>
          <div style="font-size:30px;font-weight:700;color:#FFFFFF;text-align:center;">{esc(nodes[0].label)} — {esc(nodes[0].sub[:18])}</div>
        </div>
        <div data-step="{step_of(1)}">{_cite_pill(s0)}</div>"""

    elif slt in ("short_live_typing_card", "short_code_or_steps"):
        lns = sbeat.code_lines[:3] if sbeat.code_lines else [f"{nd.label}: {nd.sub[:18]}" for nd in nodes]
        code_h = "".join(
            f'<div class="mono" style="font-size:25px;line-height:1.8;color:{"#EB8B1B" if i==0 else "#F4F4F5"};">&gt; {esc(ln[:34])}</div>'
            for i, ln in enumerate(lns)
        )
        body_inner = f"""
        <div class="base-only" style="text-align:center;margin-bottom:26px;">
          <div style="font-size:54px;font-weight:700;line-height:1.2;">{esc(sbeat.headline)}</div>
        </div>
        <div style="position:relative;width:920px;min-height:390px;">
          <div class="glass-card base-only" style="position:absolute;inset:0;background:#1B1B1F;"></div>
          <div class="base-only" style="position:relative;height:52px;background:#25252A;border-radius:22px 22px 0 0;display:flex;align-items:center;padding:0 24px;gap:10px;">
            <span style="width:12px;height:12px;border-radius:50%;background:#EF4444;"></span>
            <span style="width:12px;height:12px;border-radius:50%;background:#F59E0B;"></span>
            <span style="width:12px;height:12px;border-radius:50%;background:#22C55E;"></span>
            <span class="mono" style="margin-left:12px;font-size:20px;color:#A1A1AA;">terminal — live</span>
          </div>
          <div data-typing="1" style="position:relative;padding:34px;">{code_h}</div>
        </div>
        <div data-step="{step_of(1)}" style="margin-top:34px;display:flex;align-items:center;gap:24px;" class="glass-card orange-glow">
          <div style="padding:26px 32px;display:flex;align-items:center;gap:22px;width:920px;">
            {app_squircle("robot", 92, True)}
            <div>
              <div style="font-size:31px;font-weight:700;color:#4ADE80;">✓ {esc(nodes[0].label)}</div>
              <div style="font-size:24px;color:#D4D4D8;margin-top:6px;">{esc(nodes[0].sub[:24])}</div>
            </div>
          </div>
        </div>"""

    elif slt in ("short_browser_zoom_proof", "short_live_source_proof"):
        vx, vy, vw, vh = CAM_VIEWPORT_SHORT
        body_inner = f"""
        <div class="base-only" style="text-align:center;">
          <div style="font-size:52px;font-weight:700;line-height:1.18;">{esc(sbeat.headline)}</div>
        </div>
        <div class="base-only" style="position:fixed;left:{vx}px;top:{vy}px;width:{vw}px;height:{vh}px;border:2px solid rgba(235,139,27,0.55);border-radius:22px;background:#141418;box-shadow:0 24px 60px rgba(0,0,0,0.65);"></div>
        <div style="margin-top:{vh + 115}px;display:flex;flex-direction:column;gap:18px;width:920px;">
          {''.join(
              f'<div data-step="{step_of(i)}" class="glass-card {"orange-glow" if i==0 else ""}" style="padding:22px 28px;display:flex;align-items:center;justify-content:space-between;">'
              f'<div style="display:flex;align-items:center;gap:18px;">{app_squircle(nd.icon, 68, i==0)}'
              f'<div><div style="font-size:29px;font-weight:700;">{esc(nd.label)}</div><div style="font-size:22px;color:#A1A1AA;">{esc(nd.sub[:20])}</div></div></div>'
              f'<span class="pill pill-orange" style="font-size:22px;">{esc(nd.metric or nd.tag)}</span></div>'
              for i, nd in enumerate(nodes[:2])
          )}
        </div>"""

    elif slt == "short_growth_curve":
        chart_svg = _build_chart_svg(sbeat.chart_points, None, width=900, height=390)
        body_inner = f"""
        <div class="base-only" style="text-align:center;margin-bottom:20px;">
          <div style="font-size:54px;font-weight:700;line-height:1.2;">{esc(sbeat.headline)}</div>
          <div style="margin-top:14px;"><span class="pill pill-orange-solid" style="font-size:25px;padding:7px 26px;">{esc(sbeat.highlight_badge)}</span></div>
        </div>
        <div style="position:relative;width:920px;padding:24px 10px;">
          <div class="glass-card base-only" style="position:absolute;inset:0;"></div>
          <div style="position:relative;">{chart_svg}</div>
        </div>
        <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:920px;padding:26px 32px;margin-top:24px;text-align:center;">
          <div style="font-size:30px;font-weight:700;">{esc(nodes[0].label)}：{esc(nodes[0].sub[:22])}</div>
        </div>
        <div data-step="{step_of(1)}">{_cite_pill(s0)}</div>"""

    elif slt == "short_second_level_crowd":
        crowd_figs = "".join(_human_silhouette_svg(False, 175) for _ in range(4))
        hero_fig = _human_silhouette_svg(True, 175)
        body_inner = f"""
        <div class="base-only" style="text-align:center;margin-bottom:26px;">
          <div style="font-size:58px;font-weight:700;">第二層思考</div>
          <div style="font-size:26px;color:#A1A1AA;margin-top:6px;">{esc(sbeat.headline)}</div>
        </div>
        <div style="display:flex;align-items:flex-end;gap:18px;margin:20px 0 34px 0;">
          <div data-step="{step_of(0)}" style="display:flex;gap:14px;">{crowd_figs}</div>
          <div data-step="{step_of(1)}" style="margin-left:18px;">{hero_fig}</div>
        </div>
        <div data-step="{step_of(0)}" class="glass-card" style="width:900px;padding:24px 30px;margin-bottom:18px;border-color:rgba(239,68,68,0.45);">
          <div style="font-size:22px;color:#F87171;font-weight:700;">✕ 第一層直覺：{esc(nodes[0].label)}</div>
          <div style="font-size:25px;color:#D4D4D8;margin-top:6px;">{esc(nodes[0].sub[:24])}</div>
        </div>
        <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:900px;padding:24px 30px;">
          <div style="font-size:22px;color:#EB8B1B;font-weight:700;">✓ 第二層真相：{esc(nodes[1].label)}</div>
          <div style="font-size:25px;color:#FFFFFF;margin-top:6px;">{esc(nodes[1].sub[:24])}</div>
        </div>"""

    elif slt in ("short_versus_stamp", "short_before_after_versus"):
        body_inner = f"""
        <div class="base-only" style="text-align:center;margin-bottom:26px;">
          <div style="font-size:54px;font-weight:700;">{esc(sbeat.headline)}</div>
        </div>
        <div data-step="{step_of(0)}" class="glass-card" style="width:900px;padding:34px;position:relative;">
          <div style="font-size:32px;font-weight:700;color:#A1A1AA;">以前：{esc(nodes[0].label)}</div>
          <div style="font-size:26px;color:#D4D4D8;margin-top:12px;">{esc(nodes[0].sub[:28])}</div>
          <span style="position:absolute;top:28px;right:30px;transform:rotate(-8deg);border:3px solid #EF4444;color:#F87171;padding:4px 18px;border-radius:8px;font-size:24px;font-weight:700;">痛點</span>
        </div>
        <div data-wipe="1" style="font-size:44px;color:#EB8B1B;font-weight:700;margin:18px 0;">↓</div>
        <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:900px;padding:34px;display:flex;align-items:center;justify-content:space-between;">
          <div>
            <div style="font-size:34px;font-weight:700;color:#4ADE80;">現在：{esc(nodes[1].label)}</div>
            <div style="font-size:26px;color:#FFFFFF;margin-top:12px;">{esc(nodes[1].sub[:26])}</div>
          </div>
          {app_squircle(nodes[1].icon, 102, True)}
        </div>"""

    else:  # short_kpi_stack / short_progressive_flow
        cards_h = []
        for i, nd in enumerate(nodes[:3]):
            st = step_of(i)
            cards_h.append(
                f'<div class="slot-wrap" style="width:900px;height:178px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:900px;height:178px;padding:26px 32px;display:flex;align-items:center;justify-content:space-between;">'
                f'<div style="display:flex;align-items:center;gap:24px;">'
                f'{app_squircle(nd.icon, 86, i == 0)}'
                f'<div><div style="font-size:33px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:24px;color:#A1A1AA;margin-top:6px;">{esc(nd.sub[:22])}</div></div></div>'
                + (f'<span class="pill pill-orange" style="font-size:24px;padding:8px 20px;">{esc(nd.metric or nd.tag)}</span>' if (nd.metric or nd.tag) else "")
                + '</div></div>'
            )
        body_inner = f"""
        <div class="base-only" style="text-align:center;margin-bottom:26px;">
          <div style="font-size:56px;font-weight:700;line-height:1.18;">{esc(sbeat.headline)}</div>
          {f'<div style="margin-top:16px;"><span class="pill pill-orange-solid" style="font-size:25px;padding:7px 26px;">{esc(sbeat.highlight_badge)}</span></div>' if sbeat.highlight_badge else ''}
        </div>
        <div style="display:flex;flex-direction:column;gap:24px;">{''.join(cards_h)}</div>
        <div data-step="{step_of(1)}">{_cite_pill(s0)}</div>"""

    doc = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>{base_css(bg_hex, tokens.short_width, tokens.short_height)}</style></head>
    <body>
      <div class="base-only" style="position:absolute;top:68px;left:70px;right:70px;display:flex;justify-content:center;">
        <div class="cite-badge" style="margin:0;padding:9px 26px;font-size:23px;border-color:rgba(235,139,27,0.60);color:#FFFFFF;">
          <span class="cite-dot"></span><span style="font-weight:700;">GARY CHEN｜{esc(script.short_hook_banner)}</span>
        </div>
      </div>
      <div style="position:absolute;top:168px;left:70px;right:70px;bottom:480px;display:flex;flex-direction:column;align-items:center;">
        {body_inner}
      </div>
    </body></html>"""
    return doc, n_clauses
