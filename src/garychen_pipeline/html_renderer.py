from __future__ import annotations

import base64
import html
from pathlib import Path

from .config import ASSETS_DIR, CrawledSource, DesignTokens, EpisodeScript, ShortBeatSpec, VisualBeat

FONT_BOLD = (ASSETS_DIR / "fonts/NotoSansTC-Bold.otf").resolve()
FONT_MED = (ASSETS_DIR / "fonts/NotoSansTC-Medium.otf").resolve()
FONT_MONO = (ASSETS_DIR / "fonts/JetBrainsMono-Bold.ttf").resolve()

# Authentic Brand Marks & Crisp Stroke Icons (24x24 viewBox)
ICON_SVGS: dict[str, str] = {
    "github": '<path fill="currentColor" stroke="none" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>',
    "claude": '<path fill="#D97757" stroke="none" d="M5 7h14v7h-2v3h-2v-3H9v3H7v-3H5V7zm3 2v2h2V9H8zm6 0v2h2V9h-2z"/>',
    "openai": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    "meta": '<path d="M5.5 15.5c-1.8 0-3-1.4-3-3.5 0-2.6 2-5 4.2-5 1.9 0 3.3 1.4 5.3 4.3 2-2.9 3.4-4.3 5.3-4.3 2.2 0 4.2 2.4 4.2 5 0 2.1-1.2 3.5-3 3.5-1.6 0-2.9-1.1-4.6-3.6l-1.9 2.7c-1.7 2.5-3 0.9-6.5 0.9z"/>',
    "google": '<path d="M21 12.2c0-.7-.1-1.3-.2-1.9H12v3.7h5.1c-.2 1.2-.9 2.2-1.9 2.9v2.4h3c1.8-1.6 2.8-4.1 2.8-7.1z"/><circle cx="12" cy="12" r="9"/>',
    "nvidia": '<path d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z"/><circle cx="12" cy="12" r="2.8" fill="currentColor"/>',
    "aws": '<path d="M4 16c4.5 3 11.5 3 16 0"/><polyline points="17 14 20 16 18 19"/><path d="M7 11l3-6 3 6M8 9h4M15 5l2 6 2-6"/>',
    "docker": '<rect x="3" y="11" width="18" height="7" rx="3"/><rect x="6" y="7" width="3" height="3"/><rect x="10" y="7" width="3" height="3"/><rect x="10" y="3" width="3" height="3"/><rect x="14" y="7" width="3" height="3"/>',
    "n8n": '<circle cx="6" cy="12" r="2.6"/><circle cx="12" cy="8" r="2.6"/><circle cx="18" cy="12" r="2.6"/><circle cx="12" cy="16" r="2.6"/><line x1="8.3" y1="10.8" x2="9.8" y2="9.2"/><line x1="14.2" y1="9.2" x2="15.7" y2="10.8"/><line x1="8.3" y1="13.2" x2="9.8" y2="14.8"/>',
    "zapier": '<line x1="12" y1="3" x2="12" y2="21"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="5.6" y1="5.6" x2="18.4" y2="18.4"/><line x1="18.4" y1="5.6" x2="5.6" y2="18.4"/>',
    "notion": '<rect x="4" y="3" width="16" height="18" rx="2.5"/><path d="M9 16V8l6 8V8"/>',
    "slack": '<rect x="6" y="10" width="5" height="2" rx="1"/><rect x="13" y="12" width="5" height="2" rx="1"/><rect x="12" y="6" width="2" height="5" rx="1"/><rect x="10" y="13" width="2" height="5" rx="1"/>',
    "gmail": '<rect x="3" y="5" width="18" height="14" rx="2"/><polyline points="3 7 12 13 21 7"/>',
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
    "sparkles": '<path d="M12 3l1.8 5.6a2 2 0 0 0 1.3 1.3L20.7 12l-5.6 1.8a2 2 0 0 0-1.3 1.3L12 20.7l-1.8-5.6a2 2 0 0 0-1.3-1.3L3.3 12l5.6-1.8a2 2 0 0 0 1.3-1.3L12 3z"/>',
}

SQUIRCLE_BRAND_BG: dict[str, tuple[str, str]] = {
    "github": ("#18181B", "#FFFFFF"),
    "claude": ("#F5EFE6", "#D97757"),
    "openai": ("#FFFFFF", "#10A37F"),
    "meta": ("#FFFFFF", "#0668E1"),
    "google": ("#FFFFFF", "#4285F4"),
    "nvidia": ("#142608", "#76B900"),
    "aws": ("#1E242E", "#FF9900"),
    "docker": ("#0B2138", "#2496ED"),
    "n8n": ("#2B1419", "#EA4B71"),
    "zapier": ("#2B160C", "#FF4F00"),
    "notion": ("#FFFFFF", "#18181B"),
    "slack": ("#241229", "#E01E5A"),
    "gmail": ("#FFFFFF", "#EA4335"),
}


def svg_icon(name: str, size: int = 30, color: str = "#EB8B1B") -> str:
    key = (name or "sparkles").lower()
    body = ICON_SVGS.get(key, ICON_SVGS["sparkles"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" style="color:{color};display:block;">{body}</svg>'
    )


def app_squircle(icon_name: str, size: int = 92, glow: bool = False) -> str:
    key = (icon_name or "sparkles").lower()
    bg, fg = SQUIRCLE_BRAND_BG.get(key, ("#2F2F33", "#EB8B1B"))
    border = "2px solid #EB8B1B" if glow else "1.5px solid rgba(255,255,255,0.14)"
    sh = "0 0 38px rgba(235,139,27,0.42), 0 14px 30px rgba(0,0,0,0.45)" if glow else "0 14px 28px rgba(0,0,0,0.38)"
    rad = int(round(size * 0.25))
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:{rad}px;background:{bg};border:{border};'
        f'box-shadow:{sh};display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
        f'{svg_icon(key, int(size * 0.52), fg)}</div>'
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
      position: absolute; top: 18px; left: 26px;
      display: flex; align-items: baseline; gap: 10px; font-size: 16px; z-index: 15;
    }}
    .chap-crumb .num {{ color: #EB8B1B; font-weight: 700; letter-spacing: 0.4px; }}
    .chap-crumb .lbl {{ color: #787880; font-weight: 500; }}
    .stage {{
      position: absolute; top: 56px; left: 80px; right: 80px; bottom: 162px;
      display: flex; flex-direction: column; justify-content: center; align-items: center;
    }}
    .ghost {{
      border: 1.8px dashed rgba(255,255,255,0.14);
      background: rgba(255,255,255,0.012);
      border-radius: 22px;
    }}
    .slot-wrap {{ position: relative; }}
    .slot-wrap > .ghost {{ position: absolute; inset: 0; pointer-events: none; }}
    .glass-card {{
      background: linear-gradient(180deg, rgba(49,49,53,0.96) 0%, rgba(38,38,41,0.96) 100%);
      border: 1.2px solid rgba(255,255,255,0.10);
      border-radius: 22px;
      box-shadow: 0 18px 42px rgba(0,0,0,0.42);
    }}
    .glass-card.orange-glow {{
      border: 2px solid #EB8B1B;
      box-shadow: 0 0 32px rgba(235,139,27,0.22), 0 18px 42px rgba(0,0,0,0.45);
    }}
    .pill {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 14px; border-radius: 999px; font-size: 16px; font-weight: 700;
    }}
    .pill-orange {{ background: rgba(235,139,27,0.16); color: #F59E0B; border: 1.2px solid rgba(235,139,27,0.55); }}
    .pill-orange-solid {{ background: #EB8B1B; color: #141414; }}
    .pill-green {{ background: rgba(34,197,94,0.14); color: #4ADE80; border: 1.2px solid rgba(34,197,94,0.48); }}
    .pill-red {{ background: rgba(239,68,68,0.15); color: #F87171; border: 1.2px solid rgba(239,68,68,0.48); }}
    .pill-muted {{ background: rgba(255,255,255,0.07); color: #A1A1AA; border: 1px solid rgba(255,255,255,0.10); }}
    .cite-badge {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 16px; border-radius: 999px;
      background: rgba(22,22,25,0.88); border: 1px solid rgba(255,255,255,0.11);
      font-size: 15px; color: #A1A1AA; margin-top: 18px;
    }}
    .cite-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #EB8B1B; }}
    .bar-title {{
      display: flex; align-items: center; gap: 16px; align-self: flex-start; margin-bottom: 34px;
    }}
    .bar-line {{ width: 5px; height: 38px; background: #EB8B1B; border-radius: 3px; }}
    .feathered-3d {{
      -webkit-mask-image: radial-gradient(ellipse 78% 76% at 50% 50%, #000 50%, transparent 98%);
      mask-image: radial-gradient(ellipse 78% 76% at 50% 50%, #000 50%, transparent 98%);
    }}
    """


def _cite_pill(s0: CrawledSource | None) -> str:
    if not s0:
        return ""
    dt_p = f" · {esc(s0.published_date)}" if s0.published_date else ""
    return f'<div class="cite-badge"><span class="cite-dot"></span><span>公開來源：{esc(s0.domain)}{dt_p}｜{esc(s0.title[:36])}</span></div>'


def build_long_beat_html(
    script: EpisodeScript,
    beat: VisualBeat,
    ai_img_path: str | None,
    sources_by_id: dict[str, CrawledSource],
    tokens: DesignTokens,
) -> tuple[str, int]:
    """
    Returns `(html_document, num_steps)` where elements with `data-step="0..num_steps-1"`
    are captured as independent RGBA layers for true 60fps spring animation!
    """
    bg_hex = tokens.bg_stock_hex if script.avatar_mode else tokens.bg_tutorial_hex
    cited = [sources_by_id[sid] for sid in beat.source_ids if sid in sources_by_id]
    s0 = cited[0] if cited else None
    nodes = beat.nodes[:4]
    n_clauses = max(1, len(beat.clauses))
    lt = beat.layout_type
    ai_uri = img_to_data_uri(ai_img_path)
    scr_uri = img_to_data_uri(s0.screenshot_path) if (s0 and s0.screenshot_path) else ""

    # Subtle chapter breadcrumb ONLY on Chapter 2+ (exact match to 01_UrFrDJ & 02_aCvEYcz!)
    crumb_html = ""
    if beat.chapter_index >= 2:
        crumb_html = (
            f'<div class="chap-crumb base-only">'
            f'<span class="num">{beat.chapter_index:02d} / {beat.total_chapters:02d}</span>'
            f'<span class="lbl">{esc(beat.chapter_title)}</span></div>'
        )

    def step_of(idx: int) -> int:
        return min(n_clauses - 1, idx)

    stage_inner = ""

    # 1. CLAUDE CHAT / TERMINAL DIALOG (exact replica of aCvEYcz t=3s..9s: compact 660x470 centered window!)
    if lt == "claude_chat_dialog":
        rows = []
        cmds = beat.code_lines if beat.code_lines else [n.label for n in nodes]
        for i, nd in enumerate(nodes[:3]):
            st = step_of(i)
            line_main = cmds[i] if i < len(cmds) else nd.label
            rows.append(
                f'<div data-step="{st}" style="display:flex;flex-direction:column;gap:7px;">'
                f'<div style="display:flex;align-items:center;gap:11px;font-size:23px;font-weight:700;">'
                f'<span style="width:10px;height:10px;border-radius:50%;background:#EB8B1B;flex-shrink:0;"></span>'
                f'<span class="mono">{esc(line_main[:42])}</span></div>'
                f'<div style="color:#A1A1AA;font-size:19px;padding-left:22px;">└ {esc(nd.sub or nd.label)}</div>'
                + (
                    f'<div style="margin-left:22px;margin-top:4px;background:#232326;border:1px solid rgba(255,255,255,0.11);border-radius:10px;padding:9px 16px;font-size:19px;color:#E4E4E7;" class="mono">&gt; {esc(nd.tag)}</div>'
                    if nd.tag
                    else ""
                )
                + "</div>"
            )
        stage_inner = f"""
        <div class="glass-card base-only" style="width:690px;min-height:450px;position:absolute;"></div>
        <div style="width:690px;min-height:450px;border-radius:22px;overflow:hidden;position:relative;">
          <div class="base-only" style="height:44px;background:#242427;border-bottom:1px solid rgba(255,255,255,0.08);display:flex;align-items:center;justify-content:space-between;padding:0 18px;">
            <div style="display:flex;gap:7px;">
              <span style="width:10px;height:10px;border-radius:50%;background:#52525B;"></span>
              <span style="width:10px;height:10px;border-radius:50%;background:#52525B;"></span>
              <span style="width:10px;height:10px;border-radius:50%;background:#52525B;"></span>
            </div>
            <span class="mono" style="font-size:16px;color:#8E8E93;">claude</span>
            <span style="width:36px;"></span>
          </div>
          <div style="padding:32px 36px;display:flex;flex-direction:column;gap:24px;">
            {''.join(rows)}
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 2. APP SQUIRCLES + PRICE STRIKETHROUGH (exact replica of UrFrDJ t=9s..18s!)
    elif lt == "app_squircles_strikethrough":
        comp_icons = [("claude", "Claude Code"), ("openai", "Codex"), ("zapier", "Zapier")]
        comp_items = []
        for idx_c, (ic_k, ic_lbl) in enumerate(comp_icons):
            comp_items.append(
                f'<div style="display:flex;flex-direction:column;align-items:center;gap:10px;opacity:0.45;filter:grayscale(0.85);">'
                f'{app_squircle(ic_k, 74, False)}'
                f'<span style="font-size:16px;color:#A1A1AA;">{ic_lbl}</span>'
                f'<span class="pill pill-red" style="font-size:14px;">$20–$200/月</span></div>'
            )
        hero_nd = nodes[0]
        hero_badge = beat.badge_text or "$0 / 月"
        stage_inner = f"""
        <div data-step="{step_of(0)}" style="display:flex;gap:48px;margin-bottom:44px;">{''.join(comp_items)}</div>
        <div style="display:flex;align-items:center;gap:44px;">
          <div data-step="{step_of(1)}" style="font-size:36px;font-weight:700;color:#EF4444;text-decoration:line-through;opacity:0.85;">$20–$200</div>
          <div class="slot-wrap" style="width:136px;height:136px;">
            <div class="ghost base-only" style="border-radius:34px;"></div>
            <div data-step="{step_of(1)}" style="display:flex;flex-direction:column;align-items:center;gap:14px;">
              {app_squircle(hero_nd.icon, 136, True)}
            </div>
          </div>
          <div data-step="{step_of(2)}" style="font-size:48px;font-weight:700;color:#4ADE80;">{esc(hero_badge)}</div>
        </div>
        <div data-step="{step_of(2)}" style="margin-top:30px;display:flex;flex-direction:column;align-items:center;">
          <span class="pill pill-muted" style="font-size:20px;padding:8px 24px;color:#FFFFFF;">{esc(beat.visual_title or hero_nd.label)}</span>
          {_cite_pill(s0)}
        </div>"""

    # 3. ECOSYSTEM NODE GRAPH WITH SVG CONNECTOR LINES (exact replica of UrFrDJ t=27s..39s!)
    elif lt == "ecosystem_node_graph":
        hero_nd = nodes[0]
        children = nodes[1:4] if len(nodes) > 1 else nodes[:3]
        while len(children) < 3:
            children.append(nodes[-1])
        child_cols = []
        for idx_ch, ch in enumerate(children[:3]):
            st = step_of(idx_ch + 1)
            tag_pill = f'<span class="pill pill-muted" style="font-size:15px;margin-top:6px;">{esc(ch.tag)}</span>' if ch.tag else ""
            child_cols.append(
                f'<div style="display:flex;flex-direction:column;align-items:center;width:240px;">'
                f'<div class="slot-wrap" style="width:88px;height:88px;">'
                f'<div class="ghost base-only" style="border-radius:22px;"></div>'
                f'<div data-step="{st}">{app_squircle(ch.icon, 88, False)}</div></div>'
                f'<div data-step="{st}" style="text-align:center;margin-top:12px;">'
                f'<div style="font-size:21px;font-weight:700;">{esc(ch.label)}</div>'
                f'<div style="font-size:16px;color:#9CA3AF;margin-top:4px;">{esc(ch.sub[:18])}</div>'
                f'{tag_pill}</div></div>'
            )
        stage_inner = f"""
        <div class="base-only" style="font-size:26px;font-weight:700;color:#D4D4D8;margin-bottom:22px;letter-spacing:0.3px;">{esc(beat.visual_title)}</div>
        <div style="position:relative;width:980px;height:430px;display:flex;flex-direction:column;align-items:center;">
          <div data-step="{step_of(0)}" style="z-index:5;display:flex;flex-direction:column;align-items:center;">
            {app_squircle(hero_nd.icon, 108, True)}
            <span style="font-size:20px;font-weight:700;margin-top:10px;color:#EB8B1B;">{esc(hero_nd.label)}</span>
          </div>
          <svg width="860" height="110" viewBox="0 0 860 110" style="margin-top:4px;overflow:visible;">
            <line class="base-only" x1="430" y1="0" x2="150" y2="100" stroke="rgba(255,255,255,0.10)" stroke-width="2" stroke-dasharray="6 6"/>
            <line class="base-only" x1="430" y1="0" x2="430" y2="100" stroke="rgba(255,255,255,0.10)" stroke-width="2" stroke-dasharray="6 6"/>
            <line class="base-only" x1="430" y1="0" x2="710" y2="100" stroke="rgba(255,255,255,0.10)" stroke-width="2" stroke-dasharray="6 6"/>
            <line data-step="{step_of(1)}" x1="430" y1="0" x2="150" y2="100" stroke="#EB8B1B" stroke-width="2.6"/>
            <line data-step="{step_of(2)}" x1="430" y1="0" x2="430" y2="100" stroke="#EB8B1B" stroke-width="2.6"/>
            <line data-step="{step_of(3)}" x1="430" y1="0" x2="710" y2="100" stroke="#EB8B1B" stroke-width="2.6"/>
          </svg>
          <div style="display:flex;justify-content:space-between;width:840px;margin-top:4px;">
            {''.join(child_cols)}
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 4. PROTAGONIST GARY APP FLOW (exact replica of aCvEYcz t=45s..60s / acv_motion_every250ms.jpg!)
    elif lt == "protagonist_app_flow":
        flow_nodes = nodes[:3]
        while len(flow_nodes) < 3:
            flow_nodes.append(nodes[-1])
        stage_inner = f"""
        <div class="base-only" style="display:flex;flex-direction:column;align-items:center;margin-bottom:38px;">
          {svg_icon("layers", 28, "#A1A1AA")}
          <div style="font-size:36px;font-weight:700;margin-top:8px;">{esc(beat.visual_title)}</div>
        </div>
        <div style="display:flex;align-items:center;gap:28px;">
          <div data-step="{step_of(0)}" style="display:flex;align-items:center;gap:20px;">
            <div style="display:flex;flex-direction:column;align-items:center;gap:8px;">
              <div style="width:78px;height:78px;border-radius:50%;border:2.5px solid #EB8B1B;display:flex;align-items:center;justify-content:center;background:rgba(235,139,27,0.10);">
                {svg_icon("users", 36, "#FFFFFF")}
              </div>
              <span style="font-size:17px;font-weight:700;">Gary</span>
            </div>
            <div class="glass-card" style="width:225px;padding:22px 20px;border-radius:24px;position:relative;">
              <span class="pill pill-muted" style="position:absolute;top:-12px;right:14px;font-size:13px;">v1.0</span>
              <div style="font-size:20px;font-weight:700;margin-bottom:14px;">{esc(flow_nodes[0].label)}</div>
              <div style="font-size:15px;color:#A1A1AA;line-height:1.7;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:10px;">
                {esc(flow_nodes[0].sub)}
              </div>
              <div style="font-size:16px;font-weight:700;color:#EB8B1B;margin-top:10px;">{esc(flow_nodes[0].tag or "自動觸發")}</div>
            </div>
          </div>

          <div data-step="{step_of(1)}" style="font-size:30px;color:#EB8B1B;font-weight:700;">→</div>
          <div class="slot-wrap" style="width:116px;height:116px;">
            <div class="ghost base-only" style="border-radius:26px;"></div>
            <div data-step="{step_of(1)}" style="display:flex;flex-direction:column;align-items:center;gap:10px;">
              {app_squircle(flow_nodes[1].icon, 92, True)}
              <span style="font-size:17px;font-weight:700;">{esc(flow_nodes[1].label[:12])}</span>
            </div>
          </div>

          <div data-step="{step_of(2)}" style="font-size:30px;color:#EB8B1B;font-weight:700;">→</div>
          <div class="slot-wrap" style="width:116px;height:116px;">
            <div class="ghost base-only" style="border-radius:26px;"></div>
            <div data-step="{step_of(2)}" style="display:flex;flex-direction:column;align-items:center;gap:10px;">
              {app_squircle(flow_nodes[2].icon, 92, False)}
              <span style="font-size:17px;font-weight:700;">{esc(flow_nodes[2].label[:12])}</span>
            </div>
          </div>

          <div data-step="{step_of(3)}" style="display:flex;align-items:center;gap:16px;">
            <span style="font-size:30px;color:#22C55E;font-weight:700;">→</span>
            <div class="glass-card orange-glow" style="padding:20px 24px;max-width:290px;">
              <div style="font-size:19px;font-weight:700;color:#4ADE80;">✓ {esc(beat.callout_title)}</div>
              <div style="font-size:16px;color:#E4E4E7;margin-top:6px;line-height:1.45;">{esc(beat.callout_body[:34])}</div>
            </div>
          </div>
        </div>"""

    # 5. COMPACT 4-STEP HORIZONTAL AGENDA (exact replica of UrFrDJ t=48s..51s!)
    elif lt == "agenda_four_steps":
        boxes = []
        for i in range(4):
            nd = nodes[i] if i < len(nodes) else nodes[-1]
            st = step_of(i)
            boxes.append(
                f'<div class="slot-wrap" style="width:230px;height:155px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:230px;height:155px;padding:18px 20px;display:flex;flex-direction:column;justify-content:space-between;align-items:center;">'
                f'<span style="align-self:flex-start;font-size:15px;color:#8E8E93;font-weight:700;">{i+1}</span>'
                f'{svg_icon(nd.icon, 34, "#EB8B1B")}'
                f'<span style="font-size:21px;font-weight:700;">{esc(nd.label[:9])}</span>'
                f'</div></div>'
            )
            if i < 3:
                boxes.append(f'<span class="base-only" style="font-size:24px;color:#71717A;">→</span>')
        stage_inner = f"""
        <div class="base-only" style="margin-bottom:32px;"><span class="pill pill-muted" style="font-size:17px;">◎ 今天這集</span></div>
        <div style="display:flex;align-items:center;gap:18px;">{''.join(boxes)}</div>"""

    # 6. SEAMLESS VIGNETTE-FEATHERED 3D DIORAMA + PILL SPLIT (exact replica of aCvEYcz t=24s & t=42s!)
    elif lt == "concept_hero_split_3d":
        pills_col = []
        for i, nd in enumerate(nodes[:3]):
            st = step_of(i)
            is_bad = (nd.trend == "down")
            p_cls = "pill-red" if is_bad else ("pill-green" if i == 0 else "pill-orange")
            sym = "✕" if is_bad else "✓"
            pills_col.append(
                f'<div class="slot-wrap" style="width:460px;height:96px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card" style="width:460px;height:96px;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;">'
                f'<div style="display:flex;align-items:center;gap:16px;">'
                f'<span class="pill {p_cls}" style="padding:5px 12px;">{sym}</span>'
                f'<div><div style="font-size:22px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:16px;color:#A1A1AA;margin-top:3px;">{esc(nd.sub[:24])}</div></div></div>'
                + (f'<span class="mono" style="font-size:18px;color:#EB8B1B;">{esc(nd.tag)}</span>' if nd.tag else "")
                + '</div></div>'
            )
        art_block = (
            f'<img src="{ai_uri}" class="feathered-3d" style="width:760px;height:520px;object-fit:cover;display:block;"/>'
            if ai_uri
            else f'<div style="width:520px;height:400px;display:flex;align-items:center;justify-content:center;">{app_squircle(nodes[0].icon, 160, True)}</div>'
        )
        stage_inner = f"""
        <div style="display:flex;align-items:center;gap:54px;">
          <div style="display:flex;flex-direction:column;gap:20px;">
            <div class="base-only" style="font-size:34px;font-weight:700;margin-bottom:8px;">{esc(beat.visual_title)}</div>
            {''.join(pills_col)}
          </div>
          <div data-step="{step_of(0)}">{art_block}</div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 7. LIVE DARK-MODE WEBPAGE / GITHUB / PAPER SCREENSHOT TOUR (exact replica of UrFrDJ t=74s, t=128s!)
    elif lt == "browser_ui_live_tour" and (scr_uri or ai_uri):
        hero_src = scr_uri or ai_uri
        callouts = []
        for i, nd in enumerate(nodes[:3]):
            st = step_of(i)
            callouts.append(
                f'<div class="slot-wrap" style="width:420px;height:94px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:420px;height:94px;padding:16px 22px;display:flex;align-items:center;gap:16px;">'
                f'<span style="width:34px;height:34px;border-radius:50%;background:#EB8B1B;color:#141414;font-weight:700;font-size:18px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">{i+1}</span>'
                f'<div><div style="font-size:21px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:16px;color:#A1A1AA;margin-top:3px;">{esc(nd.sub[:24])}</div></div></div></div>'
            )
        stage_inner = f"""
        <div style="display:flex;align-items:center;gap:44px;">
          <div data-step="{step_of(0)}" style="border-radius:22px;overflow:hidden;border:1.5px solid rgba(255,255,255,0.13);box-shadow:0 28px 70px rgba(0,0,0,0.62);">
            <img src="{hero_src}" style="width:940px;height:540px;object-fit:cover;object-position:top center;display:block;"/>
          </div>
          <div style="display:flex;flex-direction:column;gap:18px;">
            <div class="base-only" style="font-size:30px;font-weight:700;margin-bottom:6px;">{esc(beat.visual_title)}</div>
            {''.join(callouts)}
          </div>
        </div>
        <div data-step="{step_of(1)}">{_cite_pill(s0)}</div>"""

    # 8. GITHUB PR CHECKS CARD (exact replica of aCvEYcz thumbnail & PR checks!)
    elif lt in ("github_pr_checks_card", "feature_pill_matrix"):
        chk_rows = []
        for i, nd in enumerate(nodes[:3]):
            st = step_of(i)
            chk_rows.append(
                f'<div class="slot-wrap" style="width:620px;height:74px;">'
                f'<div class="ghost base-only" style="border-radius:14px;"></div>'
                f'<div data-step="{st}" style="width:620px;height:74px;padding:0 22px;border-radius:14px;background:#252528;border:1px solid rgba(255,255,255,0.09);display:flex;align-items:center;justify-content:space-between;">'
                f'<div style="display:flex;align-items:center;gap:14px;">'
                f'{svg_icon("github", 24, "#E4E4E7")}'
                f'<span class="mono" style="font-size:21px;font-weight:700;">{esc(nd.label)}</span>'
                f'<span style="font-size:17px;color:#9CA3AF;">— {esc(nd.sub[:22])}</span></div>'
                f'<span style="width:28px;height:28px;border-radius:50%;background:#22C55E;color:#09090B;display:flex;align-items:center;justify-content:center;font-weight:700;">✓</span>'
                f'</div></div>'
            )
        stage_inner = f"""
        <div class="glass-card base-only" style="width:680px;height:390px;position:absolute;border:1.5px solid rgba(34,197,94,0.35);"></div>
        <div style="width:680px;padding:30px;display:flex;flex-direction:column;gap:14px;position:relative;">
          <div class="base-only" style="font-size:24px;font-weight:700;margin-bottom:6px;">{esc(beat.visual_title)}</div>
          {''.join(chk_rows)}
          <div data-step="{step_of(2)}" style="margin-top:8px;">
            <span style="display:inline-block;background:#238636;color:#FFFFFF;font-weight:700;font-size:19px;padding:10px 24px;border-radius:10px;">
              ✓ {esc(beat.badge_text or beat.callout_title or "All checks have passed")}
            </span>
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 9. BEFORE VS AFTER STAMP WORKFLOW CARD (exact replica of UrFrDJ t=884s!)
    elif lt == "before_after_workflow_card":
        l_nd = nodes[0]
        r_nd = nodes[1] if len(nodes) > 1 else nodes[0]
        stage_inner = f"""
        <div style="display:flex;align-items:center;gap:36px;">
          <div data-step="{step_of(0)}" class="glass-card" style="width:450px;height:380px;padding:32px;display:flex;flex-direction:column;justify-content:space-between;position:relative;">
            <div style="display:flex;align-items:center;gap:12px;font-size:28px;font-weight:700;color:#E4E4E7;">
              {svg_icon("lock", 28, "#A1A1AA")} <span>以前：{esc(l_nd.label[:10])}</span>
            </div>
            <div style="font-size:21px;color:#A1A1AA;line-height:1.65;">{esc(l_nd.sub)}</div>
            <div style="align-self:flex-end;transform:rotate(-9deg);border:3px solid #EF4444;color:#F87171;background:rgba(239,68,68,0.14);padding:5px 20px;border-radius:8px;font-size:26px;font-weight:700;">
              {esc(l_nd.tag or "麻煩耗時")}
            </div>
          </div>
          <span data-step="{step_of(1)}" style="font-size:34px;color:#EB8B1B;font-weight:700;">→</span>
          <div class="slot-wrap" style="width:450px;height:380px;">
            <div class="ghost base-only"></div>
            <div data-step="{step_of(1)}" class="glass-card orange-glow" style="width:450px;height:380px;padding:32px;display:flex;flex-direction:column;justify-content:space-between;">
              <div style="display:flex;align-items:center;gap:12px;font-size:28px;font-weight:700;color:#FFFFFF;">
                {svg_icon("zap", 28, "#4ADE80")} <span>現在：{esc(r_nd.label[:10])}</span>
              </div>
              <div style="display:flex;align-items:center;justify-content:center;gap:18px;">
                {app_squircle(r_nd.icon, 78, True)}
                <span style="color:#4ADE80;font-size:24px;font-weight:700;">— ✓ —</span>
                {app_squircle(nodes[-1].icon, 78, False)}
              </div>
              <div style="text-align:center;"><span class="pill pill-green" style="font-size:19px;padding:7px 24px;">{esc(r_nd.tag or "一鍵自動化")}</span></div>
            </div>
          </div>
        </div>"""

    # 10. US STOCKS: NEGATIVE-SPACE BIG STATEMENT (exact replica of KWAvlqx t=263s, t=1131s!)
    elif lt == "stocks_big_statement":
        headline = beat.badge_text if (beat.badge_text and len(beat.badge_text) >= 6) else beat.visual_title
        stage_inner = f"""
        <div data-step="{step_of(0)}" style="display:flex;align-items:center;gap:24px;">
          <div style="width:6px;height:72px;background:#EB8B1B;border-radius:3px;"></div>
          <div>
            <div style="font-size:62px;font-weight:700;letter-spacing:-0.8px;">{esc(headline)}</div>
            <div data-step="{step_of(1)}" style="font-size:24px;color:#9CA3AF;margin-top:12px;">{esc(beat.callout_body or beat.visual_subtitle)}</div>
          </div>
        </div>
        <div data-step="{step_of(2)}">{_cite_pill(s0)}</div>"""

    # 11. US STOCKS: COMPACT ASYMMETRIC KPI CARDS (exact replica of KWAvlqx t=15s, t=449s, t=697s!)
    elif lt in ("stocks_kpi_asymmetric", "stocks_valuation_scenarios"):
        n_c = min(3, max(2, len(nodes)))
        cards = []
        for i, nd in enumerate(nodes[:n_c]):
            st = step_of(i)
            is_down = (nd.trend == "down")
            p_cls = "pill-red" if is_down else "pill-green"
            arr = "▼ " if is_down else "▲ "
            cards.append(
                f'<div class="slot-wrap" style="width:410px;height:230px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:410px;height:230px;padding:28px 30px;display:flex;flex-direction:column;justify-content:space-between;">'
                f'<div style="font-size:19px;color:#9CA3AF;font-weight:500;">{esc(nd.label)}</div>'
                f'<div style="font-size:54px;font-weight:700;letter-spacing:-1px;color:#FFFFFF;">{esc(nd.metric)}</div>'
                f'<div><span class="pill {p_cls}">{arr}{esc(nd.sub[:20])}</span></div>'
                f'</div></div>'
            )
        stage_inner = f"""
        <div style="width:1340px;">
          <div class="bar-title base-only">
            <div class="bar-line"></div>
            <span style="font-size:34px;font-weight:700;">{esc(beat.visual_title)}</span>
          </div>
          <div style="display:flex;gap:32px;">{''.join(cards)}</div>
          <div data-step="{step_of(n_c - 1)}">{_cite_pill(s0)}</div>
        </div>"""

    # 12. US STOCKS: BORDERLESS MINIMALIST FOUR PILLARS (exact replica of KWAvlqx t=201s, t=387s, t=1193s!)
    else:  # stocks_four_pillars & fallback
        cols = []
        n_p = min(4, max(3, len(nodes)))
        for i in range(n_p):
            nd = nodes[i] if i < len(nodes) else nodes[-1]
            st = step_of(i)
            cols.append(
                f'<div data-step="{st}" style="flex:1;display:flex;flex-direction:column;align-items:center;text-align:center;padding:0 16px;">'
                f'<div style="width:58px;height:58px;border-radius:16px;background:#2A2A2E;border:1px solid rgba(255,255,255,0.10);display:flex;align-items:center;justify-content:center;margin-bottom:20px;">'
                f'{svg_icon(nd.icon, 28, "#EB8B1B")}</div>'
                f'<div style="font-size:24px;font-weight:700;">{esc(nd.label)}</div>'
                + (f'<div style="font-size:18px;color:#EB8B1B;font-weight:700;margin-top:6px;">{esc(nd.tag)}</div>' if nd.tag else "")
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

    doc = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>{base_css(bg_hex, tokens.long_width, tokens.long_height)}</style></head>
    <body>
      {crumb_html}
      <div class="stage">{stage_inner}</div>
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
    bg_hex = tokens.bg_stock_hex if script.avatar_mode else tokens.bg_tutorial_hex
    cited = [sources_by_id[sid] for sid in sbeat.source_ids if sid in sources_by_id]
    s0 = cited[0] if cited else None
    ai_uri = img_to_data_uri(ai_img_path)
    scr_uri = img_to_data_uri(s0.screenshot_path) if (s0 and s0.screenshot_path) else ""
    thumb_uri = img_to_data_uri(str(long_thumb_path)) if (long_thumb_path and long_thumb_path.exists()) else ""
    n_clauses = max(1, len(sbeat.clauses))

    def step_of(i: int) -> int:
        return min(n_clauses - 1, i)

    if sbeat.is_cta:
        body_inner = f"""
        <div class="base-only" style="text-align:center;">
          <div style="font-size:54px;font-weight:700;line-height:1.2;">{esc(sbeat.headline)}</div>
          <div style="margin-top:16px;"><span class="pill pill-orange-solid" style="font-size:24px;padding:7px 26px;">完整深度長片已上線</span></div>
        </div>
        <div data-step="{step_of(0)}" class="glass-card orange-glow" style="width:920px;padding:20px;margin-top:32px;">
          {f'<img src="{thumb_uri}" style="width:100%;height:495px;object-fit:cover;border-radius:16px;display:block;"/>' if thumb_uri else ''}
        </div>
        <div data-step="{step_of(1)}" class="glass-card" style="width:920px;padding:30px;margin-top:26px;text-align:center;">
          <div style="font-size:28px;font-weight:700;color:#E4E4E7;">《{esc(script.short_cta_target_title[:24])}》</div>
          <div style="margin-top:22px;background:#EB8B1B;color:#141414;font-size:33px;font-weight:700;padding:18px 30px;border-radius:999px;">
            ↙ 點擊左下角「關聯影片」看完整版
          </div>
        </div>"""
    else:
        use_scr = (sbeat.layout_type == "short_live_source_proof" and scr_uri)
        hero_media = scr_uri if use_scr else ai_uri
        media_cls = "" if use_scr else "feathered-3d"
        cards_h = []
        for i, nd in enumerate(sbeat.nodes[:3]):
            st = step_of(i)
            cards_h.append(
                f'<div class="slot-wrap" style="width:920px;height:102px;">'
                f'<div class="ghost base-only"></div>'
                f'<div data-step="{st}" class="glass-card {"orange-glow" if i == 0 else ""}" style="width:920px;height:102px;padding:18px 26px;display:flex;align-items:center;justify-content:space-between;">'
                f'<div style="display:flex;align-items:center;gap:18px;">'
                f'{app_squircle(nd.icon, 62, i == 0)}'
                f'<div><div style="font-size:29px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:21px;color:#A1A1AA;margin-top:2px;">{esc(nd.sub[:22])}</div></div></div>'
                + (f'<span class="pill pill-orange" style="font-size:20px;">{esc(nd.tag)}</span>' if nd.tag else "")
                + '</div></div>'
            )
        body_inner = f"""
        <div class="base-only" style="text-align:center;">
          <div style="font-size:54px;font-weight:700;line-height:1.18;">{esc(sbeat.headline)}</div>
          {f'<div style="margin-top:14px;"><span class="pill pill-orange-solid" style="font-size:24px;padding:6px 24px;">{esc(sbeat.highlight_badge)}</span></div>' if sbeat.highlight_badge else ''}
        </div>
        <div data-step="{step_of(0)}" style="width:920px;margin-top:24px;display:flex;flex-direction:column;align-items:center;">
          {f'<img src="{hero_media}" class="{media_cls}" style="width:920px;height:460px;object-fit:cover;border-radius:20px;display:block;"/>' if hero_media else ''}
          {_cite_pill(s0)}
        </div>
        <div style="display:flex;flex-direction:column;gap:16px;margin-top:22px;">{''.join(cards_h)}</div>"""

    doc = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>{base_css(bg_hex, tokens.short_width, tokens.short_height)}</style></head>
    <body>
      <div class="base-only" style="position:absolute;top:68px;left:70px;right:70px;display:flex;justify-content:center;">
        <div class="cite-badge" style="margin:0;padding:8px 24px;font-size:22px;border-color:rgba(235,139,27,0.55);color:#FFFFFF;">
          <span class="cite-dot"></span><span style="font-weight:700;">GARY CHEN｜{esc(script.short_hook_banner)}</span>
        </div>
      </div>
      <div style="position:absolute;top:162px;left:70px;right:70px;bottom:490px;display:flex;flex-direction:column;align-items:center;">
        {body_inner}
      </div>
    </body></html>"""
    return doc, n_clauses
