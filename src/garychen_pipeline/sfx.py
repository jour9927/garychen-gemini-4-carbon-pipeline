from __future__ import annotations

import numpy as np


def synthesize_ambient_bed(
    total_samples: int,
    sr: int = 44100,
    voice_track: np.ndarray | None = None,
    category: str = "ai_agent",
) -> np.ndarray:
    """
    Synthesizes an authentic @garychenai broadcast-warm studio acoustic floor + ultra-subtle dark-tech
    ambient pulse bed (sidechain-ducked under speech), eliminating sterile -inf dB digital silence
    gaps so inter-sentence breathing matches `01_UrFrDJ` (`p05 ≈ -65 dB`, `p20 ≈ -41 dB`).
    """
    if total_samples <= 0:
        return np.zeros(0, dtype=np.float32)

    rng = np.random.default_rng(2026)
    # 1. Warm low-passed studio room air (-60 dBFS)
    white = rng.normal(0.0, 1.0, total_samples).astype(np.float32)
    k_room = np.hanning(96).astype(np.float32)
    k_room /= k_room.sum()
    room_air = np.convolve(white, k_room, mode="same") * 0.00095

    # 2. Ultra-subtle warm harmonic pad (low-passed fifths, -42 dBFS, slower & calmer for us_stocks)
    t = np.arange(total_samples, dtype=np.float32) / float(sr)
    root_hz = 98.0 if category == "us_stocks" else 110.0  # G2 vs A2 warm studio fundamental
    lfo1 = 0.58 + 0.42 * np.sin(2.0 * np.pi * 0.085 * t)
    lfo2 = 0.55 + 0.45 * np.sin(2.0 * np.pi * 0.053 * t + 1.1)
    pad = (
        np.sin(2.0 * np.pi * root_hz * t) * 0.52 * lfo1
        + np.sin(2.0 * np.pi * (root_hz * 1.5) * t) * 0.31 * lfo2
        + np.sin(2.0 * np.pi * (root_hz * 2.0) * t) * 0.17 * lfo1
    ).astype(np.float32)

    # Gentle soft rhythmic pulse every 0.75s (subtle Remotion explainer momentum, barely perceptible)
    beat_hz = 1.15 if category == "us_stocks" else 1.35
    pulse_env = (0.82 + 0.18 * (np.sin(2.0 * np.pi * beat_hz * t) ** 4)).astype(np.float32)
    pad = pad * pulse_env * 0.0052

    # 3. Smooth sidechain ducking when Gary is speaking (-6.5 dB under active speech)
    if voice_track is not None and len(voice_track) == total_samples:
        win = max(64, int(sr * 0.08))
        abs_v = np.abs(voice_track)
        # Downsampled envelope for speed on multi-minute tracks
        step = max(1, win // 4)
        coarse = abs_v[::step]
        k_env = np.ones(8, dtype=np.float32) / 8.0
        smooth_c = np.convolve(coarse, k_env, mode="same")
        speaking = np.clip(smooth_c / 0.025, 0.0, 1.0)
        duck_c = 1.0 - 0.54 * speaking
        duck = np.interp(
            np.linspace(0, len(duck_c) - 1, total_samples, dtype=np.float32),
            np.arange(len(duck_c), dtype=np.float32),
            duck_c,
        ).astype(np.float32)
        pad *= duck

    # Fade in first 0.5s and fade out last 0.8s
    n_in = min(total_samples // 4, int(0.5 * sr))
    n_out = min(total_samples // 4, int(0.8 * sr))
    if n_in > 8:
        pad[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)
    if n_out > 8:
        pad[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)

    return (room_air + pad).astype(np.float32)


def synthesize_sfx(kind: str, sr: int = 44100) -> np.ndarray:
    """
    V4 Tactile Studio Foley SFX (ZERO sine-beep spam!):
      - `whoosh`: Filtered warm air whoosh on chapter transitions only
      - `typing`: Realistic multi-key mechanical switch burst for live terminal / code / prompt typing
      - `click`: Crisp dual-transient macOS trackpad/mouse click for browser zoom-click
      - `thock` / `pop`: Warm damped low-mid matte UI thock (-33 dBFS) on beat card entrance
      - `stamp`: Deep matte stamp thud on Before/After & shock reveals
    """
    if kind == "whoosh":
        dur = 0.28
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
        rng = np.random.default_rng(42)
        noise = rng.normal(0.0, 1.0, n).astype(np.float32)
        k1 = np.hanning(44).astype(np.float32)
        k1 /= k1.sum()
        k2 = np.hanning(140).astype(np.float32)
        k2 /= k2.sum()
        band = np.convolve(noise, k1, mode="same") - np.convolve(noise, k2, mode="same")
        env = (np.sin(np.pi * (t / dur)) ** 2.1).astype(np.float32)
        return (band * env * 0.055).astype(np.float32)

    if kind in ("typing", "terminal"):
        dur = 0.52
        n = int(sr * dur)
        out = np.zeros(n, dtype=np.float32)
        rng = np.random.default_rng(108)
        offsets = [0.01, 0.075, 0.135, 0.215, 0.28, 0.365, 0.435]
        for idx, off in enumerate(offsets):
            pos = int(off * sr)
            kn = min(int(0.028 * sr), n - pos)
            if kn <= 8:
                continue
            kt = np.linspace(0, kn / sr, kn, endpoint=False, dtype=np.float32)
            burst = rng.normal(0.0, 1.0, kn).astype(np.float32)
            k_lp = np.hanning(10).astype(np.float32)
            k_lp /= k_lp.sum()
            filtered = np.convolve(burst, k_lp, mode="same")
            body = np.sin(2.0 * np.pi * (240.0 + (idx % 3) * 28.0) * kt) * np.exp(-kt * 135.0)
            transient = filtered * np.exp(-kt * 210.0)
            gain = 0.024 * (0.82 + 0.18 * ((idx * 37) % 5) / 4.0)
            out[pos : pos + kn] += (transient * 0.7 + body * 0.45) * gain
        return out

    if kind == "click":
        dur = 0.065
        n = int(sr * dur)
        out = np.zeros(n, dtype=np.float32)
        rng = np.random.default_rng(77)
        for off, amp in ((0.0, 0.036), (0.034, 0.019)):
            p = int(off * sr)
            kn = min(int(0.018 * sr), n - p)
            kt = np.linspace(0, kn / sr, kn, endpoint=False, dtype=np.float32)
            click_n = rng.normal(0.0, 1.0, kn).astype(np.float32) * np.exp(-kt * 320.0)
            thock = np.sin(2.0 * np.pi * 620.0 * np.exp(-kt * 45.0) * kt) * np.exp(-kt * 190.0)
            out[p : p + kn] += (click_n * 0.45 + thock * 0.55) * amp
        return out

    if kind == "stamp":
        dur = 0.14
        t = np.linspace(0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
        thud = np.sin(2.0 * np.pi * (125.0 * np.exp(-t * 15.0)) * t) * np.exp(-t * 26.0)
        return (thud * 0.045).astype(np.float32)

    if kind in ("thock", "pop"):
        dur = 0.046
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
        # Soft matte low-mid thock (185Hz -> 92Hz), ZERO high-pitched sine beep!
        thock = np.sin(2.0 * np.pi * (185.0 * np.exp(-t * 28.0)) * t) * np.exp(-t * 78.0)
        return (thock * 0.020).astype(np.float32)

    return np.zeros(0, dtype=np.float32)
