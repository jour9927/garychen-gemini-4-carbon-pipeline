from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import (
    BeatLayoutType,
    CONFIGS_DIR,
    CrawledSource,
    EpisodeScript,
    PROJECT_ROOT,
    ShortBeatLayoutType,
    ShortBeatSpec,
    TopicCandidate,
    VisualBeat,
    VisualNode,
)
from .tts_normalizer import to_spoken_tts_text

TUTORIAL_CHAPTER_LAYOUT_MAP: list[list[BeatLayoutType]] = [
    ["app_squircles_strikethrough", "claude_chat_dialog", "slash_command_prompt_bar", "browser_ui_live_tour", "agenda_four_steps"],
    ["ecosystem_node_graph", "code_editor_live_preview", "browser_ui_live_tour", "slash_command_prompt_bar", "concept_hero_split_3d"],
    ["protagonist_app_flow", "claude_chat_dialog", "browser_ui_live_tour", "code_editor_live_preview", "before_after_workflow_card"],
    ["claude_chat_dialog", "code_editor_live_preview", "browser_ui_live_tour", "github_pr_blast_radius", "ecosystem_node_graph"],
    ["swarm_subagents_grid", "ecosystem_node_graph", "code_editor_live_preview", "browser_ui_live_tour", "github_pr_blast_radius"],
    ["before_after_workflow_card", "animated_growth_curve", "stocks_kpi_asymmetric", "browser_ui_live_tour", "second_level_thinking_crowd"],
    ["second_level_thinking_crowd", "moat_shield_architecture", "github_pr_blast_radius", "concept_hero_split_3d", "stocks_big_statement"],
]

STOCKS_CHAPTER_LAYOUT_MAP: list[list[BeatLayoutType]] = [
    ["stocks_kpi_asymmetric", "animated_growth_curve", "browser_ui_live_tour", "second_level_thinking_crowd", "stocks_four_pillars"],
    ["ecosystem_node_graph", "stocks_kpi_asymmetric", "operating_leverage_chart", "browser_ui_live_tour", "stocks_big_statement"],
    ["stocks_kpi_asymmetric", "browser_ui_live_tour", "animated_growth_curve", "operating_leverage_chart", "before_after_workflow_card"],
    ["second_level_thinking_crowd", "stocks_kpi_asymmetric", "operating_leverage_chart", "browser_ui_live_tour", "ecosystem_node_graph"],
    ["moat_shield_architecture", "ecosystem_node_graph", "stocks_four_pillars", "before_after_workflow_card", "concept_hero_split_3d"],
    ["stocks_valuation_scenarios", "animated_growth_curve", "stocks_kpi_asymmetric", "before_after_workflow_card", "stocks_big_statement"],
    ["stocks_four_pillars", "second_level_thinking_crowd", "moat_shield_architecture", "stocks_kpi_asymmetric", "stocks_big_statement"],
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


def resolve_agy_cli() -> str | None:
    cand = shutil.which("agy")
    if cand and Path(cand).exists():
        return cand
    for p in (Path.home() / ".local/bin/agy", Path("/opt/homebrew/bin/agy"), Path("/usr/local/bin/agy")):
        if p.exists():
            return str(p)
    return None


def load_gemini_api_key() -> tuple[str, str]:
    """Checks local `agy` CLI first, then optional GEMINI_API_KEY in `.env` / environment."""
    env_file = PROJECT_ROOT / ".env"
    file_vars: dict[str, str] = {}
    if env_file.exists():
        for raw_ln in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            ln = raw_ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            file_vars[k.strip()] = v.strip().strip("\"'")

    cfg_json = CONFIGS_DIR / "gemini.json"
    if cfg_json.exists():
        try:
            jd = json.loads(cfg_json.read_text(encoding="utf-8"))
            if jd.get("api_key"):
                file_vars.setdefault("GEMINI_API_KEY", str(jd["api_key"]).strip())
            if jd.get("model"):
                file_vars.setdefault("GC_GEMINI_MODEL", str(jd["model"]).strip())
        except Exception:
            pass

    key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or file_vars.get("GEMINI_API_KEY")
        or file_vars.get("GOOGLE_API_KEY")
        or ""
    ).strip()
    if key == "your_gemini_api_key_here":
        key = ""
    model = (os.environ.get("GC_GEMINI_MODEL") or file_vars.get("GC_GEMINI_MODEL") or "agy:gemini-4-carbon").strip()
    return key, model


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
    s = taiwanize_text(text).strip()
    s = re.sub(r"^(?:哈囉|嗨|嘿)?\s*(?:大家好|各位觀眾|各位朋友)[，,！!。]*\s*(?:我是\s*Gary[，,！!。]*)?", "", s)
    s = re.sub(r"^(?:歡迎回到我的頻道|歡迎來到\s*Gary\s*的頻道)[，,！!。]*", "", s)
    s = re.sub(r"[，,。！!]*\s*(?:走起|衝吧|讓我們開始吧|話不多說馬上開始)[！!。]*$", "", s)
    return s.strip(" ，,")


def smart_trim(text: str, max_units: float = 9.5) -> str:
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
    cleaned_src = re.sub(r"第[一二三四五12345]幕講[^，。！？；]+[，。；]?", "", cleaned_src)
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
    V5 Cloud Gemini Master Scriptwriter via Local `agy` CLI (ZERO local 8B Ollama!):
      - Primary engine: Local `agy` CLI (`--disable-slash-commands --mode plan -p`) running Google Gemini 4
        inside a trusted clean sandbox directory (`PROJECT_ROOT / ".worker_mps/agy_sandbox"`).
      - Pass 1 (1 Unified Master Narrative Pass): Writes all 7 chapters × 5 progressive beats (= 35 Long beats,
        ~3,200–3,600 chars -> 7.5–9.5 min deep @garychenai storytelling!) + 10-beat Funnel Short script in one
        coherent creative arc!
      - Pass 2 (Parallel 2-way `ThreadPoolExecutor` Scene Compiler): Compiles all 35 beats into structured
        Remotion `VisualBeat` JSON with tight `<=9.5` unit card labels (zero single-char line wraps!).
    """

    def __init__(self, agy_model: str | None = None):
        self.agy_bin = resolve_agy_cli()
        self.api_key, cfg_model = load_gemini_api_key()
        self.agy_model = agy_model or os.environ.get("GC_AGY_MODEL", "").strip()
        self.gemini_model = cfg_model if not cfg_model.startswith("agy:") else "gemini-2.5-pro"
        self.sandbox_dir = PROJECT_ROOT / ".worker_mps/agy_sandbox"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    def _call_agy_cli(self, system_prompt: str, user_prompt: str, effort: str = "medium", timeout_s: int = 180) -> str:
        if not self.agy_bin:
            raise RuntimeError("`agy` CLI binary not found.")
        combined = (
            f"【系統角色與嚴格輸出規範】\n{system_prompt}\n"
            "⚠️ 重要：請直接輸出最終文字或 JSON 內容，絕對不要呼叫任何工具、不要讀寫任何檔案、不要加前後寒暄解釋！\n\n"
            f"【任務內容】\n{user_prompt}"
        )
        models_to_try = [self.agy_model, None] if self.agy_model else [None]
        last_err = ""
        for mdl in models_to_try:
            for attempt in range(2):
                cmd = [
                    self.agy_bin,
                    "--disable-slash-commands",
                    "--mode",
                    "plan",
                    "--effort",
                    effort,
                    "--print-timeout",
                    f"{timeout_s - 10}s",
                ]
                if mdl:
                    cmd.extend(["--model", mdl])
                cmd.extend(["-p", combined])
                t0 = time.time()
                try:
                    r = subprocess.run(
                        cmd,
                        cwd=str(self.sandbox_dir),
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=timeout_s,
                    )
                    out = (r.stdout or "").strip()
                    # Strip any terminal spinner escape sequences if present
                    out = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out).strip()
                    if r.returncode == 0 and len(out) >= 20:
                        print(f"  [agy-gemini] pass ok ({time.time() - t0:.1f}s, effort={effort}, chars={len(out)})", flush=True)
                        return out
                    last_err = (r.stderr or out or f"rc={r.returncode}")[:240]
                except Exception as exc:
                    last_err = str(exc)[:240]
                time.sleep(1.0)
        raise RuntimeError(f"agy CLI Gemini generation failed: {last_err}")

    def _call_llm_raw(
        self,
        system_prompt: str,
        user_prompt: str,
        effort: str = "medium",
        json_mode: bool = False,
    ) -> str:
        if self.agy_bin:
            return self._call_agy_cli(system_prompt, user_prompt, effort=effort, timeout_s=210)
        if self.api_key:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.api_key)
            cfg = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.42,
                max_output_tokens=8192,
                response_mime_type="application/json" if json_mode else "text/plain",
            )
            resp = client.models.generate_content(model=self.gemini_model, contents=user_prompt, config=cfg)
            return str(resp.text or "").strip()
        raise RuntimeError("Neither local `agy` CLI nor `GEMINI_API_KEY` is available (local Ollama is disabled).")

    def _call_llm_json(self, system_prompt: str, user_prompt: str, effort: str = "medium") -> dict[str, Any]:
        for attempt in range(3):
            raw = self._call_llm_raw(
                system_prompt,
                user_prompt + "\n\n請嚴格只輸出一個合法的純 JSON 物件（以 `{` 開頭、`}` 結尾，字串內引用請用『』不要用未跳脫雙引號，不要加 markdown 說明）！",
                effort=effort,
                json_mode=True,
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
        raise ValueError("No valid JSON object in Gemini output")

    def _genre_system_prompt(self, category: str) -> str:
        if category == "us_stocks":
            return (
                "你是台灣頂級科技與美股深度分析 YouTube 頻道「Gary Chen (@garychenai)」本人主筆。\n"
                "請 100% 還原 Gary 在《META 財報後下跌 10%，為什麼我反而加倉？》與《Google 估值大反轉》的敘事靈魂：\n"
                "- 開場第一句話直接切入市場恐慌情緒與真實 SEC 財報數據的巨大預期差，絕對不說『哈囉大家好』『我是 Gary』『走起』！\n"
                "- 善用『白話講就是…』『但如果我們換個角度進入第二層思考…』『這背後的營運槓桿邏輯其實很直白…』將複雜財報與技術壁壘講得一聽就懂、極具洞察力，絕不寫簡報條列式的破碎短句！\n"
                "- 全程道地台灣繁體中文財經科技語彙（營收、營業利益率、營運槓桿、營運現金流 OCF、資本支出 CapEx、本益比 PE、轉換成本、安全邊際）。"
            )
        return (
            "你是台灣頂級 AI Agent 與軟體工程教學 YouTube 頻道「Gary Chen (@garychenai)」本人主筆。\n"
            "請 100% 還原 Gary 在《Meta Muse 新手教學》、《pstack 一個月 2500 個 PR》與《用 AI 寫程式你得懂的 CI/CD》的敘事靈魂：\n"
            "- 開場第一句話直接切入開發者／工作者的真實痛點或訂閱費門檻，立刻亮出今天的主角工具與硬核星標數據，絕對不說『哈囉大家好』『我是 Gary』『走起』！\n"
            "- 句子自然連貫有故事感，善用『對非技術背景的朋友來說，白話講就是…』『我們一樣請出老朋友主角 Gary 舉個具體例子…』『把這道自動防線建立起來，才不會做 A 壞 B，陷入找 bug 打地鼠的無限迴圈』，絕不寫破碎簡報短句！\n"
            "- 全程道地台灣繁體中文開發者口語（專案、套件、資料夾、伺服器、終端機、資訊欄、踩坑），口語台詞內不要硬唸 http 網址或參數符號。"
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
        beats_per_chap = 5  # 35 rich progressive beats -> ~7.5 to 9.5 minutes deep @garychenai episode!

        src_digest = [
            {
                "source_id": s.source_id,
                "type": s.source_type,
                "domain": s.domain,
                "title": s.title,
                "date": s.published_date,
                "metrics": s.metrics[:6],
                "facts": s.key_facts[:6],
                "commands": s.code_or_commands[:5],
                "prs": s.pr_or_issue_items[:5],
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
        chapter_arc_guide = (
            "7 大章節深度脈絡：(1) 市場恐慌 vs SEC 年報成績單預期差；(2) 核心商業模式與算力變現飛輪；(3) 五年度營收與營業利益率的營運槓桿拆解；(4) 雲端巨頭 CapEx 的第一層直覺 vs 第二層思考；(5) 競爭對手最難跨越的三大護城河與轉換成本；(6) 本益比與現金流三種估值情境推演；(7) 必須緊盯的三大風險與『Gary 聊美股』免責聲明收尾。"
            if is_stocks
            else f"7 大章節深度脈絡：(1) 主流付費方案痛點 vs 開源主角 {topic.primary_entity} 破題與本集路線圖；(2) 為什麼傳統腳本一改版就壞？白話拆解底層雙引擎架構；(3) 主角 Gary 的完整生活／工作自動化實戰案例（把具體金額、步驟講出畫面感）；(4) 從零本機環境部署、安裝與跑通第一個自動任務；(5) 進階多模型串接、主控＋子 Agent 分工與 PR 把關防線；(6) 開源本機跑 vs 官方雲端版 vs 商業付費工具的成本與隱私權衡；(7) 新手最容易踩的三個實戰大坑與『AI 實戰營』招牌收尾。"
        )

        # PASS 1: Single Coherent Gemini 4 Master Scriptwriting Call (whole episode written in one breath!)
        pass1_prompt = (
            f"主題：{topic.title}\n"
            f"核心主角：{topic.primary_entity}\n"
            f"已爬蟲查證之公開權威資料：\n{json.dumps(src_digest, ensure_ascii=False, indent=2)}\n\n"
            f"{chapter_arc_guide}\n\n"
            f"請一氣呵成創作出完整、有深度、前後呼應的 Gary Chen 長片與對應推流 Shorts 腳本 JSON：\n"
            f"- 共 **7 個章節 (`chapters`)**，每個章節包含 **5 段 (`paragraphs`) 層層遞進、絕不重複的自然台灣口語逐字稿**（全片共 **35 段**）！\n"
            "- **每段口語逐字稿必填 85～115 個繁體中文字**（包含 3～4 個自然流暢、邏輯飽滿的句子，把查證數據、底層原因與生活比喻講透，嚴禁簡報式破碎短句）！\n"
            "- 同時附上 **10 幕對應推流 Shorts (`short_beats`)**，每幕 `narration` 30～42 字，第 10 幕明確引導點擊畫面左下角『關聯影片』看完整長片！\n"
            "輸出純 JSON 格式：\n"
            "{\n"
            '  "title": "極具點擊吸引力的完整 Gary Chen 長片標題(18-28字)",\n'
            '  "thumbnail_line1": "封面黃字第一行(4-7字)",\n'
            '  "thumbnail_line2": "封面白字第二行(4-7字)",\n'
            '  "youtube_description_summary": "150字內精華說明",\n'
            '  "hashtags": ["#GaryChen", "..."],\n'
            '  "chapters": [\n'
            '    {\n'
            '      "index": 1,\n'
            '      "chapter_title": "犀利章節標題(5-10字)",\n'
            '      "paragraphs": ["第1段85-115字完整口語...", "第2段...", "第3段...", "第4段...", "第5段..."]\n'
            '    }\n'
            '  ],\n'
            '  "short_title": "高張力短片標題 #Shorts",\n'
            '  "short_hook_banner": "6字內頂部標籤",\n'
            '  "short_beats": [\n'
            '    {"narration": "30-42字口語", "headline": "10字內標題", "sub_caption": "18字內副標", "highlight_badge": "數據標籤", "nodes": [{"label": "8字內名詞", "sub": "16字內說明", "tag": "數據", "icon": "robot"}]}\n'
            '  ]\n'
            "}"
        )
        master_doc = self._call_llm_json(sys_prompt, pass1_prompt, effort="medium")
        raw_chaps = (master_doc.get("chapters") or [])[:7]
        default_titles = (
            ["市場恐慌與真實成績單", "商業模式與算力飛輪", "五年財報與營運槓桿", "資本支出的第二層思考", "競爭對手難跨越護城河", "估值倍數與三情境推演", "三大風險與投資觀點"]
            if is_stocks
            else ["為什麼現在該認識它", "底層雙引擎白話拆解", "主角 Gary 的實戰案例", "三分鐘本機部署實測", "多代理分工與把關防線", "開源本機 vs 付費方案", "三個必避踩坑與總結"]
        )
        while len(raw_chaps) < 7:
            idx = len(raw_chaps)
            raw_chaps.append({"index": idx + 1, "chapter_title": default_titles[idx], "paragraphs": []})

        all_chapter_titles = [taiwanize_text(str(c.get("chapter_title") or default_titles[i]))[:14] for i, c in enumerate(raw_chaps)]
        pipeline_bar_labels = all_chapter_titles[1:6]
        layout_grid = STOCKS_CHAPTER_LAYOUT_MAP if is_stocks else TUTORIAL_CHAPTER_LAYOUT_MAP

        # Flatten all 35 (chapter_idx, chapter_title, beat_in_chap, layout_type, paragraph_text)
        flat_items: list[dict[str, Any]] = []
        for ch_pos, c_obj in enumerate(raw_chaps):
            paras = [scrub_slop_phrases(str(p)) for p in (c_obj.get("paragraphs") or []) if len(scrub_slop_phrases(str(p))) >= 24]
            while len(paras) < beats_per_chap:
                s_ref = sources[(ch_pos + len(paras)) % max(1, len(sources))] if sources else None
                f_ref = s_ref.key_facts[len(paras) % len(s_ref.key_facts)] if (s_ref and s_ref.key_facts) else topic.why_now
                paras.append(scrub_slop_phrases(f"接著我們把鏡頭拉近看公開查證的細節，{f_ref}，白話講這正是決定長期穩定度與報酬率的分水嶺。"))
            paras = paras[:beats_per_chap]

            if ch_pos == 6:
                if is_stocks and "Gary 聊美股" not in paras[-1]:
                    paras[-1] = (
                        "最後還是要提醒大家持續追蹤雲端巨頭自研晶片進度與毛利率變化，"
                        "如果你喜歡這種把 SEC 財報數字跟產業底層邏輯拆開來看的深度分析，"
                        "記得幫我按讚訂閱追蹤 Gary 聊美股，本片內容僅供研究參考不構成投資建議，我們下次見"
                    )
                elif not is_stocks and "AI 實戰營" not in paras[-1]:
                    paras[-1] = (
                        "那以上就是今天的完整實戰內容，感謝你看到這邊。如果鋪天蓋地的 AI 資訊讓你覺得眼花撩亂，"
                        "歡迎加入我在下方資訊欄整理的 AI 實戰營社群，這支影片用到的設定清單跟模板都在裡面，那我們下次見"
                    )

            for b_i in range(beats_per_chap):
                flat_items.append(
                    {
                        "global_idx": len(flat_items),
                        "chapter_index": ch_pos + 1,
                        "chapter_title": all_chapter_titles[ch_pos],
                        "beat_in_chap": b_i,
                        "layout_type": layout_grid[ch_pos][b_i],
                        "paragraph": paras[b_i],
                    }
                )

        # PASS 2: Parallel 2-Way Gemini Scene Choreographer (Beats 0..17 & Beats 18..34 simultaneously!)
        def _compile_half(batch_slice: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
            p_lines = [
                f"[{it['global_idx']}] 章節={it['chapter_title']} | 版型={it['layout_type']} | 台詞={it['paragraph']}"
                for it in batch_slice
            ]
            c_prompt = (
                "請將以下每一段定稿台詞編譯為高密度 Remotion 視覺分鏡卡片 JSON！\n"
                "⚠️ 排版鐵律：\n"
                "1. 每個 `nodes[j].label` 必須 **精簡在 4～8 個中文字以內**（絕對不可超過 9 個字，避免窄卡片單字折行）！\n"
                "2. `nodes` 必填 3～4 個具體真實專有名詞、財報科目或實戰步驟，嚴禁填『重點一』『自動化執行層』等空話！\n"
                f"3. 可選 `icon`：{sorted(VALID_ICONS)}\n"
                f"4. 查證來源摘要：{json.dumps(src_digest[:5], ensure_ascii=False)}\n\n"
                + "\n".join(p_lines)
                + "\n\n輸出 JSON 格式：\n"
                "{\n"
                '  "compiled": [\n'
                '    {\n'
                '      "global_idx": 0,\n'
                '      "visual_title": "6-13字精準畫面主標",\n'
                '      "visual_subtitle": "10-20字副標",\n'
                f'      "badge_text": "{"+65.5% YoY" if is_stocks else "$0 / 月"}",\n'
                '      "callout_title": "4-8字結論標籤",\n'
                '      "callout_body": "14-26字犀利結論",\n'
                '      "code_lines": ["真實指令或財報算式"],\n'
                '      "source_ids": ["S1"],\n'
                '      "nodes": [\n'
                '        {"label": "4-8字名詞", "sub": "10-18字白話說明", "tag": "短標籤", "metric": "含單位數據(如$2,159 億或60.4%)", "icon": "github", "trend": "up"}\n'
                '      ]\n'
                '    }\n'
                '  ]\n'
                "}"
            )
            try:
                res = self._call_llm_json(sys_prompt, c_prompt, effort="low")
                return {int(x["global_idx"]): x for x in (res.get("compiled") or []) if isinstance(x, dict) and "global_idx" in x}
            except Exception as exc:
                print(f"  [agy-gemini] batch compile fallback ({exc})", flush=True)
                return {}

        mid = len(flat_items) // 2
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_compile_half, flat_items[:mid])
            f2 = pool.submit(_compile_half, flat_items[mid:])
            compiled_map = {**f1.result(), **f2.result()}

        valid_sids = {s.source_id for s in sources} or {"S1"}
        cam_presets = [
            [0.38, 0.30, 1.32],
            [0.54, 0.46, 1.35],
            [0.44, 0.58, 1.28],
            [0.34, 0.40, 1.34],
            [0.58, 0.32, 1.30],
        ]
        scr_cursor = 0
        all_beats: list[VisualBeat] = []

        for item in flat_items:
            g_idx = item["global_idx"]
            c_idx = item["chapter_index"]
            c_title = item["chapter_title"]
            b_idx = item["beat_in_chap"]
            lt: BeatLayoutType = item["layout_type"]
            para = item["paragraph"]
            rb = compiled_map.get(g_idx, {})

            clauses = split_into_clauses(para, target_max=22)
            if len(clauses) < 2:
                clauses = [space_pad_english(para[:20]), space_pad_english(para[20:46] or c_title)]
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
                        g_idx + n_i,
                        ctx=f"{nd.get('label', '')} {nd.get('sub', '')}",
                    )
                    v_nodes.append(
                        VisualNode(
                            label=smart_trim(str(nd["label"]), 8.5),  # Strict <=8.5 units prevents single-char wrap!
                            sub=smart_trim(str(nd.get("sub") or clauses[min(n_i, len(clauses) - 1)]), 17.5),
                            tag=smart_trim(raw_tag, 8.5),
                            metric=raw_metric,
                            icon=ic,
                            trend=tr,  # type: ignore[arg-type]
                        )
                    )

            if lt == "agenda_four_steps":
                v_nodes = [
                    VisualNode(
                        label=smart_trim(all_chapter_titles[i + 1], 8.0),
                        sub=smart_trim(flat_items[(i + 1) * beats_per_chap]["paragraph"], 16.0),
                        tag=f"0{i+1}",
                        metric=f"0{i+1}",
                        icon=["layers", "users", "terminal", "robot"][i % 4],
                    )
                    for i in range(4)
                ]
            else:
                while len(v_nodes) < 3:
                    k = len(v_nodes)
                    src_k = sources[(c_idx + k) % max(1, len(sources))] if sources else None
                    cl_k = clauses[min(k, len(clauses) - 1)]
                    m_k = (src_k.metrics[k % len(src_k.metrics)] if (src_k and src_k.metrics) else (all_real_metrics[k % len(all_real_metrics)] if all_real_metrics else "+100%"))
                    lbl_k = smart_trim(cl_k.split("，")[0], 8.0) or (src_k.domain if src_k else topic.primary_entity)
                    v_nodes.append(
                        VisualNode(
                            label=lbl_k,
                            sub=smart_trim(cl_k, 17.0),
                            tag=smart_trim(m_k, 8.5),
                            metric=_ensure_numeric_metric(m_k, all_real_metrics, k, ctx=cl_k),
                            icon=("nvidia" if is_stocks else ("playwright" if k == 0 else "robot")),
                            trend="up" if k == 0 else "neutral",
                        )
                    )

            sids = [s for s in (rb.get("source_ids") or []) if s in valid_sids]
            scr_override = ""
            cam_foc = cam_presets[g_idx % len(cam_presets)]
            if lt == "browser_ui_live_tour" and all_screenshots:
                chosen_sid, chosen_png = all_screenshots[scr_cursor % len(all_screenshots)]
                scr_cursor += 1
                sids = [chosen_sid]
                scr_override = chosen_png
            elif not sids and sources:
                sids = [sources[(c_idx - 1 + b_idx) % len(sources)].source_id]

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
                off = (g_idx * 2) % max(1, len(sources[0].code_or_commands))
                code_lns = (sources[0].code_or_commands[off:] + sources[0].code_or_commands[:off])[:3]

            raw_bt = taiwanize_text(str(rb.get("badge_text") or "")).strip()
            if "或" in raw_bt or not raw_bt or (is_stocks and "$0" in raw_bt):
                raw_bt = (all_real_metrics[g_idx % len(all_real_metrics)] if all_real_metrics else "+65.5%") if is_stocks else "$0 / 月"

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
                    visual_title=smart_trim(str(rb.get("visual_title") or c_title), 13.5),
                    visual_subtitle=taiwanize_text(str(rb.get("visual_subtitle") or ""))[:40],
                    badge_text=raw_bt[:18],
                    nodes=v_nodes,
                    callout_title=smart_trim(str(rb.get("callout_title") or ("底層投資邏輯" if is_stocks else "實戰關鍵防線")), 10.0),
                    callout_body=taiwanize_text(str(rb.get("callout_body") or clauses[-1]))[:44],
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

        # Build 10-beat Pure-Remotion 9:16 Funnel Shorts from `master_doc["short_beats"]`
        short_seq = SHORT_STOCKS_SEQUENCE if is_stocks else SHORT_TUTORIAL_SEQUENCE
        raw_sbeats = master_doc.get("short_beats") or []
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
                            label=smart_trim(str(nd["label"]), 8.5),
                            sub=smart_trim(str(nd.get("sub") or ""), 16.5),
                            tag=smart_trim(raw_t, 8.5),
                            metric=_ensure_numeric_metric(raw_t, all_real_metrics, idx, ctx=str(nd.get("sub") or "")),
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
                    headline=smart_trim(str(sb.get("headline") or ("點擊左下角看完整版" if is_cta else ref_b.visual_title)), 11.5),
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

        ep_title = taiwanize_text(str(master_doc.get("title") or topic.title))
        tl1 = smart_trim(str(master_doc.get("thumbnail_line1") or topic.primary_entity), 8.5)
        tl2 = smart_trim(str(master_doc.get("thumbnail_line2") or ("華爾街看錯了？" if is_stocks else "免費接管瀏覽器")), 8.5)
        if not tl1:
            tl1 = smart_trim(topic.primary_entity, 8.5)
        if not tl2 or tl2 == tl1:
            tl2 = "三大護城河" if is_stocks else "零成本實戰"
        s_title = taiwanize_text(str(master_doc.get("short_title") or f"{ep_title[:22]}｜精華速看 #Shorts"))
        if "#Shorts" not in s_title and "#shorts" not in s_title:
            s_title = f"{s_title} #Shorts"

        return EpisodeScript(
            episode_id=episode_id,
            title=ep_title,
            thumbnail_line1=tl1,
            thumbnail_line2=tl2,
            category=topic.category,
            avatar_mode=is_stocks,
            youtube_description_summary=taiwanize_text(str(master_doc.get("youtube_description_summary") or topic.hook_angle)),
            hashtags=[str(h) for h in (master_doc.get("hashtags") or (["#美股", "#財報分析", "#Gary聊美股", "#AI投資"] if is_stocks else ["#AIAgent", "#AI教學", "#GaryChen", "#自動化"]))[:6]],
            chapters=[f"{i + 1:02d} {t}" for i, t in enumerate(all_chapter_titles)],
            beats=all_beats,
            short_title=s_title,
            short_hook_banner=smart_trim(str(master_doc.get("short_hook_banner") or tl1), 9.0),
            short_cta_target_title=ep_title,
            short_beats=short_beats,
        )
