#!/usr/bin/env python3
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path("/Users/alan_dingchaoliao/Downloads/garychen/reference_channel")
VIDS_DIR = BASE / "videos"
VIDS_DIR.mkdir(parents=True, exist_ok=True)
YTDLP = "/Users/alan_dingchaoliao/Downloads/garychen/.venv/bin/yt-dlp"

with open(BASE / "all_tabs.jsonl") as f:
    entries = [json.loads(line) for line in f if line.strip().startswith("{")]

HD_IDS = set([e["id"] for e in entries[:8]] + ["YM-6-QhGHgI", "KWAvlqxNVAk", "VbWh0Yhl_xM", "OAGdrYHz_5k"])

def download_one(idx_entry):
    idx, entry = idx_entry
    vid = entry["id"]
    out_dir = VIDS_DIR / f"{idx:02d}_{vid}"
    out_dir.mkdir(parents=True, exist_ok=True)
    done_flag = out_dir / ".done"
    if done_flag.exists() and list(out_dir.glob("*.mp4")):
        return vid, "cached"
    fmt = (
        "299+140/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"
        if vid in HD_IDS
        else "135+140/134+140/bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]"
    )
    cmd = [
        YTDLP,
        "--no-update",
        "--ignore-errors",
        "--js-runtimes", "node:/Users/alan_dingchaoliao/.local/bin/node",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:lang=zh-TW",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-subs",
        "--sub-langs", "zh-TW",
        "--sub-format", "vtt/srt/best",
        "--write-thumbnail",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        f"https://www.youtube.com/watch?v={vid}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    mp4s = list(out_dir.glob("*.mp4"))
    if mp4s:
        done_flag.write_text("ok\n")
        return vid, f"ok ({mp4s[0].stat().st_size // 1024} KB)"
    if "會員" in (res.stderr or "") or "members" in (res.stderr or "").lower():
        (out_dir / ".members_only").write_text("members_only\n")
        return vid, "members_only_skipped"
    return vid, f"failed: {(res.stderr or '')[-160:].strip()}"

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    subset = list(enumerate(entries, 1))
    if mode == "sample":
        subset = [x for x in subset if x[1]["id"] in {"UrFrDJ-G6h8", "aCvEYczBVSY", "qtHozNsemsI", "YM-6-QhGHgI", "KWAvlqxNVAk"}]
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(download_one, item): item for item in subset}
        for i, fut in enumerate(as_completed(futs), 1):
            vid, status = fut.result()
            print(f"[{i}/{len(subset)}] {vid}: {status}", flush=True)
