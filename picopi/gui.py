"""PyQtGraph live-scope window.

Shows the time-domain trace and its magnitude spectrum, with a readout of both
frequency estimates and the peak-to-peak amplitude. All heavy work happens in
:class:`~picopi.worker.AcquisitionWorker`; this window only re-draws on each
``dataReady`` signal, which keeps it responsive on a Raspberry Pi.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets

__all__ = ["LiveScopeWindow"]


class LiveScopeWindow(QtWidgets.QMainWindow):
    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.setWindowTitle("PicoPi — Live Scope")
        self.resize(900, 640)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # --- readout + controls ------------------------------------------
        self.readout = QtWidgets.QLabel("Waiting for data…")
        font = self.readout.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self.readout.setFont(font)
        layout.addWidget(self.readout)

        controls = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QPushButton("Run")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.run_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.run_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        # --- plots -------------------------------------------------------
        pg.setConfigOptions(antialias=True)
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw, stretch=1)

        self.trace_plot = self.glw.addPlot(row=0, col=0, title="Time domain")
        self.trace_plot.setLabel("bottom", "Time", units="ms")
        self.trace_plot.setLabel("left", "Voltage", units="mV")
        self.trace_plot.showGrid(x=True, y=True, alpha=0.3)
        self.trace_curve = self.trace_plot.plot(pen=pg.mkPen("y", width=1))

        self.spec_plot = self.glw.addPlot(row=1, col=0, title="Spectrum")
        self.spec_plot.setLabel("bottom", "Frequency", units="Hz")
        self.spec_plot.setLabel("left", "Magnitude")
        self.spec_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spec_curve = self.spec_plot.plot(pen=pg.mkPen("c", width=1))
        self._peak_line = self.spec_plot.addLine(x=0, pen=pg.mkPen("r", style=pg.QtCore.Qt.DashLine))

        self.worker.dataReady.connect(self.on_data)
        self.worker.error.connect(self.on_error)

    # -- control -----------------------------------------------------------

    def start(self) -> None:
        if not self.worker.isRunning():
            self.worker.start()
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop(self) -> None:
        self.worker.stop()
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    # -- slots -------------------------------------------------------------

    def on_data(self, t, mV, dt, f_fft, f_zc) -> None:
        self.trace_curve.setData(t * 1e3, mV)  # seconds -> ms

        n = mV.size
        if n >= 4 and dt > 0:
            sig = mV - np.mean(mV)
            magnitude = np.abs(np.fft.rfft(sig * np.hanning(n)))
            freqs = np.fft.rfftfreq(n, dt)
            self.spec_curve.setData(freqs, magnitude)

        if np.isfinite(f_fft):
            self._peak_line.setValue(f_fft)

        vpp = float(np.ptp(mV)) if n else 0.0
        fft_txt = f"{f_fft:,.1f} Hz" if np.isfinite(f_fft) else "—"
        zc_txt = f"{f_zc:,.1f} Hz" if np.isfinite(f_zc) else "—"
        self.readout.setText(
            f"FFT peak: {fft_txt}    Zero-crossing: {zc_txt}    Vpp: {vpp:,.0f} mV"
        )

    def on_error(self, message: str) -> None:
        self.readout.setText(f"Error: {message}")
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    # -- Qt ----------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self.worker.stop()
        super().closeEvent(event)
