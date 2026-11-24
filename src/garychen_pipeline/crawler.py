from __future__ import annotations

import datetime as dt
import html
import json
import re
from urllib.parse import quote_plus, urlparse
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from .config import CrawledSource

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_text(s: str) -> str:
    s = html.unescape(s or "")
    return re.sub(r"\s+", " ", s).strip()


def _extract_metrics(text: str) -> list[str]:
    patterns = [
        r"\$[\d,]+(?:\.\d+)?\s*(?:B|M|K|億|萬|兆|/mo|/month|/月)?",
        r"\d+(?:\.\d+)?\s*(?:%|倍|x|X|億|萬|K\s*stars|stars|tokens|GB|TB|ms)",
    ]
    found: list[str] = []
    for pat in patterns:
        for m in re.findall(pat, text):
            val = m.strip()
            if val and val not in found and len(val) <= 28:
                found.append(val)
            if len(found) >= 6:
                return found
    return found


class PublicInfoCrawler:
    """Crawls public developer/tech/financial sources and attaches verifiable source citations."""

    def __init__(self, timeout: float = 12.0):
        self.client = httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True)

    def close(self):
        self.client.close()

    def search_github_repos(self, query: str, limit: int = 4) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&order=desc&per_page={limit}"
            r = self.client.get(url, headers={**HEADERS, "Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                return out
            items = r.json().get("items", [])
            for idx, repo in enumerate(items[:limit], 1):
                full_name = repo.get("full_name", "")
                stars = repo.get("stargazers_count", 0)
                forks = repo.get("forks_count", 0)
                lang = repo.get("language") or "Multi-language"
                desc = _clean_text(repo.get("description") or "")
                updated = (repo.get("pushed_at") or repo.get("updated_at") or "")[:10]
                html_url = repo.get("html_url", f"https://github.com/{full_name}")
                readme_facts = self._fetch_github_readme_highlights(full_name)
                facts = [
                    f"GitHub 開源專案 {full_name} 累積 {stars:,} Stars 與 {forks:,} Forks（主要語言：{lang}）",
                ]
                if desc:
                    facts.append(f"官方專案定位：{desc[:140]}")
                facts.extend(readme_facts[:3])
                out.append(
                    CrawledSource(
                        source_id=f"gh_{idx}_{re.sub(r'[^a-zA-Z0-9]', '_', full_name)[:20]}",
                        title=f"GitHub: {full_name} ({stars:,} ★)",
                        url=html_url,
                        domain="github.com",
                        published_date=updated,
                        retrieved_at=_now_iso(),
                        source_type="github_repo",
                        key_facts=facts,
                        metrics=[f"{stars:,} Stars", f"{forks:,} Forks", lang],
                        excerpt=" | ".join(facts),
                    )
                )
        except Exception:
            pass
        return out

    def _fetch_github_readme_highlights(self, full_name: str) -> list[str]:
        bullets: list[str] = []
        for branch in ("main", "master"):
            try:
                raw_url = f"https://raw.githubusercontent.com/{full_name}/{branch}/README.md"
                r = self.client.get(raw_url)
                if r.status_code == 200 and len(r.text) > 80:
                    for line in r.text.splitlines():
                        line_c = re.sub(r"[#*`>\[\]]+", "", line).strip()
                        line_c = re.sub(r"\(https?://[^\)]+\)", "", line_c).strip()
                        if 28 <= len(line_c) <= 130 and not line_c.lower().startswith(("http", "!", "badge", "license")):
                            bullets.append(line_c)
                        if len(bullets) >= 4:
                            break
                    return bullets
            except Exception:
                continue
        return bullets

    def search_hackernews(self, query: str, limit: int = 4) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story&hitsPerPage={limit}"
            r = self.client.get(url)
            if r.status_code != 200:
                return out
            for idx, hit in enumerate(r.json().get("hits", [])[:limit], 1):
                title = _clean_text(hit.get("title") or "")
                ext_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                pts = hit.get("points") or 0
                cmts = hit.get("num_comments") or 0
                created = (hit.get("created_at") or "")[:10]
                dom = urlparse(ext_url).netloc.replace("www.", "") or "news.ycombinator.com"
                page_facts, excerpt = self._scrape_webpage_summary(ext_url)
                facts = [f"Hacker News 社群熱議（{pts} Points / {cmts} 則技術討論）：{title}"] + page_facts[:3]
                out.append(
                    CrawledSource(
                        source_id=f"hn_{idx}_{hit.get('objectID', idx)}",
                        title=title,
                        url=ext_url,
                        domain=dom,
                        published_date=created,
                        retrieved_at=_now_iso(),
                        source_type="tech_discussion",
                        key_facts=facts,
                        metrics=[f"{pts} HN Points", f"{cmts} 留言"] + _extract_metrics(excerpt)[:2],
                        excerpt=excerpt[:400] or title,
                    )
                )
        except Exception:
            pass
        return out

    def search_arxiv(self, query: str, limit: int = 2) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://export.arxiv.org/api/query?search_query=all:{quote_plus(query)}&sortBy=submittedDate&sortOrder=descending&max_results={limit}"
            r = self.client.get(url)
            if r.status_code != 200:
                return out
            root = ET.fromstring(r.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for idx, entry in enumerate(root.findall("a:entry", ns)[:limit], 1):
                title = _clean_text(entry.findtext("a:title", "", ns))
                summary = _clean_text(entry.findtext("a:summary", "", ns))
                link = _clean_text(entry.findtext("a:id", "", ns))
                pub = _clean_text(entry.findtext("a:published", "", ns))[:10]
                authors = [_clean_text(au.findtext("a:name", "", ns)) for au in entry.findall("a:author", ns)[:3]]
                author_str = ", ".join(a for a in authors if a)
                facts = [
                    f"arXiv 研究論文（{pub}，作者：{author_str}）：{title}",
                    f"核心發現摘要：{summary[:180]}",
                ]
                out.append(
                    CrawledSource(
                        source_id=f"arxiv_{idx}",
                        title=f"arXiv: {title}",
                        url=link,
                        domain="arxiv.org",
                        published_date=pub,
                        retrieved_at=_now_iso(),
                        source_type="research_paper",
                        key_facts=facts,
                        metrics=_extract_metrics(summary)[:3] or ["arXiv Preprint"],
                        excerpt=summary[:420],
                    )
                )
        except Exception:
            pass
        return out

    def scrape_direct_url(self, url: str, idx: int = 1) -> CrawledSource | None:
        facts, excerpt = self._scrape_webpage_summary(url)
        if not facts and not excerpt:
            return None
        dom = urlparse(url).netloc.replace("www.", "")
        title = facts[0][:90] if facts else dom
        return CrawledSource(
            source_id=f"web_{idx}",
            title=title,
            url=url,
            domain=dom,
            published_date=dt.date.today().isoformat(),
            retrieved_at=_now_iso(),
            source_type="official_doc",
            key_facts=facts[:4],
            metrics=_extract_metrics(excerpt)[:4],
            excerpt=excerpt[:450],
        )

    def _scrape_webpage_summary(self, url: str) -> tuple[list[str], str]:
        if not url.startswith("http") or any( url.lower().endswith(ext) for ext in (".pdf", ".zip", ".png", ".jpg", ".mp4") ):
            return [], ""
        try:
            r = self.client.get(url, timeout=8.0)
            if r.status_code != 200 or "text/html" not in r.headers.get("content-type", "").lower():
                return [], ""
            soup = BeautifulSoup(r.text, "lxml")
            for tag in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
                tag.decompose()
            facts: list[str] = []
            page_title = _clean_text(soup.title.string if soup.title and soup.title.string else "")
            if page_title:
                facts.append(page_title)
            meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
            if meta_desc and meta_desc.get("content"):
                md = _clean_text(meta_desc["content"])
                if len(md) > 25:
                    facts.append(md[:160])
            paras: list[str] = []
            for p in soup.find_all(["p", "li"]):
                txt = _clean_text(p.get_text(" "))
                if 40 <= len(txt) <= 220 and not any(b in txt.lower() for b in ("cookie", "privacy policy", "all rights reserved", "sign in")):
                    paras.append(txt)
                    if len(facts) < 5:
                        facts.append(txt[:160])
                if len(paras) >= 8:
                    break
            return facts, " ".join(paras)[:600]
        except Exception:
            return [], ""

    def gather_dossier(self, queries: list[str], seed_urls: list[str] | None = None, min_sources: int = 5) -> list[CrawledSource]:
        sources: list[CrawledSource] = []
        seen_urls: set[str] = set()

        def _add(items: list[CrawledSource]):
            for item in items:
                u = item.url.rstrip("/")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    sources.append(item)

        for idx, u in enumerate(seed_urls or [], 1):
            sc = self.scrape_direct_url(u, idx=idx)
            if sc:
                _add([sc])

        for q in queries[:3]:
            _add(self.search_github_repos(q, limit=3))
            _add(self.search_hackernews(q, limit=3))
            if len(sources) < min_sources:
                _add(self.search_arxiv(q, limit=2))

        # Re-number clean source IDs S1..Sn for unambiguous citation mapping
        for i, src in enumerate(sources[:10], 1):
            src.source_id = f"S{i}"
        return sources[:10]
