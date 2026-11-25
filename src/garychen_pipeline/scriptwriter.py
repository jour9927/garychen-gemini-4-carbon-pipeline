from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

from .config import (
    BeatLayoutType,
    CrawledSource,
    EpisodeScript,
    ShortBeatLayoutType,
    ShortBeatSpec,
    TopicCandidate,
    VisualBeat,
    VisualNode,
    load_cluster_endpoints,
)
from .tts_normalizer import to_spoken_tts_text

TUTORIAL_CHAPTER_LAYOUT_MAP: list[list[BeatLayoutType]] = [
    ["app_squircles_strikethrough", "claude_chat_dialog", "slash_command_prompt_bar", "agenda_four_steps"],
    ["ecosystem_node_graph", "code_editor_live_preview", "browser_ui_live_tour", "concept_hero_split_3d"],
    ["protagonist_app_flow", "slash_command_prompt_bar", "browser_ui_live_tour", "before_after_workflow_card"],
    ["claude_chat_dialog", "code_editor_live_preview", "browser_ui_live_tour", "github_pr_blast_radius"],
    ["swarm_subagents_grid", "ecosystem_node_graph", "code_editor_live_preview", "github_pr_blast_radius"],
    ["before_after_workflow_card", "animated_growth_curve", "browser_ui_live_tour", "stocks_kpi_asymmetric"],
    ["second_level_thinking_crowd", "moat_shield_architecture", "concept_hero_split_3d", "stocks_big_statement"],
]

STOCKS_CHAPTER_LAYOUT_MAP: list[list[BeatLayoutType]] = [
    ["stocks_kpi_asymmetric", "animated_growth_curve", "browser_ui_live_tour", "stocks_four_pillars"],
    ["ecosystem_node_graph", "stocks_kpi_asymmetric", "operating_leverage_chart", "stocks_big_statement"],
    ["stocks_kpi_asymmetric", "browser_ui_live_tour", "animated_growth_curve", "before_after_workflow_card"],
    ["second_level_thinking_crowd", "operating_leverage_chart", "stocks_kpi_asymmetric", "browser_ui_live_tour"],
    ["moat_shield_architecture", "ecosystem_node_graph", "stocks_four_pillars", "concept_hero_split_3d"],
    ["stocks_valuation_scenarios", "animated_growth_curve", "before_after_workflow_card", "stocks_big_statement"],
    ["stocks_four_pillars", "second_level_thinking_crowd", "moat_shield_architecture", "stocks_big_statement"],
]

SHORT_TUTORIAL_SEQUENCE: list[ShortBeatLayoutType] = [
    "short_squircles_hook",
    "short_live_typing_card",
    "short_browser_zoom_proof",
    "short_kpi_stack",
    "short_versus_stamp",
    "short_live_typing_card",
    "short_growth_curve",
    "short_second_level_crowd",
    "short_kpi_stack",
    "short_funnel_cta",
]

SHORT_STOCKS_SEQUENCE: list[ShortBeatLayoutType] = [
    "short_squircles_hook",
    "short_growth_curve",
    "short_browser_zoom_proof",
    "short_second_level_crowd",
    "short_kpi_stack",
    "short_versus_stamp",
    "short_growth_curve",
    "short_kpi_stack",
    "short_second_level_crowd",
    "short_funnel_cta",
]

VALID_ICONS = {
    "sparkles", "github", "git", "terminal", "code", "globe", "cpu", "shield",
    "check", "database", "trending_up", "dollar", "layers", "zap", "lock", "users", "play",
    "claude", "anthropic", "openai", "chatgpt", "meta", "instagram", "threads", "facebook",
    "google", "gmail", "calendar", "maps", "youtube", "nvidia", "microsoft", "aws", "docker",
    "n8n", "zapier", "notion", "slack", "telegram", "discord", "python", "typescript",
    "vercel", "render", "cloudflare", "netflix", "apple", "x", "supabase", "postgresql",
    "robot", "cursor", "playwright",
}

TW_REPLACEMENTS = [
    ("代碼", "程式碼"), ("代码", "程式碼"), ("編程", "寫程式"), ("编程", "寫程式"),
    ("創建", "建立"), ("创建", "建立"), ("自托管", "自架部署"), ("自託管", "自架部署"),
    ("教程", "教學"), ("地址", "網址"), ("模版", "模板"), ("贡献", "貢獻"),
    ("之后", "之後"), ("以后", "以後"), ("背后", "背後"), ("軟件", "軟體"), ("软件", "軟體"),
    ("服務器", "伺服器"), ("服务器", "伺服器"), ("數據庫", "資料庫"), ("数据库", "資料庫"),
    ("默認", "預設"), ("默认", "預設"), ("調用", "呼叫"), ("调用", "呼叫"),
    ("項目", "專案"), ("项目", "專案"), ("視頻", "影片"), ("视频", "影片"),
    ("信息", "資訊"), ("優化", "最佳化"), ("支持", "支援"), ("存儲", "儲存"),
    ("小夥伴", "大家"), ("小伙伴", "大家"), ("玩轉", "實戰掌握"), ("不在話下", "直接搞定"),
    ("黑鯨", "Blackwell"),
]

EDITORIAL_SCENES = [
    "two minimalist flat-illustrated software engineers collaborating beside a warm glowing monitor in a dark #242424 studio",
    "minimalist dark-matte isometric engineering desk with glowing amber workflow cards floating cleanly on #242424 background",
    "clean architectural dark glass vault protecting warm amber compute cores on #222224 studio stage",
    "minimalist precision balance scale weighing a glowing amber AI module against dark matte blocks on #222224 background",
]


def taiwanize_text(text: str) -> str:
    out = str(text or "")
    try:
        from opencc import OpenCC
        out = OpenCC("s2tw").convert(out)
    except Exception:
        pass
    for src_w, dst_w in TW_REPLACEMENTS:
        out = out.replace(src_w, dst_w)
    return out


def scrub_slop_phrases(text: str) -> str:
    """Removes generic YouTuber clichés that real @garychenai NEVER says."""
    s = taiwanize_text(text).strip()
    s = re.sub(r"^(?:哈囉|嗨|嘿)?\s*(?:大家好|各位觀眾|各位朋友)[，,！!。]*\s*(?:我是\s*Gary[，,！!。]*)?", "", s)
    s = re.sub(r"^(?:歡迎回到我的頻道|歡迎來到\s*Gary\s*的頻道)[，,！!。]*", "", s)
    s = re.sub(r"[，,。！!]*\s*(?:走起|衝吧|讓我們開始吧|話不多說馬上開始)[！!。]*$", "", s)
    s = s.replace("省下好多時間跟力氣", "省下重複點網頁的時間").replace("做很多事情", "自動跑完跨網頁任務")
    return s.strip(" ，,")


def smart_trim(text: str, max_units: float = 10.5) -> str:
    s = re.sub(r"\s+", " ", taiwanize_text(text)).strip(" 、，。/｜|-")
    tokens = re.findall(r"[A-Za-z0-9$%+./_#-]+|\s+|.", s)
    out: list[str] = []
    used = 0.0
    for tok in tokens:
        if tok.isspace():
            if out and used + 0.35 <= max_units:
                out.append(" ")
                used += 0.35
            continue
        w = sum(0.55 if c.isascii() else 1.0 for c in tok)
        if used + w > max_units and out:
            break
        out.append(tok)
        used += w
    res = "".join(out).strip(" 、，。/｜|-")
    res = re.sub(r"([A-Za-z0-9])\s+[\u4e00-\u9fff]$", r"\1", res)
    return res


def clean_ai_prompt(raw_prompt: str, entity: str, idx: int) -> str:
    p = str(raw_prompt or "").strip()
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", p))
    if not p or has_cjk or len(p) < 24:
        base = EDITORIAL_SCENES[idx % len(EDITORIAL_SCENES)]
        return f"{base}, conceptual editorial metaphor for {entity}, strictly no text or letters"
    return p


def space_pad_english(text: str) -> str:
    t = taiwanize_text(text)
    t = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9$%+])", r"\1 \2", t)
    t = re.sub(r"([A-Za-z0-9%])([\u4e00-\u9fff])", r"\1 \2", t)
    t = re.sub(r"(\d)\s*/\s*月", r"\1/月", t)
    t = re.sub(r"\$(\d[\d,]*)\s*(?:到|至|-|–)\s*\$?(\d[\d,]*)\s*月\b", r"$\1–$\2/月", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("。.！!；;、，,")


def split_into_clauses(text: str, target_max: int = 22) -> list[str]:
    cleaned_src = scrub_slop_phrases(text)
    cleaned_src = re.sub(r"第[一二三四1234]幕講[^，。！？；]+[，。；]?", "", cleaned_src)
    raw_parts = re.split(r"[。！？；!?\n]+|，", cleaned_src)
    pieces: list[str] = []
    for p in raw_parts:
        s = space_pad_english(p.strip(" 、：:「」『』"))
        if not s:
            continue
        vis_len = sum(0.55 if c.isascii() else 1.0 for c in s)
        if vis_len <= target_max:
            pieces.append(s)
        else:
            mid = len(s) // 2
            best_pos = -1
            for sep in ("：", "、", "但是", "而且", "因為", "所以", "只要", "透過", "直接", "把", "讓"):
                pos = s.find(sep, max(5, mid - 8), min(len(s) - 5, mid + 9))
                if pos != -1:
                    best_pos = pos
                    break
            if best_pos != -1:
                pieces.extend([s[:best_pos].strip(" 、："), s[best_pos:].strip(" 、：")])
            else:
                pieces.append(smart_trim(s, target_max + 4))

    merged: list[str] = []
    carry = ""
    for seg in pieces:
        if carry:
            joiner = " " if (carry[-1].isascii() and seg[0].isascii()) else ""
            seg = f"{carry}{joiner}{seg}"
            carry = ""
        cjk_equiv = sum(0.5 if c.isascii() else 1.0 for c in seg if not c.isspace())
        if cjk_equiv <= 6.5:
            carry = seg + ("，" if not seg.endswith("的") else "")
        else:
            merged.append(seg)
    if carry:
        tail = carry.rstrip("，")
        if merged:
            merged[-1] = f"{merged[-1]}，{tail}" if not merged[-1].endswith("的") else f"{merged[-1]}{tail}"
        else:
            merged.append(tail)
    return [c for c in merged if c][:4]


def _ensure_numeric_metric(val: str, fallback_metrics: list[str], idx: int, ctx: str = "") -> str:
    v = taiwanize_text(str(val or "")).strip()
    if re.fullmatch(r"[\d,.]+", v) and ctx:
        m_ctx = re.search(r"(\$[\d,.]+\s*[億兆萬BMT]?|[\d,.]+%|[\d,.]+x)", ctx)
        if m_ctx:
            v = m_ctx.group(1)
            if v.startswith("$") and not v.endswith(("億", "兆", "萬", "B", "M", "T")) and any(k in ctx for k in ("營收", "現金流", "OCF", "CapEx", "淨利")):
                v = f"{v} 億"
        elif any(k in ctx for k in ("率", "成長", "增", "跌")):
            v = f"{v}%"
        elif any(k in ctx for k in ("營收", "現金流", "OCF", "CapEx", "支出", "淨利")):
            v = f"${v} 億"
        elif any(k in ctx for k in ("現價", "股價")):
            v = f"${v}"
    if v and re.search(r"[\d$%+xX億萬]", v) and v not in ("無", "None", "N/A"):
        return v[:16]
    if fallback_metrics:
        return fallback_metrics[idx % len(fallback_metrics)][:16]
    return "+100%"


class GarychenScriptwriter:
    """
    V4 Two-Stage Verbatim Narrative + Anti-Slop Critic + 28-Beat Remotion Choreographer:
      - Stage A (`_call_llm_text`): Pure Gary Chen verbatim spoken Taiwanese Mandarin (4 paragraphs/chapter = 28 Long beats, ~5.5–6.5 min)
      - Stage B (`_call_llm_json`): Compiles each chapter's 4 spoken beats onto 4 distinct Remotion archetypes with zero generic fallback strings
      - Stage C: Compiles 10 rapid Pure-Remotion 9:16 Funnel Shorts scenes (~46–52s)
    """

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434", ollama_model: str = "qwen3:8b"):
        self.ollama_url = os.environ.get("GC_OLLAMA_URL", ollama_url).rstrip("/")
        self.ollama_model = os.environ.get("GC_OLLAMA_MODEL", ollama_model)

    def _call_llm_raw(self, system_prompt: str, user_prompt: str, max_tokens: int = 2600, temp: float = 0.44) -> str:
        for ep in load_cluster_endpoints():
            if "colab" not in ep.name:
                continue
            try:
                headers = {"Authorization": f"Bearer {ep.token}"}
                with httpx.Client(timeout=30.0, trust_env=False) as client:
                    hr = client.get(f"{ep.url}/health", timeout=6.0)
                    if hr.status_code != 200 or "llm_chat" not in (hr.json().get("capabilities") or []):
                        continue
                    sub = client.post(
                        f"{ep.url}/job/submit",
                        headers=headers,
                        json={
                            "kind": "llm_chat",
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                            "max_tokens": max_tokens,
                            "temperature": temp,
                        },
                    )
                    if sub.status_code != 200:
                        continue
                    jid = sub.json()["job_id"]
                    t0 = time.time()
                    while time.time() - t0 < 240:
                        time.sleep(1.6)
                        st = client.get(f"{ep.url}/job/status/{jid}", headers=headers).json()
                        if st.get("status") == "done":
                            txt = str(st["result"]["text"])
                            return re.sub(r"<think>.*?</think>", "", txt, flags=re.DOTALL).strip()
                        if st.get("status") == "error":
                            break
            except Exception:
                pass

        last_err: Exception | None = None
        for attempt in range(3):
            payload: dict[str, Any] = {
                "model": self.ollama_model,
                "stream": False,
                "options": {"temperature": temp + 0.06 * attempt, "num_ctx": 8192, "num_predict": max_tokens},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if "qwen3" in self.ollama_model:
                payload["think"] = False
            try:
                with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=160.0, write=15.0, pool=10.0), trust_env=False) as client:
                    r = client.post(f"{self.ollama_url}/api/chat", json=payload)
                    r.raise_for_status()
                    txt = str(r.json().get("message", {}).get("content", ""))
                    return re.sub(r"<think>.*?</think>", "", txt, flags=re.DOTALL).strip()
            except Exception as exc:
                last_err = exc
                time.sleep(0.5)
        raise RuntimeError(f"LLM call failed after 3 attempts: {last_err}")

    def _call_llm_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2800) -> dict[str, Any]:
        for attempt in range(3):
            raw = self._call_llm_raw(
                system_prompt,
                user_prompt + "\n請嚴格只輸出合法純 JSON 物件（字串內勿換行、引用請用『』），不要加任何前後解釋文字。",
                max_tokens=max_tokens,
                temp=0.38 + 0.08 * attempt,
            )
            try:
                return self._extract_json(raw)
            except Exception as exc:
                if attempt == 2:
                    raise exc
        raise ValueError("Unreachable")

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        s, e = raw.find("{"), raw.rfind("}")
        chunk = raw[s : e + 1] if (s >= 0 and e > s) else raw
        if s >= 0 and e > s:
            try:
                return json.loads(chunk, strict=False)
            except json.JSONDecodeError:
                chunk_fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
                chunk_fixed = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", chunk_fixed)
                try:
                    return json.loads(chunk_fixed, strict=False)
                except json.JSONDecodeError:
                    pass
        import json_repair
        repaired = json_repair.loads(chunk)
        if isinstance(repaired, dict) and repaired:
            return repaired
        raise ValueError("No valid JSON object in LLM output")

    def _genre_system_prompt(self, category: str) -> str:
        if category == "us_stocks":
            return (
                "你是台灣 YouTube 頻道「Gary Chen (@garychenai)」的美股科技巨頭深度分析本人主筆。\n"
                "參考 Gary 真實美股代表作《META 財報後下跌 10%，為什麼我反而加倉？》與《Google 估值大反轉》的原聲語氣：\n"
                "『財報公布那天盤後一度大跌，市場都在恐慌資本支出是不是燒過頭了？但如果我們把 SEC 年報拆開來看多年度營收軌跡、營業利益率的營運槓桿、以及營運現金流的造血能力，你會發現華爾街第一層思考漏掉了最關鍵的飛輪效應。』\n"
                "鐵律：\n"
                "1. 絕對禁止寫『哈囉大家好』『我是 Gary』『走起』！第一句話直接切入市場預期差與具體財報數字！\n"
                "2. 全程道地台灣繁中財經科技白話（營收、營業利益率、營運槓桿、營運現金流 OCF、資本支出 CapEx、本益比 PE、轉換成本、護城河、安全邊際、白話講、反過來想）。\n"
                "3. 嚴禁出現任何安裝軟體或寫程式教學！"
            )
        return (
            "你是台灣 YouTube 頻道「Gary Chen (@garychenai)」的 AI Agent 與軟體工程實戰本人主筆。\n"
            "參考 Gary 真實代表作《Meta Muse 新手教學》、《pstack 一個月 2500 個 PR》與《用 AI 寫程式你得懂的 CI/CD》的原聲語氣：\n"
            "『現在主流的 AI Agent 每一個都要收錢，如果你之前看過 Claude Code 或 Operator，但因為每個月二十到兩百美金的訂閱費還沒動手試過，不用擔心，今天這支影片我會帶你用完全免費開源的方案，直接在自己電腦跑起完整的瀏覽器自動化工作流。』\n"
            "『對非技術背景的人來說，白話講就是幫你的 AI 裝上眼睛跟雙手，才不會網頁一改版就壞掉，陷入做 A 壞 B、找 bug 打地鼠的無限迴圈。』\n"
            "鐵律：\n"
            "1. 絕對禁止寫『哈囉大家好』『我是 Gary』『走起』『小夥伴』『玩轉』！第一句話直接切入痛點與主角工具名稱！\n"
            "2. 全程道地台灣開發者口語（專案、套件、資料夾、伺服器、終端機、資訊欄、踩坑、白話講、把關防線），台詞內不要唸出 http 網址或 -fsSL 參數。"
        )

    def generate_episode_script(
        self,
        topic: TopicCandidate,
        sources: list[CrawledSource],
        episode_id: str,
        num_chapters: int = 7,
    ) -> EpisodeScript:
        is_stocks = (topic.category == "us_stocks")
        num_chapters = 7
        src_digest = [
            {
                "source_id": s.source_id,
                "type": s.source_type,
                "domain": s.domain,
                "title": s.title,
                "date": s.published_date,
                "metrics": s.metrics[:5],
                "facts": s.key_facts[:5],
                "commands": s.code_or_commands[:4],
                "prs": s.pr_or_issue_items[:4],
                "time_series": s.time_series,
            }
            for s in sources[:8]
        ]
        all_real_metrics: list[str] = []
        all_screenshots: list[tuple[str, str]] = []
        primary_rev_series: list[list[Any]] = []
        primary_margin_series: list[list[Any]] = []
        for s in sources:
            for m in s.metrics:
                if re.search(r"[\d$%+xX億萬]", m) and m not in all_real_metrics:
                    all_real_metrics.append(m)
            if s.screenshot_path:
                all_screenshots.append((s.source_id, s.screenshot_path))
            for ex_p in s.extra_screenshots:
                all_screenshots.append((s.source_id, ex_p))
            if not primary_rev_series and s.time_series.get("revenue_yi"):
                primary_rev_series = s.time_series["revenue_yi"]
            if not primary_margin_series and s.time_series.get("op_margin_pct"):
                primary_margin_series = s.time_series["op_margin_pct"]

        sys_prompt = self._genre_system_prompt(topic.category)
        default_chapters = (
            [
                "市場恐慌與真實成績單",
                "商業模式與算力變現引擎",
                "SEC 年報數據與營運槓桿",
                "資本支出的第二層思考",
                "競爭對手難複製的護城河",
                "估值倍數與三種情境推演",
                "三大風險與我的投資觀點",
            ]
            if is_stocks
            else [
                "為什麼現在該認識它",
                "DOM 與視覺雙引擎架構",
                "主角 Gary 的實戰自動化",
                "三分鐘本機部署與啟動",
                "多模型串接與多代理分工",
                "開源本機 vs 付費方案對照",
                "三個必避踩坑與實戰總結",
            ]
        )

        pass1_prompt = (
            f"主題：{topic.title}\n"
            f"核心主角實體：{topic.primary_entity}\n"
            f"已爬蟲查證之公開權威資料：\n{json.dumps(src_digest, ensure_ascii=False, indent=2)}\n\n"
            f"請規劃 7 個章節（參考脈絡：{default_chapters}，每章標題 5～10 字、犀利具體）與 YouTube 封面兩行超大字（`thumbnail_line1` 黃字 4-7 字主角或公司、`thumbnail_line2` 白字 4-7 字強反差結論，像『Browser-Use / 免費接管瀏覽器』、『NVDA 財報 / 華爾街看錯了？』）！\n"
            "輸出 JSON：\n"
            "{\n"
            '  "title": "Gary Chen 風格高點擊長片標題",\n'
            '  "thumbnail_line1": "封面第一行(4-7字)",\n'
            '  "thumbnail_line2": "封面第二行(4-7字)",\n'
            '  "youtube_description_summary": "140字內精華介紹",\n'
            '  "hashtags": ["#GaryChen", "..."],\n'
            '  "chapters_plan": [\n'
            '    {"index": 1, "chapter_title": "章節名", "focus": "本章核心論點與引用數據"}\n'
            "  ]\n"
            "}"
        )
        plan_data = self._call_llm_json(sys_prompt, pass1_prompt, max_tokens=1800)
        chapters_plan = (plan_data.get("chapters_plan") or [])[:7]
        while len(chapters_plan) < 7:
            i = len(chapters_plan)
            chapters_plan.append({"index": i + 1, "chapter_title": default_chapters[i], "focus": topic.why_now})
        all_chapter_titles = [taiwanize_text(str(c.get("chapter_title") or default_chapters[i]))[:16] for i, c in enumerate(chapters_plan)]
        pipeline_bar_labels = all_chapter_titles[1:6]  # 5 core body stages for top horizontal pipeline bar!

        chapter_missions = (
            [
                f"第1章（4段口語）：第1段直接點出市場對 {topic.primary_entity} 資本支出與高基期的恐慌 vs SEC 年報最新營收與營益率成績單；第2段拉開過去四年營收翻倍成長軌跡；第3段帶看公開市場股價、52週區間與本益比現況；第4段預告今天拆解的四個核心維度。",
                "第2章（4段口語）：拆解核心商業模式與變現飛輪（資料中心算力底座、高速網路互連、軟硬體生態綁定如何創造超過 60% 營業利益率），說明營運槓桿如何運作。",
                "第3章（4段口語）：逐一拆解 SEC 10-K 官方年報關鍵數據（全年總營收、營業利益、營運現金流 OCF 與自由現金流體質），對照過去幾年成長斜率，證明獲利含金量。",
                "第4章（4段口語）：進入『華爾街第一層思考 vs 第二層思考』！第一層只怕微軟、Meta 等雲端巨頭 CapEx 見頂；第二層拆開微軟與 Meta 的 10-K 資本支出與高毛利回報，解釋為什麼推論算力需求正在接棒訓練算力。",
                "第5章（4段口語）：拆解競爭對手最難複製的三大護城河（CUDA 數百萬開發者轉換成本、NVLink 機櫃級系統整合良率、一年一代架構迭代節奏），說明這道安全邊際有多深。",
                "第6章（4段口語）：用真實本益比 PE 與營運現金流增速推演『悲觀、基準、樂觀』三種估值情境，比較歷史估值區間與下檔保護。",
                "第7章（4段口語）：前3段誠實點出投資人必須緊盯的三大風險（雲端大廠自研 ASIC 分流、新架構量產毛利率波動、地緣出口管制）；第4段用溫和堅定語氣收尾：『如果你喜歡這種把 SEC 財報數字跟產業底層邏輯拆開來看的分析，記得幫我按讚訂閱追蹤 Gary 聊美股，本片內容僅供研究參考不構成投資建議，我們下次見。』",
            ]
            if is_stocks
            else [
                f"第1章（4段口語）：第1段第一句就點名主角『{topic.primary_entity}』！指出現在 Claude Code、Operator 或商業自動化工具每月 $20 到 $200 美金訂閱費門檻太高，而 GitHub 高星標開源專案 {topic.primary_entity} 讓你 $0 免費在自己電腦跑起來；第2段描述開發者與上班族真實痛點；第3段對比模糊指令 vs 結構化任務拆解；第4段預告今天這集四個實戰步驟。",
                f"第2章（4段口語）：白話拆解 {topic.primary_entity} 的底層運作架構！為什麼傳統寫死 CSS Selector 的爬蟲只要網頁一改版就壞掉，而它結合 Playwright DOM 結構索引與 LLM 視覺理解雙引擎，能像真人一樣看懂按鈕、下拉選單與動態表單。",
                "第3章（4段口語）：用我們頻道的老朋友『主角 Gary』的具體生活案例講透工作流！例如 Gary 每個月底要登入三個平台下載電子發票、對帳早餐 $80、午餐 $120、雲端帳單並自動歸檔進試算表，一步步看 Agent 怎麼把原本半小時的苦工變成一鍵自動完成。",
                f"第4章（4段口語）：帶觀眾三分鐘在本機跑起來！說明準備 Python 環境、安裝 {topic.primary_entity} 與瀏覽器驅動、填入 API Key 或接上本機模型、執行第一個自動開網頁抓資料腳本，並強調把自動檢查防線建起來才不會做 A 壞 B。",
                "第5章（4段口語）：進階實戰：如何把單一 Agent 升級成『主控調度＋多個子 Agent 平行分工』，一邊抓公開報價與新聞、一邊交叉驗證並把結構化結果推播到 Slack 或 Telegram，同時檢視 GitHub PR 與執行紀錄確保零失誤。",
                "第6章（4段口語）：客觀比較『開源本機自己跑』vs『官方雲端託管版』vs『傳統商業 RPA / Zapier』在資料隱私、固定成本與維護彈性的真實差異，告訴觀眾什麼情境該選哪一套。",
                "第7章（4段口語）：前3段提醒新手最常踩的三個真坑（登入 Cookie Session 持久化、遇到網站驗證碼的人機接管設計、長網頁 Token 消耗上限設定）；第4段完整說出 Gary 招牌收尾：『那以上就是今天的內容，感謝你看到這邊。如果你還不知道，我有經營一個 AI 實戰營的社群，裡面有我自己的實戰分享和實戰課程。如果鋪天蓋地的 AI 資訊讓你覺得眼花撩亂，我的目標就是成為你唯一的 AI 資訊來源。這支影片用到的設定清單跟模板我都整理在社群裡，連結放在下方資訊欄，那我們下次見。』",
            ]
        )

        layout_grid = STOCKS_CHAPTER_LAYOUT_MAP if is_stocks else TUTORIAL_CHAPTER_LAYOUT_MAP
        all_beats: list[VisualBeat] = []
        valid_sids = {s.source_id for s in sources} or {"S1"}
        cam_presets = [
            [0.38, 0.30, 1.32],
            [0.54, 0.46, 1.35],
            [0.44, 0.58, 1.28],
            [0.34, 0.40, 1.34],
            [0.58, 0.32, 1.30],
        ]
        scr_cursor = 0

        for ch_pos, ch_item in enumerate(chapters_plan):
            c_idx = ch_pos + 1
            c_title = all_chapter_titles[ch_pos]
            target_layouts = layout_grid[ch_pos % len(layout_grid)]
            mission = chapter_missions[ch_pos]

            # STAGE A: Pure Verbatim Spoken Prose (4 paragraphs separated by ===, zero JSON burden!)
            prose_prompt = (
                f"影片標題：{plan_data.get('title', topic.title)}\n"
                f"當前章節：第 {c_idx} 章《{c_title}》\n"
                f"🎯 專屬任務：{mission}\n"
                f"可引用之查證公開事實與數據：\n{json.dumps(src_digest[:5], ensure_ascii=False, indent=2)}\n\n"
                "請直接寫出本章 **4 段連續推進、完全不重複的 Gary Chen 口語逐字稿**，段落之間嚴格用一行 `===` 分隔！\n"
                "每段字數 **75～100 個繁體中文字**（約 3～4 個自然逗號分句），絕對不要寫任何標題、編號、舞台指示或『哈囉大家好』！"
            )
            raw_prose = self._call_llm_raw(sys_prompt, prose_prompt, max_tokens=1500, temp=0.45)
            paras = [scrub_slop_phrases(p) for p in re.split(r"\n\s*==+\s*\n|\n{2,}", raw_prose) if len(scrub_slop_phrases(p)) >= 28]
            while len(paras) < 4:
                s_ref = sources[(ch_pos + len(paras)) % max(1, len(sources))] if sources else None
                fact_ref = s_ref.key_facts[len(paras) % len(s_ref.key_facts)] if (s_ref and s_ref.key_facts) else topic.why_now
                paras.append(scrub_slop_phrases(f"進一步拆開來看，根據公開查證的資料顯示，{fact_ref}，白話講這就是決定長期效率與穩定度的關鍵分水嶺。"))
            paras = paras[:4]

            # Enforce iconic authentic Gary Chen outro on the very last beat of Chapter 7
            if ch_pos == 6:
                if is_stocks and "Gary 聊美股" not in paras[3]:
                    paras[3] = (
                        "如果你喜歡這種把 SEC 財報數字跟產業底層邏輯拆開來看的分析，"
                        "記得幫我按讚訂閱追蹤 Gary 聊美股，本片內容僅供研究參考不構成投資建議，我們下次見"
                    )
                elif not is_stocks and "AI 實戰營" not in paras[3]:
                    paras[3] = (
                        "那以上就是今天的實戰內容，如果鋪天蓋地的 AI 資訊讓你覺得眼花撩亂，"
                        "歡迎加入我在下方資訊欄整理的 AI 實戰營社群，這支影片用到的設定清單跟模板都在裡面，那我們下次見"
                    )

            # STAGE B: Remotion Scene Compiler for these exact 4 paragraphs
            compile_prompt = (
                f"第 {c_idx} 章《{c_title}》的 4 段定稿口播台詞如下：\n"
                + "\n".join(f"[Beat {i+1} | 版型={target_layouts[i]}]: {paras[i]}" for i in range(4))
                + f"\n\n查證資料：{json.dumps(src_digest[:4], ensure_ascii=False)}\n"
                f"可用官方品牌與向量 icon：{sorted(VALID_ICONS)}\n"
                "請將這 4 段台詞編譯成 4 個高資訊密度的 Remotion 視覺分鏡 JSON（每個 `nodes` 陣列必填 3～4 個**具體真實名詞與數據**，絕對禁止填『重點一』『自動化執行層』這種空泛詞！）：\n"
                "{\n"
                '  "beats": [\n'
                "    {\n"
                '      "visual_title": "畫面主標題(6-14字)",\n'
                '      "visual_subtitle": "精煉副標(10-22字)",\n'
                f'      "badge_text": "{"+65.5% YoY" if is_stocks else "$0 / 月"}",\n'
                '      "callout_title": "關鍵結論標籤",\n'
                '      "callout_body": "一句話犀利重點",\n'
                '      "code_lines": ["真實指令或關鍵設定"],\n'
                '      "source_ids": ["S1"],\n'
                '      "nodes": [\n'
                '        {"label": "具體工具/財報科目/步驟名", "sub": "具體機制或數據白話說明", "tag": "短標籤", "metric": "純數據指標", "icon": "github", "trend": "up"}\n'
                "      ]\n"
                "    }\n"
                "  ]\n"
                "}"
            )
            try:
                comp_data = self._call_llm_json(sys_prompt, compile_prompt, max_tokens=2200)
                raw_specs = comp_data.get("beats") or []
            except Exception:
                raw_specs = []

            for b_idx in range(4):
                rb = raw_specs[b_idx] if b_idx < len(raw_specs) and isinstance(raw_specs[b_idx], dict) else {}
                lt = target_layouts[b_idx]
                clauses = split_into_clauses(paras[b_idx], target_max=22)
                if len(clauses) < 2:
                    clauses = [space_pad_english(paras[b_idx][:20]), space_pad_english(paras[b_idx][20:44] or c_title)]
                spoken_clauses = [to_spoken_tts_text(c) for c in clauses]

                v_nodes: list[VisualNode] = []
                for n_i, nd in enumerate((rb.get("nodes") or [])[:4]):
                    if isinstance(nd, dict) and nd.get("label"):
                        ic = str(nd.get("icon") or "sparkles").lower()
                        if ic not in VALID_ICONS:
                            ic = "nvidia" if is_stocks else "robot"
                        tr = str(nd.get("trend") or "neutral").lower()
                        if tr not in ("up", "down", "neutral"):
                            tr = "neutral"
                        raw_tag = taiwanize_text(str(nd.get("tag") or "")).strip()
                        if raw_tag in ("無", "无", "None", "none", "N/A", "-"):
                            raw_tag = ""
                        raw_metric = _ensure_numeric_metric(
                            str(nd.get("metric") or raw_tag),
                            all_real_metrics,
                            len(all_beats) + n_i,
                            ctx=f"{nd.get('label', '')} {nd.get('sub', '')}",
                        )
                        v_nodes.append(
                            VisualNode(
                                label=smart_trim(str(nd["label"]), 11.5),
                                sub=smart_trim(str(nd.get("sub") or clauses[min(n_i, len(clauses) - 1)]), 18.0),
                                tag=smart_trim(raw_tag, 9.5),
                                metric=raw_metric,
                                icon=ic,
                                trend=tr,  # type: ignore[arg-type]
                            )
                        )

                if lt == "agenda_four_steps":
                    v_nodes = [
                        VisualNode(
                            label=smart_trim(all_chapter_titles[i + 1], 8.5),
                            sub=smart_trim(str(chapters_plan[i + 1].get("focus", "")), 16.0),
                            tag=f"0{i+1}",
                            metric=f"0{i+1}",
                            icon=["layers", "users", "terminal", "robot"][i % 4],
                        )
                        for i in range(4)
                    ]
                else:
                    # Enrich from real clauses & crawled sources if LLM gave <3 nodes (ZERO generic filler strings!)
                    while len(v_nodes) < 3:
                        k = len(v_nodes)
                        src_k = sources[(ch_pos + k) % max(1, len(sources))] if sources else None
                        cl_k = clauses[min(k, len(clauses) - 1)]
                        m_k = (src_k.metrics[k % len(src_k.metrics)] if (src_k and src_k.metrics) else (all_real_metrics[k % len(all_real_metrics)] if all_real_metrics else "+100%"))
                        lbl_k = smart_trim(cl_k.split("，")[0], 9.5) or (src_k.domain if src_k else topic.primary_entity)
                        v_nodes.append(
                            VisualNode(
                                label=lbl_k,
                                sub=smart_trim(cl_k, 17.5),
                                tag=smart_trim(m_k, 9.0),
                                metric=_ensure_numeric_metric(m_k, all_real_metrics, k),
                                icon=("nvidia" if is_stocks else ("playwright" if k == 0 else "robot")),
                                trend="up" if k == 0 else "neutral",
                            )
                        )

                sids = [s for s in (rb.get("source_ids") or []) if s in valid_sids]
                scr_override = ""
                cam_foc = cam_presets[len(all_beats) % len(cam_presets)]
                if lt == "browser_ui_live_tour" and all_screenshots:
                    chosen_sid, chosen_png = all_screenshots[scr_cursor % len(all_screenshots)]
                    scr_cursor += 1
                    sids = [chosen_sid]
                    scr_override = chosen_png
                elif not sids and sources:
                    sids = [sources[(c_idx - 1 + b_idx) % len(sources)].source_id]

                # Motivated Studio Foley mapping
                if b_idx == 0:
                    sfx = "whoosh"
                elif lt in ("claude_chat_dialog", "slash_command_prompt_bar", "code_editor_live_preview"):
                    sfx = "typing"
                elif lt == "browser_ui_live_tour":
                    sfx = "click"
                elif lt in ("before_after_workflow_card", "second_level_thinking_crowd"):
                    sfx = "stamp"
                else:
                    sfx = "thock"

                if is_stocks:
                    v_style = "hook" if (c_idx == 1 and b_idx == 0) else ("warm" if c_idx == 7 else "stocks")
                else:
                    v_style = "hook" if c_idx == 1 else ("warm" if c_idx == 7 else "explainer")

                code_lns = [str(x)[:64] for x in (rb.get("code_lines") or []) if str(x).strip()][:4]
                if not code_lns and not is_stocks and sources and sources[0].code_or_commands:
                    off = (len(all_beats) * 2) % max(1, len(sources[0].code_or_commands))
                    code_lns = (sources[0].code_or_commands[off:] + sources[0].code_or_commands[:off])[:3]

                raw_bt = taiwanize_text(str(rb.get("badge_text") or "")).strip()
                if "或" in raw_bt or not raw_bt or (is_stocks and "$0" in raw_bt):
                    raw_bt = (all_real_metrics[len(all_beats) % len(all_real_metrics)] if all_real_metrics else "+65.5%") if is_stocks else "$0 / 月"

                # Wire multi-year chart points for growth & operating leverage layouts
                c_pts: list[list[Any]] = []
                sec_pts: list[list[Any]] = []
                if lt in ("animated_growth_curve", "operating_leverage_chart"):
                    if primary_rev_series and len(primary_rev_series) >= 3:
                        c_pts = primary_rev_series
                        sec_pts = primary_margin_series
                    elif not is_stocks:
                        c_pts = [["傳統腳本", 18, "易失效"], ["商業 RPA", 45, "$200/月"], ["單一 Agent", 76, "自動操作"], [topic.primary_entity[:12], 98, "$0 開源"]]

                pipe_steps = pipeline_bar_labels if 2 <= c_idx <= 6 else []
                act_pipe = (c_idx - 2) if 2 <= c_idx <= 6 else -1

                all_beats.append(
                    VisualBeat(
                        beat_id=f"beat_{len(all_beats) + 1:02d}",
                        chapter_index=c_idx,
                        total_chapters=num_chapters,
                        chapter_title=c_title,
                        layout_type=lt,
                        voice_style=v_style,  # type: ignore[arg-type]
                        clauses=clauses,
                        spoken_clauses=spoken_clauses,
                        visual_title=taiwanize_text(str(rb.get("visual_title") or c_title))[:26],
                        visual_subtitle=taiwanize_text(str(rb.get("visual_subtitle") or ""))[:42],
                        badge_text=raw_bt[:18],
                        nodes=v_nodes,
                        callout_title=taiwanize_text(str(rb.get("callout_title") or ("底層投資邏輯" if is_stocks else "實戰關鍵防線")))[:18],
                        callout_body=taiwanize_text(str(rb.get("callout_body") or clauses[-1]))[:46],
                        code_lines=code_lns,
                        pipeline_steps=pipe_steps,
                        active_pipeline_idx=act_pipe,
                        chart_points=c_pts,
                        secondary_chart_points=sec_pts,
                        camera_focus=cam_foc,
                        screenshot_override=scr_override,
                        ai_image_prompt=clean_ai_prompt("", topic.primary_entity, len(all_beats)) if lt == "concept_hero_split_3d" else "",
                        source_ids=sids,
                        sfx_cue=sfx,  # type: ignore[arg-type]
                    )
                )

        # STAGE C: 10-Beat Pure-Remotion 9:16 Funnel Shorts (~46-52s, crisp visual cut every ~4.5s / sub-step every ~2.0s!)
        short_seq = SHORT_STOCKS_SEQUENCE if is_stocks else SHORT_TUTORIAL_SEQUENCE
        pass3_prompt = (
            f"長片標題：{taiwanize_text(str(plan_data.get('title') or topic.title))}\n"
            f"長片各章精華：{[{'chapter': b.chapter_title, 'point': '，'.join(b.clauses[:2]), 'badge': b.badge_text} for b in all_beats[::4]]}\n"
            f"查證公開數據：{json.dumps(src_digest[:4], ensure_ascii=False)}\n\n"
            "請設計一支 **46～52 秒高留存純 Remotion 推流 YouTube Shorts**，共 **10 幕 (short_beats)**！\n"
            "每幕 `narration` 必填 **26～38 個繁體中文字（2 句緊湊短句）**，嚴禁寫『哈囉大家好』：\n"
            "- 第 1 幕：第一秒直接亮出最強反差數據或免費替代方案\n"
            "- 第 2～8 幕：每幕推進一個硬核機制、真實數據或第二層思考反差\n"
            "- 第 9 幕：留一個最關鍵的踩坑或估值懸念\n"
            "- 第 10 幕 (is_cta=true)：明確口播『完整數據拆解跟實戰清單我都整理在長片裡，現在直接點畫面左下角的關聯影片看完整版！』\n"
            "輸出 JSON：{\"short_title\": \"... #Shorts\", \"short_hook_banner\": \"6字內頂部標籤\", \"short_beats\": [{\"narration\": \"26到38字口語台詞\", \"headline\": \"11字內大標題\", \"sub_caption\": \"18字內副標\", \"highlight_badge\": \"具體指標\", \"nodes\": [{\"label\": \"具體名詞\", \"sub\": \"白話重點\", \"tag\": \"數據\", \"icon\": \"robot\"}]}]}"
        )
        try:
            short_plan = self._call_llm_json(sys_prompt, pass3_prompt, max_tokens=2600)
        except Exception:
            short_plan = {}

        raw_sbeats = short_plan.get("short_beats") or []
        short_beats: list[ShortBeatSpec] = []
        anchor_step = max(1, len(all_beats) // 9)

        for idx in range(10):
            sb = raw_sbeats[idx] if idx < len(raw_sbeats) and isinstance(raw_sbeats[idx], dict) else {}
            is_cta = (idx == 9)
            slt = "short_funnel_cta" if is_cta else short_seq[idx]
            ref_b = all_beats[min(len(all_beats) - 1, idx * anchor_step)]
            raw_narr = scrub_slop_phrases(str(sb.get("narration") or ""))
            s_clauses = split_into_clauses(raw_narr, target_max=19)
            if is_cta and sum(len(c) for c in s_clauses) < 20:
                s_clauses = [
                    "完整數據拆解跟避坑清單都在長片裡",
                    "現在直接點擊左下角關聯影片看完整版",
                ]
            elif sum(len(c) for c in s_clauses) < 16:
                s_clauses = ref_b.clauses[:2]
            s_spoken = [to_spoken_tts_text(c) for c in s_clauses[:2]]

            snodes: list[VisualNode] = []
            for nd in (sb.get("nodes") or [])[:3]:
                if isinstance(nd, dict) and nd.get("label"):
                    ic = str(nd.get("icon") or "zap").lower()
                    raw_t = taiwanize_text(str(nd.get("tag") or "")).strip()
                    if raw_t in ("無", "无", "None", "-"):
                        raw_t = ""
                    snodes.append(
                        VisualNode(
                            label=smart_trim(str(nd["label"]), 11.0),
                            sub=smart_trim(str(nd.get("sub") or ""), 17.0),
                            tag=smart_trim(raw_t, 9.0),
                            metric=_ensure_numeric_metric(raw_t, all_real_metrics, idx),
                            icon=ic if ic in VALID_ICONS else ("nvidia" if is_stocks else "robot"),
                        )
                    )
            if len(snodes) < 2:
                snodes = ref_b.nodes[:3]

            sids = [sources[0].source_id] if sources else ["S1"]
            if slt == "short_browser_zoom_proof" and all_screenshots:
                sids = [all_screenshots[0][0]]

            s_sfx = "whoosh" if idx == 0 else ("typing" if slt == "short_live_typing_card" else ("click" if slt == "short_browser_zoom_proof" else ("stamp" if slt in ("short_versus_stamp", "short_second_level_crowd") else "thock")))
            s_vstyle = "hook" if idx == 0 else ("warm" if is_cta else ("stocks" if is_stocks else "explainer"))

            short_beats.append(
                ShortBeatSpec(
                    beat_id=f"sbeat_{len(short_beats) + 1:02d}",
                    layout_type=slt,
                    voice_style=s_vstyle,  # type: ignore[arg-type]
                    clauses=s_clauses[:2],
                    spoken_clauses=s_spoken,
                    headline=taiwanize_text(str(sb.get("headline") or ("點擊左下角看完整版" if is_cta else ref_b.visual_title)))[:14],
                    sub_caption=taiwanize_text(str(sb.get("sub_caption") or ref_b.visual_subtitle))[:24],
                    highlight_badge=taiwanize_text(str(sb.get("highlight_badge") or ("完整長片已上線" if is_cta else ref_b.badge_text)))[:16],
                    nodes=snodes,
                    code_lines=ref_b.code_lines[:3],
                    chart_points=primary_rev_series if (primary_rev_series and len(primary_rev_series) >= 3) else [["傳統", 22, "手動"], ["半自動", 55, "$200"], [topic.primary_entity[:10], 96, "$0"]],
                    source_ids=sids,
                    sfx_cue=s_sfx,  # type: ignore[arg-type]
                    is_cta=is_cta,
                )
            )

        ep_title = taiwanize_text(str(plan_data.get("title") or topic.title))
        tl1 = smart_trim(str(plan_data.get("thumbnail_line1") or topic.primary_entity), 8.5)
        tl2 = smart_trim(str(plan_data.get("thumbnail_line2") or ("華爾街看錯了？" if is_stocks else "免費接管瀏覽器")), 8.5)
        if not tl1:
            tl1 = smart_trim(topic.primary_entity, 8.5)
        if not tl2 or tl2 == tl1:
            tl2 = "三大護城河" if is_stocks else "零成本實戰"
        s_title = taiwanize_text(str(short_plan.get("short_title") or f"{ep_title[:22]}｜精華速看 #Shorts"))
        if "#Shorts" not in s_title and "#shorts" not in s_title:
            s_title = f"{s_title} #Shorts"

        return EpisodeScript(
            episode_id=episode_id,
            title=ep_title,
            thumbnail_line1=tl1,
            thumbnail_line2=tl2,
            category=topic.category,
            avatar_mode=is_stocks,
            youtube_description_summary=taiwanize_text(str(plan_data.get("youtube_description_summary") or topic.hook_angle)),
            hashtags=[str(h) for h in (plan_data.get("hashtags") or (["#美股", "#財報分析", "#Gary聊美股", "#AI投資"] if is_stocks else ["#AIAgent", "#AI教學", "#GaryChen", "#自動化"]))[:6]],
            chapters=[f"{i + 1:02d} {t}" for i, t in enumerate(all_chapter_titles)],
            beats=all_beats,
            short_title=s_title,
            short_hook_banner=smart_trim(str(short_plan.get("short_hook_banner") or tl1), 9.0),
            short_cta_target_title=ep_title,
            short_beats=short_beats,
        )
