from __future__ import annotations

import json
import re

import httpx

from .config import REF_CHANNEL_DIR, TopicCandidate

TICKER_MAP = {
    "nvidia": "NVDA",
    "輝達": "NVDA",
    "meta": "META",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "microsoft": "MSFT",
    "apple": "AAPL",
    "tsmc": "TSM",
    "台積電": "TSM",
    "tesla": "TSLA",
    "amd": "AMD",
}


class UnattendedTopicScout:
    """Discovers high-signal AI Agent / Vibe Coding / US Stocks topics and extracts exact primary entities & tickers."""

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

    def _is_duplicate(self, entity: str) -> bool:
        e_low = entity.lower()
        return any(e_low in t.lower() for t in self.existing_titles if len(e_low) >= 4)

    def discover_candidates(self, category_filter: str | None = None, limit: int = 5) -> list[TopicCandidate]:
        candidates: list[TopicCandidate] = []
        client = httpx.Client(timeout=10.0, follow_redirects=True)
        try:
            gh_queries = [
                ("mcp server agent", "ai_agent"),
                ("browser use ai agent", "ai_agent"),
                ("ai coding workflow", "vibe_coding"),
            ]
            for q, cat in gh_queries:
                if category_filter and category_filter != cat:
                    continue
                r = client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": f"{q} stars:>2500", "sort": "stars", "order": "desc", "per_page": 5},
                    headers={"User-Agent": "GarychenScout/2.0"},
                )
                if r.status_code == 200:
                    for item in r.json().get("items", []):
                        name = item.get("name", "")
                        full_name = item.get("full_name", "")
                        stars = int(item.get("stargazers_count") or 0)
                        desc = (item.get("description") or "").strip()
                        if self._is_duplicate(name):
                            continue
                        score = min(99.0, 75.0 + min(24.0, stars / 8000.0))
                        is_browser = "browser" in f"{name} {desc}".lower()
                        tag_label = "瀏覽器 AI Agent" if is_browser else ("AI Coding 工作流" if cat == "vibe_coding" else "開源 AI Agent 工具")
                        candidates.append(
                            TopicCandidate(
                                topic_id=f"gh_{re.sub(r'[^a-z0-9]+', '_', name.lower())[:18]}",
                                title=f"不花錢升級你的開發流！{name} 新手實戰教學（{stars:,} Stars {tag_label}）",
                                primary_entity=name,
                                category=cat,  # type: ignore[arg-type]
                                hook_angle=f"為什麼開源專案 {full_name} 能在 GitHub 狂飆 {stars:,} 顆星？這集直接帶你拆解核心原理：{desc[:90]}",
                                why_now=f"GitHub 突破 {stars:,} Stars：{desc[:110]}",
                                score=round(score, 2),
                                seed_queries=[full_name, f"{name} AI", f"{name} docs"],
                                seed_urls=[item.get("html_url", "")],
                            )
                        )
        except Exception:
            pass
        finally:
            client.close()

        if not candidates:
            candidates.append(
                TopicCandidate(
                    topic_id="mcp_servers_guide",
                    title="從零搞懂 MCP (Model Context Protocol)：讓 Claude 與 AI Agent 一鍵串接所有工具！",
                    primary_entity="modelcontextprotocol",
                    category="ai_agent",
                    hook_angle="以前每換一個 AI 就要重接一次 API，現在只要掛上 MCP Server，資料庫、GitHub 跟瀏覽器全部直接打通！",
                    why_now="Anthropic 推出的開源標準 MCP 成為 AI Agent 串接工具的事實標準",
                    score=95.0,
                    seed_queries=["modelcontextprotocol/servers", "Model Context Protocol MCP"],
                    seed_urls=["https://github.com/modelcontextprotocol/servers"],
                )
            )

        uniq: dict[str, TopicCandidate] = {}
        for c in sorted(candidates, key=lambda x: x.score, reverse=True):
            if c.topic_id not in uniq:
                uniq[c.topic_id] = c
        return list(uniq.values())[:limit]

    def pick_unattended(self, custom_topic: str | None = None, category: str | None = None, seed_urls: list[str] | None = None) -> TopicCandidate:
        if custom_topic:
            cat = category or (
                "us_stocks"
                if any(w in custom_topic.lower() for w in ("美股", "財報", "股價", "估值", "nvidia", "meta", "google", "amazon", "護城河"))
                else "ai_agent"
            )
            tickers = [sym for kw, sym in TICKER_MAP.items() if kw in custom_topic.lower()]
            if cat == "us_stocks" and not tickers:
                tickers = ["NVDA", "META", "GOOGL"]
            eng_words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", custom_topic)
            entity = eng_words[0] if eng_words else custom_topic[:12]
            return TopicCandidate(
                topic_id=re.sub(r"[^a-zA-Z0-9]+", "_", (entity or "topic").lower()).strip("_")[:20] or "custom_ep",
                title=custom_topic,
                primary_entity=entity,
                category=cat,  # type: ignore[arg-type]
                hook_angle=custom_topic,
                why_now="即時公開數據與架構深度拆解",
                score=100.0,
                seed_queries=[entity, custom_topic[:24]],
                seed_urls=seed_urls or [],
                tickers=list(dict.fromkeys(tickers)),
            )
        return self.discover_candidates(category_filter=category, limit=5)[0]
