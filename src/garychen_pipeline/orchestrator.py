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
    V4 Studio Unattended Orchestrator:
      1. Unattended Topic Scout
      2. Multi-Year SEC 10-K XBRL Time-Series + Live CNBC Market + GitHub Repo/PRs + Multi-View 1600x1000 Dark Captures
      3. Two-Stage Verbatim Gary Chen Prose + Anti-Slop Critic + 28-Beat Remotion Choreographer + 10-Beat Pure-Remotion Short
      4. Qwen3-TTS-12Hz-1.7B-Base Native Taiwanese Voice Cloning + Studio Ambient Bed & Motivated Foley (-20.5 LUFS)
      5. PyTorch Dark-Matte Editorial Scene Generation
      6. High-Density 60fps Remotion Long Video (Camera Zoom/Cursor, Live Typing, Curve Wipes, Spring Reveals) + Portrait Thumbnail
      7. Pure-Remotion 1080x1920 @ 60fps Traffic-Funnel Short + YouTube Publish Pack
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
        console.rule("[bold orange3]Stage 1/7 · 無人值守選題 (Unattended Topic Scout V4)")
        if episode_id and not custom_topic and (self.outputs_root / episode_id / "topic.json").exists():
            topic = TopicCandidate.model_validate_json((self.outputs_root / episode_id / "topic.json").read_text(encoding="utf-8"))
            ep_id = episode_id
        else:
            topic = self.scout.pick_unattended(custom_topic=custom_topic, category=category, seed_urls=seed_urls)
            ep_id = episode_id or f"{ts_slug}_{re.sub(r'[^a-zA-Z0-9]+', '_', topic.topic_id).strip('_')[:20]}"
        ep_dir = self.outputs_root / ep_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / "topic.json").write_text(topic.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]✓ Topic:[/green] {topic.title} [dim](entity={topic.primary_entity}, cat={topic.category}, tickers={topic.tickers})[/dim]")

        console.rule("[bold orange3]Stage 2/7 · 多年度 SEC 10-K 時序 / GitHub PR / 多視角暗色截圖爬蟲")
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
        n_scr = sum((1 if s.screenshot_path else 0) + len(s.extra_screenshots) for s in sources)
        console.print(
            f"[green]✓ Verified {len(sources)} primary sources ({n_scr} distinct 1600x1000 dark views):[/green] "
            + ", ".join(f"[{s.source_id}] {s.domain}" for s in sources)
        )

        console.rule("[bold orange3]Stage 3/7 · 雙階段白話編劇 + 反廢話審稿 + 28幕 Remotion 視覺編排")
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
        console.print(f"[green]✓ Long Script:[/green] {script.title} ({len(script.beats)} Remotion beats / {len(script.chapters)} chapters)")
        console.print(f"[green]✓ Funnel Short:[/green] {script.short_title} ({len(script.short_beats)} Pure-Remotion vertical beats)")

        console.rule("[bold orange3]Stage 4/7 · Qwen3-TTS 台灣原聲克隆 + 錄音室環境底噪與擬真 Foley 混音")
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
        long_dur, long_cues = self.voice_cloner.build_master_timeline(
            long_synth, long_master_wav, inter_beat_pause=0.20, chapter_pause=0.36, category=script.category
        )
        write_webvtt(long_cues, ep_dir / "long_subtitles.vtt")
        console.print(f"[green]✓ Long Voiceover Mastered:[/green] {long_dur:.1f}s ({len(long_cues)} cues, -20.5 LUFS) via [cyan]{tts_backend}[/cyan]")

        short_beat_reqs = [
            {
                "id": sb.beat_id,
                "clauses": sb.clauses,
                "spoken_clauses": sb.spoken_clauses,
                "voice_style": sb.voice_style,
                "sfx_cue": sb.sfx_cue,
            }
            for sb in script.short_beats
        ]
        short_synth, tts_backend_s = self.voice_cloner.synthesize_beats(short_beat_reqs, ep_dir / "audio_short")
        short_master_wav = ep_dir / "short_master.wav"
        short_dur, short_cues = self.voice_cloner.build_master_timeline(
            short_synth, short_master_wav, inter_beat_pause=0.12, chapter_pause=0.18, category=script.category
        )
        write_webvtt(short_cues, ep_dir / "short_subtitles.vtt")
        console.print(f"[green]✓ Shorts Voiceover Mastered:[/green] {short_dur:.1f}s ({len(short_cues)} cues, -20.5 LUFS) via [cyan]{tts_backend_s}[/cyan]")

        console.rule("[bold orange3]Stage 5/7 · PyTorch 暗色插畫生成 (精準點綴，零廉價貼圖感)")
        img_reqs: list[dict] = []
        for idx, b in enumerate(script.beats):
            if b.layout_type == "concept_hero_split_3d" and b.ai_image_prompt:
                img_reqs.append({"id": b.beat_id, "prompt": b.ai_image_prompt, "width": 1024, "height": 768, "steps": 24, "seed": 5100 + idx * 31})
        img_map, img_backend = (self.image_gen.generate_batch(img_reqs, ep_dir / "images") if img_reqs else ({}, "pure_remotion_svg"))
        console.print(f"[green]✓ Generated {len(img_map)} Editorial Dark-Matte Illustrations[/green] via [cyan]{img_backend}[/cyan]")

        console.rule("[bold orange3]Stage 6/7 · V4 60fps 高密度 Remotion 動態引擎 (運鏡/打字/成長曲線/彈簧) + 封面圖")
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
        console.print(f"[green]✓ Rendered V4 Long Video:[/green] {long_mp4} ({long_mp4.stat().st_size / (1024*1024):.2f} MB)")

        console.rule("[bold orange3]Stage 7/7 · V4 純 Remotion 1080x1920 @ 60fps 對應推流 Shorts 合成")
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
        console.print(f"[bold green]🎉 V4 Studio Episode Complete![/bold green] -> {ep_dir}")
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
