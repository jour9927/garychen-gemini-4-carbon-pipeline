from __future__ import annotations

from pathlib import Path
from garychen_pipeline.config import CrawledSource, DesignTokens, TopicCandidate
from garychen_pipeline.renderer_long import GarychenLongRenderer
from garychen_pipeline.renderer_short import GarychenShortsRenderer
from garychen_pipeline.scriptwriter import GarychenScriptwriter, space_pad_english, split_to_subtitle_lines


def test_subtitle_formatting():
    s = space_pad_english("現在的AI Agent每一個都要錢，除了Meta推出的Muse。")
    assert "AI Agent" in s
    assert not s.endswith("。")
    lines = split_to_subtitle_lines("你可能在用AI開發產品時遇過這樣的狀況，AI寫完一個功能問你要不要開PR，你按下同意之後卻卡在CI檢查。")
    assert len(lines) >= 2


def test_all_eight_layouts_and_short_render():
    topic = TopicCandidate(
        topic_id="unit_test_mcp",
        title="從零搞懂 MCP 工作流",
        category="ai_agent",
        hook_angle="一套標準串接所有 AI Agent 工具",
        why_now="GitHub 35,000+ Stars",
    )
    sources = [
        CrawledSource(
            source_id="S1",
            title="GitHub: modelcontextprotocol/servers",
            url="https://github.com/modelcontextprotocol/servers",
            domain="github.com",
            published_date="2026-11-24",
            key_facts=["官方 MCP Servers 儲存庫超過 35,000 Stars"],
            metrics=["35,000+ Stars"],
        )
    ]
    sw = GarychenScriptwriter()
    script = sw._normalize_and_validate({}, topic, sources, "ep_unit", num_chapters=8)
    assert len(script.scenes) == 8
    assert len(script.short_scenes) == 4
    assert script.short_scenes[-1].is_cta is True

    lr = GarychenLongRenderer(DesignTokens())
    s_map = {"S1": sources[0]}
    for sc in script.scenes:
        im = lr.render_scene_state(script, sc, 0, sc.narration_lines[0], None, s_map)
        assert im.size == (1920, 1080)

    sr = GarychenShortsRenderer(DesignTokens())
    for ssc in script.short_scenes:
        sim = sr.render_short_state(script, ssc, 0, ssc.narration_lines[0], None, None, s_map)
        assert sim.size == (1080, 1920)


if __name__ == "__main__":
    test_subtitle_formatting()
    test_all_eight_layouts_and_short_render()
    print("ALL_UNIT_TESTS_PASSED")
