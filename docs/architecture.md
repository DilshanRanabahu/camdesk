# CamDesk — Architecture & Folder Structure

How the app is organized so it stays **smooth** (video never waits on anything) and **easy to extend** (V2/V3 features plug in without rewrites).

Related docs: [feature.md](feature.md) · [ui-design.md](ui-design.md) · [decisions.md](decisions.md) · [AGENTS.md](../AGENTS.md)

> **Status:** build steps 1–5 done (✅ in the folder tree and build order). `app.py` is the composition root: it builds the services, AppState and AppController, and a temporary preview window (until MainWindow in step 6).

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
| **Recorder** | `Recorder` (QThread + queue) | Remux H.264 + AAC audio packets → MKV (no re-encode), new file every 30 min | Camera FPS |
| **Control** | `CameraClient` (QThread; its event queue keeps commands in order) | HTTP commands to phone; re-reads status after each one | On demand |
| **Poller** | QTimer inside the `CameraClient` thread | `status.json` + `sensors.json` (settings, capabilities, battery) | Every 5 s |
| **Motion** (V2) | `MotionDetector` (QThread) | Downscaled grayscale diff | ~5 FPS |
| **Snapshot** | `QThreadPool` task | Encode + save JPEG | On demand |

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
                                          LatestFrameBuffer  (size 1, overwrite)
                                                   │ "frame_ready" signal (coalesced)
                                                   ▼
                                    VideoWidget (QOpenGLWidget, UI thread)
                                      upload planes as textures (row padding skipped)
                                      fragment shader: YUV → RGB (BT.601/709, TV/full range)
                                                   │
                                                   ▼
                                                Screen
```

**Optimizations**
1. **LatestFrameBuffer** — holds only the newest frame. If the UI is busy, old frames are dropped, so latency never grows.
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
│       │   ├── state.py          # ✅ AppState (QObject + signals, emit-on-change)
│       │   ├── controller.py     # ✅ AppController — every user action, optimistic + throttled
│       │   ├── messages.py       # ✅ User-facing text produced by core (toasts)
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
│       ├── capture/              # Saving to disk
│       │   ├── recorder.py       # Packet remux → MKV (video + audio), 30-min segments at keyframes
│       │   ├── converter.py      # V2: MKV → MP4 for sharing
│       │   ├── snapshot.py       # Save JPEG from latest frame
│       │   └── storage.py        # File naming, captures folder, free-space checks
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
│       │   └── fake_video_source.py  # ✅ Color bars + moving bar; can simulate failed opens / drops
│       │
│       ├── ui/
│       │   ├── main_window.py    # Frameless window, layout, shortcuts
│       │   ├── title_bar.py      # Custom title bar + camera selector pill
│       │   ├── connect_view.py   # First-launch / connect screen
│       │   ├── status_bar.py
│       │   ├── strings.py        # ✅ All user-facing text (English)
│       │   ├── preview_window.py # ✅ TEMPORARY (step 4): bare live-video window until MainWindow (step 6)
│       │   ├── video/
│       │   │   ├── video_widget.py   # ✅ QOpenGLWidget, texture upload, view modes, repaint watchdog
│       │   │   ├── shaders.py        # ✅ YUV → RGB shaders (NV12 / YUV420P, BT.601/709)
│       │   │   └── overlays.py       # ✅ Debug overlay (Ctrl+D); later: REC badge, focus ring, flash
│       │   ├── panels/
│       │   │   ├── control_dock.py   # Floating auto-hide dock
│       │   │   └── side_panel.py     # Camera / Image / Advanced cards
│       │   ├── widgets/              # Reusable components from ui-design.md
│       │   │   ├── toggle.py
│       │   │   ├── slider.py
│       │   │   ├── icon_button.py
│       │   │   ├── card.py
│       │   │   └── toast.py
│       │   └── theme/
│       │       ├── tokens.py         # ✅ Colors, spacing, radius, fonts (from ui-design.md)
│       │       ├── stylesheet.py     # Builds QSS from tokens
│       │       └── icons.py          # Loads + recolors Lucide SVGs
│       │
│       ├── resources/            # ✅ Logo files (built by scripts/make_icons.py)
│       │   ├── app.ico           # ✅ Window/taskbar icon, 16–256 px
│       │   ├── icon.png          # ✅ 1024 px transparent app icon
│       │   ├── wordmark.png      # ✅ "CamDesk" logo (README banner, connect screen)
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
│   ├── test_timing.py            # ✅
│   ├── test_stream_service.py    # ✅ Reconnect, backoff, FAILED/retry, fallback, coalescing
│   ├── test_rtsp_source.py       # ✅ PyAV source on a generated MKV file
│   ├── test_video_widget.py      # ✅ Renders real frames, reads back pixel colors
│   ├── test_state.py             # ✅ Emit-on-change, keep capabilities while switching
│   ├── test_controller.py        # ✅ End-to-end: real client + stream, fake phone + fake video
│   ├── test_recorder.py          # Segmenting at 30 min, MKV playable — step 8
│   └── test_storage.py           # step 8
│
└── scripts/
    ├── run.ps1                   # ✅ Run in dev mode (passes args through)
    ├── make_icons.py             # ✅ Builds icon.png, app.ico, wordmark.png from source images
    └── build.ps1                 # Nuitka → dist\CamDesk.exe — step 10
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
| Dev: `nuitka` | Build the .exe — added in step 10 |

Python 3.12, managed with **uv** (`uv sync`, `uv run`). `uv.lock` is committed so every build uses the same versions.

---

## 8. Error Handling & Logging

- Every service catches its own errors, logs them, and reports a **user-friendly** message through `AppState.notification`.
- Network errors → reconnect logic, not crashes.
- Unexpected exceptions → global handler logs the traceback and shows "Something went wrong · Open log".
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
6. UI shell — theme, main window, title bar, connect screen, status bar
7. Control dock + side panel → camera controls working
8. `capture/` — snapshot + MKV recording with 30-min segments
9. Reconnect, toasts, settings persistence, shortcuts
10. Nuitka build → `CamDesk.exe`
