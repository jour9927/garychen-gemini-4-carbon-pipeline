from __future__ import annotations

import datetime as dt
import html
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from .config import CrawledSource

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

CHROME_APP_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Noise domains / generic unrelated repos that must NEVER pollute technical/financial citations
BLOCKED_NOISE_PATTERNS = (
    "animate-css",
    "torproject.org",
    "why-do-all-browsers-user-agents",
    "awesome-list",
    "free-programming-books",
)


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
            if val and val not in found and len(val) <= 26:
                found.append(val)
            if len(found) >= 6:
                return found
    return found


def _extract_commands(md_text: str) -> list[str]:
    cmds: list[str] = []
    for m in re.finditer(r"```(?:bash|sh|zsh|shell|python)?\n(.*?)```", md_text, re.DOTALL):
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and 6 <= len(ln) <= 72:
                cmds.append(ln)
                if len(cmds) >= 5:
                    return cmds
    return cmds


class PublicInfoCrawler:
    """
    V2 Precision Crawler:
      - Enforces strict entity & topic relevance filtering (zero off-topic noise)
      - Crawls primary GitHub repo API + README + latest Releases + linked official homepage/docs
      - Crawls entity-matched Hacker News discussions, ArXiv papers, and Yahoo Finance market quotes
      - Captures real dark-mode 1440x900 browser screenshots via Playwright + local Chrome for authentic UI scenes!
    """

    def __init__(self, timeout: float = 12.0):
        self.client = httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True)

    def close(self):
        self.client.close()

    @staticmethod
    def _entity_tokens(entity: str, queries: list[str]) -> list[str]:
        raw = " ".join([entity] + queries[:2])
        toks = [t.lower() for t in re.findall(r"[a-zA-Z0-9_-]{3,}", raw)]
        stop = {"mcp", "agent", "agents", "workflow", "official", "github", "the", "and", "for", "with", "how", "ai"}
        specific = [t for t in toks if t not in stop]
        return specific or toks[:3]

    def _is_relevant(self, title: str, url: str, excerpt: str, required_tokens: list[str]) -> float:
        u_low = url.lower()
        if any(b in u_low for b in BLOCKED_NOISE_PATTERNS):
            return 0.0
        blob = f"{title} {url} {excerpt}".lower()
        if not required_tokens:
            return 0.8
        hits = sum(1 for tok in required_tokens if tok in blob)
        if hits == 0:
            return 0.15
        return min(1.0, 0.55 + 0.25 * hits)

    def inspect_github_repo_direct(self, full_name: str) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            r = self.client.get(f"https://api.github.com/repos/{full_name}", headers={**HEADERS, "Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                return out
            repo = r.json()
            stars = int(repo.get("stargazers_count") or 0)
            forks = int(repo.get("forks_count") or 0)
            issues = int(repo.get("open_issues_count") or 0)
            lang = repo.get("language") or "Python"
            desc = _clean_text(repo.get("description") or "")
            homepage = (repo.get("homepage") or "").strip()
            updated = (repo.get("pushed_at") or repo.get("updated_at") or "")[:10]
            html_url = repo.get("html_url", f"https://github.com/{full_name}")

            readme_bullets, cmds = self._fetch_github_readme(full_name)
            rel_fact = self._fetch_github_latest_release(full_name)

            facts = [f"GitHub 官方開源儲存庫 {full_name}：{stars:,} Stars、{forks:,} Forks（主要語言 {lang}）"]
            if desc:
                facts.append(f"官方核心定位：{desc[:150]}")
            if rel_fact:
                facts.append(rel_fact)
            facts.extend(readme_bullets[:4])

            out.append(
                CrawledSource(
                    source_id="gh_primary",
                    title=f"{full_name} ({stars:,} ★)",
                    url=html_url,
                    domain="github.com",
                    published_date=updated,
                    retrieved_at=_now_iso(),
                    source_type="github_primary",
                    relevance_score=1.0,
                    key_facts=facts,
                    metrics=[f"{stars:,} Stars", f"{forks:,} Forks", lang, f"{issues} Issues"],
                    code_or_commands=cmds,
                    excerpt=" | ".join(facts[:4]),
                )
            )

            # Follow official homepage/documentation site if present!
            if homepage and homepage.startswith("http") and "github.com" not in homepage:
                hp_src = self.scrape_direct_url(homepage, label_prefix="官方網站與文件")
                if hp_src:
                    hp_src.relevance_score = 0.98
                    out.append(hp_src)
        except Exception:
            pass
        return out

    def _fetch_github_readme(self, full_name: str) -> tuple[list[str], list[str]]:
        for branch in ("main", "master"):
            try:
                r = self.client.get(f"https://raw.githubusercontent.com/{full_name}/{branch}/README.md")
                if r.status_code == 200 and len(r.text) > 100:
                    cmds = _extract_commands(r.text)
                    bullets: list[str] = []
                    for line in r.text.splitlines():
                        lc = re.sub(r"[#*`>\[\]]+", "", line).strip()
                        lc = re.sub(r"\(https?://[^\)]+\)", "", lc).strip()
                        if 30 <= len(lc) <= 140 and not lc.lower().startswith(("http", "!", "badge", "license", "<img", "<div", "<p")):
                            bullets.append(lc)
                        if len(bullets) >= 6:
                            break
                    return bullets, cmds
            except Exception:
                continue
        return [], []

    def _fetch_github_latest_release(self, full_name: str) -> str:
        try:
            r = self.client.get(f"https://api.github.com/repos/{full_name}/releases/latest", headers={**HEADERS, "Accept": "application/vnd.github+json"})
            if r.status_code == 200:
                d = r.json()
                tag = d.get("tag_name") or ""
                pub = (d.get("published_at") or "")[:10]
                name = _clean_text(d.get("name") or tag)
                if tag:
                    return f"最新正式版本 {tag}（發布於 {pub}）：{name[:80]}"
        except Exception:
            pass
        return ""

    def search_github_repos(self, query: str, req_tokens: list[str], limit: int = 3) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&order=desc&per_page=6"
            r = self.client.get(url, headers={**HEADERS, "Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                return out
            for repo in r.json().get("items", []):
                full_name = repo.get("full_name", "")
                desc = _clean_text(repo.get("description") or "")
                html_url = repo.get("html_url", f"https://github.com/{full_name}")
                rel = self._is_relevant(full_name, html_url, desc, req_tokens)
                if rel < 0.55:
                    continue
                stars = int(repo.get("stargazers_count") or 0)
                forks = int(repo.get("forks_count") or 0)
                lang = repo.get("language") or "Python"
                updated = (repo.get("pushed_at") or repo.get("updated_at") or "")[:10]
                readme_bullets, cmds = self._fetch_github_readme(full_name)
                facts = [f"相關生態開源專案 {full_name}（{stars:,} Stars / {forks:,} Forks）"]
                if desc:
                    facts.append(desc[:140])
                facts.extend(readme_bullets[:2])
                out.append(
                    CrawledSource(
                        source_id=f"gh_{len(out)+1}",
                        title=f"{full_name} ({stars:,} ★)",
                        url=html_url,
                        domain="github.com",
                        published_date=updated,
                        retrieved_at=_now_iso(),
                        source_type="github_repo",
                        relevance_score=rel,
                        key_facts=facts,
                        metrics=[f"{stars:,} Stars", f"{forks:,} Forks", lang],
                        code_or_commands=cmds,
                        excerpt=" | ".join(facts),
                    )
                )
                if len(out) >= limit:
                    break
        except Exception:
            pass
        return out

    def search_hackernews(self, query: str, req_tokens: list[str], limit: int = 3) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story&hitsPerPage=10"
            r = self.client.get(url)
            if r.status_code != 200:
                return out
            for hit in r.json().get("hits", []):
                title = _clean_text(hit.get("title") or "")
                ext_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                created = (hit.get("created_at") or "")[:10]
                # Reject ancient pre-2023 stories so AI/tech tutorials stay modern
                if created and created[:4].isdigit() and int(created[:4]) < 2023:
                    continue
                rel = self._is_relevant(title, ext_url, "", req_tokens)
                if rel < 0.55:
                    continue
                pts = int(hit.get("points") or 0)
                cmts = int(hit.get("num_comments") or 0)
                dom = urlparse(ext_url).netloc.replace("www.", "") or "news.ycombinator.com"
                page_facts, excerpt = self._scrape_webpage_summary(ext_url)
                facts = [f"Hacker News 工程師社群實測討論（{pts} Points / {cmts} 則留言）：{title}"] + page_facts[:2]
                out.append(
                    CrawledSource(
                        source_id=f"hn_{hit.get('objectID')}",
                        title=title[:85],
                        url=ext_url,
                        domain=dom,
                        published_date=created,
                        retrieved_at=_now_iso(),
                        source_type="hn_discussion",
                        relevance_score=rel,
                        key_facts=facts,
                        metrics=[f"{pts} HN Points", f"{cmts} 則討論"] + _extract_metrics(excerpt)[:2],
                        excerpt=excerpt[:420] or title,
                    )
                )
                if len(out) >= limit:
                    break
        except Exception:
            pass
        return out

    def fetch_yahoo_finance_quotes(self, tickers: list[str]) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        for sym in tickers[:4]:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"
                r = self.client.get(url)
                if r.status_code != 200:
                    continue
                res = (r.json().get("chart", {}).get("result") or [None])[0]
                if not res:
                    continue
                meta = res.get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or price
                high52 = meta.get("fiftyTwoWeekHigh")
                low52 = meta.get("fiftyTwoWeekLow")
                currency = meta.get("currency", "USD")
                chg_pct = ((price - prev) / prev * 100.0) if (price and prev) else 0.0
                pub_url = f"https://finance.yahoo.com/quote/{sym}"
                facts = [
                    f"{sym} 最新公開市場報價：${price:,.2f} {currency}（年內區間 ${low52:,.2f} – ${high52:,.2f}，區間變動 {chg_pct:+.1f}%）",
                ]
                out.append(
                    CrawledSource(
                        source_id=f"yf_{sym.lower()}",
                        title=f"Yahoo Finance 市場數據：{sym} (${price:,.2f})",
                        url=pub_url,
                        domain="finance.yahoo.com",
                        published_date=dt.date.today().isoformat(),
                        retrieved_at=_now_iso(),
                        source_type="market_data",
                        relevance_score=1.0,
                        key_facts=facts,
                        metrics=[f"${price:,.2f}", f"{chg_pct:+.1f}% (1Y)", f"52W High ${high52:,.0f}"],
                        excerpt=facts[0],
                    )
                )
            except Exception:
                continue
        return out

    def search_arxiv(self, query: str, req_tokens: list[str], limit: int = 2) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://export.arxiv.org/api/query?search_query=all:{quote_plus(query)}&sortBy=relevance&order=descending&max_results=5"
            r = self.client.get(url)
            if r.status_code != 200:
                return out
            root = ET.fromstring(r.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                title = _clean_text(entry.findtext("a:title", "", ns))
                summary = _clean_text(entry.findtext("a:summary", "", ns))
                link = _clean_text(entry.findtext("a:id", "", ns))
                rel = self._is_relevant(title, link, summary, req_tokens)
                if rel < 0.55:
                    continue
                pub = _clean_text(entry.findtext("a:published", "", ns))[:10]
                authors = [_clean_text(au.findtext("a:name", "", ns)) for au in entry.findall("a:author", ns)[:2]]
                facts = [
                    f"arXiv 技術論文（{pub}，{', '.join(authors)}）：{title}",
                    f"實驗與架構重點：{summary[:180]}",
                ]
                out.append(
                    CrawledSource(
                        source_id=f"arxiv_{len(out)+1}",
                        title=title[:80],
                        url=link,
                        domain="arxiv.org",
                        published_date=pub,
                        retrieved_at=_now_iso(),
                        source_type="research_paper",
                        relevance_score=rel,
                        key_facts=facts,
                        metrics=_extract_metrics(summary)[:3] or ["arXiv Paper"],
                        excerpt=summary[:400],
                    )
                )
                if len(out) >= limit:
                    break
        except Exception:
            pass
        return out

    def scrape_direct_url(self, url: str, label_prefix: str = "") -> CrawledSource | None:
        if "github.com/" in url:
            m = re.search(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", url)
            if m:
                gh_items = self.inspect_github_repo_direct(m.group(1))
                if gh_items:
                    return gh_items[0]
        facts, excerpt = self._scrape_webpage_summary(url)
        if not facts and not excerpt:
            return None
        dom = urlparse(url).netloc.replace("www.", "")
        raw_t = facts[0][:80] if facts else dom
        title = f"{label_prefix}：{raw_t}" if label_prefix else raw_t
        return CrawledSource(
            source_id="web_direct",
            title=title,
            url=url,
            domain=dom,
            published_date=dt.date.today().isoformat(),
            retrieved_at=_now_iso(),
            source_type="official_doc",
            relevance_score=0.95,
            key_facts=facts[:4],
            metrics=_extract_metrics(excerpt)[:4],
            excerpt=excerpt[:450],
        )

    def _scrape_webpage_summary(self, url: str) -> tuple[list[str], str]:
        if not url.startswith("http") or any(url.lower().endswith(ext) for ext in (".pdf", ".zip", ".png", ".jpg", ".mp4")):
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
                if len(md) > 20:
                    facts.append(md[:160])
            paras: list[str] = []
            for p in soup.find_all(["p", "li", "h2", "h3"]):
                txt = _clean_text(p.get_text(" "))
                if 32 <= len(txt) <= 210 and not any(b in txt.lower() for b in ("cookie", "privacy policy", "all rights reserved", "sign in")):
                    paras.append(txt)
                    if len(facts) < 6:
                        facts.append(txt[:160])
                if len(paras) >= 10:
                    break
            return facts, " ".join(paras)[:650]
        except Exception:
            return [], ""

    @staticmethod
    def capture_source_screenshots(sources: list[CrawledSource], out_dir: Path, max_captures: int = 4):
        """Captures real crisp 1440x900 dark-mode webpage screenshots for `live_web_screenshot_spotlight` scenes."""
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            from playwright.sync_api import sync_playwright
            launch_kwargs = {"headless": True}
            if Path(CHROME_APP_BIN).exists():
                launch_kwargs["executable_path"] = CHROME_APP_BIN
            with sync_playwright() as p:
                browser = p.chromium.launch(**launch_kwargs)
                ctx = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    color_scheme="dark",
                    device_scale_factor=1.5,
                    locale="zh-TW",
                )
                captured = 0
                for src in sources:
                    if captured >= max_captures:
                        break
                    out_png = out_dir / f"{src.source_id}.png"
                    if out_png.exists() and out_png.stat().st_size > 5000:
                        src.screenshot_path = str(out_png)
                        captured += 1
                        continue
                    try:
                        page = ctx.new_page()
                        page.goto(src.url, wait_until="domcontentloaded", timeout=10000)
                        page.wait_for_timeout(900)
                        # Hide common cookie banners cleanly
                        page.evaluate(
                            """() => {
                                for (const sel of ['[id*="cookie"]', '[class*="cookie"]', '[aria-label*="cookie"]']) {
                                    document.querySelectorAll(sel).forEach(el => el.style.display = 'none');
                                }
                            }"""
                        )
                        page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": 1440, "height": 900})
                        page.close()
                        if out_png.exists() and out_png.stat().st_size > 5000:
                            src.screenshot_path = str(out_png)
                            captured += 1
                    except Exception:
                        continue
                ctx.close()
                browser.close()
        except Exception as exc:
            print(f"[crawler] Screenshot capture skipped ({exc})", flush=True)

    def gather_dossier(
        self,
        queries: list[str],
        primary_entity: str = "",
        seed_urls: list[str] | None = None,
        tickers: list[str] | None = None,
        screenshots_dir: Path | None = None,
    ) -> list[CrawledSource]:
        req_tokens = self._entity_tokens(primary_entity, queries)
        sources: list[CrawledSource] = []
        seen_urls: set[str] = set()

        def _add(items: list[CrawledSource]):
            for item in items:
                u = item.url.rstrip("/")
                if u and u not in seen_urls and not any(b in u.lower() for b in BLOCKED_NOISE_PATTERNS):
                    seen_urls.add(u)
                    sources.append(item)

        # 1. Direct primary URLs (including GitHub repo + linked homepage!)
        for u in (seed_urls or []):
            if "github.com/" in u:
                m = re.search(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", u)
                if m:
                    _add(self.inspect_github_repo_direct(m.group(1)))
                    continue
            sc = self.scrape_direct_url(u)
            if sc:
                _add([sc])

        # 2. Live financial market quotes when analyzing US stocks
        if tickers:
            _add(self.fetch_yahoo_finance_quotes(tickers))

        # 3. Entity-filtered GitHub, Hacker News, and ArXiv
        for q in queries[:3]:
            _add(self.search_github_repos(q, req_tokens, limit=2))
            _add(self.search_hackernews(q, req_tokens, limit=2))
            _add(self.search_arxiv(q, req_tokens, limit=2))

        # Sort by relevance_score descending so S1..Sn are always the highest-signal primary sources
        sources.sort(key=lambda s: s.relevance_score, reverse=True)
        sources = sources[:8]
        for i, src in enumerate(sources, 1):
            src.source_id = f"S{i}"

        if screenshots_dir is not None and sources:
            self.capture_source_screenshots(sources, screenshots_dir, max_captures=4)

        return sources
