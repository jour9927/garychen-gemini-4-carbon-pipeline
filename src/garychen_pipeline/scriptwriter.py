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

TUTORIAL_LAYOUTS: list[BeatLayoutType] = [
    "app_squircles_strikethrough",
    "claude_chat_dialog",
    "agenda_four_steps",
    "ecosystem_node_graph",
    "protagonist_app_flow",
    "browser_ui_live_tour",
    "concept_hero_split_3d",
    "feature_pill_matrix",
    "github_pr_checks_card",
    "before_after_workflow_card",
]

STOCKS_LAYOUTS: list[BeatLayoutType] = [
    "stocks_kpi_asymmetric",
    "stocks_big_statement",
    "stocks_four_pillars",
    "browser_ui_live_tour",
    "ecosystem_node_graph",
    "concept_hero_split_3d",
    "before_after_workflow_card",
    "stocks_valuation_scenarios",
]

SHORT_LAYOUTS: list[ShortBeatLayoutType] = [
    "short_shock_metric_hero",
    "short_progressive_flow",
    "short_live_source_proof",
    "short_before_after_versus",
    "short_code_or_steps",
    "short_funnel_cta",
]

VALID_ICONS = {
    "sparkles", "github", "terminal", "code", "globe", "cpu", "shield",
    "check", "database", "trending_up", "dollar", "layers", "zap", "lock", "users", "play",
    "claude", "openai", "meta", "google", "nvidia", "aws", "docker", "n8n", "zapier", "notion", "slack", "gmail",
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
    ("代理", "Agent"), ("黑鯨", "Blackwell"),
]

DIORAMA_SCENES = [
    "minimalist 3D dark studio conveyor belt carrying glowing amber and cyan data cubes through an orange scanner gate on #262626 charcoal stage",
    "tactile 3D matte gunmetal modular nodes connected by warm glowing #EB8B1B fiber-optic bridges, isometric product render on #262626 background",
    "sleek 3D architectural glass shield vault guarding glowing golden compute cores on dark charcoal #222224 surface, soft rim lighting",
    "minimalist 3D precision balance scale weighing a compact glowing amber AI core against heavy dark iron blocks on #222224 stage",
    "isometric 3D flywheel turbine with glowing orange energy rings accelerating on matte black #1E1E1E pedestal, Cinema4D Octane studio lighting",
    "clean 3D server cluster rack with warm amber telemetry light bars floating on #222224 dark matte background",
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


def smart_trim(text: str, max_units: float = 9.5) -> str:
    """Word-safe visual trimmer: CJK=1.0 unit, ASCII=0.55 unit; NEVER cuts inside an English word or number!"""
    s = re.sub(r"\s+", " ", taiwanize_text(text)).strip(" 、，。/｜|-")
    tokens = re.findall(r"[A-Za-z0-9$%+./_-]+|\s+|.", s)
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
    # Avoid dangling single-char CJK suffix after a space like "瀏覽器 AI Agent 教"
    res = re.sub(r"([A-Za-z0-9])\s+[\u4e00-\u9fff]$", r"\1", res)
    return res


def clean_ai_prompt(raw_prompt: str, entity: str, idx: int) -> str:
    p = str(raw_prompt or "").strip()
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", p))
    lower_p = p.lower()
    is_placeholder = any(k in lower_p for k in ("concrete english", "metaphor prompt", "english 3d dark matte", "placeholder"))
    if not p or has_cjk or is_placeholder or len(p) < 26:
        base = DIORAMA_SCENES[idx % len(DIORAMA_SCENES)]
        return f"{base}, clean conceptual metaphor for {entity}, strictly no text or letters"
    return p


def space_pad_english(text: str) -> str:
    t = taiwanize_text(text)
    t = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9$%+])", r"\1 \2", t)
    t = re.sub(r"([A-Za-z0-9%])([\u4e00-\u9fff])", r"\1 \2", t)
    # Keep `/月` glued cleanly (`$200 / 月` -> `$200/月`)
    t = re.sub(r"(\d)\s*/\s*月", r"\1/月", t)
    t = re.sub(r"\$(\d[\d,]*)\s*(?:到|至|-|–)\s*\$?(\d[\d,]*)\s*月\b", r"$\1–$\2/月", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("。.！!；;、，,")


def split_into_clauses(text: str, target_max: int = 22) -> list[str]:
    cleaned_src = taiwanize_text(text)
    # Remove any accidental meta-stage narration if a model echoed prompt structure
    cleaned_src = re.sub(r"第[一二三123]幕講[^，。！？；]+[，。；]?", "", cleaned_src)
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


def _char_bigrams(s: str) -> set[str]:
    clean = re.sub(r"\s+", "", s)
    return {clean[i : i + 2] for i in range(len(clean) - 1)} if len(clean) >= 2 else {clean}


def _is_too_similar(cand: str, seen_list: list[str], thresh: float = 0.68) -> bool:
    bg_c = _char_bigrams(cand)
    if not bg_c:
        return False
    for prev in seen_list:
        bg_p = _char_bigrams(prev)
        if bg_p and len(bg_c & bg_p) / max(1, min(len(bg_c), len(bg_p))) >= thresh:
            return True
    return False


def _ensure_numeric_metric(val: str, fallback_metrics: list[str], idx: int) -> str:
    v = taiwanize_text(str(val or "")).strip()
    if v and re.search(r"[\d$%+xX億萬]", v) and v not in ("無", "None", "N/A"):
        return v[:16]
    if fallback_metrics:
        return fallback_metrics[idx % len(fallback_metrics)][:16]
    return "+100%"


class GarychenScriptwriter:
    """
    V3 Studio Multi-Genre Director powered by Qwen2.5-32B-Instruct on RTX PRO 6000 (96GB Blackwell).
    Strictly separates:
      - Tutorial / AI Agent / Vibe Coding architecture (7 chapters × 3-4 beats, protagonist Gary case study, AI 實戰營 outro)
      - US Stocks Deep-Dive architecture (7 chapters × 3-4 beats, SEC 10-K KPIs, 1st vs 2nd level thinking, 3 moats, PE/DCF valuation, Gary 聊美股 disclaimer outro)
    """

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434", ollama_model: str = "qwen3:8b"):
        self.ollama_url = os.environ.get("GC_OLLAMA_URL", ollama_url).rstrip("/")
        self.ollama_model = os.environ.get("GC_OLLAMA_MODEL", ollama_model)

    def _call_llm_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 3200) -> dict[str, Any]:
        for ep in load_cluster_endpoints():
            if "colab" not in ep.name:
                continue
            try:
                headers = {"Authorization": f"Bearer {ep.token}"}
                with httpx.Client(timeout=30.0) as client:
                    hr = client.get(f"{ep.url}/health", timeout=6.0)
                    if hr.status_code != 200 or "llm_chat" not in (hr.json().get("capabilities") or []):
                        continue
                    sub = client.post(
                        f"{ep.url}/job/submit",
                        headers=headers,
                        json={
                            "kind": "llm_chat",
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt + "\n請嚴格只輸出合法 JSON 物件，不要加任何前後解釋文字。",
                            "max_tokens": max_tokens,
                            "temperature": 0.45,
                        },
                    )
                    if sub.status_code != 200:
                        continue
                    jid = sub.json()["job_id"]
                    t0 = time.time()
                    while time.time() - t0 < 260:
                        time.sleep(1.8)
                        sr = client.get(f"{ep.url}/job/status/{jid}", headers=headers)
                        st = sr.json()
                        if st.get("status") == "done":
                            return self._extract_json(st["result"]["text"])
                        if st.get("status") == "error":
                            break
            except Exception:
                pass

        last_err: Exception | None = None
        for attempt in range(3):
            payload_json: dict[str, Any] = {
                "model": self.ollama_model,
                "stream": False,
                "options": {"temperature": 0.42 + 0.08 * attempt, "num_ctx": 6144, "num_predict": max_tokens},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt + "\n請只輸出合法純 JSON 物件（字串內請勿換行），不要加任何解釋。"},
                ],
            }
            if "qwen3" in self.ollama_model:
                payload_json["think"] = False
            try:
                t_call = time.time()
                with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=150.0, write=15.0, pool=10.0)) as client:
                    r = client.post(f"{self.ollama_url}/api/chat", json=payload_json)
                    r.raise_for_status()
                    parsed = self._extract_json(r.json().get("message", {}).get("content", "{}"))
                    print(f"  [scriptwriter] LLM pass ok ({time.time() - t_call:.1f}s)", flush=True)
                    return parsed
            except Exception as exc:
                print(f"  [scriptwriter] Retry {attempt + 1}/3 after {exc}", flush=True)
                last_err = exc
                time.sleep(0.5)
        raise RuntimeError(f"LLM JSON extraction failed after 3 attempts: {last_err}")

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
        try:
            import json_repair
            repaired = json_repair.loads(chunk)
            if isinstance(repaired, dict) and repaired:
                return repaired
        except Exception:
            pass
        raise ValueError("No valid JSON object in LLM output")

    def _genre_system_prompt(self, category: str) -> str:
        if category == "us_stocks":
            return (
                "你是 YouTube 頻道「Gary Chen (@garychenai)」的美股科技巨頭深度分析主筆與 Remotion 視覺導演。\n"
                "以下是 Gary 本人在真實美股影片《META 財報後下跌 10%，為什麼我反而加倉？》與《Amazon 財報分析》的原汁原味講話方式：\n"
                "『財報公布那天盤後一度大跌，市場都在恐慌資本支出是不是燒過頭了？但如果我們把財報拆開來看營運現金流跟高利潤業務的增速，你會發現華爾街的第一層思考漏掉了最關鍵的飛輪效應。』\n"
                "嚴格遵守以下鐵律：\n"
                "1. 這是【美股商業模式、SEC 官方財報數字、CapEx 第二層思考、三大護城河與估值推算】深度分析片！絕對禁止出現『怎麼安裝』、『下載安裝程式』、『開資料夾』這種軟體教學內容！\n"
                "2. 全程使用自然道地的台灣繁體中文財經與科技口語（營收、毛利率、營業利益率、營運現金流、自由現金流、資本支出 CapEx、本益比 PE、護城河、加倉、華爾街、飛輪效應、白話講、反過來想）。\n"
                "3. 台詞內不能直接唸網址或程式碼，但要把 SEC 10-K 財報與市場報價的真實數字自然講進推理邏輯裡，拒絕小學生式的空洞廢話（嚴禁寫『因為很多人用所以很好』）！"
            )
        return (
            "你是 YouTube 頻道「Gary Chen (@garychenai)」的 AI Agent 與軟體工程教學本人編劇與 Remotion 視覺導演。\n"
            "以下是 Gary 本人在真實爆款片《Meta Muse 新手教學》與《用 AI 寫程式你得懂的 CI/CD》的原汁原味講話方式：\n"
            "『現在的 AI Agent 每一個都要錢，如果你之前看我介紹過 Claude Code 還有 Codex，但因為每個月幾十塊甚至上百塊美金的訂閱費到現在都還沒動手試過的話，不用擔心，今天這支影片我會讓你不花任何一毛錢，直接在自己電腦跑起完整的自動化工作流。』\n"
            "『要搞懂這件事，一樣是我們的主角 Gary，他之前開發了一款記帳軟體，早餐 80、午餐 120、捷運 35，學會把程式碼推上 GitHub... 白話講就是把原本最繁瑣的手動流程全部變成自動化，才不會做 A 壞 B，陷入找 bug 打地鼠的無限迴圈。』\n"
            "嚴格遵守以下鐵律：\n"
            "1. 全程使用自然道地的台灣繁體中文口語（專案、套件、資料夾、伺服器、終端機、資訊欄、踩坑、白話講、反過來想），絕不使用中國用語（代碼、創建、自托管、教程、軟件）。\n"
            "2. 拒絕空洞小學生廢話（嚴禁寫『它有很多星星表示很多人用』）！每一幕都必須講出具體痛點、具體運作機制、主角 Gary 的真實應用情境（如自動整理發票記帳、Gmail 摘要推播到 Slack/Telegram、GitHub PR 自動把關），台詞裡不要生硬唸出 http 網址或 -fsSL 參數（指令顯示在畫面上，口語自然說『在終端機貼上官方這一行指令』）。"
        )

    def generate_episode_script(
        self,
        topic: TopicCandidate,
        sources: list[CrawledSource],
        episode_id: str,
        num_chapters: int = 7,
    ) -> EpisodeScript:
        is_stocks = (topic.category == "us_stocks")
        num_chapters = max(6, num_chapters)
        src_digest = [
            {
                "source_id": s.source_id,
                "type": s.source_type,
                "domain": s.domain,
                "title": s.title,
                "date": s.published_date,
                "metrics": s.metrics[:5],
                "facts": s.key_facts[:4],
                "commands": s.code_or_commands[:2],
                "has_screenshot": bool(s.screenshot_path),
            }
            for s in sources[:8]
        ]
        all_real_metrics: list[str] = []
        for s in sources:
            for m in s.metrics:
                if re.search(r"[\d$%+xX億萬]", m) and m not in all_real_metrics:
                    all_real_metrics.append(m)

        sys_prompt = self._genre_system_prompt(topic.category)

        default_chapters = (
            [
                "開場｜市場恐慌與預期差",
                "商業模式與營收引擎拆解",
                "官方財報關鍵數據與現金流",
                "拆解資本支出：第二層思考",
                "AI 時代的三大核心護城河",
                "估值推算與三種情境",
                "真實風險提示與我的觀點",
            ]
            if is_stocks
            else [
                "為什麼現在該認識它",
                "底層架構白話拆解",
                "主角 Gary 的實戰情境",
                "從零部署與介面導覽",
                "串接 AI 與工具鏈實戰",
                "跟主流付費方案差在哪",
                "踩坑提醒與我的搭配法",
            ]
        )

        pass1_prompt = (
            f"主題：{topic.title}\n"
            f"主角實體：{topic.primary_entity}\n"
            f"影片類型：{'美股科技巨頭深度財報與護城河分析' if is_stocks else 'AI Agent 與自動化工作流深度實戰教學'}\n"
            f"已爬蟲查證之公開權威資料：\n{json.dumps(src_digest, ensure_ascii=False, indent=2)}\n\n"
            f"請規劃整支深度長片的 {num_chapters} 個章節（參考章節脈絡：{default_chapters[:num_chapters]}，章節標題要犀利具體、符合該類型，4～10 字），以及 YouTube 封面圖兩行超大字標題（`thumbnail_line1` 黃字 4-7 字重點、`thumbnail_line2` 白字 4-7 字反差或承諾，像 Gary 真實封面『Muse / 新手教學』、『AI 寫程式 / 必懂 CI/CD』、『NVDA 財報 / 三大護城河』）！\n"
            "輸出 JSON：\n"
            "{\n"
            '  "title": "Gary Chen 風格高點擊長片標題",\n'
            '  "thumbnail_line1": "封面第一行大字(4-7字)",\n'
            '  "thumbnail_line2": "封面第二行大字(4-7字)",\n'
            '  "youtube_description_summary": "140字內具體精華介紹",\n'
            '  "hashtags": ["#GaryChen", "..."],\n'
            '  "chapters_plan": [\n'
            '    {"index": 1, "chapter_title": "具體章節名", "focus": "本章要講透的核心論點、數據與案例", "primary_source_id": "S1"}\n'
            "  ]\n"
            "}"
        )

        plan_data = self._call_llm_json(sys_prompt, pass1_prompt, max_tokens=2000)
        chapters_plan = plan_data.get("chapters_plan") or []
        while len(chapters_plan) < num_chapters:
            idx = len(chapters_plan) + 1
            chapters_plan.append(
                {
                    "index": idx,
                    "chapter_title": default_chapters[(idx - 1) % len(default_chapters)],
                    "focus": topic.why_now,
                    "primary_source_id": sources[(idx - 1) % max(1, len(sources))].source_id if sources else "S1",
                }
            )
        chapters_plan = chapters_plan[:num_chapters]
        all_chapter_titles = [taiwanize_text(str(c.get("chapter_title") or default_chapters[i]))[:12] for i, c in enumerate(chapters_plan)]

        palette_layouts = STOCKS_LAYOUTS if is_stocks else TUTORIAL_LAYOUTS
        all_beats: list[VisualBeat] = []
        valid_sids = {s.source_id for s in sources} or {"S1"}
        screenshot_sids = [s.source_id for s in sources if s.screenshot_path]

        # PASS 2: Generate 3 deep, non-overlapping progressive beats per chapter with chapter-specific missions & rolling anti-repetition memory!
        chapter_missions = (
            [
                "第1章專屬任務：只講『財報公布後的市場情緒反應 vs 真實財報成績單的巨大預期差』，破題點出華爾街在怕什麼、為什麼值得深挖。",
                "第2章專屬任務：只講『核心商業模式與營收結構拆解』（資料中心算力、網路互連與軟硬整合如何賺錢），不要重複第1章開場話術。",
                "第3章專屬任務：只講『SEC 10-K 官方財報硬核數字與現金流體質』（總營收、營業利益率 60%+、營運現金流 OCF 造血能力），逐一解讀數字意義。",
                "第4章專屬任務：只講『算力資本支出 CapEx 的第一層思考 vs 第二層思考』（對照微軟與 Meta 等雲端巨頭資本支出如何轉化為算力飛輪）。",
                "第5章專屬任務：只講『競爭對手最難複製的三大護城河』（CUDA 開發者生態轉換成本、NVLink 機櫃級系統整合、一年一迭代產品節奏）。",
                "第6章專屬任務：只講『估值倍數 PE 推算與悲觀／基準／樂觀三種情境假設』，用數字推演安全邊際。",
                "第7章專屬任務：前兩幕講『投資人必須追蹤的三大真實風險（自研晶片競爭、毛利率波動、監管週期）』；第三幕請用溫和堅定語氣收尾：『如果你喜歡這種把財報跟產業底層邏輯拆開來看的分析，記得幫我按讚訂閱追蹤 Gary 聊美股，本片內容僅供研究參考不構成投資建議，我們下次見！』",
            ]
            if is_stocks
            else [
                "第1章專屬任務：第1幕點出『現在主流 AI Agent 每月 $20–$200/月 訂閱費太貴』並引出今天免費開源主角與 GitHub 星標數據；第2幕講它能幫一般人省下哪些重複網頁操作；第3幕預告今天影片四個實戰重點（切勿提及記帳軟體，留給第3章）。",
                "第2章專屬任務：只講『底層運作架構白話拆解』（為什麼傳統爬蟲改版就壞，而 DOM 結構樹＋視覺理解雙引擎能像真人一樣看懂按鈕與表單），嚴禁提及記帳軟體。",
                "第3章專屬任務：只在本章講『主角 Gary 的具體生活自動化案例』（例如自動登入後台下載每月電子發票、比價並整理進資料庫），把輸入到輸出的四步驟講清楚。",
                "第4章專屬任務：只講『三分鐘本機環境部署與暗色介面導覽』（Python 環境準備、安裝套件、啟動介面與執行第一個自動搜尋任務），嚴禁重複前面發票記帳故事。",
                "第5章專屬任務：只講『串接主流 AI 模型與進階工作流』（如何切換 Claude、OpenAI 或本機模型，並把抓完的結果自動推播到通知工具），三個 beat 必須講三個不同細節，嚴禁複製貼上相同句子！",
                "第6章專屬任務：只講『開源本機跑 vs 官方雲端版（如每小時 $0.06 計費）vs 高價商業方案的優缺點對照』（隱私、穩定度、成本邊界）。",
                "第7章專屬任務：前兩幕講『新手最容易踩的三個坑（登入 Session 保存、反爬蟲驗證碼、Token 消耗控制）』；最後第3幕請完整說出 Gary 招牌收尾：『那以上就是今天的內容，感謝你看到這邊。如果你還不知道，我有經營一個 AI 實戰營的社群，裡面有我自己的實戰分享和實戰課程。如果 AI 的資訊鋪天蓋地讓你覺得眼花撩亂，我的目標就是成為你唯一的 AI 資訊來源。這支影片提到的實戰模板與設定清單我都整理在社群裡，連結放在下方資訊欄，那我們下次見！』",
            ]
        )
        seen_narrations: list[str] = []

        for ch_pos, ch_item in enumerate(chapters_plan):
            beats_per_chap = 3
            is_first_chap = (ch_pos == 0)
            is_last_chap = (ch_pos == num_chapters - 1)
            mission_txt = chapter_missions[min(ch_pos, len(chapter_missions) - 1)]
            avoid_block = (
                f"\n⚠️ 前面章節已講過的句子（本章嚴禁重複相同案例或相似句型！）：{seen_narrations[-8:]}\n"
                if seen_narrations
                else ""
            )
            genre_rules = (
                "- 美股版面規則：3 個 beat 請選用 3 個不同版型，靈活搭配 `stocks_kpi_asymmetric`（`metric` 必填 `$2,159 億`、`+65.5%`、`60.4%`、`16.7x` 等純數字指標）、`stocks_big_statement`、`stocks_four_pillars`、`browser_ui_live_tour`、`stocks_valuation_scenarios`！絕對禁止出現安裝軟體或寫程式教學！"
                if is_stocks
                else (
                    "- 第1章版面規則：第1幕用 `app_squircles_strikethrough`，第2幕用 `claude_chat_dialog` 或 `concept_hero_split_3d`，第3幕用 `agenda_four_steps`！"
                    if is_first_chap
                    else "- 教學版面規則：本章 3 個 beat 請選用 3 個不同版型（從 `ecosystem_node_graph`、`protagonist_app_flow`、`browser_ui_live_tour`、`concept_hero_split_3d`、`github_pr_checks_card`、`before_after_workflow_card` 中挑選），且 3 個 beat 的台詞必須步步推進、絕不重複！"
                )
            )

            pass2_prompt = (
                f"影片標題：{plan_data.get('title', topic.title)}\n"
                f"全片章節：{all_chapter_titles}\n"
                f"已查證公開數據與來源：\n{json.dumps(src_digest, ensure_ascii=False, indent=2)}\n"
                f"{avoid_block}\n"
                f"現在請針對第 {ch_item['index']} 章（{all_chapter_titles[ch_pos]}）：\n"
                f"🎯 {mission_txt}\n"
                f"請設計 **{beats_per_chap} 個內容完全不重複、層層遞進的 Remotion 動態分鏡 Beat**！\n"
                "每個 Beat 的 `narration` 必須是 **65～98 個中文字的自然道地台灣口語講解（包含 3～4 個逗號分句）**，嚴禁出現『第一幕講…第二幕講…』這種舞台指示語，字串內引用請用『』不要用英文雙引號！\n"
                f"可選 `layout_type`：{palette_layouts}\n"
                f"可選品牌與向量 `icon`：{sorted(VALID_ICONS)}\n"
                f"{genre_rules}\n"
                "輸出 JSON 格式：\n"
                "{\n"
                '  "beats": [\n'
                "    {\n"
                f'      "chapter_index": {ch_item["index"]},\n'
                '      "layout_type": "ecosystem_node_graph",\n'
                '      "voice_style": "hook | explainer | warm",\n'
                '      "narration": "道地台灣口語講解內容",\n'
                '      "visual_title": "簡潔畫面標題",\n'
                '      "visual_subtitle": "精煉副標",\n'
                f'      "badge_text": "{"+65.5% YoY" if is_stocks else "$0 / 月"}",\n'
                '      "nodes": [\n'
                '        {"label": "具體名稱", "sub": "白話重點", "tag": "標籤", "metric": "122K ★", "icon": "github", "trend": "up"}\n'
                "      ],\n"
                '      "callout_title": "核心洞察",\n'
                '      "callout_body": "一句話犀利結論",\n'
                '      "code_lines": ["pip install browser-use"],\n'
                '      "ai_image_prompt": "",\n'
                '      "source_ids": ["S1"],\n'
                '      "sfx_cue": "pop"\n'
                "    }\n"
                "  ]\n"
                "}"
            )
            chunk_data = self._call_llm_json(sys_prompt, pass2_prompt, max_tokens=1600)
            raw_beats = (chunk_data.get("beats") or [])[:beats_per_chap]
            for b_idx, rb in enumerate(raw_beats):
                if not isinstance(rb, dict):
                    continue
                c_idx = ch_pos + 1
                c_title = all_chapter_titles[ch_pos]
                lt = rb.get("layout_type")
                if is_first_chap and not is_stocks and b_idx == 0:
                    lt = "app_squircles_strikethrough"
                elif is_first_chap and not is_stocks and b_idx == beats_per_chap - 1:
                    lt = "agenda_four_steps"
                elif lt not in palette_layouts:
                    lt = palette_layouts[len(all_beats) % len(palette_layouts)]
                if all_beats and all_beats[-1].layout_type == lt:
                    lt = palette_layouts[(palette_layouts.index(lt) + 1) % len(palette_layouts)]

                narr_str = taiwanize_text(str(rb.get("narration") or "").strip())
                if is_last_chap and b_idx == len(raw_beats) - 1:
                    if is_stocks and "Gary 聊美股" not in narr_str:
                        narr_str = (
                            "最後還是要提醒大家關注雲端巨頭自研晶片進度跟毛利率變化，"
                            "如果你喜歡這種把財報跟底層邏輯拆開來看的分析，記得按讚訂閱追蹤 Gary 聊美股，"
                            "本片內容僅供研究參考不構成投資建議，我們下次見"
                        )
                    elif not is_stocks and "AI 實戰營" not in narr_str:
                        narr_str = (
                            "那以上就是今天的實戰內容，如果你覺得鋪天蓋地的 AI 資訊讓你眼花撩亂，"
                            "歡迎加入我在下方資訊欄整理的 AI 實戰營社群，這支影片用到的設定清單跟模板都在裡面，那我們下次見"
                        )
                elif _is_too_similar(narr_str, seen_narrations):
                    src_fb = sources[(ch_pos + b_idx) % max(1, len(sources))] if sources else None
                    m_fb = (src_fb.metrics[0] if (src_fb and src_fb.metrics) else (all_real_metrics[0] if all_real_metrics else "關鍵指標"))
                    dom_fb = src_fb.domain if src_fb else "公開權威報告"
                    narr_str = (
                        f"接著我們進一步看{c_title}背後的實測表現，"
                        f"根據 {dom_fb} 公開查證的 {m_fb} 關鍵數據，"
                        f"這套架構在真實負載下展現出極高的穩定度，也是拉開實戰差距的關鍵細節"
                    )

                seen_narrations.append(narr_str)
                clauses = split_into_clauses(narr_str, target_max=22)
                if len(clauses) < 2:
                    clauses = split_into_clauses(f"{c_title}背後最關鍵的差異，其實藏在底層運作邏輯與真實數據裡", target_max=22)
                spoken_clauses = [to_spoken_tts_text(c) for c in clauses]

                v_nodes: list[VisualNode] = []
                for n_i, nd in enumerate((rb.get("nodes") or [])[:4]):
                    if isinstance(nd, dict) and nd.get("label"):
                        ic = str(nd.get("icon") or "sparkles").lower()
                        if ic not in VALID_ICONS:
                            ic = "nvidia" if is_stocks else "sparkles"
                        tr = str(nd.get("trend") or "neutral").lower()
                        if tr not in ("up", "down", "neutral"):
                            tr = "neutral"
                        raw_tag = taiwanize_text(str(nd.get("tag") or "")).strip()
                        if raw_tag in ("無", "无", "None", "none", "N/A", "-"):
                            raw_tag = ""
                        raw_metric = _ensure_numeric_metric(str(nd.get("metric") or raw_tag), all_real_metrics, len(all_beats) + n_i)
                        v_nodes.append(
                            VisualNode(
                                label=smart_trim(str(nd["label"]), 11.5),
                                sub=smart_trim(str(nd.get("sub") or ""), 17.0),
                                tag=smart_trim(raw_tag, 9.0),
                                metric=raw_metric,
                                icon=ic,
                                trend=tr,  # type: ignore[arg-type]
                            )
                        )

                if lt == "agenda_four_steps":
                    roadmap_chaps = all_chapter_titles[1:5] if len(all_chapter_titles) >= 5 else all_chapter_titles[:4]
                    v_nodes = [
                        VisualNode(
                            label=smart_trim(ct, 7.5),
                            sub=smart_trim(str(chapters_plan[min(len(chapters_plan) - 1, i + 1)].get("focus", "")), 14.0),
                            tag=f"0{i+1}",
                            metric=f"0{i+1}",
                            icon=["layers", "users", "terminal", "zap"][i % 4],
                        )
                        for i, ct in enumerate(roadmap_chaps)
                    ]
                elif len(v_nodes) < 3:
                    src0 = sources[(c_idx - 1) % max(1, len(sources))] if sources else None
                    m_list = (src0.metrics if src0 and src0.metrics else all_real_metrics) or ["+100%"]
                    fallback_labels = (
                        ["核心營收動能", "現金流護城河", "資本支出效率", "長期估值錨點"]
                        if is_stocks
                        else [topic.primary_entity, "自動化執行層", "多模型串接", "本機零成本"]
                    )
                    while len(v_nodes) < 3:
                        k = len(v_nodes)
                        v_nodes.append(
                            VisualNode(
                                label=smart_trim(fallback_labels[k % len(fallback_labels)], 10.5),
                                sub=smart_trim(clauses[min(k, len(clauses) - 1)], 16.0),
                                tag=smart_trim(m_list[k % len(m_list)], 9.0),
                                metric=_ensure_numeric_metric(m_list[k % len(m_list)], all_real_metrics, k),
                                icon="trending_up" if is_stocks else "zap",
                                trend="up" if k == 0 else "neutral",
                            )
                        )

                sids = [s for s in (rb.get("source_ids") or []) if s in valid_sids]
                if lt == "browser_ui_live_tour" and screenshot_sids:
                    if not any(s in screenshot_sids for s in sids):
                        sids = [screenshot_sids[len(all_beats) % len(screenshot_sids)]]
                if not sids and sources:
                    sids = [sources[(c_idx - 1) % len(sources)].source_id]

                sfx = str(rb.get("sfx_cue") or ("terminal" if lt == "claude_chat_dialog" else "pop"))
                if sfx not in ("none", "pop", "terminal", "whoosh", "stamp"):
                    sfx = "pop"
                if len(all_beats) == 0 or all_beats[-1].chapter_index != c_idx:
                    sfx = "whoosh"

                v_style = str(rb.get("voice_style") or ("hook" if c_idx == 1 else ("warm" if c_idx == num_chapters else "explainer")))
                if v_style not in ("hook", "explainer", "warm"):
                    v_style = "explainer"

                code_lns = [str(x)[:64] for x in (rb.get("code_lines") or []) if str(x).strip()][:4]
                if not code_lns and not is_stocks and sources and sources[0].code_or_commands:
                    code_lns = sources[0].code_or_commands[:3]

                raw_bt = taiwanize_text(str(rb.get("badge_text") or "")).strip()
                if "或" in raw_bt or not raw_bt or (is_stocks and "$0" in raw_bt):
                    raw_bt = (all_real_metrics[len(all_beats) % len(all_real_metrics)] if all_real_metrics else "+65.5%") if is_stocks else "$0 / 月"

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
                        visual_title=taiwanize_text(str(rb.get("visual_title") or c_title))[:28],
                        visual_subtitle=taiwanize_text(str(rb.get("visual_subtitle") or ""))[:42],
                        badge_text=raw_bt[:18],
                        nodes=v_nodes,
                        callout_title=taiwanize_text(str(rb.get("callout_title") or ("投資邏輯重點" if is_stocks else "Gary 實戰重點")))[:18],
                        callout_body=taiwanize_text(str(rb.get("callout_body") or clauses[-1]))[:48],
                        code_lines=code_lns,
                        ai_image_prompt=clean_ai_prompt(str(rb.get("ai_image_prompt") or ""), topic.primary_entity, len(all_beats)),
                        source_ids=sids,
                        sfx_cue=sfx,  # type: ignore[arg-type]
                    )
                )

        # PASS 3: Dedicated 42–52s High-Retention Traffic-Funnel Shorts (8 vertical progressive scenes!)
        pass3_prompt = (
            f"長片標題：{taiwanize_text(str(plan_data.get('title') or topic.title))}\n"
            f"長片類型：{'美股財報與護城河分析' if is_stocks else 'AI Agent 與工作流實戰教學'}\n"
            f"長片各章核心亮點：{[{'chapter': b.chapter_title, 'point': '，'.join(b.clauses[:2]), 'badge': b.badge_text} for b in all_beats[::3]]}\n"
            f"查證公開數據：{json.dumps(src_digest[:4], ensure_ascii=False)}\n\n"
            "請設計一支 **42～52 秒超緊湊對應推流 YouTube Shorts**，共 **8 幕 (short_beats)**！\n"
            "每一幕 `narration` 必須是 **32～48 個中文字的道地台灣口語（自然分成 2～3 句短句）**：\n"
            "- 第 1 幕（0-5s）：最強反差數據或痛點直接破題，讓人滑不走\n"
            "- 第 2～6 幕：每幕拆解一個核心亮點與公開查證數據\n"
            "- 第 7 幕：故意留一個最關鍵的懸念（例如『但真正決定成敗的其實是第三個細節...』）\n"
            "- 第 8 幕 (is_cta=true)：明確口播『我已經把完整拆解步驟、真實數據跟避坑清單整理在完整長片裡，現在直接點畫面左下角的關聯影片就能看完整版！』\n"
            "輸出 JSON：{\"short_title\": \"... #Shorts\", \"short_hook_banner\": \"6字內頂部標籤\", \"short_beats\": [{\"layout_type\": \"short_shock_metric_hero\", \"narration\": \"32到48字完整台灣口語台詞\", \"headline\": \"12字內大標題\", \"sub_caption\": \"20字內副標\", \"highlight_badge\": \"具體數據\", \"nodes\": [{\"label\": \"重點\", \"sub\": \"白話說明\", \"tag\": \"數據\", \"icon\": \"zap\"}], \"ai_image_prompt\": \"English 3D dark studio metaphor prompt\", \"source_ids\": [\"S1\"], \"is_cta\": false}]}"
        )
        try:
            short_plan = self._call_llm_json(sys_prompt, pass3_prompt, max_tokens=2800)
        except Exception:
            short_plan = {}

        raw_sbeats = short_plan.get("short_beats") or []
        short_beats: list[ShortBeatSpec] = []
        anchor_step = max(1, len(all_beats) // 7)
        chapter_anchor_beats = [all_beats[min(len(all_beats) - 1, i * anchor_step)] for i in range(8)]

        for idx in range(8):
            sb = raw_sbeats[idx] if idx < len(raw_sbeats) and isinstance(raw_sbeats[idx], dict) else {}
            is_cta = (idx == 7)
            slt = "short_funnel_cta" if is_cta else sb.get("layout_type", SHORT_LAYOUTS[idx % 5])
            if slt not in SHORT_LAYOUTS:
                slt = SHORT_LAYOUTS[idx % 5]
            if idx == 2 and screenshot_sids:
                slt = "short_live_source_proof"
            ref_b = chapter_anchor_beats[idx]
            raw_narr = taiwanize_text(str(sb.get("narration") or ""))
            s_clauses = split_into_clauses(raw_narr, target_max=19)
            if is_cta and sum(len(c) for c in s_clauses) < 22:
                s_clauses = [
                    "完整拆解數據跟實戰細節我都整理在長片裡了",
                    "現在直接點擊畫面左下角的關聯影片看完整版",
                ]
            elif sum(len(c) for c in s_clauses) < 18:
                s_clauses = ref_b.clauses[:3]
            s_spoken = [to_spoken_tts_text(c) for c in s_clauses[:3]]

            snodes: list[VisualNode] = []
            for nd in (sb.get("nodes") or [])[:3]:
                if isinstance(nd, dict) and nd.get("label"):
                    ic = str(nd.get("icon") or "zap").lower()
                    raw_t = taiwanize_text(str(nd.get("tag") or "")).strip()
                    if raw_t in ("無", "无", "None", "-"):
                        raw_t = ""
                    snodes.append(
                        VisualNode(
                            label=taiwanize_text(str(nd["label"]))[:18],
                            sub=taiwanize_text(str(nd.get("sub") or ""))[:24],
                            tag=raw_t[:14],
                            metric=_ensure_numeric_metric(raw_t, all_real_metrics, idx),
                            icon=ic if ic in VALID_ICONS else "zap",
                        )
                    )
            if len(snodes) < 2:
                snodes = ref_b.nodes[:3]
            sids = [s for s in (sb.get("source_ids") or []) if s in valid_sids]
            if slt == "short_live_source_proof" and screenshot_sids:
                sids = [screenshot_sids[0]]
            elif not sids and sources:
                sids = [sources[idx % len(sources)].source_id]

            short_beats.append(
                ShortBeatSpec(
                    beat_id=f"sbeat_{len(short_beats) + 1:02d}",
                    layout_type=slt,  # type: ignore[arg-type]
                    voice_style="hook" if idx == 0 else ("warm" if is_cta else "explainer"),
                    clauses=s_clauses[:3],
                    spoken_clauses=s_spoken,
                    headline=taiwanize_text(str(sb.get("headline") or ("點擊左下角看完整版" if is_cta else ref_b.visual_title)))[:15],
                    sub_caption=taiwanize_text(str(sb.get("sub_caption") or ref_b.visual_subtitle))[:26],
                    highlight_badge=taiwanize_text(str(sb.get("highlight_badge") or ("完整長片已上線" if is_cta else ref_b.badge_text)))[:16],
                    nodes=snodes,
                    ai_image_prompt=clean_ai_prompt(str(sb.get("ai_image_prompt") or ""), topic.primary_entity, idx + 30),
                    source_ids=sids,
                    is_cta=is_cta,
                )
            )

        ep_title = taiwanize_text(str(plan_data.get("title") or topic.title))
        tl1 = smart_trim(str(plan_data.get("thumbnail_line1") or topic.primary_entity), 8.6)
        tl2 = smart_trim(str(plan_data.get("thumbnail_line2") or ("三大護城河" if is_stocks else "零成本實戰")), 8.6)
        if not tl1:
            tl1 = smart_trim(topic.primary_entity, 8.6)
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
