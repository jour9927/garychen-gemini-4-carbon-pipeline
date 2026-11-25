from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from rich.console import Console

from .config import CrawledSource, EpisodeScript, OUTPUTS_DIR, TopicCandidate
from .crawler import PublicInfoCrawler
from .image_gen import GarychenImageGenerator
from .renderer_long import GarychenLongRenderer
from .renderer_short import GarychenShortsRenderer
from .scriptwriter import GarychenScriptwriter
from .topic_scout import UnattendedTopicScout
from .voice_cloner import GarychenVoiceCloner

console = Console()


def _fmt_vtt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _fmt_yt_chap_ts(sec: float) -> str:
    tot = max(0, int(sec))
    m, s = divmod(tot, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"


def write_webvtt(cues: list[dict], out_vtt: Path):
    lines = ["WEBVTT", "Kind: captions", "Language: zh-TW", ""]
    for c in cues:
        lines.append(f"{_fmt_vtt_ts(c['start'])} --> {_fmt_vtt_ts(c['end'])}")
        lines.append(c["text"])
        lines.append("")
    out_vtt.write_text("\n".join(lines), encoding="utf-8")


class GarychenUnattendedPipeline:
    """
    V3 Studio Unattended Orchestrator:
      - SEC EDGAR XBRL + Live Market + GitHub/Docs/ArXiv Precision Crawler + Retina Dark-Mode Captures
      - Qwen2.5-32B Genre-Specialized Director (7 deep chapters × 3 progressive beats + 8-beat 45s Funnel Short)
      - Bilingual Phonetic Normalizer + 48-step F5-TTS + Whisper Word Alignment + Studio EQ (-20.5 LUFS)
      - 28-step SDXL Base Vignette-Feathered 3D Dioramas + True 60fps Layer-Spring Remotion Compositor + Studio Portrait Thumbnail
    """

    def __init__(self, outputs_root: Path | None = None):
        self.outputs_root = outputs_root or OUTPUTS_DIR
        self.scout = UnattendedTopicScout()
        self.scriptwriter = GarychenScriptwriter()
        self.voice_cloner = GarychenVoiceCloner()
        self.image_gen = GarychenImageGenerator()
        self.long_renderer = GarychenLongRenderer()
        self.short_renderer = GarychenShortsRenderer()

    def run(
        self,
        custom_topic: str | None = None,
        category: str | None = None,
        seed_urls: list[str] | None = None,
        episode_id: str | None = None,
        num_chapters: int = 7,
    ) -> dict:
        ts_slug = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        console.rule("[bold orange3]Stage 1/7 · 無人值守選題 (Unattended Topic Scout V3)")
        topic: TopicCandidate = self.scout.pick_unattended(custom_topic=custom_topic, category=category, seed_urls=seed_urls)
        ep_id = episode_id or f"{ts_slug}_{re.sub(r'[^a-zA-Z0-9]+', '_', topic.topic_id).strip('_')[:20]}"
        ep_dir = self.outputs_root / ep_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / "topic.json").write_text(topic.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]✓ Topic:[/green] {topic.title} [dim](entity={topic.primary_entity}, cat={topic.category}, tickers={topic.tickers})[/dim]")

        console.rule("[bold orange3]Stage 2/7 · 深度領域爬蟲 (SEC 10-K / 即時股價 / GitHub / 實時暗色網頁截圖)")
        sources_file = ep_dir / "crawled_sources.json"
        if sources_file.exists():
            sources = [CrawledSource.model_validate(x) for x in json.loads(sources_file.read_text(encoding="utf-8"))]
        else:
            crawler = PublicInfoCrawler()
            try:
                sources = crawler.gather_dossier(
                    queries=topic.seed_queries,
                    primary_entity=topic.primary_entity,
                    category=topic.category,
                    seed_urls=topic.seed_urls,
                    tickers=topic.tickers,
                    screenshots_dir=ep_dir / "source_screenshots",
                )
            finally:
                crawler.close()
            sources_file.write_text(
                json.dumps([s.model_dump() for s in sources], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        n_scr = sum(1 for s in sources if s.screenshot_path)
        console.print(
            f"[green]✓ Verified {len(sources)} primary sources ({n_scr} live dark-mode screenshots):[/green] "
            + ", ".join(f"[{s.source_id}] {s.domain}" for s in sources)
        )

        console.rule("[bold orange3]Stage 3/7 · Qwen2.5-32B 分流導演與分鏡編排 (教學 vs 美股專屬劇本)")
        script_file = ep_dir / "episode_script.json"
        if script_file.exists():
            script = EpisodeScript.model_validate_json(script_file.read_text(encoding="utf-8"))
        else:
            script = self.scriptwriter.generate_episode_script(
                topic=topic,
                sources=sources,
                episode_id=ep_id,
                num_chapters=num_chapters,
            )
            script_file.write_text(script.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]✓ Long Script:[/green] {script.title} ({len(script.beats)} beats / {len(script.chapters)} chapters)")
        console.print(f"[green]✓ Funnel Short:[/green] {script.short_title} ({len(script.short_beats)} vertical beats)")

        console.rule("[bold orange3]Stage 4/7 · 雙語讀音正規化 + 48步 F5-TTS 聲音克隆 + Whisper 字級對齊")
        long_beat_reqs = [
            {
                "id": b.beat_id,
                "clauses": b.clauses,
                "spoken_clauses": b.spoken_clauses,
                "voice_style": b.voice_style,
                "sfx_cue": b.sfx_cue,
            }
            for b in script.beats
        ]
        long_synth, tts_backend = self.voice_cloner.synthesize_beats(long_beat_reqs, ep_dir / "audio_long")
        long_master_wav = ep_dir / "long_master.wav"
        long_dur, long_cues = self.voice_cloner.build_master_timeline(long_synth, long_master_wav)
        write_webvtt(long_cues, ep_dir / "long_subtitles.vtt")
        console.print(f"[green]✓ Long Voiceover Mastered:[/green] {long_dur:.1f}s ({len(long_cues)} cues, -20.5 LUFS) via [cyan]{tts_backend}[/cyan]")

        short_beat_reqs = [
            {
                "id": sb.beat_id,
                "clauses": sb.clauses,
                "spoken_clauses": sb.spoken_clauses,
                "voice_style": sb.voice_style,
                "sfx_cue": "pop",
            }
            for sb in script.short_beats
        ]
        short_synth, tts_backend_s = self.voice_cloner.synthesize_beats(short_beat_reqs, ep_dir / "audio_short")
        short_master_wav = ep_dir / "short_master.wav"
        short_dur, short_cues = self.voice_cloner.build_master_timeline(
            short_synth, short_master_wav, inter_beat_pause=0.16, chapter_pause=0.22
        )
        write_webvtt(short_cues, ep_dir / "short_subtitles.vtt")
        console.print(f"[green]✓ Shorts Voiceover Mastered:[/green] {short_dur:.1f}s ({len(short_cues)} cues, -20.5 LUFS) via [cyan]{tts_backend_s}[/cyan]")

        console.rule("[bold orange3]Stage 5/7 · 28-Step SDXL Base 無邊框暗色羽化 3D 場景插圖生成")
        AI_LAYOUTS = {"concept_hero_split_3d", "browser_ui_live_tour"}
        img_reqs: list[dict] = []
        for idx, b in enumerate(script.beats):
            if b.layout_type in AI_LAYOUTS:
                img_reqs.append({"id": b.beat_id, "prompt": b.ai_image_prompt, "width": 1216, "height": 832, "steps": 28, "seed": 5100 + idx * 31})
        for idx, sb in enumerate(script.short_beats):
            if not sb.is_cta:
                img_reqs.append({"id": sb.beat_id, "prompt": sb.ai_image_prompt, "width": 1024, "height": 768, "steps": 24, "seed": 7200 + idx * 41})
        img_map, img_backend = self.image_gen.generate_batch(img_reqs, ep_dir / "images")
        console.print(f"[green]✓ Generated {len(img_map)} Studio 3D Illustrations[/green] via [cyan]{img_backend}[/cyan]")

        console.rule("[bold orange3]Stage 6/7 · Remotion 圖層彈簧動畫 1920x1080 @ 60fps 合成 + 真人肖像封面圖")
        long_mp4 = ep_dir / "garychen_long.mp4"
        thumb_png = ep_dir / "thumbnail.png"
        self.long_renderer.encode_video(
            script=script,
            line_cues=long_cues,
            master_audio_wav=long_master_wav,
            total_duration=long_dur,
            image_map=img_map,
            sources=sources,
            out_mp4=long_mp4,
            thumbnail_png=thumb_png,
        )
        console.print(f"[green]✓ Rendered V3 Long Video:[/green] {long_mp4} ({long_mp4.stat().st_size / (1024*1024):.2f} MB)")

        console.rule("[bold orange3]Stage 7/7 · Remotion 圖層彈簧動畫 1080x1920 @ 60fps 對應推流 Shorts 合成")
        short_mp4 = ep_dir / "garychen_short_funnel.mp4"
        self.short_renderer.encode_short(
            script=script,
            line_cues=short_cues,
            master_audio_wav=short_master_wav,
            total_duration=short_dur,
            image_map=img_map,
            long_thumb_path=thumb_png,
            sources=sources,
            out_mp4=short_mp4,
        )
        publish_md = self._write_publish_pack(ep_dir, script, long_cues, sources)
        summary = {
            "episode_id": ep_id,
            "episode_dir": str(ep_dir),
            "long_title": script.title,
            "short_title": script.short_title,
            "long_mp4": str(long_mp4),
            "short_mp4": str(short_mp4),
            "thumbnail_png": str(thumb_png),
            "publish_pack_md": str(publish_md),
            "long_duration_sec": long_dur,
            "short_duration_sec": short_dur,
            "beats_count": len(script.beats),
            "cues_count": len(long_cues),
            "sources_count": len(sources),
            "live_screenshots_count": n_scr,
            "tts_backend": tts_backend,
            "image_backend": img_backend,
        }
        (ep_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[bold green]🎉 V3 Studio Episode Complete![/bold green] -> {ep_dir}")
        return summary

    @staticmethod
    def _write_publish_pack(ep_dir: Path, script: EpisodeScript, long_cues: list[dict], sources: list[CrawledSource]) -> Path:
        beat_starts: dict[str, float] = {}
        for c in long_cues:
            bid = c["beat_id"]
            if bid not in beat_starts:
                beat_starts[bid] = c["start"]
        chap_starts: dict[int, tuple[str, float]] = {}
        for b in script.beats:
            if b.chapter_index not in chap_starts:
                chap_starts[b.chapter_index] = (b.chapter_title, beat_starts.get(b.beat_id, 0.0))

        chap_lines = [f"{_fmt_yt_chap_ts(0.0 if idx == 1 else csec)} {ctitle}" for idx, (ctitle, csec) in sorted(chap_starts.items())]
        src_lines = [f"- [{s.source_id}] {s.title} ({s.domain})：{s.url}" for s in sources]

        is_stocks = (script.category == "us_stocks")
        top_block = (
            [script.youtube_description_summary]
            if is_stocks
            else [
                "加入我的 Skool，查看完整文章還有提示詞模板：https://www.skool.com/gary-chen",
                "--",
                script.youtube_description_summary,
            ]
        )
        footer_block = (
            [
                "📢 追蹤 Gary 聊美股",
                "👍 覺得有幫助請按讚、訂閱、開小鈴鐺！",
                "",
                "⚠️ 免責聲明：本頻道內容僅供參考，不構成投資建議。投資有風險，請自行判斷。",
            ]
            if is_stocks
            else [
                "📢 追蹤我的頻道",
                "👍 覺得有幫助請按讚、訂閱、開小鈴鐺！",
            ]
        )

        md = [
            f"# {script.title}",
            "",
            "## 📺 長片 YouTube 資訊欄 (直接複製貼上)",
            "```text",
            *top_block,
            "",
            "📌 時間戳",
            *chap_lines,
            "",
            "🌐 本集爬蟲查證公開資訊與資料來源",
            *src_lines,
            "",
            *footer_block,
            "",
            " ".join(script.hashtags),
            "```",
            "",
            "## 📱 對應推流 Shorts 標題與關聯設定",
            f"- **Shorts 標題**：`{script.short_title}`",
            f"- **關聯影片 (Related Video)**：綁定本集長片《{script.title}》作為左下角推流入口",
            "",
        ]
        out_p = ep_dir / "youtube_publish_pack.md"
        out_p.write_text("\n".join(md), encoding="utf-8")
        return out_p
