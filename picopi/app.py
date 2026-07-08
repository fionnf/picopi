"""Command-line entry point: wires a backend to the worker and GUI."""

from __future__ import annotations

import argparse
import sys

__all__ = ["main", "build_backend"]


def build_backend(args):
    """Construct the acquisition backend selected on the command line."""
    if args.simulate:
        from .backends import SimulatedBackend

        return SimulatedBackend(
            frequency=args.sim_freq,
            sample_rate=args.sample_rate,
            samples=args.samples,
        )

    from .backends import PicoScope2000Backend

    return PicoScope2000Backend(
        channel=args.channel,
        v_range=args.range,
        timebase=args.timebase,
        samples=args.samples,
        trigger_mV=args.trigger,
    )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="picopi",
        description="Live PicoScope 2000-series trace with frequency measurement.",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Use a synthetic signal instead of real hardware (no PicoSDK needed).",
    )
    parser.add_argument(
        "--sim-freq",
        type=float,
        default=1000.0,
        help="Frequency (Hz) of the simulated signal (with --simulate).",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=200_000.0,
        help="Sample rate (Hz) for the simulated backend.",
    )
    parser.add_argument("--channel", default="A", help="Scope channel (A/B). Hardware only.")
    parser.add_argument(
        "--range", default="2V", help="Voltage range, e.g. 50MV, 500MV, 2V, 5V. Hardware only."
    )
    parser.add_argument(
        "--timebase", type=int, default=8, help="PicoScope timebase index. Hardware only."
    )
    parser.add_argument("--samples", type=int, default=2000, help="Samples per capture block.")
    parser.add_argument(
        "--trigger", type=float, default=0.0, help="Rising-edge trigger threshold (mV). Hardware only."
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    backend = build_backend(args)

    from PyQt5 import QtWidgets

    from .gui import LiveScopeWindow
    from .worker import AcquisitionWorker

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    worker = AcquisitionWorker(backend)
    window = LiveScopeWindow(worker)
    window.show()
    window.start()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
