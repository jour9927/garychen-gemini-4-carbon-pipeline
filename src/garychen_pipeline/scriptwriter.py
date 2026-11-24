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

TUTORIAL_LAYOUT_ROTATION: list[BeatLayoutType] = [
    "claude_terminal_progressive",
    "pricing_strikethrough_reveal",
    "chapter_roadmap_agenda",
    "progressive_slot_pipeline",
    "live_web_screenshot_spotlight",
    "hub_ecosystem_radiate",
    "ai_editorial_split_card",
    "github_pr_checks_mock",
    "branch_merge_diagram",
    "before_after_stamp_compare",
    "checklist_two_tier_defense",
    "versus_debate_columns",
    "kpi_financial_cards",
    "summary_three_pillars",
]

STOCKS_LAYOUT_ROTATION: list[BeatLayoutType] = [
    "kpi_financial_cards",
    "chapter_roadmap_agenda",
    "hub_ecosystem_radiate",
    "live_web_screenshot_spotlight",
    "ai_editorial_split_card",
    "progressive_slot_pipeline",
    "versus_debate_columns",
    "before_after_stamp_compare",
    "checklist_two_tier_defense",
    "summary_three_pillars",
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
    "check", "database", "trending_up", "dollar", "layers", "zap", "lock", "users", "play"
}


TW_REPLACEMENTS = [
    ("代碼", "程式碼"),
    ("代码", "程式碼"),
    ("編程", "寫程式"),
    ("编程", "寫程式"),
    ("創建", "建立"),
    ("创建", "建立"),
    ("自托管", "自架部署"),
    ("自託管", "自架部署"),
    ("教程", "教學"),
    ("地址", "網址"),
    ("模版", "模板"),
    ("贡献", "貢獻"),
    ("安裝完 n8n 后", "安裝完 n8n 後"),
    ("之后", "之後"),
    ("以后", "以後"),
    ("背后", "背後"),
    ("軟件", "軟體"),
    ("软件", "軟體"),
    ("服務器", "伺服器"),
    ("服务器", "伺服器"),
    ("數據庫", "資料庫"),
    ("数据库", "資料庫"),
    ("默認", "預設"),
    ("默认", "預設"),
    ("調用", "呼叫"),
    ("调用", "呼叫"),
    ("項目", "專案"),
    ("项目", "專案"),
    ("視頻", "影片"),
    ("视频", "影片"),
    ("信息", "資訊"),
]

DIORAMA_SCENES = [
    "isometric 3D dark studio diorama of glowing modular workflow nodes connected by amber light beams on matte charcoal desk",
    "sleek 3D architectural cutaway of an autonomous AI engine processing data cubes with warm orange rim lighting",
    "minimalist 3D glass terminal dashboard floating above brushed gunmetal hardware modules, studio softbox lighting",
    "tactile 3D precision vault shield protecting glowing golden data crystals on dark slate pedestal",
    "3D mechanical balance scale comparing a compact glowing amber core against heavy legacy iron blocks",
    "3D ecosystem hub radiating clean fiber-optic pathways to six floating tool satellites on dark charcoal stage",
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
    if not p or has_cjk or "Concrete English" in p or len(p) < 18:
        base = DIORAMA_SCENES[idx % len(DIORAMA_SCENES)]
        return f"{base}, inspired by {entity} system architecture, strictly no text"
    return p


def space_pad_english(text: str) -> str:
    t = taiwanize_text(text)
    t = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9$%+])", r"\1 \2", t)
    t = re.sub(r"([A-Za-z0-9%])([\u4e00-\u9fff])", r"\1 \2", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("。.！!；;、，,")


def split_into_clauses(text: str, target_max: int = 22) -> list[str]:
    raw_parts = re.split(r"[。！？；!?\n]+|，", taiwanize_text(text))
    pieces: list[str] = []
    for p in raw_parts:
        s = space_pad_english(p.strip(" 、：:「」"))
        if not s:
            continue
        if len(s) <= target_max + 6:
            pieces.append(s)
        else:
            # Prefer splitting on space, colon, or natural Chinese particle near middle — never mid-word!
            mid = len(s) // 2
            best_pos = -1
            for sep in (" ", "：", "、", "的", "把", "讓", "跟", "並"):
                pos = s.find(sep, max(6, mid - 7), min(len(s) - 5, mid + 8))
                if pos != -1:
                    best_pos = pos + (0 if sep == " " else 1)
                    break
            if best_pos != -1:
                pieces.extend([s[:best_pos].strip(" 、："), s[best_pos:].strip(" 、：")])
            else:
                pieces.append(s[: target_max + 6].strip())

    # Merge tiny discourse markers (<= 6 chars like '首先', '不過', '現在', '接下來') into adjacent clause!
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


class GarychenScriptwriter:
    """
    V2 Multi-Pass Director powered by Qwen2.5-14B-Instruct on RTX PRO 6000 CUDA (with fast Ollama fallback).
    Produces 18–24 progressive visual beats across 6 real Garychen chapters + an 8-beat 45s Funnel Short!
    """

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434", ollama_model: str = "qwen3:8b"):
        self.ollama_url = os.environ.get("GC_OLLAMA_URL", ollama_url).rstrip("/")
        self.ollama_model = os.environ.get("GC_OLLAMA_MODEL", ollama_model)

    def _call_llm_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2200) -> dict[str, Any]:
        # Priority 1: RTX PRO 6000 Colab Qwen2.5-14B-Instruct CUDA Worker
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
                            "user_prompt": user_prompt + "\n請只輸出合法 JSON 物件，不要加任何解釋。",
                            "max_tokens": max_tokens,
                            "temperature": 0.55,
                        },
                    )
                    if sub.status_code != 200:
                        continue
                    jid = sub.json()["job_id"]
                    t0 = time.time()
                    while time.time() - t0 < 180:
                        time.sleep(1.5)
                        sr = client.get(f"{ep.url}/job/status/{jid}", headers=headers)
                        st = sr.json()
                        if st.get("status") == "done":
                            return self._extract_json(st["result"]["text"])
                        if st.get("status") == "error":
                            break
            except Exception:
                pass

        # Priority 2: Fast unconstrained Local Ollama Qwen3:8b
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.5, "num_ctx": 8192, "num_predict": max_tokens},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt + "\n請只輸出純 JSON 物件，絕對不要輸出 Markdown 以外的多餘說明。"},
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
                # Repair trailing commas
                chunk_fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
                return json.loads(chunk_fixed)
        raise ValueError("No valid JSON object in LLM output")

    def generate_episode_script(
        self,
        topic: TopicCandidate,
        sources: list[CrawledSource],
        episode_id: str,
        num_chapters: int = 6,
    ) -> EpisodeScript:
        src_digest = [
            {
                "source_id": s.source_id,
                "domain": s.domain,
                "title": s.title,
                "date": s.published_date,
                "metrics": s.metrics[:4],
                "facts": s.key_facts[:3],
                "commands": s.code_or_commands[:2],
                "has_screenshot": bool(s.screenshot_path),
            }
            for s in sources[:6]
        ]

        sys_prompt = (
            "你是 YouTube 頻道「Gary Chen (@garychenai)」的本人編劇與 Remotion 動態視覺導演。\n"
            "你必須 100% 還原 Gary Chen 的真實講話風格與教學結構：\n"
            "- 台灣繁體中文口語（專案、套件、資料夾、伺服器、資訊欄、留言區、踩坑、白話講），絕不使用中國用語，絕不出現生硬模板詞（嚴禁出現『核心解析1』、『痛點拆解/核心架構/實戰落地』這類空洞套話！）。\n"
            "- 開場直接從具體情境切入（例如：『你可能在用 AI 寫程式或抓資料的時候遇過這種狀況...』或『財報公布當天盤後大跌，但市場到底看漏了什麼？』），並用『我們的主角 Gary』舉具體生活化案例（例如做記帳軟體、整理 IG 收藏、自動化排程）。\n"
            "- 自然把爬蟲抓到的真實數據（GitHub Stars、版本號、股價營收、論文結論）講進台詞裡，並標記對應的 source_ids（如 [\"S1\"]）。"
        )

        # PASS 1: Master Outline (6 concrete chapters) + 7-beat High-Retention Funnel Short
        pass1_prompt = (
            f"主題：{topic.title}\n"
            f"主角實體：{topic.primary_entity}\n"
            f"類別：{topic.category}\n"
            f"已查證公開資訊：\n{json.dumps(src_digest, ensure_ascii=False, indent=2)}\n\n"
            f"請先規劃整部影片的 {num_chapters} 個具體章節（章節名要像 Gary 真實影片，例如『為什麼選它』、『背後運作原理』、『三步安裝實戰』、『進階避坑技巧』、『跟競品差在哪』、『我的搭配建議』，每章 4–8 字），以及對應推流這支長片的 7 幕快節奏 YouTube Shorts 腳本（約 45 秒，最後一幕 is_cta=true 引導點擊左下角關聯影片看完整版）！\n"
            "輸出 JSON 格式：\n"
            "{\n"
            '  "title": "Gary Chen 風格高點擊長片標題",\n'
            '  "youtube_description_summary": "120字內精華介紹",\n'
            '  "hashtags": ["#AIAgent", "#AI教學", "#GaryChen"],\n'
            '  "chapters_plan": [\n'
            '    {"index": 1, "chapter_title": "具體章節名", "focus": "本章要講透的具體內容與案例", "primary_source_id": "S1"}\n'
            "  ],\n"
            '  "short_title": "爆點 Shorts 標題 #Shorts",\n'
            '  "short_hook_banner": "6字內頂部標籤",\n'
            '  "short_beats": [\n'
            "    {\n"
            '      "layout_type": "short_shock_metric_hero | short_progressive_flow | short_live_source_proof | short_before_after_versus | short_code_or_steps | short_funnel_cta",\n'
            '      "narration": "22到38字口語台詞",\n'
            '      "headline": "12字內大字重點",\n'
            '      "sub_caption": "18字內補充說明",\n'
            '      "highlight_badge": "具體數據標籤 (如 121K+ Stars / $0 免費)",\n'
            '      "nodes": [{"label": "具體名稱", "sub": "具體細節", "tag": "數據", "icon": "github"}],\n'
            '      "ai_image_prompt": "English 3D isometric dark studio metaphor prompt, no text",\n'
            '      "source_ids": ["S1"],\n'
            '      "is_cta": false\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        plan_data = self._call_llm_json(sys_prompt, pass1_prompt, max_tokens=2400)
        chapters_plan = plan_data.get("chapters_plan") or []
        while len(chapters_plan) < num_chapters:
            idx = len(chapters_plan) + 1
            chapters_plan.append(
                {
                    "index": idx,
                    "chapter_title": ["為什麼值得學", "底層運作原理", "從零開始實戰", "真實案例拆解", "常見踩坑指南", "我的搭配建議"][(idx - 1) % 6],
                    "focus": topic.why_now,
                    "primary_source_id": sources[(idx - 1) % max(1, len(sources))].source_id if sources else "S1",
                }
            )
        chapters_plan = chapters_plan[:num_chapters]
        all_chapter_titles = [str(c.get("chapter_title", f"重點 {i+1}"))[:10] for i, c in enumerate(chapters_plan)]

        # PASS 2: Generate 3 rich progressive VisualBeats per pair of chapters (3 calls × 2 chapters = 18 rich beats!)
        palette_layouts = STOCKS_LAYOUT_ROTATION if topic.category == "us_stocks" else TUTORIAL_LAYOUT_ROTATION
        all_beats: list[VisualBeat] = []
        valid_sids = {s.source_id for s in sources} or {"S1"}
        screenshot_sids = [s.source_id for s in sources if s.screenshot_path]

        for pair_start in range(0, num_chapters, 2):
            pair = chapters_plan[pair_start : pair_start + 2]
            pass2_prompt = (
                f"影片標題：{plan_data.get('title', topic.title)}\n"
                f"全片章節：{all_chapter_titles}\n"
                f"公開資訊與真實數據：\n{json.dumps(src_digest, ensure_ascii=False, indent=2)}\n\n"
                f"現在請針對第 {pair[0]['index']} 章到第 {pair[-1]['index']} 章：\n"
                f"{json.dumps(pair, ensure_ascii=False)}\n"
                "為『每一個章節』設計 **3 個連貫的視覺分鏡 Beat**（所以這次共輸出 6 個 beats）！\n"
                "每個 Beat 代表約 8–12 秒的口語講解（約 45–75 個中文字，自然分成 3 句短句 clauses），當 Gary 唸第 1、2、3 句時，畫面上的卡片/終端機指令/流程箭頭會依序動畫彈出！\n"
                f"可選 layout_type 清單：{palette_layouts}\n"
                f"可選 icon 清單：{sorted(VALID_ICONS)}\n"
                "請確保：\n"
                "- 第 1 章若有開場情境請用 claude_terminal_progressive 或 pricing_strikethrough_reveal 或 kpi_financial_cards，最後一幕可用 chapter_roadmap_agenda 預告今天會講哪幾件事！\n"
                "- 若某來源有 has_screenshot=true，至少安排一幕 live_web_screenshot_spotlight 展示真實網頁截圖！\n"
                "- nodes 裡的 label / sub / tag 必須寫出真實工具名、真實步驟、真實數字或真實指令，絕對禁止寫空洞套話！\n"
                "輸出 JSON 格式：\n"
                "{\n"
                '  "beats": [\n'
                "    {\n"
                '      "chapter_index": 1,\n'
                '      "layout_type": "progressive_slot_pipeline",\n'
                '      "voice_style": "hook | explainer | warm",\n'
                '      "narration": "45到75字口語台詞，自然帶出真實數據或 Gary 的實戰例子",\n'
                '      "visual_title": "14字內具體畫面主標題",\n'
                '      "visual_subtitle": "22字內具體副標題",\n'
                '      "badge_text": "亮點數字或狀態標籤",\n'
                '      "nodes": [\n'
                '        {"label": "具體步驟或工具名", "sub": "一句話白話解釋", "tag": "數字或狀態", "icon": "github", "trend": "up | down | neutral"}\n'
                "      ],\n"
                '      "callout_title": "Gary 實戰重點",\n'
                '      "callout_body": "28字內具體結論",\n'
                '      "code_lines": ["pip install ...", "npx ..."],\n'
                '      "ai_image_prompt": "Concrete English 3D studio diorama metaphor (e.g. robotic arm sorting glowing browser windows on a conveyor belt), no text",\n'
                '      "source_ids": ["S1"],\n'
                '      "sfx_cue": "pop | terminal | whoosh | stamp"\n'
                "    }\n"
                "  ]\n"
                "}"
            )
            chunk_data = self._call_llm_json(sys_prompt, pass2_prompt, max_tokens=3000)
            raw_beats = chunk_data.get("beats") or []
            for b_idx, rb in enumerate(raw_beats):
                if not isinstance(rb, dict):
                    continue
                c_idx = int(rb.get("chapter_index") or pair[min(len(pair) - 1, b_idx // 3)]["index"])
                c_idx = max(1, min(num_chapters, c_idx))
                c_title = all_chapter_titles[c_idx - 1]
                lt = rb.get("layout_type")
                if lt not in palette_layouts:
                    lt = palette_layouts[(len(all_beats)) % len(palette_layouts)]

                narr_str = taiwanize_text(str(rb.get("narration") or "").strip())
                clauses = split_into_clauses(narr_str, target_max=22)
                if len(clauses) < 2:
                    clauses = split_into_clauses(f"{c_title}其實沒有想像中複雜，我們直接拆開來看最核心的做法", target_max=22)

                v_nodes: list[VisualNode] = []
                for nd in (rb.get("nodes") or [])[:4]:
                    if isinstance(nd, dict) and nd.get("label"):
                        ic = str(nd.get("icon") or "sparkles").lower()
                        if ic not in VALID_ICONS:
                            ic = "sparkles"
                        tr = str(nd.get("trend") or "neutral").lower()
                        if tr not in ("up", "down", "neutral"):
                            tr = "neutral"
                        raw_tag = taiwanize_text(str(nd.get("tag") or "")).strip()
                        if raw_tag in ("無", "无", "None", "none", "N/A", "-"):
                            raw_tag = ""
                        v_nodes.append(
                            VisualNode(
                                label=taiwanize_text(str(nd["label"]))[:20],
                                sub=taiwanize_text(str(nd.get("sub") or ""))[:30],
                                tag=raw_tag[:16],
                                icon=ic,
                                trend=tr,  # type: ignore[arg-type]
                            )
                        )
                # If chapter_roadmap_agenda has < 4 nodes, populate with actual chapter titles!
                if lt == "chapter_roadmap_agenda" and len(v_nodes) < 4:
                    v_nodes = [
                        VisualNode(label=taiwanize_text(ct), sub=taiwanize_text(chapters_plan[i].get("focus", ""))[:18], tag=f"0{i+1}", icon="layers")
                        for i, ct in enumerate(all_chapter_titles[:4])
                    ]
                elif len(v_nodes) < 2:
                    src0 = sources[(c_idx - 1) % max(1, len(sources))] if sources else None
                    m0 = src0.metrics[0] if (src0 and src0.metrics) else "關鍵指標"
                    v_nodes = [
                        VisualNode(label=topic.primary_entity[:16], sub=clauses[0][:22], tag=m0, icon="zap", trend="up"),
                        VisualNode(label=taiwanize_text(c_title), sub=clauses[-1][:22], tag="實戰重點", icon="check", trend="neutral"),
                    ]

                sids = [s for s in (rb.get("source_ids") or []) if s in valid_sids]
                if lt == "live_web_screenshot_spotlight" and screenshot_sids:
                    if not any(s in screenshot_sids for s in sids):
                        sids = [screenshot_sids[len(all_beats) % len(screenshot_sids)]]
                if not sids and sources:
                    sids = [sources[(c_idx - 1) % len(sources)].source_id]

                sfx = str(rb.get("sfx_cue") or ("terminal" if lt == "claude_terminal_progressive" else "pop"))
                if sfx not in ("none", "pop", "terminal", "whoosh", "stamp"):
                    sfx = "pop"
                if len(all_beats) == 0 or all_beats[-1].chapter_index != c_idx:
                    sfx = "whoosh"

                v_style = str(rb.get("voice_style") or ("hook" if c_idx == 1 else ("warm" if c_idx == num_chapters else "explainer")))
                if v_style not in ("hook", "explainer", "warm"):
                    v_style = "explainer"

                code_lns = [str(x)[:64] for x in (rb.get("code_lines") or []) if str(x).strip()][:4]
                if not code_lns and sources and sources[0].code_or_commands:
                    code_lns = sources[0].code_or_commands[:3]

                all_beats.append(
                    VisualBeat(
                        beat_id=f"beat_{len(all_beats) + 1:02d}",
                        chapter_index=c_idx,
                        total_chapters=num_chapters,
                        chapter_title=taiwanize_text(c_title),
                        layout_type=lt,
                        voice_style=v_style,  # type: ignore[arg-type]
                        clauses=clauses,
                        visual_title=taiwanize_text(str(rb.get("visual_title") or c_title))[:28],
                        visual_subtitle=taiwanize_text(str(rb.get("visual_subtitle") or ""))[:40],
                        badge_text=taiwanize_text(str(rb.get("badge_text") or ""))[:18],
                        nodes=v_nodes,
                        callout_title=taiwanize_text(str(rb.get("callout_title") or "Gary 實戰重點"))[:18],
                        callout_body=taiwanize_text(str(rb.get("callout_body") or clauses[-1]))[:46],
                        code_lines=code_lns,
                        ai_image_prompt=clean_ai_prompt(str(rb.get("ai_image_prompt") or ""), topic.primary_entity, len(all_beats)),
                        source_ids=sids,
                        sfx_cue=sfx,  # type: ignore[arg-type]
                    )
                )

        # PASS 3: Dedicated 40–50s High-Retention Traffic-Funnel Shorts Script (7 full spoken beats!)
        pass3_prompt = (
            f"長片標題：{taiwanize_text(str(plan_data.get('title') or topic.title))}\n"
            f"長片各章節精華：{[{'chapter': b.chapter_title, 'point': '，'.join(b.clauses[:2]), 'badge': b.badge_text} for b in all_beats[::3]]}\n"
            f"公開來源數據：{json.dumps(src_digest[:4], ensure_ascii=False)}\n\n"
            "請專門為這支長片設計一支 **40～50 秒對應推流 YouTube Shorts**，共 **7 幕 (short_beats)**！\n"
            "注意每一幕的 `narration` 必須是 **完整 28～45 個中文字的自然台灣口語句子（至少兩到三句話，絕對不能只寫四五個字的標題！）**：\n"
            "- 第 1 幕：痛點＋驚人公開數據破題（如 GitHub 幾萬顆星或股價營收反差）\n"
            "- 第 2～6 幕：濃縮長片最吸睛的核心原理、關鍵指令/指標、競品對比與避坑重點（留一個關鍵細節懸念在長片）\n"
            "- 第 7 幕 (is_cta=true)：明確口播『完整實戰步驟、指令模板跟公開查證來源我都整理在長片裡了，現在直接點擊左下角關聯影片看完整版！』\n"
            "輸出 JSON：{\"short_title\": \"... #Shorts\", \"short_hook_banner\": \"6字內標籤\", \"short_beats\": [{\"layout_type\": \"short_shock_metric_hero\", \"narration\": \"完整30到45字口語台詞，分成兩三句話講清楚\", \"headline\": \"12字內大標題\", \"sub_caption\": \"18字內副標\", \"highlight_badge\": \"具體數據\", \"nodes\": [{\"label\": \"重點\", \"sub\": \"白話說明\", \"tag\": \"數據\", \"icon\": \"zap\"}], \"ai_image_prompt\": \"distinct English 3D dark studio diorama prompt\", \"source_ids\": [\"S1\"], \"is_cta\": false}]}"
        )
        try:
            short_plan = self._call_llm_json(sys_prompt, pass3_prompt, max_tokens=2400)
        except Exception:
            short_plan = {}
        raw_sbeats = short_plan.get("short_beats") or plan_data.get("short_beats") or []
        short_beats: list[ShortBeatSpec] = []
        chapter_anchor_beats = all_beats[:: max(1, len(all_beats) // 6)][:6]
        for idx in range(7):
            sb = raw_sbeats[idx] if idx < len(raw_sbeats) and isinstance(raw_sbeats[idx], dict) else {}
            is_cta = (idx == 6) or bool(sb.get("is_cta") and idx >= 5)
            slt = "short_funnel_cta" if is_cta else sb.get("layout_type", SHORT_LAYOUTS[idx % 5])
            if slt not in SHORT_LAYOUTS:
                slt = SHORT_LAYOUTS[idx % 5]
            if idx == 2 and screenshot_sids:
                slt = "short_live_source_proof"
            ref_b = chapter_anchor_beats[min(idx, len(chapter_anchor_beats) - 1)]
            raw_narr = taiwanize_text(str(sb.get("narration") or ""))
            s_clauses = split_into_clauses(raw_narr, target_max=19)
            # Guarantee rich 24–45 char spoken sentences per Short beat (never 4-char fragments!)
            if is_cta and sum(len(c) for c in s_clauses) < 22:
                s_clauses = [
                    "完整實戰步驟與避坑細節我都整理在長片裡了",
                    "現在直接點擊畫面左下角關聯影片看完整版",
                ]
            elif sum(len(c) for c in s_clauses) < 18:
                s_clauses = ref_b.clauses[:3]
            snodes: list[VisualNode] = []
            for nd in (sb.get("nodes") or [])[:3]:
                if isinstance(nd, dict) and nd.get("label"):
                    ic = str(nd.get("icon") or "zap").lower()
                    snodes.append(
                        VisualNode(
                            label=taiwanize_text(str(nd["label"]))[:16],
                            sub=taiwanize_text(str(nd.get("sub") or ""))[:22],
                            tag=taiwanize_text(str(nd.get("tag") or ""))[:14],
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
                    headline=taiwanize_text(str(sb.get("headline") or ("點擊左下角看完整教學" if is_cta else ref_b.visual_title)))[:15],
                    sub_caption=taiwanize_text(str(sb.get("sub_caption") or ref_b.visual_subtitle))[:24],
                    highlight_badge=taiwanize_text(str(sb.get("highlight_badge") or ("完整長片已上線" if is_cta else ref_b.badge_text)))[:16],
                    nodes=snodes,
                    ai_image_prompt=clean_ai_prompt(str(sb.get("ai_image_prompt") or ""), topic.primary_entity, idx + 20),
                    source_ids=sids,
                    is_cta=is_cta,
                )
            )

        ep_title = taiwanize_text(str(plan_data.get("title") or topic.title))
        s_title = taiwanize_text(str(short_plan.get("short_title") or plan_data.get("short_title") or f"{ep_title[:22]}｜精華速看 #Shorts"))
        if "#Shorts" not in s_title and "#shorts" not in s_title:
            s_title = f"{s_title} #Shorts"
        return EpisodeScript(
            episode_id=episode_id,
            title=ep_title,
            category=topic.category,
            avatar_mode=(topic.category == "us_stocks"),
            youtube_description_summary=taiwanize_text(str(plan_data.get("youtube_description_summary") or topic.hook_angle)),
            hashtags=[str(h) for h in (plan_data.get("hashtags") or ["#AIAgent", "#AI教學", "#GaryChen", "#自動化", "#Shorts"])[:6]],
            chapters=[f"{i + 1:02d} {taiwanize_text(t)}" for i, t in enumerate(all_chapter_titles)],
            beats=all_beats,
            short_title=s_title,
            short_hook_banner=taiwanize_text(str(short_plan.get("short_hook_banner") or plan_data.get("short_hook_banner") or all_chapter_titles[0]))[:10],
            short_cta_target_title=ep_title,
            short_beats=short_beats,
        )
