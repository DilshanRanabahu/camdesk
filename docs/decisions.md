# CamDesk — Project Decisions

Final decisions for the project. Anything not listed here follows [architecture.md](architecture.md), [feature.md](feature.md) and [ui-design.md](ui-design.md).

**Status:** Approved · **Date:** 2026-11-23

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
| 10 | Testing | Unit tests for logic + **fake camera** (plays a video file) | Develop and test without the phone |
| 11 | Performance check | Debug overlay (CPU, FPS, latency), checked at build step 4 | Prove the smoothness target early |
| 18 | MJPEG fallback decoder | **PyAV (FFmpeg)** instead of PyTurboJPEG | PyTurboJPEG needs a separate native libjpeg-turbo install on Windows; FFmpeg's decoder is already bundled and fast enough for a fallback |
| 19 | Fake camera location | `src/camdesk/dev/` (not `tests/`) | `--fake` mode in the app needs it, not just tests |
| 20 | Qt package | **PySide6-Essentials** (not full `PySide6`) | Has everything CamDesk needs (Widgets, OpenGL, Test); skips WebEngine/3D/Multimedia add-ons — much smaller download and `.exe` |
| 21 | Frame types location | `VideoFrame` + `LatestFrameBuffer` in `core/frames.py` (not `stream/`) | The UI's video widget reads frames, and the UI may only import `core/` |
| 22 | Low-latency input | FFmpeg `fflags=nobuffer` for the camera | Lower delay; drops only the single frame read while probing at connect time |
| 24 | YUV→RGB matrix uniform | Set with `QMatrix3x3`, not `setUniformValueArray` | PySide6 silently uploads nothing for a mat3 via the array call → black video (caught by the render tests) |
| 25 | Missed-repaint safety | 100 ms watchdog repaints if a frame is waiting | A dropped `update()` before the widget is exposed stalled the first frame for 3.4 s |
| 23 | Decoder order | D3D11VA → DXVA2 → software (CUDA skipped) | Measured: 5% / 8% / 33% CPU; CUDA fails on the phone's stream |

### Security
| # | Topic | Decision | Reason |
|---|---|---|---|
| 9 | Camera login | **Enable username + password in IP Webcam** | Stream is unencrypted; stops others on the Wi-Fi from watching |
| — | Password storage | Windows Credential Manager (`keyring`) | Never stored in plain text |

### Release
| # | Topic | Decision | Reason |
|---|---|---|---|
| 13 | Distribution | **Portable `.exe`** first; Inno Setup installer later | Fastest way to run it |
| 14 | Icon / logo | Simple camera-lens icon in accent blue `#4C8DFF` | Matches the UI theme |
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
| Exposure compensation | −20 to +20 steps | −20 to +20 steps |
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
| Exposure range −20 to +20 | Exposure slider (V2) uses this range |
| Strong Wi-Fi, 2.4 GHz | 1080p is fine; 2.4 GHz can be crowded — show bitrate in debug overlay |
| Phone IP can change | Remember camera by name, and show a clear "camera not found" message with the new-IP hint |
| 4 GB RAM, Samsung battery manager | Samsung may kill IP Webcam in the background — see phone setup below |

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

### Open question
- **Latency vs. resolution:** test 1280×720 / lower quality to get under 200 ms (CamDesk itself adds ~2 ms).
- **Bitrate:** 16 Mbps is heavy for 2.4 GHz Wi-Fi and disk space. Consider lowering IP Webcam's video quality, or 1280×720, if the stream stutters. To be checked with the debug overlay in build step 4.

## 6. Future Idea (not in V1)

**USB mode via ADB:** `adb forward tcp:8080 tcp:8080` lets CamDesk connect to `localhost:8080` over the USB cable — no Wi-Fi needed, lower latency, and the phone charges at the same time. ADB is already installed on this PC, so this is easy to add later.
