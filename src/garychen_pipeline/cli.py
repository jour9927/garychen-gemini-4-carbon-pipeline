from __future__ import annotations

import argparse
import json
import sys

import httpx
from rich.console import Console
from rich.table import Table

from .config import load_cluster_endpoints
from .orchestrator import GarychenUnattendedPipeline
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
            r = httpx.get(f"{ep.url}/health", timeout=6.0)
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

    try:
        r_ol = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        models = [m["name"] for m in r_ol.json().get("models", [])]
        t.add_row("Local", "alan-hub Ollama", "http://127.0.0.1:11434", "[green]ONLINE[/green]", ", ".join(models))
    except Exception as e:
        t.add_row("Local", "alan-hub Ollama", "http://127.0.0.1:11434", "[red]OFFLINE[/red]", str(e)[:50])

    console.print(t)


def main():
    ap = argparse.ArgumentParser(description="Garychen (@garychenai) Unattended Long + Funnel Shorts Production Pipeline")
    ap.add_argument("--topic", default=None, help="Optional custom topic (omit for 100%% unattended auto-discovery)")
    ap.add_argument("--category", choices=["ai_agent", "vibe_coding", "ai_fundamentals", "us_stocks"], default=None)
    ap.add_argument("--seed-url", action="append", default=[], help="Optional public URLs to crawl first")
    ap.add_argument("--episode-id", default=None, help="Optional fixed episode directory ID (enables checkpoint resume)")
    ap.add_argument("--chapters", type=int, default=6, help="Number of chapters/scenes in long video (default: 6)")
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
