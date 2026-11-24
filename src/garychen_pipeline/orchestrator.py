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
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
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
    Master Unattended Orchestrator (lives on local machine 本機 first).
    Saves checkpoints after every stage so remote GPU disconnection never loses state.
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
        num_chapters: int = 6,
    ) -> dict:
        ts_slug = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        # 1. Unattended Topic Discovery & Selection
        console.rule("[bold orange3]Stage 1/7 · 無人值守選題 (Unattended Topic Scout)")
        topic: TopicCandidate = self.scout.pick_unattended(custom_topic=custom_topic, category=category, seed_urls=seed_urls)
        ep_id = episode_id or f"{ts_slug}_{re.sub(r'[^a-zA-Z0-9]+', '_', topic.topic_id).strip('_')[:20]}"
        ep_dir = self.outputs_root / ep_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / "topic.json").write_text(topic.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]✓ Selected Topic:[/green] {topic.title} [dim](score={topic.score}, cat={topic.category})[/dim]")

        # 2. Live Public Web Crawling & Source Verification
        console.rule("[bold orange3]Stage 2/7 · 公開資訊爬蟲與來源查證 (Public Web Crawler)")
        sources_file = ep_dir / "crawled_sources.json"
        if sources_file.exists():
            sources = [CrawledSource.model_validate(x) for x in json.loads(sources_file.read_text(encoding="utf-8"))]
        else:
            crawler = PublicInfoCrawler()
            try:
                sources = crawler.gather_dossier(queries=topic.seed_queries, seed_urls=topic.seed_urls, min_sources=5)
            finally:
                crawler.close()
            sources_file.write_text(
                json.dumps([s.model_dump() for s in sources], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        console.print(f"[green]✓ Crawled {len(sources)} public sources:[/green] " + ", ".join(f"[{s.source_id}] {s.domain}" for s in sources))

        # 3. Garychen Persona AI Scriptwriting (Long + Corresponding Shorts Funnel)
        console.rule("[bold orange3]Stage 3/7 · AI 產稿與雙規分鏡腳本 (Long + Funnel Shorts Script)")
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
        console.print(f"[green]✓ Generated Long Title:[/green] {script.title} ({len(script.scenes)} scenes)")
        console.print(f"[green]✓ Generated Funnel Short:[/green] {script.short_title} ({len(script.short_scenes)} vertical scenes)")

        # 4. PyTorch Voice Cloning (RTX PRO 6000 Priority -> B850 -> Local Cache)
        console.rule("[bold orange3]Stage 4/7 · PyTorch 本人聲音克隆配音 (RTX PRO 6000 Priority)")
        long_tts_items: list[dict] = []
        for sc in script.scenes:
            for l_idx, ln in enumerate(sc.narration_lines):
                long_tts_items.append(
                    {
                        "id": f"{sc.scene_id}_l{l_idx + 1:02d}",
                        "scene_id": sc.scene_id,
                        "line_idx": l_idx,
                        "voice_style": sc.voice_style,
                        "text": ln,
                    }
                )
        long_synth, tts_backend_long = self.voice_cloner.synthesize_lines(long_tts_items, ep_dir / "audio_long")
        for orig, syn in zip(long_tts_items, long_synth):
            syn["scene_id"] = orig["scene_id"]
            syn["line_idx"] = orig["line_idx"]
        long_master_wav = ep_dir / "long_master.wav"
        long_dur, long_cues = self.voice_cloner.concat_master_track(long_synth, long_master_wav)
        write_webvtt(long_cues, ep_dir / "long_subtitles.vtt")
        console.print(f"[green]✓ Long Voiceover Mastered:[/green] {long_dur:.1f}s (-21.0 LUFS) via [cyan]{tts_backend_long}[/cyan]")

        short_tts_items: list[dict] = []
        for sc in script.short_scenes:
            for l_idx, ln in enumerate(sc.narration_lines):
                short_tts_items.append(
                    {
                        "id": f"{sc.scene_id}_l{l_idx + 1:02d}",
                        "scene_id": sc.scene_id,
                        "line_idx": l_idx,
                        "voice_style": sc.voice_style,
                        "text": ln,
                    }
                )
        short_synth, tts_backend_short = self.voice_cloner.synthesize_lines(short_tts_items, ep_dir / "audio_short")
        for orig, syn in zip(short_tts_items, short_synth):
            syn["scene_id"] = orig["scene_id"]
            syn["line_idx"] = orig["line_idx"]
        short_master_wav = ep_dir / "short_master.wav"
        short_dur, short_cues = self.voice_cloner.concat_master_track(
            short_synth, short_master_wav, inter_line_pause=0.11, inter_scene_pause=0.25
        )
        write_webvtt(short_cues, ep_dir / "short_subtitles.vtt")
        console.print(f"[green]✓ Shorts Voiceover Mastered:[/green] {short_dur:.1f}s (-21.0 LUFS) via [cyan]{tts_backend_short}[/cyan]")

        # 5. PyTorch AI Image Generation (RTX PRO 6000 Priority)
        console.rule("[bold orange3]Stage 5/7 · PyTorch AI 產圖 (RTX PRO 6000 Priority)")
        img_reqs: list[dict] = []
        for idx, sc in enumerate(script.scenes):
            img_reqs.append({"id": sc.scene_id, "prompt": sc.ai_image_prompt, "width": 768, "height": 512, "seed": 3100 + idx * 19})
        for idx, ssc in enumerate(script.short_scenes):
            if not ssc.is_cta:
                img_reqs.append({"id": ssc.scene_id, "prompt": ssc.ai_image_prompt, "width": 640, "height": 512, "seed": 5200 + idx * 23})
        img_map, img_backend = self.image_gen.generate_batch(img_reqs, ep_dir / "images")
        console.print(f"[green]✓ Generated {len(img_map)} AI Illustrations[/green] via [cyan]{img_backend}[/cyan]")

        # 6. Render 1920x1080 @ 60fps Long Video + Thumbnail
        console.rule("[bold orange3]Stage 6/7 · 1920x1080 @ 60fps 長片動態合成渲染")
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
        console.print(f"[green]✓ Rendered Long Video:[/green] {long_mp4} ({long_mp4.stat().st_size / (1024*1024):.2f} MB)")

        # 7. Render 1080x1920 @ 60fps Corresponding Funnel Short + Publish Pack
        console.rule("[bold orange3]Stage 7/7 · 1080x1920 @ 60fps 對應推流 Shorts 合成與上架包")
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
            "sources_count": len(sources),
            "tts_backend": tts_backend_long,
            "image_backend": img_backend,
        }
        (ep_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[bold green]🎉 Unattended Episode Complete![/bold green] -> {ep_dir}")
        return summary

    @staticmethod
    def _write_publish_pack(ep_dir: Path, script: EpisodeScript, long_cues: list[dict], sources: list[CrawledSource]) -> Path:
        # Compute exact chapter start timestamps from first cue of each scene
        scene_starts: dict[str, float] = {}
        for c in long_cues:
            sid = c["scene_id"]
            if sid not in scene_starts:
                scene_starts[sid] = c["start"]
        chap_lines = []
        for idx, sc in enumerate(script.scenes):
            st = 0.0 if idx == 0 else scene_starts.get(sc.scene_id, 0.0)
            chap_lines.append(f"{_fmt_yt_chap_ts(st)} {sc.chapter_title}")

        src_lines = []
        for s in sources:
            src_lines.append(f"- [{s.source_id}] {s.title} ({s.domain})：{s.url}")

        md = [
            f"# {script.title}",
            "",
            "## 📺 長片 YouTube 資訊欄 (直接複製貼上)",
            "```text",
            "加入我的 Skool，查看完整文章還有提示詞模板：https://www.skool.com/gary-chen",
            "--",
            script.youtube_description_summary,
            "",
            "📌 時間戳",
            *chap_lines,
            "",
            "🌐 本集引用公開資訊與資料來源",
            *src_lines,
            "",
            "📢 追蹤我的頻道",
            "👍 覺得有幫助請按讚、訂閱、開小鈴鐺！",
            "",
            " ".join(script.hashtags),
            "```",
            "",
            f"## 📱 對應推流 Shorts 標題與關聯設定",
            f"- **Shorts 標題**：`{script.short_title}`",
            f"- **關聯影片 (Related Video)**：綁定本集長片《{script.title}》作為左下角推流入口",
            "",
        ]
        out_p = ep_dir / "youtube_publish_pack.md"
        out_p.write_text("\n".join(md), encoding="utf-8")
        return out_p
