from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .config import CrawledSource, EpisodeScript, SceneLayoutType, SceneSpec, ShortSceneSpec, TopicCandidate

ALL_LAYOUTS: list[SceneLayoutType] = [
    "hero_comparison_cards",
    "hub_spoke_ecosystem",
    "split_ai_illustration_callout",
    "step_pipeline_flow",
    "terminal_code_window",
    "crawled_evidence_spotlight",
    "checklist_architecture_box",
    "versus_debate_matrix",
]


def space_pad_english(text: str) -> str:
    """Match Garychen's subtitle typography: clean spaces between CJK and English/numbers, no trailing period."""
    t = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9$%+])", r"\1 \2", text)
    t = re.sub(r"([A-Za-z0-9%])([\u4e00-\u9fff])", r"\1 \2", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.rstrip("。.")
    return t


def split_to_subtitle_lines(paragraph: str, max_chars: int = 22) -> list[str]:
    parts = re.split(r"[。！？；!?\n]+|，(?=.{8,})", paragraph)
    lines: list[str] = []
    for raw in parts:
        s = space_pad_english(raw.strip(" ，、：:"))
        if not s:
            continue
        if len(s) <= max_chars + 6:
            lines.append(s)
        else:
            # Split long clauses cleanly at comma or space
            subparts = re.split(r"[，、,]+", s)
            buf = ""
            for sp in subparts:
                sp = sp.strip()
                if not sp:
                    continue
                if not buf:
                    buf = sp
                elif len(buf) + 1 + len(sp) <= max_chars + 4:
                    buf = f"{buf}，{sp}"
                else:
                    lines.append(space_pad_english(buf))
                    buf = sp
            if buf:
                lines.append(space_pad_english(buf))
    return [ln for ln in lines if ln]


class GarychenScriptwriter:
    """Generates authentic @garychenai long-form + corresponding funnel Shorts scripts grounded in crawled sources."""

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434", ollama_model: str = "qwen3:8b"):
        self.ollama_url = os.environ.get("GC_OLLAMA_URL", ollama_url).rstrip("/")
        self.ollama_model = os.environ.get("GC_OLLAMA_MODEL", ollama_model)
        self.openai_base = os.environ.get("GC_LLM_BASE_URL", "").rstrip("/")
        self.openai_key = os.environ.get("GC_LLM_API_KEY", "")
        self.openai_model = os.environ.get("GC_LLM_MODEL", "gpt-4.1")

    def _call_llm_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        # 1. Optional OpenAI-compatible endpoint if configured
        if self.openai_base and self.openai_key:
            try:
                with httpx.Client(timeout=90.0) as client:
                    r = client.post(
                        f"{self.openai_base}/chat/completions",
                        headers={"Authorization": f"Bearer {self.openai_key}"},
                        json={
                            "model": self.openai_model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.55,
                        },
                    )
                    if r.status_code == 200:
                        txt = r.json()["choices"][0]["message"]["content"]
                        return self._extract_json(txt)
            except Exception:
                pass

        # 2. Local Ollama Qwen3:8b (runs 100% unattended on Apple M3 Pro GPU)
        with httpx.Client(timeout=180.0) as client:
            r = client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "options": {"temperature": 0.55, "num_ctx": 8192, "num_predict": 4096},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "{}")
            return self._extract_json(content)

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        s = raw.find("{")
        e = raw.rfind("}")
        if s >= 0 and e > s:
            return json.loads(raw[s : e + 1])
        return json.loads(raw)

    def generate_episode_script(
        self,
        topic: TopicCandidate,
        sources: list[CrawledSource],
        episode_id: str,
        num_chapters: int = 6,
    ) -> EpisodeScript:
        source_digest = []
        for s in sources[:8]:
            source_digest.append(
                {
                    "source_id": s.source_id,
                    "domain": s.domain,
                    "title": s.title,
                    "date": s.published_date,
                    "facts": s.key_facts[:3],
                    "metrics": s.metrics[:3],
                }
            )

        system_prompt = (
            "你是台灣頂尖 AI 與科技商業頻道「Gary Chen (@garychenai)」的專屬總編劇與視覺分鏡導演。\n"
            "你的文風特徵：\n"
            "1. 繁體中文（台灣用語：專案、套件、資料、伺服器、程式碼、介面、資訊欄、留言區），語氣像聰明務實的朋友用最白話方式拆解複雜技術與商業邏輯。\n"
            "2. 開場前 15 秒直接切入觀眾痛點或市場反差，絕不廢話；常以「我們的主角 Gary」舉生活化實戰例子。\n"
            "3. 必須自然融入爬蟲抓到的真實公開資訊與數據（例如 GitHub Stars、HN 討論熱度、論文數據或官方規格），並在每個場景標註對應的 source_ids（如 [\"S1\"]）。\n"
            "4. 同時產出一部 16:9 完整教學長片（6 個章節，共 6 個高密度精華視覺場景）以及一部對應推流長片的 9:16 YouTube Shorts 短片（4 個垂直場景，最後一幕明確引導點擊左下角關聯影片看完整長片）。\n"
            "請嚴格輸出符合結構的 JSON 物件。"
        )

        user_prompt = (
            f"主題：{topic.title}\n"
            f"分類：{topic.category}\n"
            f"切入鉤子：{topic.hook_angle}\n"
            f"已爬取公開資訊與來源清單（請務必引用真實數據並填寫 source_ids）：\n"
            f"{json.dumps(source_digest, ensure_ascii=False, indent=2)}\n\n"
            "請輸出以下 JSON 欄位：\n"
            "{\n"
            '  "title": "吸引點擊的 Gary Chen 風格長片標題",\n'
            '  "youtube_description_summary": "120字內精華影片介紹",\n'
            '  "hashtags": ["#AIAgent", "#AI教學", ...],\n'
            '  "scenes": [\n'
            "    {\n"
            '      "chapter_index": 1,\n'
            '      "chapter_title": "4到7字章節名",\n'
            '      "layout_type": "hero_comparison_cards | hub_spoke_ecosystem | split_ai_illustration_callout | step_pipeline_flow | terminal_code_window | crawled_evidence_spotlight | checklist_architecture_box | versus_debate_matrix",\n'
            '      "voice_style": "hook | explainer | warm",\n'
            '      "narration": "約 65 到 95 字的白話口播稿，自然提到公開數據或來源觀察",\n'
            '      "visual_title": "畫面主標題 (12字內)",\n'
            '      "visual_subtitle": "畫面副標題 (18字內)",\n'
            '      "badge_text": "右上或卡片重點數據標籤 (如 免費 / 35K+ Stars / 省 80% 時間)",\n'
            '      "nodes": [{"label": "節點或步驟標題", "sub": "簡短說明", "tag": "數據或狀態"}],\n'
            '      "callout_title": "重點框標題",\n'
            '      "callout_body": "重點框一句話結論",\n'
            '      "ai_image_prompt": "English visual prompt describing a clean modern 3D isometric tech object or conceptual illustration, no text",\n'
            '      "source_ids": ["S1"]\n'
            "    }\n"
            "  ],\n"
            '  "short_title": "對應推流長片的 Shorts 標題 #Shorts",\n'
            '  "short_hook_banner": "Shorts 頂部 8 字內爆點標題",\n'
            '  "short_scenes": [\n'
            "    {\n"
            '      "voice_style": "hook | explainer | warm",\n'
            '      "narration": "約 25 到 40 字的快節奏口播",\n'
            '      "headline": "畫面大字重點",\n'
            '      "highlight_badge": "數據亮點標籤",\n'
            '      "bullet_points": ["重點一", "重點二"],\n'
            '      "ai_image_prompt": "English prompt for vertical 3D tech spot visual, no text",\n'
            '      "source_ids": ["S1"],\n'
            '      "is_cta": false\n'
            "    }\n"
            "  ]\n"
            "}\n"
            f"注意：scenes 請剛好給出 {num_chapters} 個章節場景（每個章節不同 layout_type），short_scenes 請給出 4 個場景且最後一個 is_cta 為 true 並引導觀眾點左下角看完整長片！"
        )

        raw_data: dict[str, Any] = {}
        try:
            raw_data = self._call_llm_json(system_prompt, user_prompt)
        except Exception as exc:
            print(f"[scriptwriter] LLM fallback synthesis triggered ({exc})", flush=True)

        return self._normalize_and_validate(raw_data, topic, sources, episode_id, num_chapters)

    def _normalize_and_validate(
        self,
        raw: dict[str, Any],
        topic: TopicCandidate,
        sources: list[CrawledSource],
        episode_id: str,
        num_chapters: int,
    ) -> EpisodeScript:
        valid_sids = {s.source_id for s in sources} or {"S1"}
        default_sid = sources[0].source_id if sources else "S1"

        raw_scenes = raw.get("scenes") if isinstance(raw.get("scenes"), list) else []
        scenes: list[SceneSpec] = []

        for idx in range(num_chapters):
            rs = raw_scenes[idx] if idx < len(raw_scenes) and isinstance(raw_scenes[idx], dict) else {}
            layout = rs.get("layout_type")
            if layout not in ALL_LAYOUTS:
                layout = ALL_LAYOUTS[idx % len(ALL_LAYOUTS)]
            src_for_scene = sources[idx % len(sources)] if sources else None
            default_fact = src_for_scene.key_facts[0] if (src_for_scene and src_for_scene.key_facts) else topic.why_now
            narration_raw = rs.get("narration") or (
                f"第 {idx + 1} 個重點我們來看實戰細節。根據 {src_for_scene.domain if src_for_scene else '公開資料'} 的最新數據，{default_fact}。"
                "對我們日常工作流來說，這能大幅減少重複踩坑的時間。"
            )
            if isinstance(rs.get("narration_lines"), list) and rs["narration_lines"]:
                lines = [space_pad_english(str(x)) for x in rs["narration_lines"] if str(x).strip()]
            else:
                lines = split_to_subtitle_lines(str(narration_raw))
            if not lines:
                lines = [space_pad_english(topic.hook_angle)]

            raw_nodes = rs.get("nodes") if isinstance(rs.get("nodes"), list) else []
            norm_nodes: list[dict] = []
            for nd in raw_nodes[:5]:
                if isinstance(nd, dict):
                    norm_nodes.append(
                        {
                            "label": str(nd.get("label") or nd.get("title") or "關鍵環節")[:20],
                            "sub": str(nd.get("sub") or nd.get("desc") or "")[:28],
                            "tag": str(nd.get("tag") or nd.get("badge") or "")[:16],
                        }
                    )
            if len(norm_nodes) < 3:
                metrics = (src_for_scene.metrics if src_for_scene else []) or ["自動化", "高效率", "可驗證"]
                norm_nodes = [
                    {"label": "痛點拆解", "sub": "傳統手動流程耗時易錯", "tag": metrics[0] if len(metrics) > 0 else "Step 1"},
                    {"label": "核心架構", "sub": "標準化串接工具與上下文", "tag": metrics[1] if len(metrics) > 1 else "Step 2"},
                    {"label": "實戰落地", "sub": "自動執行檢查與結果驗證", "tag": metrics[2] if len(metrics) > 2 else "Step 3"},
                ]

            sids = [s for s in (rs.get("source_ids") or []) if s in valid_sids]
            if not sids and src_for_scene:
                sids = [src_for_scene.source_id]

            v_style = rs.get("voice_style") if rs.get("voice_style") in ("hook", "explainer", "warm") else (
                "hook" if idx == 0 else ("warm" if idx == num_chapters - 1 else "explainer")
            )

            scenes.append(
                SceneSpec(
                    scene_id=f"scene_{idx + 1:02d}",
                    chapter_index=idx + 1,
                    total_chapters=num_chapters,
                    chapter_title=str(rs.get("chapter_title") or f"核心解析 {idx + 1}")[:12],
                    layout_type=layout,
                    voice_style=v_style,  # type: ignore[arg-type]
                    narration_lines=lines,
                    visual_title=str(rs.get("visual_title") or topic.title[:16])[:22],
                    visual_subtitle=str(rs.get("visual_subtitle") or default_fact[:24])[:34],
                    badge_text=str(rs.get("badge_text") or ((src_for_scene.metrics[0] if src_for_scene and src_for_scene.metrics else "實戰必學")))[:18],
                    nodes=norm_nodes,
                    callout_title=str(rs.get("callout_title") or "Gary 實戰筆記")[:18],
                    callout_body=str(rs.get("callout_body") or lines[-1])[:46],
                    ai_image_prompt=str(
                        rs.get("ai_image_prompt")
                        or f"3D isometric dark studio icon of {topic.category} workflow automation glowing amber nodes"
                    ),
                    source_ids=sids,
                )
            )

        # Normalize Shorts funnel script (4 crisp vertical scenes funneling to the long video)
        raw_shorts = raw.get("short_scenes") if isinstance(raw.get("short_scenes"), list) else []
        short_scenes: list[ShortSceneSpec] = []
        for idx in range(4):
            ss = raw_shorts[idx] if idx < len(raw_shorts) and isinstance(raw_shorts[idx], dict) else {}
            is_cta = idx == 3 or bool(ss.get("is_cta"))
            src_for_s = sources[idx % len(sources)] if sources else None
            if is_cta and idx == 3:
                default_s_narr = "這套架構還有三個新手最容易踩坑的細節，我已經把完整實戰步驟跟公開數據整理在長片裡，馬上點擊左下角關聯影片看完整版！"
            elif idx == 0:
                default_s_narr = topic.hook_angle
            else:
                default_s_narr = "，".join(scenes[min(idx, len(scenes) - 1)].narration_lines[:2])
            s_lines = split_to_subtitle_lines(str(ss.get("narration") or default_s_narr), max_chars=16)
            bullets = [str(b)[:20] for b in (ss.get("bullet_points") or []) if str(b).strip()][:3]
            if not bullets:
                bullets = [nd["label"] + "：" + nd["sub"][:10] for nd in scenes[min(idx, len(scenes) - 1)].nodes[:3]]
            sids = [s for s in (ss.get("source_ids") or []) if s in valid_sids]
            if not sids and src_for_s:
                sids = [src_for_s.source_id]
            short_scenes.append(
                ShortSceneSpec(
                    scene_id=f"short_{idx + 1:02d}",
                    voice_style="hook" if idx == 0 else ("warm" if is_cta else "explainer"),
                    narration_lines=s_lines,
                    headline=str(ss.get("headline") or ("點擊左下角看完整教學" if is_cta else scenes[min(idx, len(scenes) - 1)].visual_title))[:16],
                    highlight_badge=str(ss.get("highlight_badge") or ("完整長片已上線" if is_cta else scenes[min(idx, len(scenes) - 1)].badge_text))[:16],
                    bullet_points=bullets,
                    ai_image_prompt=str(
                        ss.get("ai_image_prompt")
                        or f"vertical sleek 3D glowing AI agent cube module dark studio amber rim light, scene {idx + 1}"
                    ),
                    source_ids=sids or [default_sid],
                    is_cta= (idx == 3),
                )
            )

        ep_title = str(raw.get("title") or topic.title)
        return EpisodeScript(
            episode_id=episode_id,
            title=ep_title,
            category=topic.category,
            avatar_mode=(topic.category == "us_stocks"),
            youtube_description_summary=str(raw.get("youtube_description_summary") or topic.hook_angle),
            hashtags=[str(h) for h in (raw.get("hashtags") or ["#AIAgent", "#AI教學", "#GaryChen", "#自動化工作流", "#Shorts"])[:6]],
            chapters=[f"{sc.chapter_index:02d} {sc.chapter_title}" for sc in scenes],
            scenes=scenes,
            short_title=str(raw.get("short_title") or f"{ep_title[:28]}｜精華速看 #Shorts"),
            short_hook_banner=str(raw.get("short_hook_banner") or scenes[0].chapter_title)[:12],
            short_cta_target_title=ep_title,
            short_scenes=short_scenes,
        )
