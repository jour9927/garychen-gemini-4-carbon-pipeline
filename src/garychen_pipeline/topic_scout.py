from __future__ import annotations

import json
import re

import httpx

from .config import REF_CHANNEL_DIR, TopicCandidate

TICKER_MAP = {
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "輝達": "NVDA",
    "blackwell": "NVDA",
    "meta": "META",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "googl": "GOOGL",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "aws": "AMZN",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "apple": "AAPL",
    "aapl": "AAPL",
    "tsmc": "TSM",
    "台積電": "TSM",
    "tesla": "TSLA",
    "tsla": "TSLA",
    "amd": "AMD",
}


class UnattendedTopicScout:
    """V3 Topic Scout: discovers non-duplicate high-star AI Agent / Engineering / US Stocks topics with exact entity & ticker binding."""

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
                ("browser use ai agent", "ai_agent"),
                ("mcp server agent", "ai_agent"),
                ("ai coding workflow", "vibe_coding"),
            ]
            for q, cat in gh_queries:
                if category_filter and category_filter != cat:
                    continue
                r = client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": f"{q} stars:>4000", "sort": "stars", "order": "desc", "per_page": 6},
                    headers={"User-Agent": "GarychenScout/3.0"},
                )
                if r.status_code == 200:
                    for item in r.json().get("items", []):
                        name = item.get("name", "")
                        full_name = item.get("full_name", "")
                        stars = int(item.get("stargazers_count") or 0)
                        desc = (item.get("description") or "").strip()
                        if self._is_duplicate(name):
                            continue
                        is_browser = "browser" in f"{name} {desc}".lower()
                        tag_label = "瀏覽器 AI Agent" if is_browser else ("自動化工作流" if "workflow" in desc.lower() else "開源 AI Agent")
                        score = min(99.5, 74.0 + min(25.0, stars / 7500.0))
                        candidates.append(
                            TopicCandidate(
                                topic_id=f"gh_{re.sub(r'[^a-z0-9]+', '_', name.lower())[:18]}",
                                title=f"{name} 新手實戰教學，零成本打造你的專屬 {tag_label}！",
                                primary_entity=name,
                                category=cat,  # type: ignore[arg-type]
                                hook_angle=f"現在主流 AI Agent 每個月都要 $20 到 $200 美金訂閱費，但 GitHub 突破 {stars:,} 顆星的開源專案 {full_name} 讓你免費在自己電腦跑起來：{desc[:100]}",
                                why_now=f"GitHub 突破 {stars:,} Stars：{desc[:120]}",
                                score=round(score, 2),
                                seed_queries=[full_name, f"{name} tutorial", f"{name} workflow"],
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
                    topic_id="browser_use_agent",
                    title="Browser-Use 新手教學，免費讓 AI 自動幫你操作瀏覽器！",
                    primary_entity="browser-use",
                    category="ai_agent",
                    hook_angle="不花一毛訂閱費，直接讓開源 AI Agent 幫你自動開網頁、查資料、填表單！",
                    why_now="開源瀏覽器 AI Agent 突破十萬顆星",
                    score=96.0,
                    seed_queries=["browser-use/browser-use", "browser-use python"],
                    seed_urls=["https://github.com/browser-use/browser-use"],
                )
            )

        uniq: dict[str, TopicCandidate] = {}
        for c in sorted(candidates, key=lambda x: x.score, reverse=True):
            if c.topic_id not in uniq:
                uniq[c.topic_id] = c
        return list(uniq.values())[:limit]

    def pick_unattended(self, custom_topic: str | None = None, category: str | None = None, seed_urls: list[str] | None = None) -> TopicCandidate:
        if custom_topic:
            low_t = custom_topic.lower()
            cat = category or (
                "us_stocks"
                if any(w in low_t for w in ("美股", "財報", "股價", "估值", "加倉", "護城河", "capex", "nvidia", "nvda", "meta", "google", "amazon"))
                else "ai_agent"
            )
            tickers = [sym for kw, sym in TICKER_MAP.items() if kw in low_t]
            tickers = list(dict.fromkeys(tickers))
            if cat == "us_stocks" and not tickers:
                tickers = ["NVDA"]
            eng_words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{1,}", custom_topic)
            entity = tickers[0] if (cat == "us_stocks" and tickers) else (eng_words[0] if eng_words else custom_topic[:10])
            queries = (
                [f"{entity} earnings revenue capex", f"{entity} moat valuation", custom_topic[:24]]
                if cat == "us_stocks"
                else [entity, custom_topic[:24]]
            )
            return TopicCandidate(
                topic_id=re.sub(r"[^a-zA-Z0-9]+", "_", (entity or "topic").lower()).strip("_")[:20] or "custom_ep",
                title=custom_topic,
                primary_entity=entity,
                category=cat,  # type: ignore[arg-type]
                hook_angle=custom_topic,
                why_now="公開財報數據、市場預期差與護城河深度拆解" if cat == "us_stocks" else "開源實戰與底層運作深度拆解",
                score=100.0,
                seed_queries=queries,
                seed_urls=seed_urls or [],
                tickers=tickers,
            )
        return self.discover_candidates(category_filter=category, limit=5)[0]
