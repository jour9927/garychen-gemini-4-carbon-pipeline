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

        eps = load_cluster_endpoints()
        # Prefer >=9.5GB free CUDA (Colab RTX PRO 6000) first, then 36GB M3 Pro MPS (SDXL Base 1.0), then b850
        eps_img = sorted(eps, key=lambda e: (0 if "colab" in e.name else (1 if "mps" in e.name else 2)))
        for ep in eps_img:
            try:
                hr = httpx.get(f"{ep.url}/health", timeout=6.0, trust_env=False)
                if hr.status_code != 200:
                    continue
                hj = hr.json()
                gpu = hj.get("gpu") or {}
                if gpu.get("cuda_available") and int(gpu.get("free_mb", 0)) < 8500 and "sdxl_pipe" not in (hj.get("loaded_models") or []):
                    print(f"[image_gen] Skipping busy CUDA node {ep.name} (free_mb={gpu.get('free_mb')})", flush=True)
                    continue
                print(f"[image_gen] Dispatching {len(items)} AI images to {ep.name} ({ep.url})", flush=True)
                headers = {"Authorization": f"Bearer {ep.token}"}
                with httpx.Client(timeout=60.0, trust_env=False) as client:
                    sub = client.post(
                        f"{ep.url}/job/submit",
                        headers=headers,
                        json={"kind": "image_batch", "items": items},
                    )
                    sub.raise_for_status()
                    jid = sub.json()["job_id"]
                    t0 = time.time()
                    while time.time() - t0 < 900:
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
