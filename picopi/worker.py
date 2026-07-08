"""Background acquisition thread.

Runs block captures in a :class:`~PyQt5.QtCore.QThread` so USB transfers never
block the Qt event loop, and emits results (plus both frequency estimates) back
to the GUI thread via signals.
"""

from __future__ import annotations

from PyQt5 import QtCore

from .dsp import fft_frequency, zero_crossing_frequency

__all__ = ["AcquisitionWorker"]


class AcquisitionWorker(QtCore.QThread):
    """Loops ``backend.capture_block()`` and emits data until stopped."""

    # (time_s, volts_mV, dt_s, f_fft_hz, f_zero_crossing_hz)
    dataReady = QtCore.pyqtSignal(object, object, float, float, float)
    error = QtCore.pyqtSignal(str)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self._running = False

    def run(self) -> None:
        self._running = True
        try:
            self.backend.open()
        except Exception as exc:  # pragma: no cover - hardware/driver errors
            self.error.emit(f"Failed to open scope: {exc}")
            return

        try:
            while self._running:
                try:
                    t, mV, dt = self.backend.capture_block()
                except Exception as exc:  # pragma: no cover - hardware errors
                    self.error.emit(f"Capture failed: {exc}")
                    break
                fs = 1.0 / dt if dt > 0 else 0.0
                f_fft = fft_frequency(mV, fs)
                f_zc = zero_crossing_frequency(mV, fs)
                self.dataReady.emit(t, mV, dt, f_fft, f_zc)
        finally:
            try:
                self.backend.close()
            except Exception:  # pragma: no cover
                pass

    def stop(self) -> None:
        """Signal the loop to exit and wait for the thread to finish."""
        self._running = False
        self.wait(2000)
