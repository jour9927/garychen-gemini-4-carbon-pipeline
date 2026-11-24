from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from .config import REF_CHANNEL_DIR, TopicCandidate


class UnattendedTopicScout:
    """
    Discovers trending AI Agent / Vibe Coding / Engineering / US Stock topics from live public feeds,
    filters out topics already covered on @garychenai, and automatically picks the top candidate in unattended mode.
    """

    def __init__(self):
        self.existing_titles = self._load_existing_channel_titles()

    def _load_existing_channel_titles(self) -> list[str]:
        titles: list[str] = []
        jsonl = REF_CHANNEL_DIR / "all_tabs.jsonl"
        if jsonl.exists():
            for line in jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("{"):
                    try:
                        d = json.loads(line)
                        if d.get("title"):
                            titles.append(d["title"])
                    except Exception:
                        pass
        return titles

    def _is_duplicate(self, candidate_title: str) -> bool:
        c_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", candidate_title.lower()))
        for t in self.existing_titles:
            t_tokens = set(re.findall(r"[a-zA-Z0-9]{3,}", t.lower()))
            if c_tokens and len(c_tokens & t_tokens) >= 3:
                return True
        return False

    def discover_candidates(self, category_filter: str | None = None, limit: int = 5) -> list[TopicCandidate]:
        candidates: list[TopicCandidate] = []
        client = httpx.Client(timeout=10.0, follow_redirects=True)
        try:
            # 1. Live GitHub Trending AI Agent / MCP / Workflow ecosystems
            gh_queries = [
                ("mcp server agent", "ai_agent"),
                ("browser use ai agent", "ai_agent"),
                ("ai coding workflow eval", "vibe_coding"),
            ]
            for q, cat in gh_queries:
                if category_filter and category_filter != cat:
                    continue
                r = client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": f"{q} stars:>1500", "sort": "updated", "order": "desc", "per_page": 5},
                    headers={"User-Agent": "GarychenScout/1.0"},
                )
                if r.status_code == 200:
                    for item in r.json().get("items", []):
                        name = item.get("name", "")
                        full_name = item.get("full_name", "")
                        stars = item.get("stargazers_count", 0)
                        desc = (item.get("description") or "").strip()
                        title = f"MCP 與開源 AI Agent 新神器：{name} 實戰拆解（{stars:,} Stars 背後的工作流設計）"
                        if self._is_duplicate(name):
                            continue
                        score = min(98.0, 72.0 + min(20.0, stars / 2500.0) + (5.0 if desc else 0.0))
                        candidates.append(
                            TopicCandidate(
                                topic_id=f"gh_{name.lower()[:18]}",
                                title=title,
                                category=cat,  # type: ignore[arg-type]
                                hook_angle=f"為什麼開發者都在瘋傳 {full_name}？不用重寫底層，直接讓 AI Agent 自動接管外部工具與資料！",
                                why_now=f"GitHub 已突破 {stars:,} Stars，近期密集更新：{desc[:100]}",
                                score=round(score, 2),
                                seed_queries=[full_name, f"{name} AI agent", "Model Context Protocol workflow"],
                                seed_urls=[item.get("html_url", "")],
                            )
                        )

            # 2. Live Hacker News high-signal AI / Engineering / Infra breakthroughs
            r_hn = client.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": "Model Context Protocol OR AI Agent workflow", "tags": "story", "numericFilters": "points>80", "hitsPerPage": 6},
            )
            if r_hn.status_code == 200:
                for hit in r_hn.json().get("hits", []):
                    htitle = (hit.get("title") or "").strip()
                    pts = int(hit.get("points") or 0)
                    hurl = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    if not htitle or self._is_duplicate(htitle):
                        continue
                    cat = "vibe_coding" if any(k in htitle.lower() for k in ("code", "git", "test", "cli")) else "ai_agent"
                    if category_filter and category_filter != cat:
                        continue
                    candidates.append(
                        TopicCandidate(
                            topic_id=f"hn_{hit.get('objectID')}",
                            title=f"工程師都在討論的 AI 工作流變革：{htitle[:46]} 深度解析",
                            category=cat,  # type: ignore[arg-type]
                            hook_angle=f"在 Hacker News 衝上 {pts} 分的熱門議題，正在改變我們使用 AI Agent 的標準做法。",
                            why_now=f"HN {pts} Points 熱議中，具備明確公開數據與實戰架構可拆解",
                            score=round(min(96.0, 74.0 + pts / 25.0), 2),
                            seed_queries=[htitle, "MCP server AI agent", "Anthropic Model Context Protocol"],
                            seed_urls=[hurl],
                        )
                    )
        except Exception:
            pass
        finally:
            client.close()

        # Curated evergreen high-fit fallback if offline/rate-limited
        if not candidates:
            candidates.append(
                TopicCandidate(
                    topic_id="mcp_agent_stack_2026",
                    title="從零搞懂 MCP (Model Context Protocol)：為什麼它是 AI Agent 串接萬物的終極標準？",
                    category="ai_agent",
                    hook_angle="以前每換一個 AI 工具就要重接一次 API，現在只要一套 MCP Server，Claude、Cursor 跟開源 Agent 全部直接互通！",
                    why_now="MCP 生態系開源工具全面爆發，非技術人員與開發者都能無痛打造個人自動化工作流",
                    score=95.0,
                    seed_queries=["Model Context Protocol MCP servers", "modelcontextprotocol servers", "MCP AI Agent"],
                    seed_urls=["https://github.com/modelcontextprotocol/servers"],
                )
            )

        # Deduplicate & sort descending by score
        uniq: dict[str, TopicCandidate] = {}
        for c in sorted(candidates, key=lambda x: x.score, reverse=True):
            if c.topic_id not in uniq:
                uniq[c.topic_id] = c
        return list(uniq.values())[:limit]

    def pick_unattended(self, custom_topic: str | None = None, category: str | None = None, seed_urls: list[str] | None = None) -> TopicCandidate:
        if custom_topic:
            cat = category or ("us_stocks" if any(w in custom_topic for w in ("美股", "財報", "股價", "估值", "NVIDIA", "Meta", "Google", "Amazon")) else "ai_agent")
            return TopicCandidate(
                topic_id=re.sub(r"[^a-zA-Z0-9]+", "_", custom_topic.lower()).strip("_")[:24] or "custom_topic",
                title=custom_topic,
                category=cat,  # type: ignore[arg-type]
                hook_angle=f"今天用最白話的方式，結合最新爬蟲公開數據與官方來源，帶你一次搞懂：{custom_topic}",
                why_now="使用者指定主題或排程自動觸發",
                score=100.0,
                seed_queries=[custom_topic, f"{custom_topic} GitHub", f"{custom_topic} official"],
                seed_urls=seed_urls or [],
            )
        ranked = self.discover_candidates(category_filter=category, limit=5)
        return ranked[0]
