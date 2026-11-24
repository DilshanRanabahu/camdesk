# AGENTS.md — CamDesk

Instructions for AI coding agents (Claude Code, Copilot, Cursor, etc.) working on this project. Read this first, every session.

## Project

**CamDesk** is a Windows desktop app that views, records and controls an Android phone running the **IP Webcam** app over the same Wi-Fi. The top priority is **smooth, low-latency video**.

| Doc | Read it when |
|---|---|
| [docs/decisions.md](docs/decisions.md) | Always — approved decisions and target hardware. Do not override them. |
| [docs/architecture.md](docs/architecture.md) | Before adding or moving any code |
| [docs/feature.md](docs/feature.md) | Before starting a feature; tick its checkbox when done |
| [docs/ui-design.md](docs/ui-design.md) | Before touching anything in `src/camdesk/ui/` |

If a request conflicts with these docs, say so and ask before proceeding. If a decision changes, update the doc in the same change.

## Current Status

- Version 1 build steps **1–7 of 10 done** (see the [build order](docs/architecture.md#10-build-order-version-1)). Next: step 8, snapshots + MKV recording.
- `ui/main_window.py` is the real window: title bar, connect screen, video + control dock, side panel, status bar. Single-key shortcuts (and `Tab`) are off on the connect screen. Snapshot/Record dock buttons are disabled until step 8.
- Repo: https://github.com/DilshanRanabahu/camdesk (public, branch `main`).

## Stack

Python 3.12 · **uv** · PySide6-Essentials (Qt 6 — do not add the full `PySide6` / Addons package) · PyAV (FFmpeg) · httpx · numpy · keyring · OpenCV (V2) · pytest · ruff · Nuitka

Do not add a dependency without a clear reason; mention it in the summary of your change.

## Commands

```powershell
uv sync                          # Install / update dependencies
uv run python -m camdesk         # Run the app (last camera from settings)
uv run python -m camdesk --host 192.168.8.105   # Set and remember the phone IP
uv run python -m camdesk --fake  # Run with the fake camera (no phone needed)
uv run python -m camdesk --debug --debug-overlay   # Verbose log + Ctrl+D panel shown
uv run python -m camdesk --native-frame           # Standard Windows title bar instead of the custom one
uv run pytest                    # Run tests
uv run ruff check .              # Lint
uv run ruff format .             # Format
.\scripts\build.ps1              # Build dist\CamDesk.exe (Nuitka)
```

Always use `uv run` / `uv add` — never `pip install` and never activate a different Python.
uv was installed with winget; a terminal opened before that may not have it on `PATH` (open a new one).

## Architecture Rules (must follow)

1. **Three layers:** `ui/` → `core/` (AppController, AppState) → services (`camera/`, `stream/`, `capture/`, `vision/`, `config/`).
2. **`ui/` never imports** `av`, `httpx`, `cv2` or anything in `stream/`, `camera/`, `capture/`. It calls `AppController` and listens to `AppState` signals.
3. **Services never import widgets** and never touch the UI. They emit signals.
4. **`core/models.py`** holds plain dataclasses only — no Qt widgets, no I/O.
5. All camera URLs and setting keys live in **`camera/endpoints.py`** only. No URL strings anywhere else.
6. All colors, sizes and fonts come from **`ui/theme/tokens.py`**. No hex colors or pixel sizes hard-coded in widgets.
7. All user-facing text lives in `ui/strings.py`; text produced by the core layer (toasts) lives in `core/messages.py` (core can't import ui). English only.
8. **`app.py` is the composition root** — the only module that imports both services and UI to wire them together.

## Performance Rules (the main goal)

- **Never block the UI thread.** No network calls, decoding, file writes, `time.sleep()` or waits on the main thread.
- Video frames go through **`LatestFrameBuffer`** (size 1, overwrite). Never queue frames for display.
- Decoding uses hardware (D3D11VA → DXVA2 → software fallback). Do not convert frames to RGB on the CPU for display; the NV12 shader does it.
- **Recording remuxes packets** (H.264 + AAC audio → MKV). Never decode/re-encode to record.
- Animations only on overlay widgets — never on or over the `QOpenGLWidget` paint.
- Cross-thread communication: Qt queued signals, `queue.Queue`, or `LatestFrameBuffer`. No other shared mutable state.
- If a change could affect smoothness, check it with the debug overlay (`Ctrl+D`). Target: **1080p @ 30 FPS, ~200 ms latency, < 10% CPU**.

## Camera Facts (Galaxy A06 + IP Webcam 1.19)

- Back camera (ID 0): torch ✅, autofocus ✅. Front camera (ID 1): **no torch, fixed focus**.
- Max 30 FPS, digital zoom 1×–10×, no stabilization. The sensor has exposure −20…+20, but IP Webcam 1.19 doesn't expose it.
- Read capabilities from `status.json?show_avail=1` — **do not hard-code** per-phone behavior; the A06 values are only defaults for the fake camera.
- Phone IP is currently `192.168.8.105:8080`, but it can change — never hard-code it in source.
- Primary stream: `rtsp://<ip>:8080/h264_aac.sdp` (verified: H.264 1080p 30 FPS + AAC 44.1 kHz, ~16 Mbps; **not** `h264_ulaw.sdp` — MKV can't store μ-law) · fallback: `http://<ip>:8080/video` (MJPEG).
- Real API quirks (zoom ×100 units, `avail.torch` not `flashmode`, empty sensors, incomplete `avail` while switching) are in [docs/decisions.md](docs/decisions.md#5-verified-on-the-real-phone-2026-11-23).

## PySide6 Gotchas (learned the hard way)

- `QShaderProgram.setUniformValueArray(loc, data, 1, 9)` uploads **nothing** for a `mat3` → black video. Use `QMatrix3x3`.
- Upload textures by passing NumPy arrays straight to `glTexImage2D/glTexSubImage2D`; raw `int` pointers are rejected.
- `QSignalSpy.wait()` holds the GIL — see Testing.
- **Never connect a worker-thread signal to a lambda** that touches AppState or widgets: a lambda has no thread, so it runs on the *emitting* (worker) thread. Connect to a method of a QObject that lives on the UI thread (Qt then queues the call) and use `self.sender()` to tell sources apart.
- Any GL change must keep `tests/test_video_widget.py` (renders real frames, checks pixel colors) passing.
- A `QTimer` (or any timer) owned by a worker `QThread` must be **deleted on that thread** before it quits — use a `BlockingQueuedConnection` shutdown slot and `shiboken6.delete(timer)`. Deleting it later from the UI thread (e.g. by garbage collection) warns "Timers cannot be stopped from another thread" and can abort the process.
- On Windows, Qt's own warnings go to the debugger, not the console. To see them, set `QT_FORCE_STDERR_LOGGING=1` or install a handler with `qInstallMessageHandler`.
- Optimistic UI + polling race: ignore status reports while commands are in flight (`AppController._in_flight`). A report taken before a command runs would undo the optimistic value and the next click builds on stale state.
- `QScreen.grabWindow(0, x, y, …)` takes coordinates **relative to that screen**, not global ones (the second monitor is at negative x).

## Code Style

- Type hints everywhere; `from __future__ import annotations` at the top of each module.
- `@dataclass(frozen=True, slots=True)` for models.
- Qt signals: `snake_case` past tense (`connection_changed`, `frame_ready`).
- Use `logging` (module-level `log = logging.getLogger(__name__)`), never `print`.
- Catch errors in services, log them, and report a friendly message via `AppState.notification`. Never let a service exception crash the app.
- Keep functions small; no module over ~400 lines — split it.
- Comments explain **why**, not what.

## Testing

- Every service and model change needs a test in `tests/`.
- Tests must **not** need the real phone or network: use `camdesk.dev.fake_camera` (fixture `fake_camera` in `tests/conftest.py`) and `camdesk.dev.fake_video_source`. They live in `src/` so `--fake` mode can use them too.
- Tests run with `CAMDESK_HOME` pointed at a temp folder (autouse fixture), so they never touch real settings, logs or captures.
- Use the session-wide `qapp` fixture (a `QApplication`) for anything Qt; don't create your own `QCoreApplication`.
- The autouse `collect_qt_garbage` fixture runs `gc.collect()` after every test. Keep it: without it, Python's GC destroys a previous test's Qt objects at a random moment mid-stream and Qt can abort the run.
- Fixtures that start a `CameraClient` must stop it in a `finally:` — a running `QThread` that gets destroyed aborts the whole test process.
- `pyproject` sets `-q`; add `-o addopts=""` to see the pass/fail summary line.
- UI code: test logic in `core/` instead of testing widgets directly.
- Waiting on Qt signals from worker threads: use `SignalRecorder` from `tests/qt_helpers.py`, **not** `QSignalSpy.wait()` — PySide6's `QSignalSpy.wait()` holds the GIL, so Python slots on worker threads never run and the test times out.
- Run `uv run pytest` and `uv run ruff check .` before saying a task is done. Report failures honestly.

## Working With the Phone (ADB)

ADB is installed and the phone may be connected by USB.

- Read-only commands are fine: `adb devices`, `adb shell getprop`, `adb shell dumpsys …`.
- **Ask the user first** before anything that changes the phone: installing/uninstalling apps, changing settings, starting/stopping apps, `adb forward`.
- Never pull personal data (photos, messages, contacts) from the phone.

## Git

- One commit per build step or feature (see build order in [docs/architecture.md](docs/architecture.md#10-build-order-version-1)).
- Message style: `feat: …`, `fix: …`, `refactor: …`, `docs: …`, `test: …`, `chore: …`.
- Commit `uv.lock`. Never commit `.venv/`, `dist/`, `build/`, recordings, snapshots, logs or passwords.
- Only commit or push when the user asks. Remote: `origin` → GitHub `DilshanRanabahu/camdesk` (**public**).
- This repo's `user.email` is the GitHub **noreply** address. Never put a personal email in commits or files (e.g. `pyproject.toml` authors).

## Privacy & Security

- No telemetry, analytics or outside network calls. CamDesk only talks to the phone on the local network.
- Passwords only via `keyring` (Windows Credential Manager) — never in `settings.json`, logs or code.
- Never log full URLs that contain credentials.

## Definition of Done

- [ ] Follows the architecture and performance rules above
- [ ] Tests added/updated; `pytest` and `ruff` pass
- [ ] Works with `--fake`; tested on the real phone if it touches streaming or controls
- [ ] Matches [docs/ui-design.md](docs/ui-design.md) for any UI change
- [ ] Feature checkbox ticked in [docs/feature.md](docs/feature.md); docs updated if a decision changed
