"""PicoPi — live PicoScope 2000-series trace + frequency measurement.

A small application to display a live oscilloscope trace from a PicoScope
2000-series USB scope and continuously measure the oscillation frequency
(via FFT peak and zero-crossing). Designed to run on a Raspberry Pi.
"""

__version__ = "0.1.0"

from .dsp import fft_frequency, zero_crossing_frequency

__all__ = ["fft_frequency", "zero_crossing_frequency", "__version__"]
