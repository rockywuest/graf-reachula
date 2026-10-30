"""Spooky sound effects, synthesized at startup (no audio files to ship).

Everything is mono float32 at 16 kHz. The robot's speaker is small, so the
sounds stay above ~100 Hz.
"""

import numpy as np

SR = 16000


def normalize(x: np.ndarray, peak: float = 0.8) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


def fade(x: np.ndarray, fade_in: float = 0.05, fade_out: float = 0.3) -> np.ndarray:
    n_in, n_out = int(SR * fade_in), int(SR * fade_out)
    env = np.ones(len(x))
    env[:n_in] = np.linspace(0, 1, n_in)
    env[-n_out:] = np.linspace(1, 0, n_out)
    return x * env


def echo(x: np.ndarray, taps=((0.13, 0.45), (0.27, 0.28), (0.42, 0.15))) -> np.ndarray:
    out = np.concatenate([x, np.zeros(int(SR * taps[-1][0]))])
    for delay, gain in taps:
        d = int(SR * delay)
        out[d:d + len(x)] += gain * x
    return out


def heartbeat(beats: int = 8) -> np.ndarray:
    """Lub-dub that speeds up."""
    out = []
    for i in range(beats):
        seg = np.zeros(int(SR * max(0.5, 0.95 - i * 0.06)))
        for offset, amp in ((0.0, 1.0), (0.2, 0.7)):
            t = np.arange(int(SR * 0.16)) / SR
            thump = amp * np.exp(-t * 22) * (np.sin(2 * np.pi * 110 * t) + 0.5 * np.sin(2 * np.pi * 220 * t))
            start = int(SR * offset)
            seg[start:start + len(thump)] += thump[:len(seg) - start]
        out.append(seg)
    return normalize(np.concatenate(out), 0.9)


def ghost(seconds: float = 3.0) -> np.ndarray:
    """Wooo-OOO-ooo: a gliding, wobbling tone like a theremin."""
    t = np.arange(int(SR * seconds)) / SR
    freq = 330 + 260 * np.sin(np.pi * t / seconds) ** 2 + 18 * np.sin(2 * np.pi * 5.5 * t)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    tone = np.sin(phase) + 0.3 * np.sin(2 * phase) + 0.1 * np.sin(3 * phase)
    return normalize(echo(fade(tone, 0.4, 0.8)))


def door(seconds: float = 2.2, seed: int = 7) -> np.ndarray:
    """Creaking hinge: stick-slip clicks through a wooden resonance."""
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    t = np.arange(n) / SR
    rate = 22 + 60 * np.sin(np.pi * t / seconds) ** 1.5 + 6 * rng.standard_normal(n).cumsum() / np.sqrt(n)
    clicks = np.diff(np.floor(np.cumsum(np.clip(rate, 5, None)) / SR), prepend=0)
    kt = np.arange(int(SR * 0.03)) / SR
    kernel = np.exp(-kt * 180) * (np.sin(2 * np.pi * 780 * kt) + 0.6 * np.sin(2 * np.pi * 1650 * kt))
    return normalize(fade(np.convolve(clicks, kernel)[:n], 0.02, 0.2), 0.75)


def wind(seconds: float = 4.0, seed: int = 3) -> np.ndarray:
    """Howling wind: band-limited noise that swells, plus a faint whistle."""
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    spectrum[(freqs < 250) | (freqs > 1400)] = 0
    noise = np.fft.irfft(spectrum, n)
    t = np.arange(n) / SR
    swell = 0.35 + 0.65 * np.sin(np.pi * t / seconds) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.6 * t))
    whistle = 0.15 * np.sin(2 * np.pi * np.cumsum(820 + 120 * np.sin(2 * np.pi * 0.4 * t)) / SR)
    return normalize(fade((normalize(noise) + whistle) * swell, 0.6, 0.8), 0.7)


def boo(seconds: float = 1.1, seed: int = 11) -> np.ndarray:
    """The jump-scare hit: a sudden rasping stab that drops in pitch."""
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    t = np.arange(n) / SR
    freq = 520 * np.exp(-t * 1.6) + 140
    phase = 2 * np.pi * np.cumsum(freq) / SR
    # Square-ish wave plus noise sounds like a hoarse shout on a small speaker
    voice = np.tanh(3 * np.sin(phase)) + 0.35 * np.sin(2 * phase)
    rasp = rng.standard_normal(n) * 0.25
    env = np.minimum(1, t / 0.015) * np.exp(-t * 1.8)
    return normalize(echo(fade((voice + rasp) * env, 0.005, 0.25)), 0.95)


def bells(seconds: float = 4.0) -> np.ndarray:
    """A slow, out-of-tune church bell striking three times."""
    out = np.zeros(int(SR * seconds))
    t = np.arange(int(SR * 1.8)) / SR
    partials = ((220, 1.0), (440 * 1.01, 0.5), (523, 0.35), (660 * 0.99, 0.25))
    strike = sum(a * np.sin(2 * np.pi * f * t) for f, a in partials) * np.exp(-t * 2.2)
    for k in range(3):
        start = int(SR * 1.15 * k)
        seg = strike[:len(out) - start]
        out[start:start + len(seg)] += seg
    return normalize(fade(out, 0.01, 0.6), 0.8)


SOUNDS = {
    "heartbeat": heartbeat,
    "ghost": ghost,
    "door": door,
    "wind": wind,
    "boo": boo,
    "bells": bells,
}


def build_library() -> dict[str, np.ndarray]:
    """Render every sound once."""
    return {name: make() for name, make in SOUNDS.items()}
