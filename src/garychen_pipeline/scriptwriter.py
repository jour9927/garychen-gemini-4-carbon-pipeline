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


def clean_ai_prompt(raw_prompt: str, entity: str, idx: int) -> str:
    p = str(raw_prompt or "").strip()
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", p))
    if not p or has_cjk or "Concrete English" in p or len(p) < 22:
        base = DIORAMA_SCENES[idx % len(DIORAMA_SCENES)]
        return f"{base}, clean conceptual metaphor for {entity}, strictly no text or letters"
    return p


def space_pad_english(text: str) -> str:
    t = taiwanize_text(text)
    t = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9$%+])", r"\1 \2", t)
    t = re.sub(r"([A-Za-z0-9%])([\u4e00-\u9fff])", r"\1 \2", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("。.！!；;、，,")


def split_into_clauses(text: str, target_max: int = 21) -> list[str]:
    raw_parts = re.split(r"[。！？；!?\n]+|，", taiwanize_text(text))
    pieces: list[str] = []
    for p in raw_parts:
        s = space_pad_english(p.strip(" 、：:「」"))
        if not s:
            continue
        if len(s) <= target_max + 6:
            pieces.append(s)
        else:
            mid = len(s) // 2
            best_pos = -1
            for sep in (" ", "：", "、", "的", "把", "讓", "跟", "但", "而"):
                pos = s.find(sep, max(6, mid - 7), min(len(s) - 5, mid + 8))
                if pos != -1:
                    best_pos = pos + (0 if sep == " " else 1)
                    break
            if best_pos != -1:
                pieces.extend([s[:best_pos].strip(" 、："), s[best_pos:].strip(" 、：")])
            else:
                pieces.append(s[: target_max + 6].strip())

    merged: list[str] = []
    carry = ""
    for seg in pieces:
        if carry:
            seg = f"{carry} {seg}" if carry[-1].isascii() else f"{carry}{seg}"
            carry = ""
        if len(re.sub(r"\s+", "", seg)) <= 6:
            carry = seg + ("，" if len(seg) >= 2 else "")
        else:
            merged.append(seg)
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]}，{carry.rstrip('，')}"
        else:
            merged.append(carry.rstrip("，"))
    return [c for c in merged if c][:4]


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

        with httpx.Client(timeout=150.0) as client:
            r = client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.45, "num_ctx": 8192, "num_predict": max_tokens},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt + "\n請只輸出純 JSON 物件。"},
                    ],
                },
            )
            r.raise_for_status()
            return self._extract_json(r.json().get("message", {}).get("content", "{}"))

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            chunk = raw[s : e + 1]
            try:
                return json.loads(chunk)
            except json.JSONDecodeError:
                chunk_fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
                return json.loads(chunk_fixed)
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

        # PASS 2: Generate 3–4 deep, tightly choreographed progressive beats per chapter!
        for pair_start in range(0, num_chapters, 2):
            pair = chapters_plan[pair_start : pair_start + 2]
            beats_per_chap = 3
            genre_rules = (
                "- 美股版面規則：大量運用 `stocks_kpi_asymmetric`（呈現 SEC 10-K 營收/營益率/OCF/CapEx 真實數字，`metric` 欄位必須填 `$1,305 億`、`+114%`、`75.0%`、`28x` 這類純數字指標！）、`stocks_big_statement`（一句震撼結論）、`stocks_four_pillars`（拆解三大護城河或四大成長變數）、`browser_ui_live_tour`（展示真實財報/股價/論文網頁截圖）、`stocks_valuation_scenarios`（悲觀/基準/樂觀估值情境）！\n"
                "- 絕對禁止出現任何安裝軟體或寫程式步驟！最後一章最後一幕請自然收尾：提醒三個真實風險，並說『如果你喜歡這種把財報跟產業底層邏輯拆開來看的分析，記得幫我按讚訂閱追蹤 Gary 聊美股，本片內容僅供研究參考不構成投資建議，我們下次見！』"
                if is_stocks
                else "- 教學版面規則：第 1 章開場請搭配 `app_squircles_strikethrough`（訂閱費 `$20-$200/月` 劃掉變 `$0/月`）或 `claude_chat_dialog`（真實開發對話情境），第 1 章最後一幕用 `agenda_four_steps`（預告今天四個重點）！\n"
                "- 第 2～6 章靈活交替 `ecosystem_node_graph`（中心工具串接 Gmail/Slack/GitHub/Notion 等生態圖）、`protagonist_app_flow`（主角 Gary 的記帳或自動化專案四步流程）、`browser_ui_live_tour`（展示真實暗色網頁/GitHub 截圖）、`concept_hero_split_3d`（3D 概念場景＋左右對照）、`github_pr_checks_card`、`before_after_workflow_card`（以前自己做［麻煩］ vs 現在直接串［一鍵串接］）！\n"
                "- 最後一章最後一幕請用 Gary 招牌收尾：『那以上就是今天的內容，感謝你看到這邊。如果你還不知道，我有經營一個 AI 實戰營的社群，裡面有我自己的實戰分享和實戰課程。如果 AI 的資訊鋪天蓋地讓你覺得眼花撩亂，我的目標就是成為你唯一的 AI 資訊來源。這支影片提到的實戰模板與設定清單我都整理在社群裡，連結放在下方資訊欄，那我們下次見！』"
            )

            pass2_prompt = (
                f"影片標題：{plan_data.get('title', topic.title)}\n"
                f"全片章節：{all_chapter_titles}\n"
                f"已查證公開數據與來源：\n{json.dumps(src_digest, ensure_ascii=False, indent=2)}\n\n"
                f"現在請針對第 {pair[0]['index']} 章到第 {pair[-1]['index']} 章：\n"
                f"{json.dumps(pair, ensure_ascii=False)}\n"
                f"為『每一個章節』設計 **{beats_per_chap} 個連貫且有深度的 Remotion 動態分鏡 Beat**（本次共輸出 {len(pair) * beats_per_chap} 個 beats）！\n"
                "每個 Beat 的 `narration` 必須是 **65～105 個中文字的紮實口語講解（自然包含 3～4 個子句）**，語氣自然連貫、有邏輯推演（先講現象/痛點 -> 拆解背後原因/真實數據 -> 白話結論）！\n"
                f"可選 `layout_type`：{palette_layouts}\n"
                f"可選品牌與向量 `icon`：{sorted(VALID_ICONS)}\n"
                f"{genre_rules}\n"
                "輸出 JSON 格式：\n"
                "{\n"
                '  "beats": [\n'
                "    {\n"
                '      "chapter_index": 1,\n'
                '      "layout_type": "ecosystem_node_graph",\n'
                '      "voice_style": "hook | explainer | warm",\n'
                '      "narration": "65到105字道地台灣口語講解，有具體案例與真實查證數據，絕不講空話",\n'
                '      "visual_title": "16字內簡潔畫面標題（若該版型極簡可留精煉短標）",\n'
                '      "visual_subtitle": "24字內副標",\n'
                '      "badge_text": "關鍵數據標籤 (如 $0/月 或 +114% YoY)",\n'
                '      "nodes": [\n'
                '        {"label": "具體工具/指標名", "sub": "16字內白話重點", "tag": "狀態標籤", "metric": "$1,305 億 或 212K ★", "icon": "github", "trend": "up | down | neutral"}\n'
                "      ],\n"
                '      "callout_title": "關鍵結論",\n'
                '      "callout_body": "26字內犀利一句話洞察",\n'
                '      "code_lines": ["npx n8n", "docker compose up -d"],\n'
                '      "ai_image_prompt": "English 3D dark matte studio metaphor prompt on #262626 charcoal background, no text",\n'
                '      "source_ids": ["S1"],\n'
                '      "sfx_cue": "pop | terminal | whoosh | stamp"\n'
                "    }\n"
                "  ]\n"
                "}"
            )
            chunk_data = self._call_llm_json(sys_prompt, pass2_prompt, max_tokens=3800)
            raw_beats = chunk_data.get("beats") or []
            for b_idx, rb in enumerate(raw_beats):
                if not isinstance(rb, dict):
                    continue
                c_idx = int(rb.get("chapter_index") or pair[min(len(pair) - 1, b_idx // beats_per_chap)]["index"])
                c_idx = max(1, min(num_chapters, c_idx))
                c_title = all_chapter_titles[c_idx - 1]
                lt = rb.get("layout_type")
                if lt not in palette_layouts:
                    lt = palette_layouts[len(all_beats) % len(palette_layouts)]
                # Avoid identical consecutive layouts so visual rhythm stays dynamic like real Remotion!
                if all_beats and all_beats[-1].layout_type == lt:
                    lt = palette_layouts[(palette_layouts.index(lt) + 1) % len(palette_layouts)]

                narr_str = taiwanize_text(str(rb.get("narration") or "").strip())
                clauses = split_into_clauses(narr_str, target_max=21)
                if len(clauses) < 2:
                    clauses = split_into_clauses(f"{c_title}背後最關鍵的差異，其實藏在底層運作邏輯與真實數據裡", target_max=21)
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
                                label=taiwanize_text(str(nd["label"]))[:20],
                                sub=taiwanize_text(str(nd.get("sub") or ""))[:30],
                                tag=raw_tag[:16],
                                metric=raw_metric,
                                icon=ic,
                                trend=tr,  # type: ignore[arg-type]
                            )
                        )

                if lt == "agenda_four_steps" and len(v_nodes) < 4:
                    v_nodes = [
                        VisualNode(
                            label=ct[:8],
                            sub=taiwanize_text(chapters_plan[i].get("focus", ""))[:16],
                            tag=f"0{i+1}",
                            metric=f"0{i+1}",
                            icon=["zap", "layers", "code", "shield"][i % 4],
                        )
                        for i, ct in enumerate(all_chapter_titles[1:5] if len(all_chapter_titles) >= 5 else all_chapter_titles[:4])
                    ]
                elif len(v_nodes) < 3:
                    src0 = sources[(c_idx - 1) % max(1, len(sources))] if sources else None
                    m_list = (src0.metrics if src0 and src0.metrics else all_real_metrics) or ["+100%"]
                    while len(v_nodes) < 3:
                        k = len(v_nodes)
                        v_nodes.append(
                            VisualNode(
                                label=topic.primary_entity[:16] if k == 0 else f"{c_title[:8]}重點 {k+1}",
                                sub=clauses[min(k, len(clauses) - 1)][:24],
                                tag=m_list[k % len(m_list)][:14],
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
                        badge_text=taiwanize_text(str(rb.get("badge_text") or ""))[:18],
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
        tl1 = taiwanize_text(str(plan_data.get("thumbnail_line1") or topic.primary_entity))[:9]
        tl2 = taiwanize_text(str(plan_data.get("thumbnail_line2") or ("三大護城河" if is_stocks else "免費實戰教學")))[:9]
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
            short_hook_banner=taiwanize_text(str(short_plan.get("short_hook_banner") or tl1))[:10],
            short_cta_target_title=ep_title,
            short_beats=short_beats,
        )
