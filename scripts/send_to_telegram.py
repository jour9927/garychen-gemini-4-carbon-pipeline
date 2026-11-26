#!/usr/bin/env python3
"""
Send Garychen Gemini 4 Carbon V2 Long + Funnel Shorts + Publish Pack directly to Telegram.
Automatically resolves Chat ID from argument, GC_TG_CHAT_ID env var, or latest bot getUpdates.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_chat_id(token: str, explicit_chat_id: str | None = None) -> str:
    if explicit_chat_id:
        return str(explicit_chat_id).strip()
    env_cid = os.environ.get("GC_TG_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TG_CHAT_ID")
    if env_cid:
        return env_cid.strip()
    cfg_file = PROJECT_ROOT / "configs/telegram.json"
    if cfg_file.exists():
        d = json.loads(cfg_file.read_text(encoding="utf-8"))
        if d.get("chat_id"):
            return str(d["chat_id"]).strip()

    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates?limit=20", timeout=15.0)
    r.raise_for_status()
    updates = r.json().get("result", [])
    for upd in reversed(updates):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            cid = str(chat["id"])
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            cfg_file.write_text(json.dumps({"chat_id": cid}, indent=2), encoding="utf-8")
            return cid
    raise RuntimeError("No chat_id found. Pass --chat-id or send a message to the bot first.")


def send_episode(client: httpx.Client, token: str, chat_id: str, ep_dir: Path):
    summary = json.loads((ep_dir / "run_summary.json").read_text(encoding="utf-8"))
    long_mp4 = ep_dir / "garychen_long_tg.mp4"
    if not long_mp4.exists() or long_mp4.stat().st_size > 49 * 1024 * 1024:
        orig = ep_dir / "garychen_long.mp4"
        long_mp4 = orig

    short_mp4 = ep_dir / "garychen_short_funnel.mp4"
    pub_md = ep_dir / "youtube_publish_pack.md"

    header = (
        f"🎬 *{summary['long_title']}*\n"
        f"• 集數：`{summary['episode_id']}`\n"
        f"• 長片規格：`1920x1080 @ 60fps`（{summary['long_duration_sec']:.1f}s / {summary['beats_count']} 幕漸進動畫）\n"
        f"• 推流 Shorts：`1080x1920 @ 60fps`（{summary['short_duration_sec']:.1f}s）\n"
        f"• 查證公開來源：{summary['sources_count']} 組（含 {summary['live_screenshots_count']} 張實時網頁截圖）"
    )
    client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": header, "parse_mode": "Markdown"},
    ).raise_for_status()

    with open(long_mp4, "rb") as vf, open(ep_dir / "thumbnail.png", "rb") as tf:
        r_long = client.post(
            f"https://api.telegram.org/bot{token}/sendVideo",
            data={
                "chat_id": chat_id,
                "caption": f"📺 16:9 完整長片｜{summary['long_title']} (1080p60)",
                "width": 1920,
                "height": 1080,
                "supports_streaming": "true",
            },
            files={"video": (long_mp4.name, vf, "video/mp4"), "thumbnail": ("thumb.png", tf, "image/png")},
        )
        r_long.raise_for_status()
        print(f"[TG] Sent Long video: {long_mp4.name} ({long_mp4.stat().st_size / (1024*1024):.1f} MB)")

    with open(short_mp4, "rb") as sf:
        r_short = client.post(
            f"https://api.telegram.org/bot{token}/sendVideo",
            data={
                "chat_id": chat_id,
                "caption": f"📱 9:16 對應推流 Shorts｜{summary['short_title']} (1080x1920 @ 60fps)",
                "width": 1080,
                "height": 1920,
                "supports_streaming": "true",
            },
            files={"video": (short_mp4.name, sf, "video/mp4")},
        )
        r_short.raise_for_status()
        print(f"[TG] Sent Funnel Short: {short_mp4.name} ({short_mp4.stat().st_size / (1024*1024):.1f} MB)")

    if pub_md.exists():
        with open(pub_md, "rb") as df:
            client.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id, "caption": f"📄 YouTube 上架資訊包（時間戳＋公開來源）｜{summary['episode_id']}"},
                files={"document": (pub_md.name, df, "text/markdown")},
            ).raise_for_status()


def send_episode_saved_messages(ep_dir: Path):
    import subprocess
    import time

    summary = json.loads((ep_dir / "run_summary.json").read_text(encoding="utf-8"))
    long_mp4 = ep_dir / "garychen_long_tg.mp4"
    if not long_mp4.exists():
        long_mp4 = ep_dir / "garychen_long.mp4"
    short_mp4 = ep_dir / "garychen_short_funnel.mp4"
    pub_md = ep_dir / "youtube_publish_pack.md"

    def _osa(sc: str):
        subprocess.run(["osascript", "-e", sc], check=True)

    def _send_one(fp: Path, cap: str):
        _osa('tell application "Telegram" to activate\ndelay 0.35\ntell application "System Events" to key code 29 using command down\ndelay 0.45')
        subprocess.run(
            ["swift", "-e", f'import AppKit; let pb = NSPasteboard.general; pb.clearContents(); pb.writeObjects([NSURL(fileURLWithPath: "{fp}")])'],
            check=True,
        )
        _osa('tell application "Telegram" to activate\ndelay 0.3\ntell application "System Events" to key code 9 using command down')
        time.sleep(1.7)
        subprocess.run(["pbcopy"], input=cap.encode("utf-8"), check=True)
        _osa('tell application "Telegram" to activate\ndelay 0.25\ntell application "System Events"\nkey code 9 using command down\ndelay 0.45\nkey code 36\nend tell')
        time.sleep(2.0)

    mins = summary["long_duration_sec"] / 60.0
    thumb_png = ep_dir / "thumbnail.png"
    if thumb_png.exists():
        _send_one(thumb_png, f"🖼 V5 (AGY Gemini 4) YouTube 封面縮圖｜{summary['long_title']}")
    _send_one(
        long_mp4,
        f"📺 V5 (AGY Gemini 4 產稿) 16:9 完整長片 ({mins:.1f} 分鐘 / {summary['beats_count']} 幕 1080p60 Remotion)｜{summary['long_title']}",
    )
    _send_one(
        short_mp4,
        f"📱 V5 (AGY Gemini 4 產稿) 9:16 對應推流 Shorts ({summary['short_duration_sec']:.1f}s @ 60fps)｜{summary['short_title']}",
    )
    if pub_md.exists():
        _send_one(pub_md, f"📄 V5 YouTube 上架資訊包（含時間戳＋公開查證來源）｜{summary['episode_id']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved-messages", action="store_true", help="Send directly to macOS Telegram Desktop Saved Messages")
    ap.add_argument("--token", default=os.environ.get("GC_TG_BOT_TOKEN") or os.environ.get("FIVERR_TG_BOT_TOKEN", ""))
    ap.add_argument("--chat-id", default=None)
    ap.add_argument("--episodes", nargs="*", default=["v5_ep01_gemini4_agent", "v5_ep02_gemini4_nvda"])
    args = ap.parse_args()
    if args.saved_messages:
        for ep in args.episodes:
            ep_dir = PROJECT_ROOT / "outputs" / ep
            if ep_dir.exists():
                send_episode_saved_messages(ep_dir)
        print("[TG] SAVED_MESSAGES_SENT_OK")
        return
    if not args.token:
        sys.exit("Missing Telegram bot token (--token or GC_TG_BOT_TOKEN / FIVERR_TG_BOT_TOKEN).")

    chat_id = resolve_chat_id(args.token, args.chat_id)
    print(f"[TG] Target chat_id={chat_id}")
    with httpx.Client(timeout=180.0) as client:
        for ep in args.episodes:
            ep_dir = PROJECT_ROOT / "outputs" / ep
            if ep_dir.exists():
                send_episode(client, args.token, chat_id, ep_dir)
    print("[TG] ALL_EPISODES_SENT_OK")


if __name__ == "__main__":
    main()
