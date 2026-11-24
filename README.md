# Garychen Gemini 4 Carbon 產線 (`@garychenai`)

全自動**無人值守（Unattended）** YouTube 長片（`1920x1080 @ 60fps`）＋ 對應長片推流 Shorts（`1080x1920 @ 60fps`）復刻產線。  
完整還原 **Gary Chen (`@garychenai`)** 頻道的剪輯視覺系統、口語敘事結構、PyTorch 本人聲音克隆配音、PyTorch AI 產圖，並融合**即時公開資訊爬蟲 + 畫面與資訊欄雙重來源標註**。

---

## ✨ 核心能力與復刻規格

1. **100% 逆向還原 `@garychenai` 視覺與聲學規格**
   - **畫布與幀率**：長片 `1920x1080 @ 60fps`、推流 Shorts `1080x1920 @ 60fps`（H.264 High Profile `yuv420p`）。
   - **標準色票**：深炭灰背景 `#262626`（AI 教學系列）／`#1E1E1E`（美股財報評論系列 + 右下圓形錄音室頭像 PiP）、招牌琥珀橘 `#EB8B1B` 頂部即時進度條與發光邊框、底部圓角黑底字幕膠囊 `#090909`（`Y=922..1019`）。
   - **8 大動態資訊圖表版型**：`hero_comparison_cards`、`hub_spoke_ecosystem`、`split_ai_illustration_callout`、`step_pipeline_flow`、`terminal_code_window`、`crawled_evidence_spotlight`、`checklist_architecture_box`、`versus_debate_matrix`，隨口播行數自動切換高亮節點與轉場動畫。
   - **廣播級響度標準**：EBU R128 `-21.0 LUFS`（LRA `~4.2 LU`，44.1kHz Stereo AAC），擷取自頻道原片 40.4 dB SNR 乾淨人聲母帶。

2. **無人值守選題 + 公開資訊爬蟲與來源附上 (`crawler.py` & `topic_scout.py`)**
   - 自動爬取 **GitHub API / README、Hacker News Algolia、arXiv 最新論文與官方技術部落格**。
   - 自動比對 `reference_channel/all_tabs.jsonl`（頻道既有 84 支影片）避免重複主題，無須人工介入直接選出最高分題目開工。
   - **雙重來源標註**：每個畫面右上角與重點卡內嵌 `來源 [S1] domain · 日期｜標題` 膠囊標籤，並於 `youtube_publish_pack.md` 自動輸出完整可點擊引用清單。

3. **PyTorch 本人聲音克隆 (`voice_cloner.py`) & PyTorch AI 產圖 (`image_gen.py`)**
   - 依段落語氣自動切換三組擷取自 `@garychenai` 原片的乾淨參考音檔（`gary_hook.wav`、`gary_explainer.wav`、`gary_warm.wav`），透過 **PyTorch `F5-TTS` (`F5TTS_v1_Base` + 繁簡發音前端自動校正)** 直接唸出中英夾雜講稿。
   - 透過 **PyTorch `diffusers` (`stabilityai/sdxl-turbo`)** 產出符合頻道深色琥珀光影美學的 3D／等距視覺插圖。

4. **主腳本本機優先 + RTX PRO 6000 & B850 Tailscale SSH 分散式算力調度**
   - **本機 (`alan-hub`)**：所有主腳本、爬蟲、分鏡、字幕與產出音檔／圖檔／成片**第一時間落盤於本機**，每個 Stage 皆設斷點續傳（Checkpointing），遠端臨時節點斷線絕不遺失任何程式碼或資產。
   - **臨時高速節點 (`RTX PRO 6000 Blackwell 96GB` Colab `:19743`)**：優先承接所有 PyTorch 聲音克隆配音與 AI 產圖重活。
   - **常駐節點 (`b850` / `b850-ubuntu`, `100.100.230.119:18793`)**：已實作 Tailscale SSH 可達（`./bin/ssh-b850`）與常駐 Worker 鏡像同步。

---

## 🚀 快速執行指南

### 1. 檢查叢集與算力節點健康狀態（RTX PRO 6000 + B850 + 本機）
```bash
./bin/garychen-run --health
./bin/ssh-b850 "hostname && uptime"
```

### 2. 全自動無人值守產出（自動爬蟲選題 → 查證來源 → AI 產稿 → PyTorch 配音 → AI 產圖 → 60fps 長片 + 推流 Shorts）
```bash
./bin/garychen-run
```

### 3. 指定不同類型主題（AI Agent 實戰／Vibe Coding／美股深度分析）
```bash
# AI Agent / 工程教學模式（#262626 畫布）
./bin/garychen-run --topic "MCP Server 實戰教學：如何讓 AI Agent 安全串接本地資料庫與 GitHub" --category ai_agent

# 美股財報深度分析模式（自動啟用 #1E1E1E 畫布 + 右下角 Gary 錄音室圓形頭像）
./bin/garychen-run --topic "NVIDIA 財報深度解析：Blackwell 算力需求見頂了嗎？三大護城河拆解" --category us_stocks
```

---

## 📂 產出目錄結構 (`outputs/<episode_id>/`)

- `garychen_long.mp4`：`1920x1080 @ 60fps` 完整教學／分析長片
- `garychen_short_funnel.mp4`：`1080x1920 @ 60fps` 對應長片推流 YouTube Shorts（結尾內建左下角關聯影片導流卡）
- `thumbnail.png`：`1920x1080` 高清封面圖
- `crawled_sources.json`：爬蟲抓取之公開資訊、數據指標與原始網址查證紀錄
- `episode_script.json`：完整長短片結構化腳本與視覺分鏡定義
- `long_subtitles.vtt` / `short_subtitles.vtt`：精確時間軸繁體中文字幕檔
- `youtube_publish_pack.md`：一鍵複製上架標題、時間戳章節、公開資訊來源引用清單與 Shorts 關聯設定
