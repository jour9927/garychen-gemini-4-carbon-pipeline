from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
CONFIGS_DIR = PROJECT_ROOT / "configs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
REF_CHANNEL_DIR = PROJECT_ROOT / "reference_channel"


class DesignTokens(BaseModel):
    """Exact pixel, motion & acoustic tokens reverse-engineered from @garychenai Remotion 1080p60 masters."""
    bg_tutorial_hex: str = "#242424"
    bg_stock_hex: str = "#1E1E1E"
    card_bg_hex: str = "#2E2E32"
    card_border_hex: str = "#424246"
    accent_orange_hex: str = "#EB8B1B"
    accent_gold_thumb_hex: str = "#FFC700"
    accent_green_hex: str = "#22C55E"
    accent_red_hex: str = "#EF4444"
    text_primary_hex: str = "#FFFFFF"
    text_secondary_hex: str = "#A1A1AA"
    subtitle_pill_hex: str = "#090909"
    fps: int = 60
    long_width: int = 1920
    long_height: int = 1080
    short_width: int = 1080
    short_height: int = 1920
    target_lufs: float = -20.5


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
    extra_screenshots: list[str] = Field(default_factory=list)
    live_video_path: str = ""
    key_facts: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    code_or_commands: list[str] = Field(default_factory=list)
    pr_or_issue_items: list[str] = Field(default_factory=list)
    time_series: dict[str, list[list[Any]]] = Field(default_factory=dict)
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
    "app_squircles_strikethrough",
    "claude_chat_dialog",
    "slash_command_prompt_bar",
    "agenda_four_steps",
    "code_editor_live_preview",
    "protagonist_app_flow",
    "ecosystem_node_graph",
    "browser_ui_live_tour",
    "github_pr_blast_radius",
    "github_pr_checks_card",
    "swarm_subagents_grid",
    "before_after_workflow_card",
    "concept_hero_split_3d",
    "feature_pill_matrix",
    "animated_growth_curve",
    "operating_leverage_chart",
    "second_level_thinking_crowd",
    "moat_shield_architecture",
    "stocks_kpi_asymmetric",
    "stocks_big_statement",
    "stocks_four_pillars",
    "stocks_valuation_scenarios",
]


class VisualNode(BaseModel):
    label: str
    sub: str = ""
    tag: str = ""
    metric: str = ""
    icon: str = "sparkles"
    trend: Literal["up", "down", "neutral"] = "neutral"


class VisualBeat(BaseModel):
    """
    V4 High-Density 60fps Remotion Beat:
    Supports multi-step RGBA spring reveals PLUS continuous intra-beat 60fps animations:
      - Smooth camera zoom & pan (`camera_focus`) + animated macOS pointer cursor glide & click ripple
      - 60fps character-by-character live typing + blinking #EB8B1B cursor
      - 60fps left-to-right progressive SVG curve & arrow wipe
      - Top horizontal workflow pipeline indicator (`pipeline_steps` / `active_pipeline_idx`)
    """
    beat_id: str
    chapter_index: int
    total_chapters: int = 7
    chapter_title: str
    layout_type: BeatLayoutType
    voice_style: Literal["hook", "explainer", "warm", "stocks"] = "explainer"
    clauses: list[str]
    spoken_clauses: list[str] = Field(default_factory=list)
    visual_title: str = ""
    visual_subtitle: str = ""
    badge_text: str = ""
    nodes: list[VisualNode] = Field(default_factory=list)
    callout_title: str = ""
    callout_body: str = ""
    code_lines: list[str] = Field(default_factory=list)
    pipeline_steps: list[str] = Field(default_factory=list)
    active_pipeline_idx: int = -1
    chart_points: list[list[Any]] = Field(default_factory=list)
    secondary_chart_points: list[list[Any]] = Field(default_factory=list)
    camera_focus: list[float] = Field(default_factory=lambda: [0.42, 0.36, 1.30])
    screenshot_override: str = ""
    live_video_override: str = ""
    ai_image_prompt: str = ""
    source_ids: list[str] = Field(default_factory=list)
    sfx_cue: Literal["none", "pop", "thock", "typing", "terminal", "click", "whoosh", "stamp"] = "thock"


ShortBeatLayoutType = Literal[
    "short_squircles_hook",
    "short_live_typing_card",
    "short_browser_zoom_proof",
    "short_growth_curve",
    "short_versus_stamp",
    "short_kpi_stack",
    "short_second_level_crowd",
    "short_shock_metric_hero",
    "short_progressive_flow",
    "short_before_after_versus",
    "short_live_source_proof",
    "short_code_or_steps",
    "short_funnel_cta",
]


class ShortBeatSpec(BaseModel):
    beat_id: str
    layout_type: ShortBeatLayoutType = "short_kpi_stack"
    voice_style: Literal["hook", "explainer", "warm", "stocks"] = "hook"
    clauses: list[str]
    spoken_clauses: list[str] = Field(default_factory=list)
    headline: str
    sub_caption: str = ""
    highlight_badge: str = ""
    nodes: list[VisualNode] = Field(default_factory=list)
    code_lines: list[str] = Field(default_factory=list)
    chart_points: list[list[Any]] = Field(default_factory=list)
    ai_image_prompt: str = ""
    source_ids: list[str] = Field(default_factory=list)
    sfx_cue: Literal["none", "thock", "typing", "click", "whoosh", "stamp"] = "thock"
    is_cta: bool = False


class EpisodeScript(BaseModel):
    episode_id: str
    title: str
    thumbnail_line1: str = ""
    thumbnail_line2: str = ""
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
    b850_cfg = CONFIGS_DIR / "b850_endpoint.json"
    if b850_cfg.exists():
        try:
            d = json.loads(b850_cfg.read_text(encoding="utf-8"))
            if d.get("url"):
                nodes.append(
                    RemoteNodeEndpoint(
                        name="b850_tailscale",
                        url=d["url"].rstrip("/"),
                        token=d.get("token", "gc_b850_carbon_2026"),
                        ssh_alias="b850",
                        priority=2,
                    )
                )
        except Exception:
            pass
    else:
        nodes.append(
            RemoteNodeEndpoint(
                name="b850_tailscale",
                url="http://100.100.230.119:18793",
                token="gc_b850_carbon_2026",
                ssh_alias="b850",
                priority=2,
            )
        )
    nodes.append(
        RemoteNodeEndpoint(
            name="alan_hub_m3_pro_mps",
            url="http://127.0.0.1:19744",
            token="gc_mps_carbon_2026",
            priority=3,
        )
    )
    return sorted(nodes, key=lambda x: x.priority)
