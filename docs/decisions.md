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
| 3 | Audio | **Recorded with video**, kept in the phone's original format (μ-law), no conversion | MKV supports it directly; no CPU cost |
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

## 5. Future Idea (not in V1)

**USB mode via ADB:** `adb forward tcp:8080 tcp:8080` lets CamDesk connect to `localhost:8080` over the USB cable — no Wi-Fi needed, lower latency, and the phone charges at the same time. ADB is already installed on this PC, so this is easy to add later.
