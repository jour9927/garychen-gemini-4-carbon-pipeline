from __future__ import annotations

from garychen_pipeline.config import CrawledSource, DesignTokens, EpisodeScript, ShortBeatSpec, VisualBeat, VisualNode
from garychen_pipeline.html_renderer import build_long_beat_html, build_short_beat_html
from garychen_pipeline.scriptwriter import (
    STOCKS_CHAPTER_LAYOUT_MAP,
    TUTORIAL_CHAPTER_LAYOUT_MAP,
    normalize_visual_numbers,
    split_into_clauses,
    taiwanize_text,
)
from garychen_pipeline.thumbnail_gen import _pick_real_portrait, render_studio_thumbnail
from garychen_pipeline.tts_normalizer import to_spoken_tts_text


def test_v6_lossless_clauses_and_numbers():
    # Previously truncated at 26 chars in V5 — must preserve 100% of characters in V6!
    s1 = "輝達股價從五十二週高點兩百四十三美金一路殺到一百四十一美金，市場滿街都在喊泡沫。"
    c1 = split_into_clauses(s1)
    j1 = "".join(c1)
    assert "141" in j1 or "一百四十一" in j1, f"Truncated tail in: {c1}"
    assert "泡沫" in j1

    s2 = "系統會在送出最終付款或預約確認前停下來請 Gary 檢視結果，確保每一分錢都安全。"
    c2 = split_into_clauses(s2)
    assert any("結果" in x for x in c2), f"Lost '結果' in: {c2}"

    assert "65.5%" in normalize_visual_numbers("年增率高達百分之六十五點五")
    assert "$200 美金" in normalize_visual_numbers("每個月花兩百美元訂閱")

    # Verify 64-beat layout maps & zero PR-card spam
    flat_tut = [lt for row in TUTORIAL_CHAPTER_LAYOUT_MAP for lt in row]
    flat_stk = [lt for row in STOCKS_CHAPTER_LAYOUT_MAP for lt in row]
    assert len(flat_tut) == 64 and len(flat_stk) == 64
    assert flat_tut.count("github_pr_blast_radius") <= 1


def test_tts_phonetic_normalizer():
    assert "二十一萬" in to_spoken_tts_text("GitHub 突破 211,995 Stars")
    assert "一千三百零五億美金" in to_spoken_tts_text("全年營收 $1,305 億")
    assert "成長百分之九十四" in to_spoken_tts_text("營收 +94%")
    assert "N eight N" in to_spoken_tts_text("n8n 自動化")
    assert "C I C D" in to_spoken_tts_text("先等 CI/CD 通過")


def test_taiwanize_and_clauses():
    cl = split_into_clauses("首先，我們打開瀏覽器，把這段代碼放進服務器的數據庫裡，才不會做 A 壞 B。")
    joined = " ".join(cl)
    assert "程式碼" in joined and "伺服器" in joined and "資料庫" in joined
    assert all(len(c) >= 6 for c in cl)


def test_all_14_v3_layouts_render():
    tokens = DesignTokens()
    src = CrawledSource(source_id="S1", title="SEC 10-K NVDA", url="https://sec.gov", domain="sec.gov", published_date="2026-01")
    layouts = [
        "claude_chat_dialog",
        "app_squircles_strikethrough",
        "ecosystem_node_graph",
        "protagonist_app_flow",
        "agenda_four_steps",
        "concept_hero_split_3d",
        "feature_pill_matrix",
        "browser_ui_live_tour",
        "github_pr_checks_card",
        "before_after_workflow_card",
        "stocks_kpi_asymmetric",
        "stocks_big_statement",
        "stocks_four_pillars",
        "stocks_valuation_scenarios",
    ]
    beats = []
    for idx, lt in enumerate(layouts):
        beats.append(
            VisualBeat(
                beat_id=f"b_{idx}",
                chapter_index=2,
                total_chapters=7,
                chapter_title="架構拆解",
                layout_type=lt,  # type: ignore[arg-type]
                clauses=["第一句話", "第二句話", "第三句話"],
                spoken_clauses=["第一句話", "第二句話", "第三句話"],
                visual_title="測試標題",
                nodes=[
                    VisualNode(label="營收", sub="年增 114%", tag="高成長", metric="$1,305 億", icon="nvidia", trend="up"),
                    VisualNode(label="毛利率", sub="定價權極強", tag="護城河", metric="75.0%", icon="github", trend="up"),
                    VisualNode(label="現金流", sub="自由現金充沛", tag="穩健", metric="$641 億", icon="shield", trend="neutral"),
                ],
                source_ids=["S1"],
            )
        )
    sb = ShortBeatSpec(
        beat_id="sb_1",
        layout_type="short_shock_metric_hero",
        clauses=["第一句", "第二句"],
        spoken_clauses=["第一句", "第二句"],
        headline="精華重點",
        nodes=beats[0].nodes,
        source_ids=["S1"],
    )
    sc = EpisodeScript(
        episode_id="t_v3",
        title="V3 Test",
        thumbnail_line1="NVDA 財報",
        thumbnail_line2="三大護城河",
        category="us_stocks",
        avatar_mode=True,
        youtube_description_summary="desc",
        beats=beats,
        short_title="S #Shorts",
        short_hook_banner="NVDA",
        short_cta_target_title="V3 Test",
        short_beats=[sb],
    )
    for b in beats:
        doc, n_st = build_long_beat_html(sc, b, None, {"S1": src}, tokens)
        assert ('data-step="0"' in doc or 'data-typing="1"' in doc) and n_st == 3
    sdoc, sn = build_short_beat_html(sc, sb, None, None, {"S1": src}, tokens)
    assert 'data-step="0"' in sdoc and sn == 2


if __name__ == "__main__":
    test_tts_phonetic_normalizer()
    test_taiwanize_and_clauses()
    test_v6_lossless_clauses_and_numbers()
    test_all_14_v3_layouts_render()
    print("ALL_V6_UNIT_TESTS_PASSED")
