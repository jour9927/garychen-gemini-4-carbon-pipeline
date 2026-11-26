from __future__ import annotations

import argparse
import json
import sys

import httpx
from rich.console import Console
from rich.table import Table

from .config import load_cluster_endpoints
from .orchestrator import GarychenUnattendedPipeline
from .scriptwriter import load_gemini_api_key
from .topic_scout import UnattendedTopicScout

console = Console()


def cmd_health():
    t = Table(title="Garychen Gemini 4 Carbon — Cluster & Node Health")
    t.add_column("Priority", style="cyan")
    t.add_column("Node", style="bold")
    t.add_column("Endpoint")
    t.add_column("Status")
    t.add_column("Compute / Details")

    for ep in load_cluster_endpoints():
        try:
            r = httpx.get(f"{ep.url}/health", timeout=6.0, trust_env=False)
            if r.status_code == 200:
                d = r.json()
                g = d.get("gpu", {})
                t.add_row(
                    str(ep.priority),
                    ep.name,
                    ep.url,
                    "[green]ONLINE[/green]",
                    f"{g.get('gpu_name')} (free VRAM: {g.get('free_mb')} MB, CPUs: {g.get('cpus')}, disk: {d.get('disk_free_gb')} GB)",
                )
            else:
                t.add_row(str(ep.priority), ep.name, ep.url, f"[yellow]HTTP {r.status_code}[/yellow]", "")
        except Exception as e:
            t.add_row(str(ep.priority), ep.name, ep.url, "[red]OFFLINE[/red]", str(e)[:60])

    g_key, g_model = load_gemini_api_key()
    if g_key:
        t.add_row("Cloud LLM", "Google Gemini API", "generativelanguage.googleapis.com", "[green]CONFIGURED[/green]", f"model={g_model} (key_len={len(g_key)})")
    else:
        t.add_row("Cloud LLM", "Google Gemini API", "generativelanguage.googleapis.com", "[yellow]MISSING GEMINI_API_KEY[/yellow]", "Set GEMINI_API_KEY in .env or env")

    console.print(t)


def main():
    ap = argparse.ArgumentParser(description="Garychen (@garychenai) Unattended Long + Funnel Shorts Production Pipeline")
    ap.add_argument("--topic", default=None, help="Optional custom topic (omit for 100%% unattended auto-discovery)")
    ap.add_argument("--category", choices=["ai_agent", "vibe_coding", "ai_fundamentals", "us_stocks"], default=None)
    ap.add_argument("--seed-url", action="append", default=[], help="Optional public URLs to crawl first")
    ap.add_argument("--episode-id", default=None, help="Optional fixed episode directory ID (enables checkpoint resume)")
    ap.add_argument("--chapters", type=int, default=7, help="Number of chapters/scenes in long video (default: 7)")
    ap.add_argument("--scout-only", action="store_true", help="Discover and print ranked topics without rendering")
    ap.add_argument("--health", action="store_true", help="Check RTX PRO 6000 Colab, B850 Tailscale, and Local node health")
    args = ap.parse_args()

    if args.health:
        cmd_health()
        return

    if args.scout_only:
        scout = UnattendedTopicScout()
        cands = scout.discover_candidates(category_filter=args.category, limit=5)
        print(json.dumps([c.model_dump() for c in cands], ensure_ascii=False, indent=2))
        return

    pipe = GarychenUnattendedPipeline()
    summary = pipe.run(
        custom_topic=args.topic,
        category=args.category,
        seed_urls=args.seed_url or None,
        episode_id=args.episode_id,
        num_chapters=args.chapters,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
