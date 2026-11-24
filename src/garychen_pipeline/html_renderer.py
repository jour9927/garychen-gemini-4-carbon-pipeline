from __future__ import annotations

import base64
import html
from pathlib import Path

from .config import ASSETS_DIR, CrawledSource, DesignTokens, EpisodeScript, ShortBeatSpec, VisualBeat

FONT_BOLD = (ASSETS_DIR / "fonts/NotoSansTC-Bold.otf").resolve()
FONT_MED = (ASSETS_DIR / "fonts/NotoSansTC-Medium.otf").resolve()
FONT_MONO = (ASSETS_DIR / "fonts/JetBrainsMono-Bold.ttf").resolve()

# Crisp Lucide / Brand Vector SVG Paths (24x24 viewBox)
ICON_SVGS: dict[str, str] = {
    "github": '<path fill="currentColor" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>',
    "terminal": '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    "code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
    "check": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "trending_up": '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "dollar": '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "play": '<polygon points="5 3 19 12 5 21 5 3"/>',
    "sparkles": '<path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3L12 3z"/>',
}


def svg_icon(name: str, size: int = 32, color: str = "#EB8B1B") -> str:
    body = ICON_SVGS.get(name, ICON_SVGS["sparkles"])
    if name == "github":
        return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" style="color:{color};display:block;">{body}</svg>'
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="display:block;">{body}</svg>'
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
      background: radial-gradient(circle at 50% 42%, #2c2c30 0%, {bg_hex} 72%);
      color: #FFFFFF;
      font-family: 'GarySans', -apple-system, BlinkMacSystemFont, sans-serif;
      -webkit-font-smoothing: antialiased;
      position: relative;
    }}
    .mono {{ font-family: 'GaryMono', 'GarySans', monospace; }}
    .topbar {{
      position: absolute; top: 22px; left: 36px; right: 36px;
      display: flex; align-items: center; justify-content: space-between; z-index: 20;
    }}
    .chap-tag {{ display: flex; align-items: baseline; gap: 12px; font-size: 22px; }}
    .chap-num {{ color: #EB8B1B; font-weight: 700; letter-spacing: 0.5px; }}
    .chap-name {{ color: #9CA3AF; font-weight: 500; }}
    .src-pill {{
      display: inline-flex; align-items: center; gap: 10px;
      background: rgba(18, 18, 20, 0.86); border: 1px solid rgba(255,255,255,0.13);
      padding: 7px 18px; border-radius: 999px; font-size: 17px; color: #D4D4D8;
    }}
    .src-dot {{ width: 9px; height: 9px; border-radius: 50%; background: #EB8B1B; box-shadow: 0 0 8px #EB8B1B; }}
    .stage {{
      position: absolute; top: 82px; left: 72px; right: 72px; bottom: 175px;
      display: flex; flex-direction: column; justify-content: center; align-items: center;
    }}
    .ghost-slot {{
      border: 2px dashed rgba(255,255,255,0.13);
      background: rgba(255,255,255,0.015);
      border-radius: 24px;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(52,52,58,0.95) 0%, rgba(38,38,42,0.95) 100%);
      border: 1.5px solid rgba(255,255,255,0.11);
      border-radius: 24px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.38);
    }}
    .card.active {{
      border: 2.5px solid #EB8B1B;
      box-shadow: 0 0 34px rgba(235, 139, 27, 0.28), 0 18px 40px rgba(0,0,0,0.45);
    }}
    .pill {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 5px 15px; border-radius: 999px; font-size: 18px; font-weight: 700;
    }}
    .pill-orange {{ background: #EB8B1B; color: #141414; }}
    .pill-green {{ background: rgba(34,197,94,0.18); color: #4ADE80; border: 1.5px solid #22C55E; }}
    .pill-red {{ background: rgba(220,38,38,0.20); color: #F87171; border: 1.5px solid #DC2626; }}
    .pill-muted {{ background: rgba(255,255,255,0.08); color: #D4D4D8; }}
    .sec-h1 {{ font-size: 46px; font-weight: 700; letter-spacing: -0.5px; line-height: 1.22; }}
    .sec-sub {{ font-size: 24px; color: #A1A1AA; margin-top: 8px; font-weight: 500; }}
    .left-bar-header {{
      align-self: flex-start; display: flex; align-items: center; gap: 18px; margin-bottom: 34px;
    }}
    .left-bar {{ width: 7px; height: 52px; background: #EB8B1B; border-radius: 4px; }}
    """


def build_long_beat_html(
    script: EpisodeScript,
    beat: VisualBeat,
    step_idx: int,
    ai_img_path: str | None,
    sources_by_id: dict[str, CrawledSource],
    tokens: DesignTokens,
) -> str:
    bg_hex = tokens.bg_stock_hex if script.avatar_mode else tokens.bg_tutorial_hex
    cited = [sources_by_id[sid] for sid in beat.source_ids if sid in sources_by_id]
    s0 = cited[0] if cited else None

    src_html = ""
    if s0:
        dt_s = f" · {esc(s0.published_date)}" if s0.published_date else ""
        src_html = (
            f'<div class="src-pill"><span class="src-dot"></span>'
            f'<span>公開資料 [{esc(s0.source_id)}] {esc(s0.domain)}{dt_s}｜{esc(s0.title[:30])}</span></div>'
        )

    nodes = beat.nodes[:4]
    lt = beat.layout_type
    ai_uri = img_to_data_uri(ai_img_path)
    scr_uri = img_to_data_uri(s0.screenshot_path) if (s0 and s0.screenshot_path) else ""

    stage_inner = ""

    if lt == "claude_terminal_progressive":
        rows_html = []
        lines_src = beat.code_lines if beat.code_lines else [f"{n.label}  # {n.sub}" for n in nodes]
        for i, nd in enumerate(nodes[:3]):
            if i > step_idx:
                rows_html.append('<div class="ghost-slot" style="height:88px;width:100%;"></div>')
            else:
                is_cur = (i == step_idx)
                cmd_str = lines_src[i] if i < len(lines_src) else nd.label
                tag_h = f'<span class="pill {"pill-orange" if is_cur else "pill-green"}">{esc(nd.tag or "OK")}</span>' if nd.tag else ""
                rows_html.append(
                    f'<div class="card {"active" if is_cur else ""}" style="padding:18px 26px;display:flex;align-items:center;justify-content:space-between;">'
                    f'<div>'
                    f'<div style="display:flex;align-items:center;gap:12px;font-size:26px;font-weight:700;">'
                    f'<span style="width:13px;height:13px;border-radius:50%;background:{"#EB8B1B" if is_cur else "#22C55E"};display:inline-block;"></span>'
                    f'<span class="mono">{esc(cmd_str[:46])}</span></div>'
                    f'<div style="color:#A1A1AA;font-size:21px;margin-top:6px;padding-left:25px;">└ {esc(nd.sub or nd.label)}</div>'
                    f'</div>{tag_h}</div>'
                )
        stage_inner = f"""
        <div class="card" style="width:1240px;padding:0;overflow:hidden;border:1.5px solid rgba(255,255,255,0.16);">
          <div style="height:54px;background:#1C1C1F;border-bottom:1px solid rgba(255,255,255,0.1);display:flex;align-items:center;padding:0 22px;justify-content:space-between;">
            <div style="display:flex;gap:9px;">
              <span style="width:13px;height:13px;border-radius:50%;background:#52525B;"></span>
              <span style="width:13px;height:13px;border-radius:50%;background:#52525B;"></span>
              <span style="width:13px;height:13px;border-radius:50%;background:#52525B;"></span>
            </div>
            <div class="mono" style="color:#A1A1AA;font-size:20px;">claude-agent — {esc(beat.visual_title)}</div>
            <div style="width:48px;"></div>
          </div>
          <div style="padding:34px 42px;display:flex;flex-direction:column;gap:20px;">
            <div style="font-size:36px;font-weight:700;display:flex;align-items:center;gap:14px;">
              {svg_icon("terminal", 36, "#EB8B1B")} <span>{esc(beat.visual_title)}</span>
            </div>
            {''.join(rows_html)}
          </div>
        </div>"""

    elif lt == "pricing_strikethrough_reveal":
        dim_others = (step_idx >= 1)
        comp_cards = []
        for i, nd in enumerate(nodes[:3]):
            style_dim = "opacity:0.38;filter:grayscale(1);transform:scale(0.93);" if (dim_others and i > 0) else ""
            is_hero = (i == 0 and dim_others)
            badge_cls = "pill-green" if is_hero else "pill-red"
            badge_val = nd.tag or ("免費開源" if is_hero else "$20+/月")
            comp_cards.append(
                f'<div class="card {"active" if is_hero else ""}" style="width:340px;padding:34px 26px;text-align:center;position:relative;{style_dim}">'
                f'<div style="position:absolute;top:-16px;right:22px;"><span class="pill {badge_cls}">{esc(badge_val)}</span></div>'
                f'<div style="width:92px;height:92px;margin:0 auto 22px;border-radius:24px;background:rgba(235,139,27,0.12);display:flex;align-items:center;justify-content:center;">'
                f'{svg_icon(nd.icon, 48, "#EB8B1B" if is_hero else "#E4E4E7")}</div>'
                f'<div style="font-size:30px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:20px;color:#A1A1AA;margin-top:10px;">{esc(nd.sub)}</div>'
                f'</div>'
            )
        strike_bar = ""
        if dim_others:
            strike_bar = (
                f'<div style="margin-top:34px;display:flex;align-items:center;gap:28px;background:rgba(15,15,18,0.85);padding:16px 38px;border-radius:999px;border:1.5px solid #EB8B1B;">'
                f'<span style="font-size:30px;color:#EF4444;text-decoration:line-through;font-weight:700;">$20 – $200 / 月</span>'
                f'<span style="font-size:28px;color:#A1A1AA;">→</span>'
                f'<span style="font-size:34px;color:#4ADE80;font-weight:700;">{esc(beat.badge_text or "免費開源直上")}</span>'
                f'</div>'
            )
        stage_inner = f"""
        <div style="text-align:center;margin-bottom:36px;">
          <div class="sec-h1">{esc(beat.visual_title)}</div>
          <div class="sec-sub">{esc(beat.visual_subtitle)}</div>
        </div>
        <div style="display:flex;gap:42px;align-items:center;justify-content:center;">{''.join(comp_cards)}</div>
        {strike_bar}"""

    elif lt == "live_web_screenshot_spotlight" and (scr_uri or ai_uri):
        hero_img = scr_uri or ai_uri
        url_disp = s0.url if s0 else "https://github.com"
        bullets_h = []
        for i, nd in enumerate(nodes[:3]):
            if i > step_idx:
                bullets_h.append('<div class="ghost-slot" style="height:106px;"></div>')
            else:
                act = (i == step_idx)
                bullets_h.append(
                    f'<div class="card {"active" if act else ""}" style="padding:18px 22px;display:flex;gap:16px;align-items:center;">'
                    f'<div style="width:48px;height:48px;border-radius:14px;background:rgba(235,139,27,0.16);display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
                    f'{svg_icon(nd.icon, 26, "#EB8B1B")}</div>'
                    f'<div><div style="font-size:24px;font-weight:700;">{esc(nd.label)}</div>'
                    f'<div style="font-size:19px;color:#A1A1AA;margin-top:4px;">{esc(nd.sub)}</div></div></div>'
                )
        stage_inner = f"""
        <div style="display:grid;grid-template-columns:1040px 640px;gap:42px;align-items:center;width:1722px;">
          <div class="card active" style="overflow:hidden;padding:0;">
            <div style="height:46px;background:#18181B;padding:0 18px;display:flex;align-items:center;gap:14px;border-bottom:1px solid rgba(255,255,255,0.1);">
              <div style="display:flex;gap:7px;">
                <span style="width:11px;height:11px;border-radius:50%;background:#EF4444;"></span>
                <span style="width:11px;height:11px;border-radius:50%;background:#F59E0B;"></span>
                <span style="width:11px;height:11px;border-radius:50%;background:#22C55E;"></span>
              </div>
              <div class="mono" style="background:#27272A;padding:4px 16px;border-radius:8px;font-size:16px;color:#D4D4D8;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">
                {esc(url_disp)}
              </div>
            </div>
            <img src="{hero_img}" style="width:1040px;height:590px;object-fit:cover;object-position:top center;display:block;"/>
          </div>
          <div style="display:flex;flex-direction:column;gap:18px;">
            <div class="pill pill-orange" style="align-self:flex-start;">實時爬蟲公開畫面查證</div>
            <div class="sec-h1" style="font-size:38px;">{esc(beat.visual_title)}</div>
            <div style="display:flex;flex-direction:column;gap:16px;margin-top:6px;">{''.join(bullets_h)}</div>
          </div>
        </div>"""

    elif lt == "github_pr_checks_mock":
        checks_h = []
        for i, nd in enumerate(nodes[:3]):
            passed = (i <= step_idx)
            checks_h.append(
                f'<div style="display:flex;align-items:center;justify-content:space-between;padding:16px 22px;border-radius:16px;background:{"rgba(34,197,94,0.10)" if passed else "rgba(255,255,255,0.03)"};border:1px solid {"rgba(34,197,94,0.35)" if passed else "rgba(255,255,255,0.08)"};">'
                f'<div style="display:flex;align-items:center;gap:16px;">'
                f'{svg_icon("check" if passed else "cpu", 28, "#22C55E" if passed else "#71717A")}'
                f'<div><div class="mono" style="font-size:23px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:19px;color:#A1A1AA;">{esc(nd.sub)}</div></div></div>'
                f'<span class="pill {"pill-green" if passed else "pill-muted"}">{esc(nd.tag or ("Passed ✓" if passed else "Pending"))}</span>'
                f'</div>'
            )
        stage_inner = f"""
        <div class="card active" style="width:1180px;padding:38px 46px;">
          <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:22px;margin-bottom:24px;">
            <div>
              <div style="font-size:34px;font-weight:700;display:flex;align-items:center;gap:14px;">
                {svg_icon("github", 36, "#FFFFFF")} <span>{esc(beat.visual_title)}</span>
                <span style="color:#71717A;font-weight:500;">#12</span>
              </div>
              <div style="margin-top:10px;display:flex;align-items:center;gap:12px;">
                <span class="pill pill-green">● Open</span>
                <span class="mono" style="color:#A1A1AA;font-size:19px;">feature/ai-workflow → main</span>
              </div>
            </div>
            <div class="pill pill-orange" style="font-size:21px;padding:10px 24px;">{esc(beat.badge_text or "自動把關機制")}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:14px;">{''.join(checks_h)}</div>
        </div>"""

    elif lt == "kpi_financial_cards":
        cards_h = []
        n_c = min(3, max(2, len(nodes)))
        for i, nd in enumerate(nodes[:n_c]):
            if i > step_idx + 1:
                cards_h.append('<div class="ghost-slot" style="flex:1;height:320px;"></div>')
            else:
                act = (i == min(step_idx, n_c - 1))
                tr_cls = "pill-green" if nd.trend == "up" else ("pill-red" if nd.trend == "down" else "pill-orange")
                arrow = "▲ " if nd.trend == "up" else ("▼ " if nd.trend == "down" else "● ")
                big_val = nd.tag or beat.badge_text or "100%"
                cards_h.append(
                    f'<div class="card {"active" if act else ""}" style="flex:1;padding:36px 34px;display:flex;flex-direction:column;justify-content:space-between;height:330px;">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                    f'<span style="font-size:24px;color:#A1A1AA;font-weight:500;">{esc(nd.label)}</span>'
                    f'{svg_icon(nd.icon, 32, "#EB8B1B" if act else "#71717A")}</div>'
                    f'<div style="font-size:62px;font-weight:700;letter-spacing:-1px;color:#FFFFFF;margin:14px 0;">{esc(big_val)}</div>'
                    f'<div><span class="pill {tr_cls}">{arrow}{esc(nd.sub[:20] or "關鍵公開數據")}</span></div>'
                    f'</div>'
                )
        stage_inner = f"""
        <div style="width:1620px;">
          <div class="left-bar-header">
            <div class="left-bar"></div>
            <div>
              <div class="sec-h1">{esc(beat.visual_title)}</div>
              <div class="sec-sub">{esc(beat.visual_subtitle)}</div>
            </div>
          </div>
          <div style="display:flex;gap:34px;width:100%;">{''.join(cards_h)}</div>
        </div>"""

    elif lt == "before_after_stamp_compare":
        left_nd = nodes[0]
        right_nd = nodes[1] if len(nodes) > 1 else nodes[0]
        show_right = (step_idx >= 1)
        right_box = (
            f'<div class="card active" style="flex:1;padding:40px;height:430px;position:relative;display:flex;flex-direction:column;justify-content:space-between;">'
            f'<div style="display:flex;align-items:center;gap:14px;font-size:34px;font-weight:700;color:#4ADE80;">'
            f'{svg_icon("zap", 36, "#4ADE80")} <span>現在：{esc(right_nd.label)}</span></div>'
            f'<div style="font-size:26px;color:#E4E4E7;line-height:1.55;">{esc(right_nd.sub or beat.callout_body)}</div>'
            f'<div><span class="pill pill-green" style="font-size:22px;padding:10px 26px;">✓ {esc(right_nd.tag or "一鍵自動化")}</span></div>'
            f'</div>'
            if show_right
            else '<div class="ghost-slot" style="flex:1;height:430px;"></div>'
        )
        stage_inner = f"""
        <div style="width:1540px;">
          <div style="text-align:center;margin-bottom:34px;"><div class="sec-h1">{esc(beat.visual_title)}</div></div>
          <div style="display:flex;gap:44px;align-items:center;">
            <div class="card" style="flex:1;padding:40px;height:430px;position:relative;display:flex;flex-direction:column;justify-content:space-between;opacity:{'0.68' if show_right else '1.0'};">
              <div style="display:flex;align-items:center;gap:14px;font-size:34px;font-weight:700;color:#F87171;">
                {svg_icon("lock", 34, "#F87171")} <span>以前：{esc(left_nd.label)}</span>
              </div>
              <div style="font-size:26px;color:#A1A1AA;line-height:1.55;">{esc(left_nd.sub)}</div>
              <div style="transform:rotate(-8deg);align-self:flex-end;border:4px solid #EF4444;color:#EF4444;font-size:30px;font-weight:700;padding:6px 22px;border-radius:10px;background:rgba(239,68,68,0.12);">
                {esc(left_nd.tag or "麻煩耗時")}
              </div>
            </div>
            <div style="font-size:42px;color:#EB8B1B;font-weight:700;">→</div>
            {right_box}
          </div>
        </div>"""

    elif lt == "ai_editorial_split_card":
        steps_h = []
        for i, nd in enumerate(nodes[:3]):
            if i > step_idx:
                steps_h.append('<div class="ghost-slot" style="height:118px;"></div>')
            else:
                act = (i == step_idx)
                steps_h.append(
                    f'<div class="card {"active" if act else ""}" style="padding:20px 26px;display:flex;align-items:center;justify-content:space-between;">'
                    f'<div style="display:flex;align-items:center;gap:18px;">'
                    f'<div style="width:50px;height:50px;border-radius:50%;background:{"#EB8B1B" if act else "#3F3F46"};color:{"#141414" if act else "#FFF"};display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;">{i+1}</div>'
                    f'<div><div style="font-size:26px;font-weight:700;">{esc(nd.label)}</div>'
                    f'<div style="font-size:20px;color:#A1A1AA;margin-top:4px;">{esc(nd.sub)}</div></div></div>'
                    f"{f'<span class=\"pill pill-orange\">{esc(nd.tag)}</span>' if nd.tag else ''}"
                    f'</div>'
                )
        img_tag = f'<img src="{ai_uri}" style="width:100%;height:390px;object-fit:cover;border-radius:18px;display:block;"/>' if ai_uri else ""
        stage_inner = f"""
        <div style="display:grid;grid-template-columns:820px 840px;gap:46px;align-items:center;width:1706px;">
          <div>
            <div class="left-bar-header" style="margin-bottom:24px;">
              <div class="left-bar"></div>
              <div><div class="sec-h1" style="font-size:42px;">{esc(beat.visual_title)}</div>
              <div class="sec-sub">{esc(beat.visual_subtitle)}</div></div>
            </div>
            <div style="display:flex;flex-direction:column;gap:18px;">{''.join(steps_h)}</div>
          </div>
          <div class="card" style="padding:22px;">
            {img_tag}
            <div class="card active" style="margin-top:20px;padding:22px 26px;background:rgba(24,24,27,0.95);">
              <div style="font-size:24px;font-weight:700;color:#EB8B1B;display:flex;align-items:center;gap:10px;">
                {svg_icon("sparkles", 24, "#EB8B1B")} <span>{esc(beat.callout_title)}</span>
              </div>
              <div style="font-size:22px;color:#F4F4F5;margin-top:8px;line-height:1.45;">{esc(beat.callout_body)}</div>
            </div>
          </div>
        </div>"""

    elif lt in ("progressive_slot_pipeline", "chapter_roadmap_agenda", "branch_merge_diagram"):
        n_s = min(4, max(3, len(nodes)))
        slot_items = []
        for i in range(n_s):
            nd = nodes[i] if i < len(nodes) else nodes[-1]
            revealed = (lt == "chapter_roadmap_agenda") or (i <= step_idx)
            is_act = (i == min(step_idx, n_s - 1))
            if not revealed:
                slot_items.append('<div class="ghost-slot" style="flex:1;height:330px;"></div>')
            else:
                slot_items.append(
                    f'<div class="card {"active" if is_act else ""}" style="flex:1;height:330px;padding:30px 24px;display:flex;flex-direction:column;justify-content:space-between;align-items:center;text-align:center;">'
                    f'<div style="align-self:flex-start;display:flex;align-items:center;justify-content:space-between;width:100%;">'
                    f'<span style="width:36px;height:36px;border-radius:50%;background:{"#EB8B1B" if is_act else "#3F3F46"};color:{"#141414" if is_act else "#E4E4E7"};display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:19px;">{i+1}</span>'
                    f"{f'<span class=\"pill pill-muted\">{esc(nd.tag)}</span>' if nd.tag else ''}</div>"
                    f'<div style="width:78px;height:78px;border-radius:22px;background:rgba(235,139,27,0.13);display:flex;align-items:center;justify-content:center;">'
                    f'{svg_icon(nd.icon, 42, "#EB8B1B" if is_act else "#D4D4D8")}</div>'
                    f'<div><div style="font-size:27px;font-weight:700;">{esc(nd.label)}</div>'
                    f'<div style="font-size:19px;color:#A1A1AA;margin-top:8px;">{esc(nd.sub)}</div></div>'
                    f'</div>'
                )
            if i < n_s - 1:
                arr_col = "#EB8B1B" if i < step_idx else "#52525B"
                slot_items.append(f'<div style="font-size:34px;font-weight:700;color:{arr_col};">→</div>')

        branch_svg = ""
        if lt == "branch_merge_diagram":
            branch_svg = """
            <svg width="1100" height="120" viewBox="0 0 1100 120" style="margin-top:28px;">
              <line x1="80" y1="90" x2="1020" y2="90" stroke="#71717A" stroke-width="5"/>
              <path d="M 280 90 C 340 90, 350 26, 420 26 L 690 26 C 750 26, 760 90, 820 90" fill="none" stroke="#EB8B1B" stroke-width="5"/>
              <circle cx="280" cy="90" r="9" fill="#EB8B1B"/><circle cx="480" cy="26" r="9" fill="#EB8B1B"/>
              <circle cx="630" cy="26" r="9" fill="#EB8B1B"/><circle cx="820" cy="90" r="10" fill="#22C55E"/>
              <text x="20" y="97" fill="#A1A1AA" font-size="22" font-family="GaryMono">main</text>
            </svg>"""

        stage_inner = f"""
        <div style="text-align:center;margin-bottom:36px;">
          <div class="sec-h1">{esc(beat.visual_title)}</div>
          <div class="sec-sub">{esc(beat.visual_subtitle)}</div>
        </div>
        <div style="display:flex;gap:18px;align-items:center;width:1660px;">{''.join(slot_items)}</div>
        {branch_svg}"""

    elif lt == "versus_debate_columns":
        l_nd = nodes[0]
        r_nd = nodes[1] if len(nodes) > 1 else nodes[0]
        extra = nodes[2:]
        stage_inner = f"""
        <div style="width:1580px;">
          <div class="left-bar-header"><div class="left-bar"></div><div class="sec-h1">{esc(beat.visual_title)}</div></div>
          <div style="display:grid;grid-template-columns:1fr 110px 1fr;gap:24px;align-items:center;">
            <div class="card {'active' if step_idx % 2 == 0 else ''}" style="padding:36px;border-color:#22C55E;min-height:340px;">
              <div style="font-size:36px;font-weight:700;color:#4ADE80;margin-bottom:20px;">{esc(l_nd.label)}</div>
              <div style="font-size:24px;color:#F4F4F5;line-height:1.6;">● {esc(l_nd.sub)}</div>
              {f'<div style="font-size:24px;color:#D4D4D8;margin-top:14px;">● {esc(extra[0].label)}：{esc(extra[0].sub)}</div>' if extra else ''}
              {f'<div style="margin-top:22px;"><span class="pill pill-green">{esc(l_nd.tag)}</span></div>' if l_nd.tag else ''}
            </div>
            <div style="width:92px;height:92px;border-radius:50%;background:#27272A;border:3px solid #EB8B1B;box-shadow:0 0 26px rgba(235,139,27,0.4);display:flex;align-items:center;justify-content:center;font-size:30px;font-weight:700;margin:0 auto;">VS</div>
            <div class="card {'active' if step_idx % 2 == 1 else ''}" style="padding:36px;border-color:#DC2626;min-height:340px;">
              <div style="font-size:36px;font-weight:700;color:#F87171;margin-bottom:20px;">{esc(r_nd.label)}</div>
              <div style="font-size:24px;color:#F4F4F5;line-height:1.6;">● {esc(r_nd.sub)}</div>
              {f'<div style="margin-top:22px;"><span class="pill pill-red">{esc(r_nd.tag or "傳統限制")}</span></div>'}
            </div>
          </div>
          <div style="text-align:center;margin-top:34px;">
            <span style="font-size:30px;font-weight:700;border-bottom:4px solid #EB8B1B;padding-bottom:8px;">{esc(beat.callout_body)}</span>
          </div>
        </div>"""

    elif lt in ("checklist_two_tier_defense", "summary_three_pillars"):
        cols_h = []
        for i, nd in enumerate(nodes[:3]):
            act = (i <= step_idx)
            cols_h.append(
                f'<div class="card {"active" if i == step_idx else ""}" style="flex:1;padding:34px 28px;opacity:{"1" if act else "0.35"};">'
                f'<div style="width:64px;height:64px;border-radius:18px;background:rgba(34,197,94,0.16);display:flex;align-items:center;justify-content:center;margin-bottom:22px;">'
                f'{svg_icon("check" if lt == "checklist_two_tier_defense" else nd.icon, 34, "#4ADE80" if act else "#71717A")}</div>'
                f'<div style="font-size:29px;font-weight:700;">{esc(nd.label)}</div>'
                f'<div style="font-size:21px;color:#A1A1AA;margin-top:12px;line-height:1.5;">{esc(nd.sub)}</div>'
                f"{f'<div style=\"margin-top:20px;\"><span class=\"pill pill-orange\">{esc(nd.tag)}</span></div>' if nd.tag else ''}"
                f'</div>'
            )
        stage_inner = f"""
        <div style="width:1620px;">
          <div class="left-bar-header"><div class="left-bar"></div>
            <div><div class="sec-h1">{esc(beat.visual_title)}</div><div class="sec-sub">{esc(beat.visual_subtitle)}</div></div>
          </div>
          <div style="display:flex;gap:32px;">{''.join(cols_h)}</div>
        </div>"""

    else:  # hub_ecosystem_radiate
        sats_h = []
        for i, nd in enumerate(nodes[:4]):
            revealed = (i <= step_idx + 1)
            act = (i == step_idx % max(1, len(nodes)))
            if not revealed:
                sats_h.append('<div class="ghost-slot" style="padding:24px;height:132px;"></div>')
            else:
                sats_h.append(
                    f'<div class="card {"active" if act else ""}" style="padding:22px 26px;display:flex;align-items:center;gap:18px;">'
                    f'<div style="width:56px;height:56px;border-radius:16px;background:rgba(235,139,27,0.15);display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
                    f'{svg_icon(nd.icon, 30, "#EB8B1B")}</div>'
                    f'<div><div style="font-size:25px;font-weight:700;">{esc(nd.label)}</div>'
                    f'<div style="font-size:19px;color:#A1A1AA;margin-top:4px;">{esc(nd.sub)}</div></div></div>'
                )
        center_visual = (
            f'<img src="{ai_uri}" style="width:240px;height:240px;object-fit:cover;border-radius:36px;border:3px solid #EB8B1B;box-shadow:0 0 42px rgba(235,139,27,0.35);"/>'
            if ai_uri
            else f'<div class="card active" style="width:230px;height:230px;border-radius:42px;display:flex;align-items:center;justify-content:center;">{svg_icon("cpu", 96, "#EB8B1B")}</div>'
        )
        stage_inner = f"""
        <div style="text-align:center;margin-bottom:32px;">
          <div class="sec-h1">{esc(beat.visual_title)}</div>
          <div class="sec-sub">{esc(beat.visual_subtitle)}</div>
        </div>
        <div style="display:grid;grid-template-columns:540px 300px 540px;gap:42px;align-items:center;">
          <div style="display:flex;flex-direction:column;gap:24px;">{''.join(sats_h[:2])}</div>
          <div style="display:flex;flex-direction:column;align-items:center;gap:16px;">
            {center_visual}
            {f'<span class="pill pill-orange">{esc(beat.badge_text)}</span>' if beat.badge_text else ''}
          </div>
          <div style="display:flex;flex-direction:column;gap:24px;">{''.join(sats_h[2:4])}</div>
        </div>"""

    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>{base_css(bg_hex, tokens.long_width, tokens.long_height)}</style></head>
    <body>
      <div class="topbar">
        <div class="chap-tag">
          <span class="chap-num">{beat.chapter_index:02d} / {beat.total_chapters:02d}</span>
          <span class="chap-name">{esc(beat.chapter_title)}</span>
        </div>
        {src_html}
      </div>
      <div class="stage">{stage_inner}</div>
    </body></html>"""


def build_short_beat_html(
    script: EpisodeScript,
    sbeat: ShortBeatSpec,
    step_idx: int,
    ai_img_path: str | None,
    long_thumb_path: Path | None,
    sources_by_id: dict[str, CrawledSource],
    tokens: DesignTokens,
) -> str:
    cited = [sources_by_id[sid] for sid in sbeat.source_ids if sid in sources_by_id]
    s0 = cited[0] if cited else None
    ai_uri = img_to_data_uri(ai_img_path)
    scr_uri = img_to_data_uri(s0.screenshot_path) if (s0 and s0.screenshot_path) else ""
    thumb_uri = img_to_data_uri(str(long_thumb_path)) if (long_thumb_path and long_thumb_path.exists()) else ""

    if sbeat.is_cta:
        body_inner = f"""
        <div style="text-align:center;">
          <div style="font-size:56px;font-weight:700;line-height:1.2;">{esc(sbeat.headline)}</div>
          <div style="margin-top:18px;"><span class="pill pill-orange" style="font-size:26px;padding:8px 28px;">{esc(sbeat.highlight_badge or "完整長片已上線")}</span></div>
        </div>
        <div class="card active" style="width:940px;padding:24px;margin-top:34px;">
          {f'<img src="{thumb_uri}" style="width:100%;height:480px;object-fit:cover;border-radius:18px;"/>' if thumb_uri else ''}
          <div style="font-size:24px;color:#EB8B1B;font-weight:700;text-align:center;margin-top:18px;">✦ 完整實戰步驟、避坑指南與公開來源都在長片</div>
        </div>
        <div class="card active" style="width:940px;padding:34px;margin-top:28px;text-align:center;">
          <div style="font-size:32px;font-weight:700;">{esc(script.short_cta_target_title[:24])}</div>
          <div style="margin-top:24px;background:#EB8B1B;color:#141414;font-size:34px;font-weight:700;padding:20px 32px;border-radius:999px;">
            ↙ 點擊左下角「關聯影片」看完整版
          </div>
        </div>"""
    else:
        hero_media = scr_uri if (sbeat.layout_type == "short_live_source_proof" and scr_uri) else ai_uri
        nodes_h = []
        for i, nd in enumerate(sbeat.nodes[:3]):
            if i > step_idx + 1:
                nodes_h.append('<div class="ghost-slot" style="height:98px;width:940px;"></div>')
            else:
                act = (i == min(step_idx, max(0, len(sbeat.nodes[:3]) - 1)))
                nodes_h.append(
                    f'<div class="card {"active" if act else ""}" style="width:940px;padding:20px 28px;display:flex;align-items:center;justify-content:space-between;">'
                    f'<div style="display:flex;align-items:center;gap:20px;">'
                    f'<div style="width:52px;height:52px;border-radius:16px;background:rgba(235,139,27,0.16);display:flex;align-items:center;justify-content:center;">'
                    f'{svg_icon(nd.icon, 30, "#EB8B1B")}</div>'
                    f'<div><div style="font-size:30px;font-weight:700;">{esc(nd.label)}</div>'
                    f'<div style="font-size:22px;color:#A1A1AA;margin-top:3px;">{esc(nd.sub)}</div></div></div>'
                    f"{f'<span class=\"pill pill-orange\" style=\"font-size:21px;\">{esc(nd.tag)}</span>' if nd.tag else ''}"
                    f'</div>'
                )
        src_line = f"公開來源 [{esc(s0.source_id)}] {esc(s0.domain)} · {esc(s0.title[:24])}" if s0 else ""
        body_inner = f"""
        <div style="text-align:center;">
          <div style="font-size:56px;font-weight:700;line-height:1.18;">{esc(sbeat.headline)}</div>
          {f'<div style="margin-top:16px;"><span class="pill pill-orange" style="font-size:26px;padding:7px 26px;">{esc(sbeat.highlight_badge)}</span></div>' if sbeat.highlight_badge else ''}
        </div>
        <div class="card active" style="width:940px;padding:20px;margin-top:28px;">
          {f'<img src="{hero_media}" style="width:100%;height:470px;object-fit:cover;border-radius:18px;"/>' if hero_media else ''}
          {f'<div style="font-size:21px;color:#A1A1AA;text-align:center;margin-top:14px;">● {src_line}</div>' if src_line else ''}
        </div>
        <div style="display:flex;flex-direction:column;gap:16px;margin-top:24px;">{''.join(nodes_h)}</div>"""

    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"/><style>{base_css(tokens.bg_tutorial_hex, tokens.short_width, tokens.short_height)}</style></head>
    <body>
      <div style="position:absolute;top:72px;left:70px;right:70px;display:flex;justify-content:center;">
        <div class="src-pill" style="padding:10px 28px;font-size:24px;border-color:#EB8B1B;">
          <span class="src-dot"></span><span style="font-weight:700;color:#FFF;">GARY CHEN｜{esc(script.short_hook_banner)}</span>
        </div>
      </div>
      <div style="position:absolute;top:168px;left:70px;right:70px;bottom:520px;display:flex;flex-direction:column;align-items:center;">
        {body_inner}
      </div>
    </body></html>"""
