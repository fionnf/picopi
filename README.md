# PicoPi

A small Python application for a **PicoScope 2000-series** USB oscilloscope that
shows a **live trace** and continuously **measures the oscillation frequency**
(via FFT peak and zero-crossing). Built to run on a **Raspberry Pi**.

- Live time-domain trace + magnitude spectrum, drawn with **PyQtGraph**
  (fast enough for real-time refresh on a Pi).
- Two frequency estimates side by side: **FFT peak** (parabolic-interpolated)
  and **zero-crossing** (sub-sample interpolated).
- A **simulated backend** so you can run and test everything without any
  hardware or drivers.

## Quick start (no hardware)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m picopi --simulate --sim-freq 1000
```

You should see a live 1 kHz sine and both readouts converging on ~1000 Hz.

## Running against a real PicoScope (Raspberry Pi)

1. **Install the native PicoSDK driver.** The `picosdk` Python package is only a
   ctypes wrapper — it needs Pico's native `libps2000a` library. Install it from
   Pico Technology's APT repository or a `.deb`:

   ```bash
   # Add Pico's repo (see picotech.com for the current instructions), then:
   sudo apt update
   sudo apt install libps2000a          # native 2000A/B driver
   ```

2. **Install Python dependencies** (PyQt5 is best installed from apt on
   Raspberry Pi OS):

   ```bash
   sudo apt install python3-pyqt5
   pip install -r requirements.txt      # numpy, pyqtgraph, picosdk
   ```

3. **Plug in the scope and run:**

   ```bash
   python -m picopi --channel A --range 2V --timebase 8 --samples 2000
   ```

   If the scope isn't detected, check USB permissions (a `udev` rule may be
   required so a non-root user can access the device).

> **Older non-A 2000 units:** these use the `ps2000` driver rather than
> `ps2000a`. Swap the import in `picopi/backends.py`
> (`from picosdk.ps2000 import ps2000 as ps`) and the `ps2000a*` calls
> accordingly.

## Running on macOS (desktop testing before the Pi)

Useful for testing against real hardware on a laptop before final deployment.

1. **Install PicoSDK for Mac** from Pico's
   [downloads page](https://www.picotech.com/downloads) — Apple Silicon Macs
   need the native **arm64** build (Pico added arm64 support, including
   `ps2000a`, in SDK 11.1.0.474); Intel Macs use the standard x86_64 build.
   This installs `PicoSDK.framework` into `/Library/Frameworks/`.
2. **Install Python dependencies:**

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Plug in the scope and run** — same command as above. `picopi`
   auto-detects a default-location `/Library/Frameworks/PicoSDK.framework`
   install and points `DYLD_LIBRARY_PATH` at it before importing `picosdk`,
   so no manual `export` is needed for a standard install.

**Troubleshooting:** if you still see
`Failed to open scope: PicoSDK (ps2000a) not found, check LD_LIBRARY_PATH`
(the wrapper prints the Linux env var name even on macOS — a known upstream
quirk):
- Confirm the SDK actually installed to the default path above; a custom
  install location needs its own `export DYLD_LIBRARY_PATH=...` before
  running.
- Confirm architecture match — an Intel-only PicoSDK build won't load into an
  arm64 Python process (check with `lipo -info` on the `.dylib`, or reinstall
  the arm64 SDK build).

## Command-line options

| Option | Default | Notes |
| --- | --- | --- |
| `--simulate` | off | Use a synthetic signal (no hardware/PicoSDK). |
| `--sim-freq` | 1000 | Frequency (Hz) of the simulated signal. |
| `--sample-rate` | 2e5 | Sample rate (Hz) for the simulated backend. |
| `--channel` | A | Scope channel (hardware). |
| `--range` | 2V | Voltage range, e.g. `50MV`, `500MV`, `2V`, `5V` (hardware). |
| `--timebase` | 8 | PicoScope timebase index (hardware). |
| `--samples` | 2000 | Samples per capture block. |
| `--trigger` | 0 | Rising-edge trigger threshold in mV (hardware). |

## Project layout

```
picopi/
├── backends.py   # ScopeBackend interface + PicoScope2000Backend + SimulatedBackend
├── dsp.py        # fft_frequency(), zero_crossing_frequency()  (pure NumPy)
├── worker.py     # QThread that loops block captures off the UI thread
├── gui.py        # PyQtGraph window: trace + spectrum + frequency readout
└── app.py        # argparse entry point (python -m picopi / picopi)
tests/
└── test_dsp.py   # frequency estimators vs synthetic signals of known f
```

## Development

```bash
pip install pytest
pytest                       # runs the DSP unit tests (no hardware needed)

# Headless GUI smoke test (no display):
QT_QPA_PLATFORM=offscreen python -m picopi --simulate
```

## How the design works

- **Acquisition** uses PicoScope **block mode**: each refresh captures a fixed,
  triggered window. That gives a clean fixed-timebase trace and a well-defined
  buffer for the FFT / zero-crossing analysis.
- A **backend abstraction** (`ScopeBackend`) means the GUI is identical whether
  it's driving hardware or the simulator; `--simulate` just swaps the backend.
- Captures run in a **background QThread** so USB transfers never freeze the UI —
  important for smooth refresh on a Raspberry Pi. The worker computes both
  frequency estimates and emits everything to the GUI, which only re-draws.
```
