"""Frequency-estimation DSP helpers.

Pure NumPy, no Qt or hardware dependencies, so these functions can be unit
tested in isolation and reused headlessly. Both estimators take a signal array
and the sample rate ``fs`` (samples/second) and return a frequency in Hz, or
``nan`` when the signal does not contain a measurable oscillation.
"""

from __future__ import annotations

import numpy as np

__all__ = ["fft_frequency", "zero_crossing_frequency"]


def _parabolic_peak_offset(magnitude: np.ndarray, k: int) -> float:
    """Sub-bin peak offset around index ``k`` via a 3-point parabola fit.

    Returns a value in roughly (-0.5, 0.5) to be added to ``k`` for a refined
    peak location. Returns 0.0 at the array edges where the fit is undefined.
    """
    if k <= 0 or k >= magnitude.size - 1:
        return 0.0
    alpha = magnitude[k - 1]
    beta = magnitude[k]
    gamma = magnitude[k + 1]
    denom = alpha - 2.0 * beta + gamma
    if denom == 0.0:
        return 0.0
    return 0.5 * (alpha - gamma) / denom


def fft_frequency(signal, fs: float) -> float:
    """Dominant oscillation frequency (Hz) from the FFT magnitude spectrum.

    The signal is DC-removed and Hann-windowed before the real FFT. The DC bin
    is ignored and the peak is refined with parabolic interpolation for
    sub-bin accuracy.
    """
    signal = np.asarray(signal, dtype=float)
    n = signal.size
    if n < 4 or fs <= 0:
        return float("nan")

    sig = signal - np.mean(signal)
    window = np.hanning(n)
    magnitude = np.abs(np.fft.rfft(sig * window))
    if magnitude.size < 2:
        return float("nan")

    # Ignore the DC bin when locating the peak.
    search = magnitude.copy()
    search[0] = 0.0
    k = int(np.argmax(search))
    if k == 0:
        return float("nan")

    offset = _parabolic_peak_offset(magnitude, k)
    return float((k + offset) * fs / n)


def zero_crossing_frequency(signal, fs: float, hysteresis_frac: float = 0.25) -> float:
    """Fundamental frequency (Hz) from averaged rising zero-crossing periods.

    The signal is DC-removed and rising crossings are detected with a hysteresis
    gate: a crossing is only counted after the signal has first dipped below
    ``-hysteresis_frac * amplitude``. This suppresses the many false crossings a
    noisy signal produces near the zero level. Each accepted crossing is linearly
    interpolated to sub-sample precision, and the mean interval between crossings
    gives the period.

    Returns ``nan`` when fewer than two crossings are found (e.g. a flat signal,
    or a buffer shorter than ~two periods).
    """
    signal = np.asarray(signal, dtype=float)
    n = signal.size
    if n < 2 or fs <= 0:
        return float("nan")

    sig = signal - np.mean(signal)
    rms = float(np.sqrt(np.mean(sig * sig)))
    if not np.isfinite(rms) or rms == 0.0:
        return float("nan")
    # Estimate peak amplitude from RMS (exact for a sine) and gate on a fraction.
    hysteresis = hysteresis_frac * np.sqrt(2.0) * rms

    crossings = []
    armed = False
    for i in range(n - 1):
        if sig[i] < -hysteresis:
            armed = True
        if armed and sig[i] <= 0.0 < sig[i + 1]:
            # Linear interpolation of the sub-sample crossing position.
            frac = -sig[i] / (sig[i + 1] - sig[i])
            crossings.append(i + frac)
            armed = False

    if len(crossings) < 2:
        return float("nan")

    mean_period = float(np.mean(np.diff(np.asarray(crossings)))) / fs
    if mean_period <= 0.0:
        return float("nan")
    return 1.0 / mean_period
