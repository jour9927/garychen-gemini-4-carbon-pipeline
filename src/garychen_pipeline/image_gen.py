from __future__ import annotations

import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter

from .config import load_cluster_endpoints


class GarychenImageGenerator:
    """
    Dispatches PyTorch AI image generation (SDXL-Turbo / Diffusers) to RTX PRO 6000 Colab (:19688) first,
    immediately saving all generated PNG assets onto local disk (本機).
    Includes high-craft procedural studio fallback only if all remote GPU nodes are unreachable.
    """

    def generate_batch(self, items: list[dict], out_dir: Path) -> tuple[dict[str, str], str]:
        """
        items: [{"id": "scene_01", "prompt": "...", "width": 768, "height": 512}]
        Returns: ({id: local_png_path}, backend_used)
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        cached: dict[str, str] = {}
        for it in items:
            p = out_dir / f"{it['id']}.png"
            if p.exists() and p.stat().st_size > 1000:
                cached[it["id"]] = str(p)
        if len(cached) == len(items) and items:
            return cached, "local_disk_cache"

        for ep in load_cluster_endpoints():
            try:
                hr = httpx.get(f"{ep.url}/health", timeout=6.0)
                if hr.status_code != 200:
                    continue
                print(f"[image_gen] Dispatching {len(items)} AI images to {ep.name} ({ep.url})", flush=True)
                headers = {"Authorization": f"Bearer {ep.token}"}
                with httpx.Client(timeout=60.0) as client:
                    sub = client.post(
                        f"{ep.url}/job/submit",
                        headers=headers,
                        json={"kind": "image_batch", "items": items},
                    )
                    sub.raise_for_status()
                    jid = sub.json()["job_id"]
                    t0 = time.time()
                    while time.time() - t0 < 600:
                        time.sleep(2.0)
                        sr = client.get(f"{ep.url}/job/status/{jid}", headers=headers)
                        sr.raise_for_status()
                        st = sr.json()
                        if st.get("status") == "done":
                            dev = st.get("result", {}).get("device", "gpu")
                            out_map: dict[str, str] = {}
                            for o in st["result"]["outputs"]:
                                dl = client.get(f"{ep.url}/download/{o['rel_path']}", headers=headers)
                                dl.raise_for_status()
                                lp = out_dir / f"{o['id']}.png"
                                lp.write_bytes(dl.content)
                                out_map[o["id"]] = str(lp)
                            return out_map, f"{ep.name}:{dev}"
                        if st.get("status") == "error":
                            raise RuntimeError(st.get("error", "remote image_batch error")[:260])
            except Exception as exc:
                print(f"[image_gen] Node {ep.name} skipped ({exc})", flush=True)

        # Offline safety net so unattended pipeline never crashes if internet/Colab drops mid-run
        out_map = {}
        for idx, it in enumerate(items):
            lp = out_dir / f"{it['id']}.png"
            self._render_studio_fallback(lp, int(it.get("width", 768)), int(it.get("height", 512)), idx)
            out_map[it["id"]] = str(lp)
        return out_map, "local_procedural_fallback"

    @staticmethod
    def _render_studio_fallback(out_path: Path, w: int, h: int, seed: int):
        img = Image.new("RGB", (w, h), (32, 32, 34))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        cx, cy = w // 2, h // 2
        gd.ellipse((cx - 160, cy - 160, cx + 160, cy + 160), fill=(235, 139, 27, 75))
        glow = glow.filter(ImageFilter.GaussianBlur(42))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
        d = ImageDraw.Draw(img)
        for r in (60, 105, 150):
            d.rounded_rectangle((cx - r, cy - r, cx + r, cy + r), radius=24, outline=(235, 139, 27), width=3)
        img.save(str(out_path))
