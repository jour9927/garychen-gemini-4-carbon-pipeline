from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
CONFIGS_DIR = PROJECT_ROOT / "configs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
REF_CHANNEL_DIR = PROJECT_ROOT / "reference_channel"


class DesignTokens(BaseModel):
    """Exact reverse-engineered visual & audio tokens from @garychenai 1080p60 videos."""
    bg_tutorial_hex: str = "#262626"
    bg_stock_hex: str = "#1E1E1E"
    card_bg_hex: str = "#303030"
    card_border_hex: str = "#444444"
    accent_orange_hex: str = "#EB8B1B"
    accent_amber_glow_hex: str = "#F59E0B"
    accent_green_hex: str = "#22C55E"
    accent_red_hex: str = "#DC2626"
    accent_blue_hex: str = "#3B82F6"
    text_primary_hex: str = "#FFFFFF"
    text_secondary_hex: str = "#A3A3A3"
    subtitle_pill_hex: str = "#090909"
    top_bar_track_hex: str = "#333534"
    fps: int = 60
    long_width: int = 1920
    long_height: int = 1080
    short_width: int = 1080
    short_height: int = 1920
    target_lufs: float = -21.0


class CrawledSource(BaseModel):
    source_id: str
    title: str
    url: str
    domain: str
    published_date: str = ""
    retrieved_at: str = ""
    source_type: str = "web"
    relevance_score: float = 1.0
    screenshot_path: str = ""
    key_facts: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    code_or_commands: list[str] = Field(default_factory=list)
    excerpt: str = ""


class TopicCandidate(BaseModel):
    topic_id: str
    title: str
    primary_entity: str = ""
    category: Literal["ai_agent", "vibe_coding", "ai_fundamentals", "us_stocks"] = "ai_agent"
    hook_angle: str
    why_now: str
    score: float = 0.0
    seed_queries: list[str] = Field(default_factory=list)
    seed_urls: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)


BeatLayoutType = Literal[
    "claude_terminal_progressive",
    "pricing_strikethrough_reveal",
    "chapter_roadmap_agenda",
    "progressive_slot_pipeline",
    "hub_ecosystem_radiate",
    "github_pr_checks_mock",
    "live_web_screenshot_spotlight",
    "ai_editorial_split_card",
    "before_after_stamp_compare",
    "kpi_financial_cards",
    "branch_merge_diagram",
    "checklist_two_tier_defense",
    "versus_debate_columns",
    "summary_three_pillars",
]


class VisualNode(BaseModel):
    label: str
    sub: str = ""
    tag: str = ""
    icon: str = "sparkles"
    trend: Literal["up", "down", "neutral"] = "neutral"


class VisualBeat(BaseModel):
    """
    A 6–12 second beat inside a chapter.
    Contains 2–4 spoken clauses (`clauses`). As each clause is spoken, `progressive_step` advances 0 -> 1 -> 2 -> 3,
    triggering dashed-slot fills, terminal typing, dimming/strikethrough, or node highlights every ~2 seconds!
    """
    beat_id: str
    chapter_index: int
    total_chapters: int = 6
    chapter_title: str
    layout_type: BeatLayoutType
    voice_style: Literal["hook", "explainer", "warm"] = "explainer"
    clauses: list[str]
    visual_title: str
    visual_subtitle: str = ""
    badge_text: str = ""
    nodes: list[VisualNode] = Field(default_factory=list)
    callout_title: str = ""
    callout_body: str = ""
    code_lines: list[str] = Field(default_factory=list)
    ai_image_prompt: str = ""
    source_ids: list[str] = Field(default_factory=list)
    sfx_cue: Literal["none", "pop", "terminal", "whoosh", "stamp"] = "pop"


ShortBeatLayoutType = Literal[
    "short_shock_metric_hero",
    "short_progressive_flow",
    "short_before_after_versus",
    "short_live_source_proof",
    "short_code_or_steps",
    "short_funnel_cta",
]


class ShortBeatSpec(BaseModel):
    beat_id: str
    layout_type: ShortBeatLayoutType = "short_progressive_flow"
    voice_style: Literal["hook", "explainer", "warm"] = "hook"
    clauses: list[str]
    headline: str
    sub_caption: str = ""
    highlight_badge: str = ""
    nodes: list[VisualNode] = Field(default_factory=list)
    ai_image_prompt: str = ""
    source_ids: list[str] = Field(default_factory=list)
    is_cta: bool = False


class EpisodeScript(BaseModel):
    episode_id: str
    title: str
    category: Literal["ai_agent", "vibe_coding", "ai_fundamentals", "us_stocks"] = "ai_agent"
    avatar_mode: bool = False
    youtube_description_summary: str
    hashtags: list[str] = Field(default_factory=list)
    chapters: list[str] = Field(default_factory=list)
    beats: list[VisualBeat]
    short_title: str
    short_hook_banner: str
    short_cta_target_title: str
    short_beats: list[ShortBeatSpec]


class RemoteNodeEndpoint(BaseModel):
    name: str
    url: str
    token: str
    ssh_alias: str = ""
    priority: int = 1


def load_cluster_endpoints() -> list[RemoteNodeEndpoint]:
    nodes: list[RemoteNodeEndpoint] = []
    colab_cfg = CONFIGS_DIR / "colab_endpoint.json"
    if colab_cfg.exists():
        try:
            d = json.loads(colab_cfg.read_text(encoding="utf-8"))
            if d.get("url"):
                nodes.append(
                    RemoteNodeEndpoint(
                        name="colab_rtx_pro_6000",
                        url=d["url"].rstrip("/"),
                        token=d.get("token", "gc_rtx6000_carbon_2026"),
                        priority=1,
                    )
                )
        except Exception:
            pass
    env_colab = os.environ.get("GC_COLAB_URL", "").strip()
    if env_colab:
        nodes.insert(
            0,
            RemoteNodeEndpoint(
                name="colab_rtx_pro_6000_env",
                url=env_colab.rstrip("/"),
                token=os.environ.get("GC_COLAB_TOKEN", "gc_rtx6000_carbon_2026"),
                priority=0,
            ),
        )
    nodes.append(
        RemoteNodeEndpoint(
            name="b850_tailscale",
            url=os.environ.get("GC_B850_URL", "http://100.100.230.119:18793"),
            token=os.environ.get("GC_B850_TOKEN", "gc_b850_carbon_2026"),
            ssh_alias="b850",
            priority=2,
        )
    )
    return sorted(nodes, key=lambda n: n.priority)
