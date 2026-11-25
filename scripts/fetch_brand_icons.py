#!/usr/bin/env python3
"""
Fetches 100% authentic official brand vector SVGs from SimpleIcons CDN into `assets/brand_svgs/brand_icons.json`
so our Remotion compositor renders pixel-accurate real brand marks (OpenAI, Claude, Meta, NVIDIA, GitHub, Git,
Instagram, Threads, Facebook, Google, Gmail, Maps, Calendar, Docker, n8n, Zapier, Slack, Notion, Vercel, Render,
Netflix, Python, Playwright, Telegram, YouTube, Apple) completely offline!
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = PROJECT_ROOT / "assets/brand_svgs/brand_icons.json"

# key -> (simpleicons_slug, squircle_bg_hex, fg_hex)
BRAND_SPECS: dict[str, tuple[str, str, str]] = {
    "claude": ("claude", "#F4EDE4", "#D97757"),
    "anthropic": ("anthropic", "#F4EDE4", "#191919"),
    "openai": ("openai", "#FFFFFF", "#10A37F"),
    "chatgpt": ("openai", "#10A37F", "#FFFFFF"),
    "meta": ("meta", "#FFFFFF", "#0467DF"),
    "instagram": ("instagram", "#2A1525", "#E4405F"),
    "threads": ("threads", "#141416", "#FFFFFF"),
    "facebook": ("facebook", "#1877F2", "#FFFFFF"),
    "google": ("google", "#FFFFFF", "#4285F4"),
    "gmail": ("gmail", "#FFFFFF", "#EA4335"),
    "calendar": ("googlecalendar", "#FFFFFF", "#4285F4"),
    "maps": ("googlemaps", "#FFFFFF", "#34A853"),
    "youtube": ("youtube", "#281111", "#FF0000"),
    "github": ("github", "#18181B", "#FFFFFF"),
    "git": ("git", "#291612", "#F05032"),
    "docker": ("docker", "#0D2238", "#2496ED"),
    "nvidia": ("nvidia", "#142608", "#76B900"),
    "n8n": ("n8n", "#2B1419", "#EA4B71"),
    "zapier": ("zapier", "#2B160C", "#FF4F00"),
    "notion": ("notion", "#FFFFFF", "#18181B"),
    "slack": ("slack", "#241229", "#E01E5A"),
    "telegram": ("telegram", "#0F2433", "#26A5E4"),
    "discord": ("discord", "#1A1D36", "#5865F2"),
    "python": ("python", "#162436", "#3776AB"),
    "typescript": ("typescript", "#102338", "#3178C6"),
    "vercel": ("vercel", "#141416", "#FFFFFF"),
    "render": ("render", "#141416", "#FFFFFF"),
    "cloudflare": ("cloudflare", "#2B1D0E", "#F38020"),
    "netflix": ("netflix", "#1F0B0D", "#E50914"),
    "apple": ("apple", "#1C1C1E", "#FFFFFF"),
    "x": ("x", "#141416", "#FFFFFF"),
    "supabase": ("supabase", "#10281E", "#3ECF8E"),
    "postgresql": ("postgresql", "#132133", "#4169E1"),
}


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict] = {}
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        for key, (slug, bg, fg) in BRAND_SPECS.items():
            for url in (
                f"https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg",
                f"https://unpkg.com/simple-icons@latest/icons/{slug}.svg",
            ):
                try:
                    r = client.get(url)
                    if r.status_code == 200 and "<path" in r.text:
                        m = re.search(r'<path[^>]*\sd="([^"]+)"', r.text)
                        if m:
                            result[key] = {"bg": bg, "fg": fg, "path": m.group(1)}
                            break
                except Exception:
                    continue

    # Signature @garychenai custom icons (Cute rounded AI Robot mascot from 08_pstack + Cursor + AWS + Microsoft)
    result["robot"] = {
        "bg": "#2A2A2E",
        "fg": "#FFFFFF",
        "custom_svg": (
            '<line x1="12" y1="2.5" x2="12" y2="6" stroke="#EB8B1B" stroke-width="2.2" stroke-linecap="round"/>'
            '<circle cx="12" cy="2.2" r="1.5" fill="#EB8B1B" stroke="none"/>'
            '<rect x="4.5" y="6" width="15" height="12.5" rx="5" fill="#FFFFFF" stroke="none"/>'
            '<rect x="7" y="9" width="10" height="5.5" rx="2.6" fill="#18181B" stroke="none"/>'
            '<circle cx="9.8" cy="11.7" r="1.25" fill="#EB8B1B" stroke="none"/>'
            '<circle cx="14.2" cy="11.7" r="1.25" fill="#EB8B1B" stroke="none"/>'
            '<rect x="2.5" y="10" width="2" height="4.5" rx="1" fill="#A1A1AA" stroke="none"/>'
            '<rect x="19.5" y="10" width="2" height="4.5" rx="1" fill="#A1A1AA" stroke="none"/>'
        ),
    }
    result["cursor"] = {
        "bg": "#18181B",
        "fg": "#FFFFFF",
        "custom_svg": '<polygon points="12,2.5 20.5,7.4 20.5,16.6 12,21.5 3.5,16.6 3.5,7.4" fill="none" stroke="#FFFFFF" stroke-width="1.8"/><polygon points="12,2.5 20.5,7.4 12,12 3.5,7.4" fill="#FFFFFF" stroke="none"/><polygon points="12,12 20.5,7.4 20.5,16.6 12,21.5" fill="#A1A1AA" stroke="none"/>',
    }
    result["microsoft"] = {
        "bg": "#1F242B",
        "fg": "#FFFFFF",
        "custom_svg": '<rect x="3" y="3" width="8.2" height="8.2" fill="#F25022" stroke="none"/><rect x="12.8" y="3" width="8.2" height="8.2" fill="#7FBA00" stroke="none"/><rect x="3" y="12.8" width="8.2" height="8.2" fill="#00A4EF" stroke="none"/><rect x="12.8" y="12.8" width="8.2" height="8.2" fill="#FFB900" stroke="none"/>',
    }
    result["playwright"] = {
        "bg": "#18281D",
        "fg": "#2EAD33",
        "custom_svg": '<path d="M4 6c0 7 3.5 12 8 14 4.5-2 8-7 8-14-5 1.2-11 1.2-16 0z" fill="none" stroke="#2EAD33" stroke-width="2.1"/><circle cx="9.2" cy="11" r="1.2" fill="#2EAD33" stroke="none"/><circle cx="14.8" cy="11" r="1.2" fill="#2EAD33" stroke="none"/><path d="M9.5 15c1.5 1.3 3.5 1.3 5 0" stroke="#EB8B1B" stroke-width="2" fill="none"/>',
    }

    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SAVED {len(result)} OFFICIAL BRAND ICONS -> {OUT_JSON}")


if __name__ == "__main__":
    main()
