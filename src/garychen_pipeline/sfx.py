from __future__ import annotations

import numpy as np


def synthesize_sfx(kind: str, sr: int = 44100) -> np.ndarray:
    """
    Synthesizes ultra-subtle, broadcast-clean studio motion-graphics UI sound effects (-27 to -30 dBFS)
    so progressive card pops, terminal lines, stamps, and chapter transitions feel crisp and tactile.
    """
    if kind == "whoosh":
        dur = 0.26
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        rng = np.random.default_rng(42)
        noise = rng.normal(0, 1.0, len(t))
        # Simple moving-average lowpass + bell envelope + soft sine sweep
        kernel = np.hanning(36)
        kernel /= kernel.sum()
        shaped = np.convolve(noise, kernel, mode="same")
        sweep = np.sin(2 * np.pi * (180 + 260 * (t / dur)) * t) * 0.35
        env = np.sin(np.pi * (t / dur)) ** 1.8
        return ((shaped * 0.65 + sweep) * env * 0.032).astype(np.float32)

    if kind == "terminal":
        dur = 0.045
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        click = np.sin(2 * np.pi * 1450 * t) * np.exp(-t * 95)
        return (click * 0.035).astype(np.float32)

    if kind == "stamp":
        dur = 0.14
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        thud = np.sin(2 * np.pi * (135 * np.exp(-t * 14)) * t) * np.exp(-t * 24)
        return (thud * 0.055).astype(np.float32)

    if kind == "pop":
        dur = 0.075
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        pop = np.sin(2 * np.pi * (420 + 280 * (t / dur)) * t) * np.exp(-t * 48)
        return (pop * 0.030).astype(np.float32)

    return np.zeros(0, dtype=np.float32)
