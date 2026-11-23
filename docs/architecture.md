# CamDesk — Architecture & Folder Structure

How the app is organized so it stays **smooth** (video never waits on anything) and **easy to extend** (V2/V3 features plug in without rewrites).

Related docs: [feature.md](feature.md) · [ui-design.md](ui-design.md) · [decisions.md](decisions.md) · [AGENTS.md](../AGENTS.md)

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
| **Stream** | `StreamService` (QThread) | RTSP read → GPU decode (D3D11VA) → put frame in buffer; pass packets to recorder | Camera FPS |
| **Recorder** | `Recorder` (QThread + queue) | Remux H.264 + AAC audio packets → MKV (no re-encode), new file every 30 min | Camera FPS |
| **Control** | `CameraClient` (QThread + command queue) | HTTP commands to phone, in order | On demand |
| **Poller** | `StatusPoller` (QTimer in control thread) | `status.json` + `sensors.json` (battery, settings) | Every 5 s |
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
                                                   │ NV12 frame
                                                   ▼
                                          LatestFrameBuffer  (size 1, overwrite)
                                                   │ "frame_ready" signal (coalesced)
                                                   ▼
                                    VideoWidget (QOpenGLWidget, UI thread)
                                      upload Y + UV planes as 2 textures
                                      fragment shader: NV12 → RGB
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
6. **MJPEG fallback** — if RTSP fails, `MjpegSource` reads `/video` and decodes with PyAV's MJPEG decoder (FFmpeg, multi-threaded) — same widget, same buffer.

Both RTSP and MJPEG implement the same `VideoSource` interface, so the rest of the app doesn't care which is used.

---

## 4. State & Data Flow

### AppState (single source of truth)
```python
class AppState(QObject):
    connection_changed = Signal(
        ConnectionState
    )  # IDLE, CONNECTING, CONNECTED, RECONNECTING, FAILED
    stream_info_changed = Signal(StreamInfo)  # resolution, fps, latency, decoder
    camera_status_changed = Signal(CameraStatus)  # torch, night, zoom, quality, front cam...
    capabilities_changed = Signal(
        CameraCapabilities
    )  # has_torch, has_autofocus, zoom range... per active camera
    device_info_changed = Signal(DeviceInfo)  # battery, phone name
    recording_changed = Signal(RecordingState)  # active, elapsed, file path
    notification = Signal(Toast)  # messages for the toast system
```

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

When the user switches camera, `CameraClient` re-reads capabilities and `AppState.capabilities_changed` updates the UI.

### Example flow — Wi-Fi drops
```
StreamService read timeout ─▶ state RECONNECTING ─▶ UI dims last frame
   retry with backoff (0.5s, 1s, 2s, 4s … max 10s)
   success ─▶ CONNECTED   |   5 failures ─▶ FAILED (Retry button shown)
```

---

## 5. Folder Structure

```
camara/
├── docs/                         # Project documentation
│   ├── README.md                 # Docs index
│   ├── decisions.md              # Approved decisions + target hardware
│   ├── feature.md                # Feature list
│   ├── ui-design.md              # UI/UX spec
│   └── architecture.md           # This file
├── AGENTS.md                     # Rules for AI coding agents
├── CLAUDE.md                     # Points Claude Code to AGENTS.md
├── README.md                     # Setup + run instructions
├── pyproject.toml                # Dependencies, tool config (ruff, pytest) — managed by uv
├── uv.lock                       # Exact package versions (committed)
├── .python-version               # 3.12
├── .gitignore
│
├── src/
│   └── camdesk/
│       ├── __init__.py
│       ├── __main__.py           # Entry point: `python -m camdesk`
│       ├── app.py                # Creates QApplication, AppState, services, MainWindow
│       │
│       ├── core/                 # Plain Python — no Qt widgets, no network
│       │   ├── models.py         # Dataclasses: CameraProfile, StreamInfo, CameraStatus, DeviceInfo…
│       │   ├── frames.py         # VideoFrame + LatestFrameBuffer (in core so the UI may read frames)
│       │   ├── state.py          # AppState (QObject + signals)
│       │   ├── controller.py     # AppController — handles user actions, wires services
│       │   └── errors.py         # App-specific exceptions
│       │
│       ├── camera/               # Talking to the IP Webcam HTTP API
│       │   ├── endpoints.py      # All URLs + setting keys in one place
│       │   ├── client.py         # CameraClient — command queue thread (httpx)
│       │   ├── capabilities.py   # Parse status.json?show_avail=1 → CameraCapabilities
│       │   ├── poller.py         # StatusPoller — battery + settings every 5 s
│       │   └── adb.py            # V3: USB mode (adb forward), start/stop IP Webcam
│       │
│       ├── stream/               # Video input
│       │   ├── source.py         # VideoSource interface (abstract)
│       │   ├── rtsp_source.py    # PyAV RTSP + hardware decode
│       │   ├── mjpeg_source.py   # MJPEG fallback (PyAV / FFmpeg decoder)
│       │   ├── hwaccel.py        # D3D11VA → DXVA2 → software selection
│       │   └── service.py        # StreamService — thread, reconnect/backoff, stats
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
│       │   ├── settings.py       # Load/save user settings (JSON, versioned, atomic write)
│       │   ├── secrets.py        # Camera passwords via keyring (Credential Manager)
│       │   └── paths.py          # %APPDATA%\CamDesk, Videos\CamDesk, logs (CAMDESK_HOME override)
│       │
│       ├── dev/                  # Run and test without the phone (`--fake`)
│       │   ├── fake_camera.py        # Fake IP Webcam HTTP API (status.json, torch, settings…)
│       │   └── fake_video_source.py  # Plays a local video file as if it were the RTSP stream
│       │
│       ├── ui/
│       │   ├── main_window.py    # Frameless window, layout, shortcuts
│       │   ├── title_bar.py      # Custom title bar + camera selector pill
│       │   ├── connect_view.py   # First-launch / connect screen
│       │   ├── status_bar.py
│       │   ├── strings.py        # All user-facing text (English)
│       │   ├── video/
│       │   │   ├── video_widget.py   # QOpenGLWidget, texture upload, view modes
│       │   │   ├── shaders.py        # NV12 + RGB shaders
│       │   │   └── overlays.py       # REC badge, FPS/latency, focus ring, flash, debug overlay (Ctrl+D)
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
│       │       ├── tokens.py         # Colors, spacing, radius, fonts (from ui-design.md)
│       │       ├── stylesheet.py     # Builds QSS from tokens
│       │       └── icons.py          # Loads + recolors Lucide SVGs
│       │
│       ├── resources/
│       │   ├── icons/            # Lucide SVG files
│       │   └── app.ico
│       │
│       └── utils/
│           ├── logging.py        # Rotating file log in %APPDATA%\CamDesk\logs
│           └── timing.py         # FPS / latency counters
│
├── tests/
│   ├── conftest.py               # Temp CAMDESK_HOME per test + fake_camera fixture
│   ├── test_fake_camera.py
│   ├── test_logging.py
│   ├── test_endpoints.py
│   ├── test_capabilities.py
│   ├── test_recorder.py          # Segmenting at 30 min, MKV playable
│   ├── test_frame_buffer.py
│   ├── test_stream_service.py    # Reconnect, backoff, FAILED/retry, fallback, coalescing
│   ├── test_rtsp_source.py       # PyAV source on a generated MKV file
│   ├── test_timing.py
│   ├── test_settings.py
│   ├── test_storage.py
│   └── test_controller.py        # With fake camera + fake video source
│
└── scripts/
    ├── run.ps1                   # Run in dev mode
    └── build.ps1                 # Nuitka → dist\CamDesk.exe
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
| `opencv-python-headless` | Motion detection (V2) |
| Dev: `pytest`, `ruff`, `nuitka` | Tests, lint, build |

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

1. Project setup — `git init`, `uv init`, dependencies, folder skeleton, logging, settings, fake camera
2. `camera/` — endpoints + client (test against your phone)
3. `stream/` — RTSP source + hardware decode + frame buffer + service
4. `ui/video` — OpenGL video widget with NV12 shader → **first live video** + debug overlay; check 30 FPS / ~200 ms / < 10% CPU
5. `core/` — AppState + AppController wiring
6. UI shell — theme, main window, title bar, connect screen, status bar
7. Control dock + side panel → camera controls working
8. `capture/` — snapshot + MKV recording with 30-min segments
9. Reconnect, toasts, settings persistence, shortcuts
10. Nuitka build → `CamDesk.exe`
