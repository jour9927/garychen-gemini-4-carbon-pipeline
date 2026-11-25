from __future__ import annotations

import csv
import datetime as dt
import html
import io
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

# SEC EDGAR requires a descriptive User-Agent header per https://www.sec.gov/os/accessing-edgar-data
SEC_HEADERS = {
    "User-Agent": "GaryChenResearchPipeline/3.0 (contact@garychenai.com)",
    "Accept": "application/json",
}

SEC_CIK_MAP = {
    "NVDA": ("0001045810", "NVIDIA Corp."),
    "META": ("0001326801", "Meta Platforms, Inc."),
    "GOOGL": ("0001652044", "Alphabet Inc."),
    "AMZN": ("0001018724", "Amazon.com, Inc."),
    "MSFT": ("0000789019", "Microsoft Corp."),
    "AAPL": ("0000320193", "Apple Inc."),
    "TSLA": ("0001318605", "Tesla, Inc."),
    "AMD": ("0000002488", "Advanced Micro Devices, Inc."),
    "TSM": ("0001046179", "Taiwan Semiconductor Mfg."),
}

CHROME_APP_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

BLOCKED_NOISE_PATTERNS = (
    "animate-css",
    "torproject.org",
    "why-do-all-browsers-user-agents",
    "awesome-list",
    "free-programming-books",
    "audio2face",
    "facial animation",
)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_text(s: str) -> str:
    s = html.unescape(s or "")
    return re.sub(r"\s+", " ", s).strip()


def _fmt_usd_yi(val_usd: float) -> str:
    """Formats raw USD into Garychen's signature `$X,XXX 億` (hundreds of millions USD) string."""
    yi = val_usd / 1e8
    if abs(yi) >= 100:
        return f"${yi:,.0f} 億"
    return f"${yi:,.1f} 億"


def _extract_metrics(text: str) -> list[str]:
    patterns = [
        r"\$\d[\d,]*(?:\.\d+)?\s*(?:B|M|K|億|萬|兆|/mo|/month|/月)?",
        r"[+-]?\d+(?:\.\d+)?\s*(?:%|倍|x|X|億|萬|K\s*stars|stars|tokens|GB|TB)",
    ]
    found: list[str] = []
    for pat in patterns:
        for m in re.findall(pat, text):
            val = m.strip()
            if val and val not in found and 2 <= len(val) <= 24:
                found.append(val)
            if len(found) >= 6:
                return found
    return found


def _extract_commands(md_text: str) -> list[str]:
    cmds: list[str] = []
    for m in re.finditer(r"```(?:bash|sh|zsh|shell|python)?\n(.*?)```", md_text, re.DOTALL):
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and 6 <= len(ln) <= 68:
                cmds.append(ln)
                if len(cmds) >= 5:
                    return cmds
    return cmds


class PublicInfoCrawler:
    """
    V3 Precision Domain Crawler:
      - Official SEC EDGAR 10-K / 10-Q XBRL financial statement extractor (`data.sec.gov`) for US Stocks
      - Dual live stock price & 52-week range extractor (Stooq market feed + Yahoo Finance chart API)
      - Primary GitHub repo + README + latest release + official docs crawler for AI/Engineering tutorials
      - Strict relevance & noise filtering + 1440x900 Retina dark-mode browser screenshot capture!
    """

    def __init__(self, timeout: float = 14.0):
        self.client = httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True)

    def close(self):
        self.client.close()

    @staticmethod
    def _entity_tokens(entity: str, queries: list[str]) -> list[str]:
        alias_map = {
            "nvda": ["nvda", "nvidia"],
            "meta": ["meta", "llama"],
            "googl": ["googl", "google", "alphabet"],
            "amzn": ["amzn", "amazon", "aws"],
            "msft": ["msft", "microsoft", "azure"],
            "tsm": ["tsm", "tsmc"],
        }
        ent_toks = [t.lower() for t in re.findall(r"[a-zA-Z0-9_-]{3,}", entity)]
        stop = {
            "mcp", "agent", "agents", "workflow", "official", "github", "the", "and", "for", "with", "how",
            "earnings", "moat", "revenue", "capex", "valuation", "stock", "stocks", "market", "analysis", "deep", "dive", "inference",
        }
        specific_ent: list[str] = []
        for t in ent_toks:
            if t not in stop:
                for ex in alias_map.get(t, [t]):
                    if ex not in specific_ent:
                        specific_ent.append(ex)
        if specific_ent:
            return specific_ent
        raw = " ".join([entity] + queries[:2])
        toks = [t.lower() for t in re.findall(r"[a-zA-Z0-9_-]{3,}", raw)]
        specific = [t for t in toks if t not in stop]
        return specific or toks[:2]

    def _is_relevant(self, title: str, url: str, excerpt: str, required_tokens: list[str], category: str = "ai_agent") -> float:
        blob = f"{title} {url} {excerpt}".lower()
        if any(b in blob for b in BLOCKED_NOISE_PATTERNS):
            return 0.0
        if category == "us_stocks":
            # For financial analysis, reject narrow CV/graphics papers unrelated to datacenter/architecture/economics
            fin_terms = ("blackwell", "inference", "datacenter", "throughput", "gpu", "revenue", "capex", "cloud", "earnings", "stock", "market", "architecture", "tensorrt")
            if "arxiv.org" in url.lower() and not any(ft in blob for ft in fin_terms):
                return 0.0
        if not required_tokens:
            return 0.8
        hits = sum(1 for tok in required_tokens if tok in blob)
        if hits == 0:
            return 0.10
        return min(1.0, 0.55 + 0.25 * hits)

    def fetch_sec_edgar_financials(self, tickers: list[str]) -> list[CrawledSource]:
        """Pulls 100% official, auditable SEC 10-K / 10-Q XBRL metrics (Revenue, Gross Profit, Operating Income, OCF, CapEx)."""
        out: list[CrawledSource] = []
        for sym in tickers[:2]:
            cik_info = SEC_CIK_MAP.get(sym.upper())
            if not cik_info:
                continue
            cik, comp_name = cik_info
            try:
                r = httpx.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", headers=SEC_HEADERS, timeout=16.0)
                if r.status_code != 200:
                    continue
                us_gaap = r.json().get("facts", {}).get("us-gaap", {})

                def latest_annual_pair(tags: tuple[str, ...]) -> tuple[float | None, float | None, str]:
                    for tg in tags:
                        units = us_gaap.get(tg, {}).get("units", {}).get("USD", [])
                        annuals = [
                            u for u in units
                            if u.get("form") in ("10-K", "20-F") and u.get("fp") == "FY" and isinstance(u.get("val"), (int, float))
                        ]
                        if not annuals:
                            continue
                        # Deduplicate by fiscal end date, taking latest filed
                        by_end: dict[str, dict] = {}
                        for u in annuals:
                            end_d = str(u.get("end", ""))
                            if len(end_d) == 10:
                                start_d = str(u.get("start", ""))
                                # Keep full-year (~330..380 days) entries
                                if start_d:
                                    try:
                                        days = (dt.date.fromisoformat(end_d) - dt.date.fromisoformat(start_d)).days
                                        if not (330 <= days <= 385):
                                            continue
                                    except Exception:
                                        pass
                                by_end[end_d] = u
                        ordered = [by_end[k] for k in sorted(by_end.keys())]
                        if len(ordered) >= 2:
                            return float(ordered[-1]["val"]), float(ordered[-2]["val"]), ordered[-1]["end"]
                        if len(ordered) == 1:
                            return float(ordered[-1]["val"]), None, ordered[-1]["end"]
                    return None, None, ""

                rev_cur, rev_prev, fy_end = latest_annual_pair(("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"))
                op_cur, op_prev, _ = latest_annual_pair(("OperatingIncomeLoss",))
                ni_cur, ni_prev, _ = latest_annual_pair(("NetIncomeLoss",))
                ocf_cur, ocf_prev, _ = latest_annual_pair(("NetCashProvidedByUsedInOperatingActivities",))
                capex_cur, capex_prev, _ = latest_annual_pair(("PaymentsToAcquireProductiveAssets", "PaymentsToAcquirePropertyPlantAndEquipment"))

                if not rev_cur:
                    continue

                facts: list[str] = []
                metrics: list[str] = []
                rev_yoy = ((rev_cur - rev_prev) / abs(rev_prev) * 100.0) if rev_prev else 0.0
                facts.append(f"SEC 10-K 官方年報（截至 {fy_end}）：全年總營收 {_fmt_usd_yi(rev_cur)} 美金（年增 {rev_yoy:+.1f}%）")
                metrics.append(_fmt_usd_yi(rev_cur))
                if rev_prev:
                    metrics.append(f"{rev_yoy:+.1f}%")

                if op_cur and rev_cur:
                    op_margin = op_cur / rev_cur * 100.0
                    facts.append(f"營業利益達 {_fmt_usd_yi(op_cur)} 美金，營業利益率高達 {op_margin:.1f}%")
                    metrics.append(f"營益率 {op_margin:.1f}%")
                if ni_cur:
                    ni_yoy = ((ni_cur - ni_prev) / abs(ni_prev) * 100.0) if ni_prev else 0.0
                    facts.append(f"全年淨利 {_fmt_usd_yi(ni_cur)} 美金（年增 {ni_yoy:+.1f}%）")
                if ocf_cur:
                    facts.append(f"營運現金流（OCF）達 {_fmt_usd_yi(ocf_cur)} 美金，現金造血能力強勁")
                    metrics.append(f"OCF {_fmt_usd_yi(ocf_cur)}")
                if capex_cur:
                    capex_yoy = ((capex_cur - capex_prev) / abs(capex_prev) * 100.0) if capex_prev else 0.0
                    facts.append(f"資本支出（CapEx）為 {_fmt_usd_yi(capex_cur)} 美金（年變動 {capex_yoy:+.1f}%）")
                    metrics.append(f"CapEx {_fmt_usd_yi(capex_cur)}")

                sec_url = f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}"
                out.append(
                    CrawledSource(
                        source_id=f"sec_{sym.lower()}",
                        title=f"SEC EDGAR 10-K 官方財報：{comp_name} ({sym})",
                        url=sec_url,
                        domain="sec.gov",
                        published_date=fy_end or dt.date.today().isoformat(),
                        retrieved_at=_now_iso(),
                        source_type="sec_filing",
                        relevance_score=1.0,
                        key_facts=facts,
                        metrics=metrics[:5],
                        excerpt=" | ".join(facts),
                    )
                )
            except Exception:
                continue
        return out

    def fetch_market_quotes(self, tickers: list[str]) -> list[CrawledSource]:
        """Fetches real market price, 52-week high/low, and P/E multiple via CNBC Quote API + Yahoo Finance V8 + Stooq fallback."""
        out: list[CrawledSource] = []
        for sym in tickers[:3]:
            price, high52, low52, chg_1y, pe_val, mktcap_str, latest_date = None, None, None, 0.0, None, "", dt.date.today().isoformat()
            # 1. CNBC Institutional Real-Time Quote API (includes P/E, 52W range, Market Cap!)
            try:
                cnbc_u = (
                    f"https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
                    f"?symbols={sym.upper()}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
                )
                rc = self.client.get(cnbc_u, timeout=8.0)
                if rc.status_code == 200:
                    q_list = rc.json().get("FormattedQuoteResult", {}).get("FormattedQuote") or []
                    if q_list:
                        q = q_list[0]
                        p_raw = str(q.get("last") or "").replace(",", "").strip()
                        if p_raw:
                            price = float(p_raw)
                        hi_s = str(q.get("yrhiprice") or "").replace(",", "").strip()
                        lo_s = str(q.get("yrloprice") or "").replace(",", "").strip()
                        high52 = float(hi_s) if hi_s else price
                        low52 = float(lo_s) if lo_s else price
                        pe_s = str(q.get("pe") or "").replace(",", "").strip()
                        if pe_s and re.match(r"^\d+(\.\d+)?$", pe_s):
                            pe_val = float(pe_s)
                        mktcap_str = str(q.get("mktcapView") or "").strip()
                        cp_s = str(q.get("change_pct") or "").replace("%", "").replace("+", "").strip()
                        if cp_s and re.match(r"^-?\d+(\.\d+)?$", cp_s):
                            chg_1y = float(cp_s)
            except Exception:
                pass

            # 2. Try Yahoo Finance V8 fallback
            if not price:
                for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
                    try:
                        r = self.client.get(f"https://{host}/v8/finance/chart/{sym}?range=1y&interval=1d", timeout=8.0)
                        if r.status_code == 200:
                            res = (r.json().get("chart", {}).get("result") or [None])[0]
                            if res:
                                meta = res.get("meta", {})
                                price = float(meta.get("regularMarketPrice") or 0) or None
                                prev = float(meta.get("chartPreviousClose") or price or 1)
                                high52 = float(meta.get("fiftyTwoWeekHigh") or price or 0)
                                low52 = float(meta.get("fiftyTwoWeekLow") or price or 0)
                                if price and prev:
                                    chg_1y = (price - prev) / prev * 100.0
                                break
                    except Exception:
                        continue

            if price:
                pub_url = f"https://www.cnbc.com/quotes/{sym.upper()}"
                pe_clause = f"，本益比（P/E）約 {pe_val:.1f}x" if pe_val else ""
                mc_clause = f"，總市值 {mktcap_str}" if mktcap_str else ""
                fact = f"{sym.upper()} 公開市場股價報 ${price:,.2f} 美金，52 週高低點區間 ${low52:,.2f} – ${high52:,.2f}{pe_clause}{mc_clause}"
                m_list = [f"${price:,.2f}"]
                if pe_val:
                    m_list.append(f"PE {pe_val:.1f}x")
                if high52:
                    m_list.append(f"52W高 ${high52:,.0f}")
                out.append(
                    CrawledSource(
                        source_id=f"mkt_{sym.lower()}",
                        title=f"CNBC 公開市場報價與估值：{sym.upper()} (${price:,.2f}{f' / PE {pe_val:.1f}x' if pe_val else ''})",
                        url=pub_url,
                        domain="cnbc.com",
                        published_date=latest_date,
                        retrieved_at=_now_iso(),
                        source_type="market_data",
                        relevance_score=0.99,
                        key_facts=[fact],
                        metrics=m_list,
                        excerpt=fact,
                    )
                )
        return out

    def inspect_github_repo_direct(self, full_name: str) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            r = self.client.get(f"https://api.github.com/repos/{full_name}", headers={**HEADERS, "Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                return out
            repo = r.json()
            stars = int(repo.get("stargazers_count") or 0)
            forks = int(repo.get("forks_count") or 0)
            lang = repo.get("language") or "Python"
            desc = _clean_text(repo.get("description") or "")
            homepage = (repo.get("homepage") or "").strip()
            updated = (repo.get("pushed_at") or repo.get("updated_at") or "")[:10]
            html_url = repo.get("html_url", f"https://github.com/{full_name}")

            readme_bullets, cmds = self._fetch_github_readme(full_name)
            rel_fact = self._fetch_github_latest_release(full_name)

            facts = [f"GitHub 官方開源儲存庫 {full_name}：{stars:,} Stars、{forks:,} Forks（主要語言 {lang}）"]
            if desc:
                facts.append(f"官方定位：{desc[:150]}")
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
                    relevance_score=0.98,
                    key_facts=facts,
                    metrics=[f"{stars:,} ★", f"{forks:,} Forks", lang],
                    code_or_commands=cmds,
                    excerpt=" | ".join(facts[:4]),
                )
            )
            if homepage and homepage.startswith("http") and "github.com" not in homepage:
                hp_src = self.scrape_direct_url(homepage, label_prefix="官方網站")
                if hp_src:
                    hp_src.relevance_score = 0.97
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
                        if 30 <= len(lc) <= 140 and not lc.lower().startswith(("http", "!", "badge", "license", "<")):
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
                if tag:
                    return f"最新正式版本 {tag}（發布於 {pub}）"
        except Exception:
            pass
        return ""

    def search_github_repos(self, query: str, req_tokens: list[str], category: str, limit: int = 3) -> list[CrawledSource]:
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
                rel = self._is_relevant(full_name, html_url, desc, req_tokens, category)
                if rel < 0.55:
                    continue
                stars = int(repo.get("stargazers_count") or 0)
                forks = int(repo.get("forks_count") or 0)
                lang = repo.get("language") or "Python"
                updated = (repo.get("pushed_at") or repo.get("updated_at") or "")[:10]
                readme_bullets, cmds = self._fetch_github_readme(full_name)
                facts = [f"生態系開源專案 {full_name}（{stars:,} Stars / {forks:,} Forks）"]
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
                        relevance_score=min(0.92, rel),
                        key_facts=facts,
                        metrics=[f"{stars:,} ★", f"{forks:,} Forks", lang],
                        code_or_commands=cmds,
                        excerpt=" | ".join(facts),
                    )
                )
                if len(out) >= limit:
                    break
        except Exception:
            pass
        return out

    def search_hackernews(self, query: str, req_tokens: list[str], category: str, limit: int = 3) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story&hitsPerPage=12"
            r = self.client.get(url)
            if r.status_code != 200:
                return out
            for hit in r.json().get("hits", []):
                title = _clean_text(hit.get("title") or "")
                ext_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                created = (hit.get("created_at") or "")[:10]
                if created and created[:4].isdigit() and int(created[:4]) < 2024:
                    continue
                pts = int(hit.get("points") or 0)
                cmts = int(hit.get("num_comments") or 0)
                if pts < 25:
                    continue
                rel = self._is_relevant(title, ext_url, "", req_tokens, category)
                if rel < 0.55:
                    continue
                dom = urlparse(ext_url).netloc.replace("www.", "") or "news.ycombinator.com"
                page_facts, excerpt = self._scrape_webpage_summary(ext_url)
                facts = [f"媒體與社群焦點（{pts} Points / {cmts} 則討論）：{title}"] + page_facts[:2]
                out.append(
                    CrawledSource(
                        source_id=f"hn_{hit.get('objectID')}",
                        title=title[:85],
                        url=ext_url,
                        domain=dom,
                        published_date=created,
                        retrieved_at=_now_iso(),
                        source_type="hn_discussion",
                        relevance_score=min(0.90, rel),
                        key_facts=facts,
                        metrics=_extract_metrics(f"{title} {excerpt}")[:3] or [f"{pts} HN pts"],
                        excerpt=excerpt[:420] or title,
                    )
                )
                if len(out) >= limit:
                    break
        except Exception:
            pass
        return out

    def search_arxiv(self, query: str, req_tokens: list[str], category: str, limit: int = 2) -> list[CrawledSource]:
        out: list[CrawledSource] = []
        try:
            url = f"https://export.arxiv.org/api/query?search_query=all:{quote_plus(query)}&sortBy=relevance&order=descending&max_results=6"
            r = self.client.get(url)
            if r.status_code != 200:
                return out
            root = ET.fromstring(r.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                title = _clean_text(entry.findtext("a:title", "", ns))
                summary = _clean_text(entry.findtext("a:summary", "", ns))
                link = _clean_text(entry.findtext("a:id", "", ns))
                rel = self._is_relevant(title, link, summary, req_tokens, category)
                if rel < 0.55:
                    continue
                pub = _clean_text(entry.findtext("a:published", "", ns))[:10]
                facts = [f"arXiv 架構與實測論文（{pub}）：{title}", f"關鍵結論：{summary[:180]}"]
                out.append(
                    CrawledSource(
                        source_id=f"arxiv_{len(out)+1}",
                        title=title[:80],
                        url=link,
                        domain="arxiv.org",
                        published_date=pub,
                        retrieved_at=_now_iso(),
                        source_type="research_paper",
                        relevance_score=min(0.89, rel),
                        key_facts=facts,
                        metrics=_extract_metrics(summary)[:3] or ["arXiv 論文"],
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
                    if out_png.exists() and out_png.stat().st_size > 8000:
                        src.screenshot_path = str(out_png)
                        captured += 1
                        continue
                    try:
                        page = ctx.new_page()
                        page.goto(src.url, wait_until="domcontentloaded", timeout=11000)
                        page.wait_for_timeout(1100)
                        page.evaluate(
                            """() => {
                                for (const sel of ['[id*="cookie"]', '[class*="cookie"]', '[aria-label*="cookie"]', '[class*="consent"]']) {
                                    document.querySelectorAll(sel).forEach(el => el.style.display = 'none');
                                }
                            }"""
                        )
                        page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": 1440, "height": 900})
                        page.close()
                        if out_png.exists() and out_png.stat().st_size > 8000:
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
        category: str = "ai_agent",
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

        # 1. For US Stocks: Official SEC EDGAR 10-K XBRL + Live Market Quotes + Hyperscaler Peer CapEx!
        if tickers or category == "us_stocks":
            t_list = list(tickers or ["NVDA"])
            if "NVDA" in [x.upper() for x in t_list] and len(t_list) == 1:
                peer_sec = self.fetch_sec_edgar_financials(["MSFT", "META"])
                for ps in peer_sec:
                    ps.relevance_score = 0.94
                _add(self.fetch_sec_edgar_financials(t_list))
                _add(self.fetch_market_quotes(t_list))
                _add(peer_sec)
            else:
                _add(self.fetch_sec_edgar_financials(t_list))
                _add(self.fetch_market_quotes(t_list))

        # 2. Seed URLs
        for u in (seed_urls or []):
            if "github.com/" in u:
                m = re.search(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", u)
                if m:
                    _add(self.inspect_github_repo_direct(m.group(1)))
                    continue
            sc = self.scrape_direct_url(u)
            if sc:
                _add([sc])

        # 3. Domain-appropriate public sources
        for q in queries[:3]:
            if category != "us_stocks":
                _add(self.search_github_repos(q, req_tokens, category, limit=2))
            _add(self.search_hackernews(q, req_tokens, category, limit=2))
            _add(self.search_arxiv(q, req_tokens, category, limit=2))
            if category == "us_stocks" and len(sources) < 6:
                _add(self.search_github_repos(q, req_tokens, category, limit=1))

        sources.sort(key=lambda s: s.relevance_score, reverse=True)
        sources = sources[:8]
        for i, src in enumerate(sources, 1):
            src.source_id = f"S{i}"

        if screenshots_dir is not None and sources:
            self.capture_source_screenshots(sources, screenshots_dir, max_captures=4)

        return sources
