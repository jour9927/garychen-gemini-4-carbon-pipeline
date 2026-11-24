from __future__ import annotations

from garychen_pipeline.config import CrawledSource, DesignTokens, EpisodeScript, ShortBeatSpec, VisualBeat, VisualNode
from garychen_pipeline.html_renderer import build_long_beat_html, build_short_beat_html
from garychen_pipeline.scriptwriter import space_pad_english, split_into_clauses


def test_v2_all_fourteen_html_layouts():
    layouts = [
        "claude_terminal_progressive",
        "pricing_strikethrough_reveal",
        "chapter_roadmap_agenda",
        "progressive_slot_pipeline",
        "hub_ecosystem_radiate",
        "github_pr_checks_mock",
        "live_web_screenshot_spotlight",
        "ai_editorial_split_card",
        "before_after_stamp_compare",
        "kpi_financial_cards",
        "branch_merge_diagram",
        "checklist_two_tier_defense",
        "versus_debate_columns",
        "summary_three_pillars",
    ]
    nodes = [
        VisualNode(label="browser-use", sub="自動操控真實瀏覽器", tag="121K+ ★", icon="github", trend="up"),
        VisualNode(label="MCP Server", sub="統一協定直連 Claude", tag="免費開源", icon="zap", trend="up"),
        VisualNode(label="CI 自動檢查", sub="確保每次改動不壞舊功能", tag="Passed ✓", icon="shield", trend="neutral"),
        VisualNode(label="排程自動跑", sub="背景無人值守執行", tag="24/7", icon="cpu", trend="neutral"),
    ]
    beats = [
        VisualBeat(
            beat_id=f"beat_{i+1:02d}",
            chapter_index=(i % 6) + 1,
            chapter_title=f"實戰章節 {i+1}",
            layout_type=lt,  # type: ignore[arg-type]
            clauses=split_into_clauses("你可能在用AI寫程式時遇過這樣的狀況，其實背後就是這套自動化工作流在幫你把關"),
            visual_title="MCP 與瀏覽器 Agent 實戰",
            visual_subtitle="用最白話的方式拆解底層邏輯",
            badge_text="121,926 Stars",
            nodes=nodes,
            callout_title="Gary 實戰重點",
            callout_body="先把防線搭起來，疊新功能才不會做 A 壞 B",
            code_lines=["pip install browser-use", "playwright install chromium"],
            source_ids=["S1"],
        )
        for i, lt in enumerate(layouts)
    ]
    sbeat = ShortBeatSpec(
        beat_id="sbeat_01",
        layout_type="short_funnel_cta",
        clauses=["馬上點擊左下角關聯影片看完整版"],
        headline="點擊左下角看完整教學",
        highlight_badge="完整長片已上線",
        nodes=nodes[:3],
        source_ids=["S1"],
        is_cta=True,
    )
    script = EpisodeScript(
        episode_id="unit_v2",
        title="測試長片標題",
        youtube_description_summary="測試摘要",
        chapters=["01 測試"],
        beats=beats,
        short_title="測試短片 #Shorts",
        short_hook_banner="精華速看",
        short_cta_target_title="測試長片標題",
        short_beats=[sbeat],
    )
    src = {
        "S1": CrawledSource(
            source_id="S1",
            title="browser-use/browser-use",
            url="https://github.com/browser-use/browser-use",
            domain="github.com",
            published_date="2026-11-25",
        )
    }
    tok = DesignTokens()
    for b in beats:
        for step in (0, 1, 2):
            h = build_long_beat_html(script, b, step, None, src, tok)
            assert "<!DOCTYPE html>" in h and b.visual_title in h
    sh = build_short_beat_html(script, sbeat, 0, None, None, src, tok)
    assert "關聯影片" in sh
    assert "AI 寫程式" in space_pad_english("AI寫程式。")


if __name__ == "__main__":
    test_v2_all_fourteen_html_layouts()
    print("ALL_V2_UNIT_TESTS_PASSED")
