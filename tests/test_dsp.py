"""Unit tests for the frequency estimators against synthetic signals."""

import numpy as np
import pytest

from picopi.dsp import fft_frequency, zero_crossing_frequency


def make_sine(freq, fs, n, amplitude=1.0, noise=0.0, offset=0.0, phase=0.0, seed=0):
    t = np.arange(n) / fs
    sig = amplitude * np.sin(2 * np.pi * freq * t + phase) + offset
    if noise:
        sig = sig + np.random.default_rng(seed).normal(0.0, noise, n)
    return sig


def _buffer_len(freq, fs, min_periods=30, floor=4096):
    """Enough samples to hold at least ``min_periods`` cycles of ``freq``."""
    return max(floor, int(min_periods * fs / freq))


@pytest.mark.parametrize("freq", [50.0, 440.0, 1000.0, 12345.0])
def test_fft_frequency_clean(freq):
    fs = 500_000.0
    n = _buffer_len(freq, fs)
    sig = make_sine(freq, fs, n)
    est = fft_frequency(sig, fs)
    bin_width = fs / n
    assert abs(est - freq) < bin_width  # within one FFT bin


@pytest.mark.parametrize("freq", [50.0, 440.0, 1000.0, 12345.0])
def test_zero_crossing_frequency_clean(freq):
    fs = 500_000.0
    n = _buffer_len(freq, fs)
    sig = make_sine(freq, fs, n)
    est = zero_crossing_frequency(sig, fs)
    assert est == pytest.approx(freq, rel=0.01)  # within 1%


def test_estimators_ignore_dc_offset():
    fs = 500_000.0
    freq = 1000.0
    sig = make_sine(freq, fs, 4096, offset=3000.0)
    assert fft_frequency(sig, fs) == pytest.approx(freq, rel=0.02)
    assert zero_crossing_frequency(sig, fs) == pytest.approx(freq, rel=0.01)


def test_estimators_tolerate_noise():
    fs = 500_000.0
    freq = 1000.0
    sig = make_sine(freq, fs, 8192, amplitude=1000.0, noise=50.0)
    assert fft_frequency(sig, fs) == pytest.approx(freq, rel=0.02)
    assert zero_crossing_frequency(sig, fs) == pytest.approx(freq, rel=0.05)


def test_flat_signal_returns_nan():
    fs = 500_000.0
    flat = np.zeros(1024)
    assert np.isnan(fft_frequency(flat, fs))
    assert np.isnan(zero_crossing_frequency(flat, fs))


def test_invalid_inputs_return_nan():
    assert np.isnan(fft_frequency([1.0, 2.0], 0.0))
    assert np.isnan(zero_crossing_frequency([1.0], 500_000.0))
