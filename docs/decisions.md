# CamDesk — Project Decisions

Final decisions for the project. Anything not listed here follows [architecture.md](architecture.md), [feature.md](feature.md) and [ui-design.md](ui-design.md).

**Status:** Approved · **Created:** 2026-11-23 · **Last updated:** 2026-11-24 (after build step 8)

Decisions 18–43 were made during development; each row says why.

---

## 1. Decision Log

### Product
| # | Topic | Decision | Reason |
|---|---|---|---|
| 1 | App name | **CamDesk** | Short, clear, describes the app |
| 5 | Network scope | **Same Wi-Fi only** | Simple and secure; remote access can be added later |
| 12 | Language | **English only** | Keeps V1 simple |
| 17 | Privacy | **No tracking or analytics**; all data stays on the PC | Personal app; camera footage is private |

### Recording
| # | Topic | Decision | Reason |
|---|---|---|---|
| 2 | File format | **MKV** | Still playable if the app crashes or power is lost mid-recording (MP4 is not) |
| 3 | Audio | **Recorded with video** as the phone's **AAC** (RTSP `/h264_aac.sdp`), no conversion | *Changed in step 3:* MKV can't store μ-law; AAC goes into MKV (and MP4) as-is, no CPU cost, and sounds far better (44.1 kHz vs 8 kHz) |
| 4 | Split long recordings | **New file every 30 minutes** | One problem never ruins hours of footage |
| — | Convert to MP4 | Optional one-click convert, later | For sharing to phones / social media |

### Development
| # | Topic | Decision | Reason |
|---|---|---|---|
| 6 | Python environment | **uv** with a lock file | Fast installs, exact same package versions every build |
| 7 | Version control | **Git**, one commit per build step | Easy to roll back; clear history |
| 26 | Hosting | **Public GitHub repo** [DilshanRanabahu/camdesk](https://github.com/DilshanRanabahu/camdesk); commits use the GitHub **noreply** email | Personal email kept private (history rewritten before the first push) |
| 10 | Testing | Unit tests + **fake camera** (HTTP API) + **fake video** (moving test pattern) + GL render tests that read back pixels | Develop and test without the phone; 99 tests at step 4 |
| 11 | Performance check | Debug overlay (CPU, FPS, latency), checked at build step 4 | Done — results in section 5 |
| 18 | MJPEG fallback decoder | **PyAV (FFmpeg)** instead of PyTurboJPEG | PyTurboJPEG needs a separate native libjpeg-turbo install on Windows; FFmpeg's decoder is already bundled and fast enough for a fallback |
| 19 | Fake camera location | `src/camdesk/dev/` (not `tests/`) | `--fake` mode in the app needs it, not just tests |
| 20 | Qt package | **PySide6-Essentials** (not full `PySide6`) | Has everything CamDesk needs (Widgets, OpenGL, Test); skips WebEngine/3D/Multimedia add-ons — much smaller download and `.exe` |
| 21 | Frame types location | `VideoFrame` + `LatestFrameBuffer` in `core/frames.py` (not `stream/`) | The UI's video widget reads frames, and the UI may only import `core/` |
| 22 | Low-latency input | FFmpeg `fflags=nobuffer` for the camera | Lower delay; drops only the single frame read while probing at connect time |
| 27 | Core-layer text | Toast text from the controller lives in `core/messages.py` | Rule 7 keeps UI text in `ui/strings.py`, but core may not import ui |
| 28 | Cross-thread signal wiring | Worker signals connect to controller **methods**, never lambdas | A lambda runs on the emitting thread and would touch AppState off the UI thread |
| 29 | Custom title bar | Frameless window that keeps `WS_CAPTION/WS_THICKFRAME`; `WM_NCCALCSIZE` hides the native bar, `WM_NCHITTEST` reports caption/resize areas. `--native-frame` falls back | Keeps Windows Snap, Win+arrows, resize edges, shadow and rounded corners while drawing our own bar. Verified: maximized fits the work area exactly |
| 30 | Wordmark in the app | `wordmark-transparent.png` (background removed by color un-blending); README keeps the dark version | The dark box around the logo showed on the lighter card |
| 31 | Worker-thread timer cleanup | `CameraClient` shutdown runs on its own thread via `BlockingQueuedConnection` and deletes the poll timer there | Qt: "Timers cannot be stopped from another thread"; garbage-collecting it later could abort |
| 32 | Test GC | Autouse fixture collects garbage after each test | GC at a random moment mid-stream destroyed old Qt objects and aborted test runs; not reproducible in the app (40 camera switches with forced GC) |
| 33 | "No picture" watchdog | Reconnect if no frame within 10 s of connecting, or none for 5 s after | Seen on the phone right after IP Webcam starts: packets arrive but nothing decodes, which the read timeout can't catch |
| 34 | "Can't reach" message | FFmpeg's `Immediate exit requested` (our open timeout firing) maps to "Can't reach the phone" | Found on the phone test: an unreachable IP showed the vague "The video stream failed" |
| 35 | Maximized detection in the frame code | Ask Windows (`IsZoomed`), not Qt | Fullscreen → maximized: Qt still reported fullscreen, so ~7 px were cut off at every edge |
| 36 | Rotate / mirror on the phone | `orientation` and `mirror_flip` settings, not a shader | Verified: the phone re-encodes (portrait → 1080×1920), so **recordings come out rotated too**, at no PC cost |
| 37 | Tap-to-focus | Click → `focus_region` "X,Y" (-1000…1000, mapped through orientation/mirror) then `/focus`; single click waits out the double-click interval | Verified: `focus_region` only accepts a comma; double-click stays fullscreen |
| 38 | Quality slider | Sent on release, not while dragging | Each change restarts the phone's encoder |
| 39 | Stale status vs optimistic UI | Ignore status reports while commands are in flight | Found on the phone: fast Mirror + Flip clicks left mirror on |
| 40 | Snapshot source | The decoded frame on screen → JPEG with FFmpeg's mjpeg encoder (not `/shot.jpg`) | Instant, no network round-trip, already rotated/mirrored like the view; no Pillow dependency |
| 41 | Recorder design | Stream thread copies packets into a bounded queue; writer thread remuxes. Each file starts on a keyframe; one shared time origin for video + audio | The original packet is still being decoded; shared origin keeps A/V in sync (verified: ends within 0.1 s) |
| 42 | Recording only on RTSP | Refused (with a message) on the MJPEG fallback | MJPEG has no packets to remux |
| 43 | Non-blocking stop | `stop(timeout_s=0)` from the UI; the REC badge clears when the file is actually finished | Never block the UI thread; never say "saved" before it is |
| 23 | Decoder order | D3D11VA → DXVA2 → software (CUDA skipped) | Measured: 5% / 8% / 33% CPU; CUDA fails on the phone's stream |
| 24 | YUV→RGB matrix uniform | Set with `QMatrix3x3`, not `setUniformValueArray` | PySide6 silently uploads nothing for a mat3 via the array call → black video (caught by the render tests) |
| 25 | Missed-repaint safety | 100 ms watchdog repaints if a frame is waiting | A dropped `update()` before the widget is exposed stalled the first frame for 3.4 s |

### Security
| # | Topic | Decision | Reason |
|---|---|---|---|
| 9 | Camera login | **Enable username + password in IP Webcam** | Stream is unencrypted; stops others on the Wi-Fi from watching |
| — | Password storage | Windows Credential Manager (`keyring`) | Never stored in plain text |

### Release
| # | Topic | Decision | Reason |
|---|---|---|---|
| 13 | Distribution | **Portable `.exe`** first; Inno Setup installer later | Fastest way to run it |
| 14 | Icon / logo | ✅ Camera lens on a monitor with Wi-Fi arcs, dark rounded square, accent `#4C8DFF` (made with ChatGPT); plus a "Cam**Desk**" wordmark | Matches the UI theme; readable from 24 px up. Optional later: a lens-only variant for 16 px |
| 15 | Auto-update | **Not needed** | Personal use |
| 16 | License | Decide only if published (e.g. MIT); PySide6 is LGPL — fine for personal/free use | Not needed now |

---

## 2. Target Hardware

### PC
| Item | Value |
|---|---|
| OS | Windows 11 Home |
| GPU | NVIDIA GeForce MX230 (2 GB) + Intel integrated graphics |
| Video decode | H.264 hardware decode via D3D11VA (either GPU) |
| Python | 3.12 |

### Phone (read over ADB on 2026-11-23)

| Item | Value |
|---|---|
| Model | **Samsung Galaxy A06** (SM-A065F) |
| Android | 16 (SDK 36) |
| Chip | MediaTek Helio G85 (MT6769V), 8 cores, arm64 |
| RAM | ~4 GB |
| Free storage | 15 GB of 47 GB |
| Screen | 720 × 1600 |
| Battery | Health good, 283 charge cycles, ~30–33 °C while charging |
| IP Webcam | **Installed — v1.19.0.913** (`com.pas.webcam`) |
| Other camera app | `com.jacksoftw.webcam` v2.9.7 also installed — close it while using IP Webcam (only one app can use the camera) |

#### Cameras
| | Back (main) | Front |
|---|---|---|
| Camera ID | 0 | 1 |
| Sensor resolution | 4080 × 3072 (50 MP sensor, 12.5 MP binned output) | 3264 × 2448 (8 MP) |
| Aperture | f/1.8 | f/2.0 |
| Focal length | 3.97 mm | 2.77 mm |
| Autofocus | ✅ Auto, macro, continuous video, continuous picture | ❌ Fixed focus |
| Flashlight (torch) | ✅ Yes | ❌ No |
| Max frame rate | 30 FPS | 30 FPS |
| Zoom | 1× – 10× (digital only) | 1× – 10× (digital only) |
| ISO range | 25 – 16000 | 75 – 8000 |
| Exposure compensation | −20 to +20 steps (sensor; IP Webcam 1.19 doesn't expose it) | −20 to +20 steps |
| Optical / video stabilization | ❌ None | ❌ None |
| Camera API level | LEVEL_3 (full manual control) | LEVEL_3 |

Also on the back: a 2 MP depth sensor (1600 × 1200, fixed focus) — not useful for streaming.

#### Video encoder (used by IP Webcam for H.264)
| Item | Value |
|---|---|
| Hardware encoder | `c2.mtk.avc.encoder` (MediaTek) |
| Max size | 2560 × 1440 |
| Capacity | Enough for **1080p @ 60 FPS** (camera limits it to 30) |
| Max bitrate | 30 Mbps |

#### Network
| Item | Value |
|---|---|
| Phone IP | **192.168.8.105** (may change — see recommendations) |
| PC | Wired (Ethernet) to the same router, 192.168.8.100 |
| Wi-Fi | 2.4 GHz, 802.11n |
| Signal | −29 dBm (excellent) |
| Link speed | 65–72 Mbps (1080p stream needs ~4–8 Mbps ✅) |

---

## 3. What This Means for the App

| Finding | Impact on CamDesk |
|---|---|
| Max 30 FPS | Target is **1080p @ 30 FPS** — matches our goal exactly |
| Front camera has no flash | Disable the **Flashlight** button when the front camera is active |
| Front camera is fixed focus | Disable **tap-to-focus** on the front camera |
| Zoom is digital only, max 10× | Zoom slider range 1×–10× |
| No stabilization | Recommend a tripod/stand; no stabilization toggle in UI |
| Exposure range −20 to +20 (sensor) | IP Webcam doesn't offer it → exposure control stays hidden unless a phone reports it |
| Strong Wi-Fi, 2.4 GHz | 1080p @ 16 Mbps plays with 0 dropped frames (step 4); bitrate shown in the debug overlay |
| Phone IP can change | Remember camera by name, and show a clear "camera not found" message with the new-IP hint |
| 4 GB RAM, Samsung battery manager | Samsung may kill IP Webcam in the background — see phone setup below |
| No battery data from IP Webcam | Battery hidden in the status bar |

---

## 4. Recommended Phone Setup (IP Webcam)

| Setting | Value |
|---|---|
| Main camera | Back camera |
| Video resolution | **1920 × 1080** (use 1280 × 720 if Wi-Fi is busy) |
| FPS limit | 30 |
| Video encoder | H.264 (hardware) |
| Quality | 50–70% |
| Audio | On |
| Login | Username + password **on** |
| Stay awake / prevent sleep | On |
| Power | Keep phone **plugged in** for long sessions |
| Orientation | Match how the phone stands (upright phone → `portrait`), or use CamDesk's rotate control (step 7) |

**Samsung-specific (important):**
1. Settings → Apps → IP Webcam → Battery → **Unrestricted**
2. Settings → Battery → Background usage limits → add IP Webcam to **Never sleeping apps**
3. Router: give the phone a **reserved/static IP** (192.168.8.105) so CamDesk always finds it

---

## 5. Verified on the Real Phone (2026-11-23)

Tested CamDesk's camera client against IP Webcam 1.19 at `192.168.8.105:8080`.

### Stream
| Item | Measured |
|---|---|
| RTSP `/h264_aac.sdp` | ✅ Opens in ~2 s over TCP (also served: `h264_ulaw`, `h264_opus`, `h264_pcm`) |
| Video | **H.264, 1920×1080, yuv420p, 29.9 FPS** |
| Audio | **AAC, 44.1 kHz** — stored in MKV as-is (μ-law from `h264_ulaw.sdp` is rejected by the MKV muxer) |
| Keyframes | about every 2 s (good for clean 30-min splits) |
| Bitrate | **~16 Mbps** at quality 49 → ~7 GB per hour of recording ⚠️ |

### API behaviour (differs from common docs)
| Item | Real behaviour | How CamDesk handles it |
|---|---|---|
| Zoom value | `curvals.zoom` = ratio × 100 (`"100"` = 1×, `"1000"` = 10×) | Parsed as ratio; max read from `avail.zoom` |
| Zoom command | `/ptz?zoom=0…100` (`50` → `"550"` = 5.5×) | Used for the zoom slider |
| Torch support | `avail.torch` = `["on","off"]` (back) / `["off"]` (front) | Used to enable the Flashlight button |
| `avail.flashmode` | Lists `on` even on the front camera | **Ignored** (unreliable) |
| Autofocus | `avail.focusmode` = `["off"]` on the front camera | Tap-to-focus disabled |
| Switching camera | For ~2–3 s `avail` is incomplete | Keep previous capabilities (no flicker) |
| Command reply | XML `<result>Ok</result>`, unknown path → 404 | Status code checked |
| Battery (`sensors.json`) | **Empty `{}`** | Battery hidden in the UI when unavailable |
| Exposure compensation | **Not offered** | Exposure control hidden |

### Stream service on the real phone (build step 3)
| | RTSP (primary) | MJPEG (fallback) |
|---|---|---|
| Video | 1920×1080 @ 29.8 FPS | 1920×1080 @ 29.7 FPS |
| Decoder | D3D11VA (GPU) | Software (CPU) |
| CamDesk process CPU | **~8% of one core** | ~24% |
| Frames dropped | 0 | 0 |
| Frame handoff to UI | 0.5 ms median | 1.2 ms median |

### Live preview on the real phone (build step 4)
| Measurement | Result | Target |
|---|---|---|
| Render rate | **29.6–30 FPS** (1080p) | 30 FPS ✅ |
| CamDesk CPU | **~2% of the PC** (≈16% of one core, 8 cores) | < 10% ✅ |
| Frames dropped | 0 (except while a test saved a screenshot) | ✅ |
| Decode → screen inside CamDesk | ~2 ms | ✅ |
| Camera → frame decoded on PC (screen-flash test) | **~225 ms** (216–270) | ~200 ms ⚠️ |
| Glass-to-glass (adds one display refresh) | **~240–250 ms** | ~200 ms ⚠️ |

Almost all latency is before the PC (phone encoder, Wi-Fi, IP Webcam buffering). To try later: 1280×720 and/or lower quality on the phone.

### AppController on the real phone (build step 5)
15/15 checks passed, all settings restored afterwards.

| Check | Result |
|---|---|
| Connect (stream + capabilities) | ✅ 2.8 s |
| Flashlight on/off | ✅ confirmed by the phone |
| Fast zoom drag to 2× (10 steps) | ✅ throttled; phone reports 1.99× (zoom steps) |
| Switch to front camera | ✅ torch + autofocus reported unavailable; video keeps flowing (30 FPS) |
| Flashlight on the front camera | ✅ warning toast, no command sent |
| Night vision on/off | ✅ |
| `disconnect()` | ✅ returns in 0.3 ms (never blocks the UI) |

### Main window on the real phone (build step 6)
- First runs right after IP Webcam started: RTSP opened and packets arrived, but **no frame decoded** for >10 s (GPU and CPU alike). A few minutes later the identical code decoded normally (first frame ~1 s). Cause is on the phone side; decision #33 now reconnects automatically.
- In a dim room the camera delivered ~11–20 FPS instead of 30 (longer exposure). Normal camera behavior.
- Main window with GPU decoding: first frame on screen, NV12 textures, 29.9 FPS drawn, 0 dropped (fake 1280×720 stream).
- **Driven like a user against the phone (24/24 passed):** paste `http://192.168.8.105:8080` → connected in 1.1 s; 30.0 FPS drawn, D3D11VA, **2.8% CPU**, 1.9 ms decode→screen; T/+/− keys confirmed by the phone; F11/Esc; maximize fits the work area; unreachable IP → "Can't reach the phone" overlay; Change camera → recent list → reconnected. Phone settings restored.

### Controls on the real phone (build step 7)
19/19 passed, phone restored afterwards:

| Check | Result |
|---|---|
| Rotate right / left (side panel) | ✅ landscape → portrait (stream becomes **1080×1920**) → upside down → back; video keeps flowing |
| Upside-down orientation | ✅ the user's upside-down-mounted phone shows the scene upright |
| Mirror + flip toggles, clicked fast | ✅ `mirror` → `mirror,flip` → `none` (after decision #39) |
| Click on the picture | ✅ focus ring + `focus_region` 500x0 for a click on the right half |
| Quality slider drag → release | ✅ one command (70), video recovers |
| Resolution 1920×1080 → 1280×720 → back | ✅ stream recovers by itself in **2.6 s** |

### Recording on the real phone (build step 8)
~72 s recorded with 1-minute parts while streaming:

| Check | Result |
|---|---|
| Parts | ✅ part 1 = 60.3 s, part 2 started at 1:00 exactly |
| Format | ✅ H.264 1920×1080 + AAC 44.1 kHz in MKV; every part starts on a keyframe at time 0 |
| Integrity | ✅ 1800/1800 and 359/359 frames decode, 0 errors, 0 dropped packets |
| A/V sync | ✅ video and audio end within 0.1 s |
| CPU | ✅ **3.2% streaming vs 3.1% recording** — recording costs nothing measurable |
| Size | 15.9 Mbps ≈ **7.2 GB/hour** at quality 49 |
| Snapshot (Space) | ✅ 1920×1080 JPEG, 180 KB |

### Open questions
- **Latency vs. resolution:** test 1280×720 / lower quality to get under 200 ms (CamDesk itself adds ~2 ms).
- **Disk use:** 16 Mbps ≈ 7 GB per hour of recording. Playback is smooth at this bitrate (step 4), but lower quality may be worth it before recording lands (step 8).

## 6. Future Idea (not in V1)

**USB mode via ADB:** `adb forward tcp:8080 tcp:8080` lets CamDesk connect to `localhost:8080` over the USB cable — no Wi-Fi needed, lower latency, and the phone charges at the same time. ADB is already installed on this PC, so this is easy to add later.
