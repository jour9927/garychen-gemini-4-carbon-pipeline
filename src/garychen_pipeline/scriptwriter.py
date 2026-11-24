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


def space_pad_english(text: str) -> str:
    t = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9$%+])", r"\1 \2", text)
    t = re.sub(r"([A-Za-z0-9%])([\u4e00-\u9fff])", r"\1 \2", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("。.！!；;")


def split_into_clauses(text: str, target_max: int = 18) -> list[str]:
    raw_parts = re.split(r"[。！？；!?\n]+|，", text)
    clauses: list[str] = []
    for p in raw_parts:
        s = space_pad_english(p.strip(" 、：:「」"))
        if not s:
            continue
        if len(s) <= target_max + 5:
            clauses.append(s)
        else:
            # Split cleanly near middle space or CJK boundary
            mid = len(s) // 2
            sp = s.find(" ", mid - 4, mid + 6)
            if sp != -1:
                clauses.extend([s[:sp].strip(), s[sp + 1 :].strip()])
            else:
                clauses.extend([s[:target_max].strip(), s[target_max:].strip()])
    return [c for c in clauses if c][:5]


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

                narr_str = str(rb.get("narration") or "").strip()
                clauses = split_into_clauses(narr_str, target_max=18)
                if len(clauses) < 2:
                    clauses = split_into_clauses(f"{c_title}其實沒有想像中複雜，我們直接拆開來看最核心的做法", target_max=18)

                v_nodes: list[VisualNode] = []
                for nd in (rb.get("nodes") or [])[:4]:
                    if isinstance(nd, dict) and nd.get("label"):
                        ic = str(nd.get("icon") or "sparkles").lower()
                        if ic not in VALID_ICONS:
                            ic = "sparkles"
                        tr = str(nd.get("trend") or "neutral").lower()
                        if tr not in ("up", "down", "neutral"):
                            tr = "neutral"
                        v_nodes.append(
                            VisualNode(
                                label=str(nd["label"])[:18],
                                sub=str(nd.get("sub") or "")[:28],
                                tag=str(nd.get("tag") or "")[:16],
                                icon=ic,
                                trend=tr,  # type: ignore[arg-type]
                            )
                        )
                # If chapter_roadmap_agenda has < 4 nodes, populate with actual chapter titles!
                if lt == "chapter_roadmap_agenda" and len(v_nodes) < 4:
                    v_nodes = [
                        VisualNode(label=ct, sub=chapters_plan[i].get("focus", "")[:16], tag=f"0{i+1}", icon="layers")
                        for i, ct in enumerate(all_chapter_titles[:4])
                    ]
                elif len(v_nodes) < 2:
                    src0 = sources[(c_idx - 1) % max(1, len(sources))] if sources else None
                    m0 = src0.metrics[0] if (src0 and src0.metrics) else "關鍵指標"
                    v_nodes = [
                        VisualNode(label=topic.primary_entity[:16], sub=clauses[0][:22], tag=m0, icon="zap", trend="up"),
                        VisualNode(label=c_title, sub=clauses[-1][:22], tag="實戰重點", icon="check", trend="neutral"),
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
                        chapter_title=c_title,
                        layout_type=lt,
                        voice_style=v_style,  # type: ignore[arg-type]
                        clauses=clauses,
                        visual_title=str(rb.get("visual_title") or c_title)[:20],
                        visual_subtitle=str(rb.get("visual_subtitle") or "")[:34],
                        badge_text=str(rb.get("badge_text") or "")[:18],
                        nodes=v_nodes,
                        callout_title=str(rb.get("callout_title") or "Gary 實戰重點")[:18],
                        callout_body=str(rb.get("callout_body") or clauses[-1])[:42],
                        code_lines=code_lns,
                        ai_image_prompt=str(
                            rb.get("ai_image_prompt")
                            or f"isometric 3D dark matte studio diorama illustrating {topic.primary_entity} {c_title}"
                        ),
                        source_ids=sids,
                        sfx_cue=sfx,  # type: ignore[arg-type]
                    )
                )

        # Normalize Shorts Funnel Beats (6–8 fast progressive vertical beats, ending with CTA!)
        raw_sbeats = plan_data.get("short_beats") or []
        short_beats: list[ShortBeatSpec] = []
        for idx, sb in enumerate(raw_sbeats[:7]):
            if not isinstance(sb, dict):
                continue
            is_cta = (idx == len(raw_sbeats[:7]) - 1) or bool(sb.get("is_cta"))
            slt = "short_funnel_cta" if is_cta else sb.get("layout_type", SHORT_LAYOUTS[idx % 5])
            if slt not in SHORT_LAYOUTS:
                slt = SHORT_LAYOUTS[idx % 5]
            s_clauses = split_into_clauses(str(sb.get("narration") or ""), target_max=15)
            if not s_clauses:
                s_clauses = ["點擊左下角關聯影片", "直接看完整實戰教學"] if is_cta else all_beats[min(idx, len(all_beats) - 1)].clauses[:2]
            snodes: list[VisualNode] = []
            for nd in (sb.get("nodes") or [])[:3]:
                if isinstance(nd, dict) and nd.get("label"):
                    ic = str(nd.get("icon") or "zap").lower()
                    snodes.append(
                        VisualNode(
                            label=str(nd["label"])[:16],
                            sub=str(nd.get("sub") or "")[:22],
                            tag=str(nd.get("tag") or "")[:14],
                            icon=ic if ic in VALID_ICONS else "zap",
                        )
                    )
            if not snodes:
                snodes = all_beats[min(idx, len(all_beats) - 1)].nodes[:3]
            sids = [s for s in (sb.get("source_ids") or []) if s in valid_sids]
            if not sids and sources:
                sids = [sources[idx % len(sources)].source_id]
            short_beats.append(
                ShortBeatSpec(
                    beat_id=f"sbeat_{len(short_beats) + 1:02d}",
                    layout_type=slt,  # type: ignore[arg-type]
                    voice_style="hook" if idx == 0 else ("warm" if is_cta else "explainer"),
                    clauses=s_clauses,
                    headline=str(sb.get("headline") or ("點擊左下角看完整版" if is_cta else all_beats[min(idx, len(all_beats) - 1)].visual_title))[:15],
                    sub_caption=str(sb.get("sub_caption") or "")[:24],
                    highlight_badge=str(sb.get("highlight_badge") or ("完整教學已上線" if is_cta else all_beats[min(idx, len(all_beats) - 1)].badge_text))[:16],
                    nodes=snodes,
                    ai_image_prompt=str(sb.get("ai_image_prompt") or f"vertical sleek 3D dark studio diorama of {topic.primary_entity}, beat {idx+1}"),
                    source_ids=sids,
                    is_cta=is_cta,
                )
            )

        if not short_beats or not short_beats[-1].is_cta:
            short_beats.append(
                ShortBeatSpec(
                    beat_id=f"sbeat_{len(short_beats) + 1:02d}",
                    layout_type="short_funnel_cta",
                    voice_style="warm",
                    clauses=["完整步驟與避坑細節都整理在長片裡", "馬上點擊左下角關聯影片看完整版"],
                    headline="點擊左下角看完整教學",
                    sub_caption="含完整公開數據來源與實戰設定",
                    highlight_badge="完整長片已上線",
                    nodes=all_beats[0].nodes[:2],
                    source_ids=[sources[0].source_id] if sources else ["S1"],
                    is_cta=True,
                )
            )

        ep_title = str(plan_data.get("title") or topic.title)
        return EpisodeScript(
            episode_id=episode_id,
            title=ep_title,
            category=topic.category,
            avatar_mode=(topic.category == "us_stocks"),
            youtube_description_summary=str(plan_data.get("youtube_description_summary") or topic.hook_angle),
            hashtags=[str(h) for h in (plan_data.get("hashtags") or ["#AIAgent", "#AI教學", "#GaryChen", "#自動化", "#Shorts"])[:6]],
            chapters=[f"{i + 1:02d} {t}" for i, t in enumerate(all_chapter_titles)],
            beats=all_beats,
            short_title=str(plan_data.get("short_title") or f"{ep_title[:24]}｜精華速看 #Shorts"),
            short_hook_banner=str(plan_data.get("short_hook_banner") or all_chapter_titles[0])[:10],
            short_cta_target_title=ep_title,
            short_beats=short_beats,
        )
