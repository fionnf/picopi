"""Acquisition backends.

A common :class:`ScopeBackend` interface lets the same UI drive either real
PicoScope 2000-series hardware (:class:`PicoScope2000Backend`) or a hardware-free
:class:`SimulatedBackend`. Every backend yields the same
``(time_s, volts_mV, dt_s)`` tuple from :meth:`capture_block`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

__all__ = ["ScopeBackend", "SimulatedBackend", "PicoScope2000Backend"]


class ScopeBackend(ABC):
    """Abstract acquisition backend.

    Contract for :meth:`capture_block`: returns ``(time_s, volts_mV, dt_s)``
    where ``time_s`` is the sample time axis in seconds, ``volts_mV`` the sample
    values in millivolts, and ``dt_s`` the sample interval in seconds.
    """

    @abstractmethod
    def open(self) -> None:
        """Acquire/open the device. Safe to call again after :meth:`close`."""

    @abstractmethod
    def configure(self, **kwargs) -> None:
        """Update acquisition parameters. Unknown keys are ignored."""

    @abstractmethod
    def capture_block(self):
        """Capture one block. Returns ``(time_s, volts_mV, dt_s)``."""

    @abstractmethod
    def close(self) -> None:
        """Release the device. Safe to call more than once."""

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class SimulatedBackend(ScopeBackend):
    """Generates a noisy sine of known frequency — no PicoSDK required.

    Phase is carried across blocks so a live plot scrolls continuously.
    """

    def __init__(
        self,
        frequency: float = 1000.0,
        amplitude_mV: float = 1000.0,
        sample_rate: float = 200_000.0,
        samples: int = 2000,
        noise_mV: float = 20.0,
        seed: int | None = None,
    ):
        self.frequency = float(frequency)
        self.amplitude_mV = float(amplitude_mV)
        self.sample_rate = float(sample_rate)
        self.samples = int(samples)
        self.noise_mV = float(noise_mV)
        self._rng = np.random.default_rng(seed)
        self._phase = 0.0

    def open(self) -> None:
        self._phase = 0.0

    def configure(self, **kwargs) -> None:
        if kwargs.get("samples"):
            self.samples = int(kwargs["samples"])
        if kwargs.get("sample_rate"):
            self.sample_rate = float(kwargs["sample_rate"])
        if kwargs.get("frequency"):
            self.frequency = float(kwargs["frequency"])

    def capture_block(self):
        dt = 1.0 / self.sample_rate
        n = self.samples
        t = np.arange(n) * dt
        phase = self._phase + 2.0 * np.pi * self.frequency * t
        signal = self.amplitude_mV * np.sin(phase)
        signal += self._rng.normal(0.0, self.noise_mV, n)
        # Advance the phase by one full block so the next capture is continuous.
        self._phase = float((self._phase + 2.0 * np.pi * self.frequency * n * dt) % (2.0 * np.pi))
        return t, signal, dt

    def close(self) -> None:
        pass


class PicoScope2000Backend(ScopeBackend):
    """Block-mode acquisition from a PicoScope 2000A/B via the ``ps2000a`` driver.

    The ``picosdk`` wrapper and the native PicoSDK driver are imported lazily in
    :meth:`open`, so this module imports fine on machines without them (e.g. CI).
    Older non-A 2000 units use the ``ps2000`` driver instead — swapping the
    import below is the only change needed for those.
    """

    def __init__(
        self,
        channel: str = "A",
        v_range: str = "2V",
        coupling: str = "DC",
        timebase: int = 8,
        samples: int = 2000,
        trigger_mV: float = 0.0,
        trigger_enabled: bool = True,
        auto_trigger_ms: int = 1000,
    ):
        self.channel = channel.upper()
        self.v_range = v_range.upper()
        self.coupling = coupling.upper()
        self.timebase = int(timebase)
        self.samples = int(samples)
        self.trigger_mV = float(trigger_mV)
        self.trigger_enabled = bool(trigger_enabled)
        self.auto_trigger_ms = int(auto_trigger_ms)

        # Populated in open().
        self._ps = None
        self._functions = None
        self._ctypes = None
        self._handle = None
        self._max_adc = None
        self._range_const = None
        self._channel_const = None
        self._dt = None
        self._buffer_max = None
        self._buffer_min = None

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> None:
        import ctypes

        from picosdk.ps2000a import ps2000a as ps
        from picosdk.functions import assert_pico_ok, mV2adc

        self._ctypes = ctypes
        self._ps = ps
        self._functions = {"assert_pico_ok": assert_pico_ok, "mV2adc": mV2adc}

        self._handle = ctypes.c_int16()
        assert_pico_ok(ps.ps2000aOpenUnit(ctypes.byref(self._handle), None))

        self._max_adc = ctypes.c_int16()
        assert_pico_ok(ps.ps2000aMaximumValue(self._handle, ctypes.byref(self._max_adc)))

        self._channel_const = ps.PS2000A_CHANNEL["PS2000A_CHANNEL_" + self.channel]
        self._range_const = ps.PS2000A_RANGE["PS2000A_" + self.v_range]
        coupling_const = ps.PS2000A_COUPLING["PS2000A_" + self.coupling]

        assert_pico_ok(
            ps.ps2000aSetChannel(
                self._handle, self._channel_const, 1, coupling_const, self._range_const, 0.0
            )
        )

        # Simple rising-edge trigger on the active channel.
        threshold_adc = 0
        if self.trigger_enabled:
            threshold_adc = mV2adc(self.trigger_mV, self._range_const, self._max_adc)
        assert_pico_ok(
            ps.ps2000aSetSimpleTrigger(
                self._handle,
                1 if self.trigger_enabled else 0,
                self._channel_const,
                int(threshold_adc),
                ps.PS2000A_THRESHOLD_DIRECTION["PS2000A_RISING"],
                0,  # delay
                self.auto_trigger_ms,
            )
        )

        # Query the real sample interval for the chosen timebase.
        interval_ns = ctypes.c_float()
        returned_max_samples = ctypes.c_int32()
        assert_pico_ok(
            ps.ps2000aGetTimebase2(
                self._handle,
                self.timebase,
                self.samples,
                ctypes.byref(interval_ns),
                0,  # oversample (unused)
                ctypes.byref(returned_max_samples),
                0,  # segment index
            )
        )
        self._dt = interval_ns.value * 1e-9

        self._buffer_max = (ctypes.c_int16 * self.samples)()
        self._buffer_min = (ctypes.c_int16 * self.samples)()
        assert_pico_ok(
            ps.ps2000aSetDataBuffers(
                self._handle,
                self._channel_const,
                ctypes.byref(self._buffer_max),
                ctypes.byref(self._buffer_min),
                self.samples,
                0,  # segment index
                0,  # ratio mode: none
            )
        )

    def configure(self, **kwargs) -> None:
        # Applied on the next open(); reopen to take effect on live hardware.
        for key in ("channel", "v_range", "coupling", "timebase", "samples", "trigger_mV"):
            if kwargs.get(key) is not None:
                setattr(self, key, kwargs[key])

    def capture_block(self):
        ctypes = self._ctypes
        ps = self._ps
        assert_pico_ok = self._functions["assert_pico_ok"]

        assert_pico_ok(
            ps.ps2000aRunBlock(
                self._handle,
                0,  # pre-trigger samples
                self.samples,  # post-trigger samples
                self.timebase,
                0,  # oversample (unused)
                None,  # time indisposed (unused)
                0,  # segment index
                None,  # lpReady callback (poll instead)
                None,  # pParameter
            )
        )

        ready = ctypes.c_int16(0)
        while ready.value == 0:
            ps.ps2000aIsReady(self._handle, ctypes.byref(ready))

        overflow = ctypes.c_int16()
        n_samples = ctypes.c_int32(self.samples)
        assert_pico_ok(
            ps.ps2000aGetValues(
                self._handle,
                0,  # start index
                ctypes.byref(n_samples),
                1,  # downsample ratio
                0,  # ratio mode: none
                0,  # segment index
                ctypes.byref(overflow),
            )
        )

        from picosdk.functions import adc2mV

        n = n_samples.value
        volts_mV = np.asarray(adc2mV(self._buffer_max, self._range_const, self._max_adc)[:n], dtype=float)
        t = np.arange(n) * self._dt
        return t, volts_mV, self._dt

    def close(self) -> None:
        if self._ps is not None and self._handle is not None:
            try:
                self._ps.ps2000aStop(self._handle)
                self._ps.ps2000aCloseUnit(self._handle)
            finally:
                self._handle = None
