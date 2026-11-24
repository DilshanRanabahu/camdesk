# CamDesk — Architecture & Folder Structure

How the app is organized so it stays **smooth** (video never waits on anything) and **easy to extend** (V2/V3 features plug in without rewrites).

Related docs: [feature.md](feature.md) · [ui-design.md](ui-design.md) · [decisions.md](decisions.md) · [AGENTS.md](../AGENTS.md)

> **Status:** Version 1 complete — build steps 1–10 done (✅ in the folder tree and build order). `app.py` is the composition root: it builds the services, AppState, AppController and the MainWindow.

---

## 1. Architecture Overview

Three layers. Each layer only talks to the one below it; lower layers never import Qt widgets.

```
┌─────────────────────────────────────────────────────────────┐
│  UI LAYER  (PySide6 widgets, main thread only)              │
│  MainWindow · ConnectView · VideoWidget · ControlDock ·     │
│  SidePanel · StatusBar · Toasts                             │
└──────────────▲──────────────────────────────┬───────────────┘
               │ Qt signals (state changes)   │ method calls (user actions)
┌──────────────┴──────────────────────────────▼───────────────┐
│  APP LAYER                                                  │
│  AppController  — wires everything, handles user actions    │
│  AppState       — single source of truth (QObject + signals)│
└──────────────▲──────────────────────────────┬───────────────┘
               │ signals                      │ commands
┌──────────────┴──────────────────────────────▼───────────────┐
│  SERVICE LAYER  (background threads, no widgets)            │
│  StreamService · CameraClient · Recorder · SnapshotService ·│
│  StatusPoller · MotionDetector (V2) · Settings              │
└─────────────────────────────────────────────────────────────┘
```

**Rules**
- UI never talks to the network or FFmpeg directly — it calls `AppController`.
- Services never touch widgets — they emit signals; `AppState` stores the result; UI reacts.
- All cross-thread communication uses **Qt queued signals** or the **latest-frame buffer**. No shared mutable state otherwise.

---

## 2. Threading Model

The key to smoothness: the **main (UI) thread never decodes, waits on the network, or writes files**.

| Thread | Owner | Work | Rate |
|---|---|---|---|
| **Main / UI** | Qt | Widgets, input, OpenGL texture upload + draw | Display refresh (60 Hz) |
| **Stream** | `StreamService` (Python thread; emits Qt signals) | RTSP read → GPU decode (D3D11VA) → put frame in buffer; pass packets to recorder | Camera FPS |
| **Recorder** | `Recorder` (Python thread + bounded queue) | Remux H.264 + AAC packets → MKV (no re-encode), new part every 30 min at a keyframe | Camera FPS |
| **Control** | `CameraClient` (QThread; its event queue keeps commands in order) | HTTP commands to phone; re-reads status after each one | On demand |
| **Poller** | QTimer inside the `CameraClient` thread | `status.json` + `sensors.json` (settings, capabilities, battery) | Every 5 s |
| **Motion** (V2) | `MotionDetector` (QThread) | Downscaled grayscale diff | ~5 FPS |
| **Snapshot** | `SnapshotService` (short-lived thread) | Latest frame → JPEG via FFmpeg mjpeg, atomic save | On demand |

### Why the recorder gets packets, not frames
The stream thread reads **compressed H.264 video and AAC audio packets** from the same RTSP session. All packets go to the recorder untouched (remux = almost zero CPU); only video packets also go to the decoder for display. Recording never adds decode/encode work.

### Why MKV
- An MKV file stays playable up to the last written frame if the app crashes or power is lost (an unfinished MP4 is unreadable).
- MKV stores the phone's AAC audio directly — no audio conversion. (We use `/h264_aac.sdp`, not `/h264_ulaw.sdp`: FFmpeg's MKV muxer rejects μ-law.)
- Segments: the recorder closes the file and opens `..._part2.mkv` at the next **keyframe** after 30 minutes, so no frames are lost between parts.

---

## 3. Video Pipeline (the hot path)

```
 Phone ──RTSP/TCP──▶ PyAV demux ──packet──┬──▶ Recorder queue ──▶ MKV file (video + audio, 30-min parts)
                    (Stream thread)       │
                                          └──▶ D3D11VA decode (GPU)
                                                   │ NV12 frame (zero-copy NumPy views)
                                                   ▼
                                          PlayoutBuffer  (Smooth: scheduled on the phone's clock;
                                                   │        Lowest latency: newest frame only)
                                                   │ "frame_ready" signal (coalesced) + due-time timer
                                                   ▼
                                    VideoWidget (QOpenGLWidget, UI thread)
                                      upload planes as textures (row padding skipped)
                                      fragment shader: YUV → RGB (BT.601/709, TV/full range)
                                                   │
                                                   ▼
                                                Screen
```

**Optimizations**
1. **PlayoutBuffer** (`core/playout.py`) — Smooth mode shows each frame at its phone-clock time + an adaptive delay (evens out Wi-Fi bursts; see [performance.md](performance.md)); Lowest-latency mode keeps only the newest frame. Either way the queue is bounded, so latency can't grow.
2. **Coalesced repaint** — the stream thread emits `frame_ready` only if the previous frame was already drawn; never floods the event queue.
3. **NV12 → RGB in a shader** — skips CPU color conversion (the biggest CPU cost in most Python video apps).
4. **Low-latency FFmpeg options** — `rtsp_transport=tcp`, `fflags=nobuffer`, `flags=low_delay`, small probe size.
5. **Hardware decode fallback chain** — D3D11VA → DXVA2 → software (logged + shown in status bar).
6. **MJPEG fallback** — every 2nd failed RTSP attempt switches source; `MjpegSource` reads `/video` with FFmpeg's MJPEG decoder — same widget, same buffer.
7. **Zero-copy frames** — decoded planes are NumPy views into FFmpeg's memory; the only copy is the GPU upload.
8. **Repaint watchdog** — a 100 ms timer repaints if a frame is waiting, so a missed `update()` can't stall the video.

**Measured (step 4, real phone):** 1080p @ 30 FPS, ~2% CPU of the PC, 0 dropped frames, ~2 ms decode→screen, ~225 ms camera→PC.

Both RTSP and MJPEG implement the same `VideoSource` interface, so the rest of the app doesn't care which is used.

---

## 4. State & Data Flow

### AppState (single source of truth) ✅
```python
class AppState(QObject):
    # the active CameraProfile (or None)
    camera_changed = Signal(object)
    # IDLE, CONNECTING, CONNECTED, RECONNECTING, FAILED
    connection_changed = Signal(ConnectionState)
    # resolution, fps, bitrate, decoder
    stream_info_changed = Signal(StreamInfo)
    # torch, night vision, zoom ratio, quality, front camera…
    camera_status_changed = Signal(CameraStatus)
    # has_torch, has_autofocus, zoom range… for the active camera
    capabilities_changed = Signal(CameraCapabilities)
    # battery (None when the phone doesn't report it)
    device_info_changed = Signal(DeviceInfo)
    # active, elapsed, part, file path
    recording_changed = Signal(RecordingState)
    # messages for the toast system
    notification = Signal(Toast)
    # a new frame is waiting in the LatestFrameBuffer (re-emitted from the active stream)
    frame_ready = Signal()
```

Setters emit **only when the value changes**. `set_capabilities(None)` keeps the previous value (phone mid camera-switch).

### AppController ✅
- Every user action: `connect_camera`, `disconnect`, `retry`, `set_torch`, `switch_camera`, `set_zoom`/`zoom_in`/`zoom_out`, `focus`, `set_night_vision`, `set_quality`, `set_video_size`, `set_orientation`, `shutdown`.
- Services are **injected** (`client`, `make_stream(profile, password)`, `secrets`, `save_settings`) so tests use fakes.
- **Optimistic:** AppState changes at once; the phone's next status (or a failure toast + refresh) corrects it.
- **Capability-aware:** asking for something the camera can't do (e.g. torch on the front camera) shows a warning instead of sending.
- **Zoom throttling:** first change is sent at once, then at most one command per 80 ms; the last value always lands.
- **Never blocks:** `disconnect()` stops the stream without waiting (`stop(timeout_s=0)`); settings are saved on a worker thread.
- Stream signals connect to controller **methods** (not lambdas) so they're queued to the UI thread; late signals from an old stream are ignored via `sender()`.

### In-flight commands
While a command is on its way, status reports are ignored: one taken before the command ran would undo the optimistic value. The client refreshes after each command, so a fresh report always follows.

### Example flow — user turns on the flashlight
```
ControlDock click ─▶ AppController.set_torch(True)
                      ├─▶ AppState: torch=True  (optimistic, UI updates instantly)
                      └─▶ CameraClient queue: GET /enabletorch
                                 │
                       success ──┴── failure ─▶ AppState: torch=False + Toast("Flashlight failed")
```

### Camera capabilities
Controls are enabled from what the phone reports (`status.json?show_avail=1`), not hard-coded. Example on the Galaxy A06:

| | Back (ID 0) | Front (ID 1) |
|---|---|---|
| Torch | ✅ | ❌ → Flashlight button disabled |
| Autofocus | ✅ | ❌ → tap-to-focus disabled |
| Zoom | 1×–10× | 1×–10× |
| Max FPS | 30 | 30 |

When the user switches camera, `CameraClient` re-reads capabilities and `AppState.capabilities_changed` updates the UI. While the phone is mid-switch (~2–3 s) it reports an incomplete list; the client then sends `None` and the previous capabilities are kept.

### Example flow — Wi-Fi drops
```
StreamService read timeout (3 s) ─▶ state RECONNECTING ─▶ UI dims last frame (step 9)
   retry with backoff (0.5s, 1s, 2s, 4s … max 10s); every 2nd failure tries MJPEG
   first frame ─▶ CONNECTED   |   5 failures in a row ─▶ FAILED (Retry button)
```

---

## 5. Folder Structure

✅ = built · no mark = planned

```
camara/
├── docs/                         # ✅ Project documentation
│   ├── README.md                 # ✅ Docs index + progress
│   ├── decisions.md              # ✅ Decisions, target hardware, measurements
│   ├── feature.md                # ✅ Feature list with progress
│   ├── ui-design.md              # ✅ UI/UX spec
│   ├── architecture.md           # ✅ This file
│   └── assets/                   # ✅ Images for the docs (README screenshot)
├── AGENTS.md                     # ✅ Rules for AI coding agents
├── CLAUDE.md                     # ✅ Points Claude Code to AGENTS.md
├── README.md                     # ✅ Setup + run instructions
├── pyproject.toml                # ✅ Dependencies, tool config (ruff, pytest) — managed by uv
├── uv.lock                       # ✅ Exact package versions (committed)
├── .python-version               # ✅ 3.12
├── .gitignore                    # ✅
│
├── src/
│   └── camdesk/
│       ├── __init__.py           # ✅
│       ├── __main__.py           # ✅ Entry point: `python -m camdesk`
│       ├── app.py                # ✅ Composition root: args, logging, settings, services → UI
│       │
│       ├── core/                 # Plain Python — no Qt widgets, no network
│       │   ├── models.py         # ✅ Dataclasses: CameraProfile, StreamInfo, CameraStatus, DeviceInfo…
│       │   ├── frames.py         # ✅ VideoFrame + LatestFrameBuffer (in core so the UI may read frames)
│       │   ├── playout.py        # ✅ PlayoutBuffer: smooth playback on the phone's clock (default)
│       │   ├── state.py          # ✅ AppState (QObject + signals, emit-on-change)
│       │   ├── controller.py     # ✅ AppController — every user action, optimistic + throttled
│       │   ├── messages.py       # ✅ User-facing text produced by core (toasts, validation)
│       │   ├── validation.py     # ✅ Parse the connect form (accepts http://ip:port as IP Webcam shows it)
│       │   ├── capture_manager.py # ✅ Snapshot + record actions, elapsed timer, disk checks, toasts
│       │   ├── notices.py        # ✅ State changes → toasts (Reconnected, low battery)
│       │   ├── geometry.py       # ✅ Rotate order, mirror/flip toggling, click → focus_region (-1000…1000)
│       │   └── errors.py         # ✅ App-specific exceptions
│       │
│       ├── camera/               # Talking to the IP Webcam HTTP API
│       │   ├── endpoints.py      # ✅ All URLs + setting keys in one place
│       │   ├── client.py         # ✅ CameraApi (sync) + CameraClient (thread, 5 s status poll)
│       │   ├── capabilities.py   # ✅ Parse status.json?show_avail=1 → CameraCapabilities
│       │   └── adb.py            # V3: USB mode (adb forward), start/stop IP Webcam
│       │
│       ├── stream/               # Video input
│       │   ├── source.py         # ✅ VideoSource interface (abstract)
│       │   ├── rtsp_source.py    # ✅ PyAV RTSP + hardware decode (+ generic PyAvSource)
│       │   ├── mjpeg_source.py   # ✅ MJPEG fallback (PyAV / FFmpeg decoder)
│       │   ├── hwaccel.py        # ✅ D3D11VA → DXVA2 → software selection
│       │   └── service.py        # ✅ StreamService — thread, reconnect/backoff, fallback, stats
│       │
│       ├── capture/              # ✅ Saving to disk
│       │   ├── recorder.py       # ✅ Packet remux → MKV (video + audio), parts at keyframes, new part on reconnect
│       │   ├── converter.py      # V2: MKV → MP4 for sharing
│       │   ├── snapshot.py       # ✅ Latest frame → JPEG (FFmpeg mjpeg) on a worker thread
│       │   └── storage.py        # ✅ File naming, unique names, part paths, free-space checks
│       │
│       ├── vision/               # V2+
│       │   ├── motion.py         # MotionDetector
│       │   └── timelapse.py
│       │
│       ├── config/
│       │   ├── settings.py       # ✅ Load/save user settings (JSON, versioned, atomic write)
│       │   ├── secrets.py        # ✅ Camera passwords via keyring (Credential Manager)
│       │   └── paths.py          # ✅         # %APPDATA%\CamDesk, Videos\CamDesk, logs (CAMDESK_HOME override)
│       │
│       ├── dev/                  # ✅ Run and test without the phone (`--fake`)
│       │   ├── fake_camera.py        # ✅ Fake IP Webcam HTTP API, mirrors the real phone's quirks
│       │   ├── fake_video_source.py  # ✅ Color bars + moving bar; can simulate failed opens / drops
│       │   └── smoke_test.py         # ✅ --smoke-test: connect, snapshot, record 3 s, exit 0/1
│       │
│       ├── ui/
│       │   ├── settings_dialog.py # ✅ Ctrl+,: capture folders, recording part length, shortcut list
│       │   ├── main_window.py    # ✅ Custom-frame window: title bar, connect ⇄ video pages, status bar, shortcuts, geometry
│       │   ├── win_frame.py      # ✅ Native Windows behavior for the custom frame (snap, resize, shadow) via WM_NCHITTEST
│       │   ├── title_bar.py      # ✅ Custom title bar + camera selector pill + window buttons
│       │   ├── connect_view.py   # ✅ Connect screen: wordmark, IP/port, login, recent cameras
│       │   ├── status_bar.py     # ✅ Connection · battery · disk free · stream info
│       │   ├── strings.py        # ✅ All user-facing text (English)
│       │   ├── video/
│       │   │   ├── video_widget.py   # ✅ QOpenGLWidget, texture upload, view modes, repaint watchdog
│       │   │   ├── shaders.py        # ✅ YUV → RGB shaders (NV12 / YUV420P, BT.601/709)
│       │   │   ├── connection_overlay.py # ✅ Connecting / Reconnecting (dimmed) / Failed + Retry, Change camera
│       │   │   └── overlays.py       # ✅ Debug overlay (Ctrl+D), focus ring, REC badge, snapshot flash
│       │   ├── panels/
│       │   │   ├── control_dock.py   # ✅ Floating dock, fades after 3 s idle, capability-aware
│       │   │   └── side_panel.py     # ✅ Camera / Image / View cards; Tab or ◧ toggles; auto-hides < 1100 px
│       │   ├── widgets/              # Reusable components from ui-design.md
│       │   │   ├── toggle.py         # ✅ Animated switch, set_checked_silently()
│       │   │   ├── slider.py         # ✅ Labeled slider: live value_changed + value_committed on release
│       │   │   ├── card.py           # ✅ Card + labeled row
│       │   │   └── toast.py          # ✅ ToastHost + cards: icon, thumbnail, Open, auto-dismiss, max 3
│       │   └── theme/
│       │       ├── tokens.py         # ✅ Colors, spacing, radius, fonts (from ui-design.md)
│       │       ├── stylesheet.py     # ✅ Builds QSS + dark palette from tokens
│       │       └── icons.py          # ✅ Inline Lucide-style SVG icons, recolored, crisp at 1×/2×
│       │
│       ├── resources/            # ✅ Logo files (built by scripts/make_icons.py)
│       │   ├── app.ico           # ✅ Window/taskbar icon, 16–256 px
│       │   ├── icon.png          # ✅ 1024 px transparent app icon
│       │   ├── wordmark.png      # ✅ "CamDesk" logo on dark background (README banner)
│       │   ├── wordmark-transparent.png # ✅ Same, background removed (connect screen)
│       │   └── icons/            # Lucide SVG files — step 7
│       │
│       └── utils/
│           ├── logging.py        # ✅ Rotating file log in %APPDATA%\CamDesk\logs (credentials redacted)
│           └── timing.py         # ✅ RateCounter (FPS / bitrate) + CpuMeter
│
├── tests/
│   ├── conftest.py               # ✅ Temp CAMDESK_HOME per test, shared QApplication, fake_camera
│   ├── qt_helpers.py             # ✅ SignalRecorder + wait_until (QSignalSpy.wait() holds the GIL)
│   ├── test_fake_camera.py       # ✅
│   ├── test_logging.py           # ✅
│   ├── test_settings.py          # ✅
│   ├── test_endpoints.py         # ✅
│   ├── test_capabilities.py      # ✅ Includes trimmed real replies from the phone
│   ├── test_camera_client.py     # ✅ Sync API + threaded client against the fake camera
│   ├── test_frame_buffer.py      # ✅
│   ├── test_playout.py           # ✅ Bursty arrival → even display, adaptivity, resets, wake-up contract
│   ├── test_timing.py            # ✅
│   ├── test_stream_service.py    # ✅ Reconnect, backoff, FAILED/retry, fallback, coalescing
│   ├── test_rtsp_source.py       # ✅ PyAV source on a generated MKV file
│   ├── test_video_widget.py      # ✅ Renders real frames, reads back pixel colors
│   ├── test_main_window.py       # ✅ Pages, pill, overlay, recent/forget, geometry (fake phone)
│   ├── test_validation.py        # ✅ Connect-form address parsing
│   ├── test_win_frame.py         # ✅ Resize/caption hit-testing
│   ├── test_geometry.py          # ✅ Rotate order, flip toggling, focus point mapping
│   ├── test_controls.py          # ✅ Controller actions, widgets, side panel, dock, stale-report race
│   ├── test_state.py             # ✅ Emit-on-change, keep capabilities while switching
│   ├── test_controller.py        # ✅ End-to-end: real client + stream, fake phone + fake video
│   ├── test_capture.py           # ✅ Naming, JPEG colors, recorder parts/keyframes/audio, Space/R flow
│   └── test_polish.py            # ✅ Notices, toasts, settings dialog, view-mode memory, wheel zoom
│
└── scripts/
    ├── run.ps1                   # ✅ Run in dev mode (passes args through)
    ├── make_icons.py             # ✅ Builds icon.png, app.ico, wordmark.png from source images
    ├── camdesk_entry.py          # ✅ Entry point Nuitka compiles
    └── build.ps1                 # ✅ Nuitka → dist\CamDesk\CamDesk.exe (+ -Zip), then smoke test
```

---

## 6. Where Things Are Stored

| Data | Location |
|---|---|
| User settings | `%APPDATA%\CamDesk\settings.json` |
| Logs | `%APPDATA%\CamDesk\logs\camdesk.log` (rotating, 5 × 1 MB) |
| Snapshots | `%USERPROFILE%\Videos\CamDesk\Snapshots\` (changeable) |
| Recordings | `%USERPROFILE%\Videos\CamDesk\Recordings\` (changeable) |
| Passwords | Windows Credential Manager (via `keyring`), never in settings.json |

---

## 7. Dependencies

| Package | Purpose |
|---|---|
| `PySide6-Essentials` | UI, OpenGL widget, threads, signals (no Addons — keeps the .exe small) |
| `av` (PyAV) | RTSP, H.264 hardware decode, MKV remux |
| `httpx` | Camera control HTTP requests |
| `numpy` | Frame arrays |
| `keyring` | Secure password storage |
| `opencv-python-headless` | Motion detection (V2) — not added yet |
| Dev: `pytest`, `ruff` | Tests, lint |
| Dev: `nuitka` | Build the .exe (uses MSVC from Visual Studio Build Tools) |

Python 3.12, managed with **uv** (`uv sync`, `uv run`). `uv.lock` is committed so every build uses the same versions.

---

## 8. Error Handling & Logging

- Every service catches its own errors, logs them, and reports a **user-friendly** message through `AppState.notification`.
- Network errors → reconnect logic, not crashes.
- Unexpected exceptions → global handler (`app.py`) logs the traceback and shows a "Something went wrong" toast with **Open** → the log file.
- Decoder in use, stream type and reconnects are logged for troubleshooting.

---

## 9. Extending (V2 / V3)

| Feature | Plugs in at |
|---|---|
| Motion detection | `vision/motion.py` reads from `LatestFrameBuffer`; emits events to `AppState` |
| Timelapse | `vision/timelapse.py` uses `SnapshotService` on a timer |
| Audio | New `stream/audio_source.py` + playback thread |
| Multiple cameras | One `StreamService` + `CameraClient` per camera; `AppState` becomes a list of camera states; grid view in `ui/` |
| Light theme | Second token set in `theme/tokens.py` |
| MKV → MP4 convert | `capture/converter.py` (remux in a background task) |
| USB mode | `camera/adb.py` runs `adb forward tcp:8080 tcp:8080`; camera profile host becomes `127.0.0.1` — nothing else changes |

---

## 10. Build Order (Version 1)

1. ✅ Project setup — `git init`, `uv init`, dependencies, folder skeleton, logging, settings, fake camera
2. ✅ `camera/` — endpoints + client, verified against the phone
3. ✅ `stream/` — RTSP source + hardware decode + frame buffer + service
4. ✅ `ui/video` — OpenGL video widget + debug overlay → **first live video**; 30 FPS ✅ · < 10% CPU ✅ · ~240 ms latency ⚠️
5. ✅ `core/` — AppState + AppController wiring (temporary keys drive the phone)
6. ✅ UI shell — theme, main window, custom title bar, connect screen, connection overlay, status bar
7. ✅ Control dock + side panel → camera controls working (verified 19/19 on the phone)
8. ✅ `capture/` — snapshot + MKV recording with 30-min segments (verified on the phone, no extra CPU)
9. ✅ Toasts, reconnect notices + hints, settings dialog, view-mode memory, wheel zoom, crash notice
10. ✅ Nuitka build → `dist\CamDesk\CamDesk.exe` (standalone folder, ~200 MB; smoke-tested against the phone)
