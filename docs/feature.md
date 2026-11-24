# CamDesk — Features

A Windows desktop app to view, record and control an Android phone running the **IP Webcam** app.

Related docs: [decisions.md](decisions.md) · [ui-design.md](ui-design.md) · [architecture.md](architecture.md)

> **Progress (2026-11-24):** Version 1 build steps **1–9 of 10** done — everything in Version 1 works; only the `.exe` build (step 10) is left. `[x]` = done.

## Tech Stack

| Layer | Choice |
|---|---|
| UI | PySide6-Essentials (Qt 6) |
| Video decoding | PyAV (FFmpeg) — H.264 RTSP with D3D11VA → DXVA2 → software decode |
| Fallback stream | MJPEG decoded by PyAV (FFmpeg) |
| Rendering | QOpenGLWidget — YUV → RGB in a GLSL shader |
| Recording | PyAV — remux H.264 + AAC audio to MKV (no re-encoding) |
| Motion detection | OpenCV on downscaled grayscale frames |
| Camera control | httpx on its own Qt thread (ordered command queue) |
| Packaging | Nuitka (native .exe) |

**Target PC:** Windows 11, NVIDIA MX230 2 GB (+ Intel iGPU)
**Target phone:** Samsung Galaxy A06 (Android 16), IP Webcam v1.19 — full details in [decisions.md](decisions.md#2-target-hardware)
**Performance goal:** 1080p @ 30 FPS (phone maximum), ~200 ms latency, < 10% CPU
**Network:** Same Wi-Fi only · **Language:** English only

---

## Version 1 — Core (build first)

### Connection
- [x] 1. IP, port, optional username/password fields + **Connect** button (paste `http://ip:port` straight from IP Webcam)
- [x] 2. Connection status indicator (connected / connecting / lost) — dot in the pill + status bar + overlay with Retry
- [x] 3. Auto-reconnect when Wi-Fi drops (with backoff) — overlay with attempt number, hints, "Reconnected" toast (real Wi-Fi drop: video back 4.2 s after Wi-Fi returns)
- [x] 4. Remember the last camera used (+ recent cameras list, forget button)

### Live View
- [x] 5. Smooth live video with GPU decoding (RTSP H.264, MJPEG fallback)
- [x] 6. Fullscreen mode (double-click or F11)
- [x] 7. View modes: fit / fill / original size (`V` key + View card in the side panel)
- [x] 8. On-screen FPS, resolution and decoder (status bar; full numbers incl. frame age in the `Ctrl+D` overlay)
- [x] 8a. Debug overlay (`Ctrl+D`): CPU, FPS, latency, bitrate, decoder in use

### Capture
- [x] 9. Snapshot (button or Space), saved with timestamp (flash + "Open" link)
- [x] 10. Record to **MKV** (video + audio) without re-encoding, with recording timer (REC badge + status bar)
- [x] 10a. Auto-split recordings into a new file every **30 minutes** (at a keyframe; also on reconnect)
- [x] 11. "Open captures folder" button (Captures card: snapshots / recordings)

### Camera Controls (sent to the phone)
- [x] 12. Flashlight on/off — **back camera only** (front has no flash; button disabled)
- [x] 13. Switch front/back camera
- [x] 14. Zoom slider, **1× – 10×** (digital zoom)
- [x] 15. Tap-to-focus — **back camera only** (front is fixed focus; disabled). Click the picture; focus ring shows where
- [x] 16. Resolution and quality settings (stream recovers by itself after a change)
- [x] 17. Night vision on/off
- [x] 18. Rotate / flip image — done on the phone, so recordings are rotated too

### Status Bar
- [x] 19. Phone battery level + low-battery warning — shown only when the phone reports it (the A06 doesn't)
- [x] 20. Recording status and free disk space (warns < 2 GB, stops < 1 GB)

### UI
- [x] Dark theme (tokens → stylesheet + palette)

---

## Version 2 — Smart Features

- [ ] 21. **Motion detection** — highlight changes, auto-save clips, Windows notification
- [ ] 22. Motion sensitivity and detection zones
- [ ] 23. **Timelapse** — snapshot every N seconds, combine into a video
- [ ] 24. **Listen to audio** from the phone's microphone
- [ ] 25. Exposure, white balance and scene mode controls (exposure only if the phone offers it — the A06 doesn't)
- [ ] 26. Image adjustments (brightness, contrast, digital zoom)
- [ ] 27. Scheduled recording (e.g. 10 PM – 6 AM)
- [ ] 27a. One-click **Convert MKV → MP4** (for sharing)

---

## Version 3 — Advanced

- [ ] 28. **Multiple cameras** in a grid view (2×2, etc.)
- [ ] 29. Face / person detection with alerts
- [ ] 30. Overwrite oldest recordings when disk is full
- [ ] 31. Recording history and playback browser
- [ ] 32. Picture-in-picture mini window (always on top)
- [ ] 33. Start with Windows / run in system tray
- [ ] 34. Dark and light theme switch
- [ ] 35. **USB mode via ADB** — `adb forward tcp:8080 tcp:8080`, connect to `localhost` over the cable (no Wi-Fi, lower latency, phone charges)
- [ ] 36. Start/stop IP Webcam on the phone from CamDesk (via ADB)

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Snapshot |
| `R` | Start / stop recording |
| `F` / `F11` / double-click | Fullscreen (`Esc` exits) |
| `T` | Flashlight |
| `C` | Switch camera |
| `+` / `-` | Zoom in / out |
| `Tab` | Show / hide side panel |
| Click picture | Focus on that spot |
| `A` | Autofocus (temporary key until step 7) |
| `N` | Night vision (temporary key until step 7) |
| `Ctrl` + `D` | Debug overlay |
| `Ctrl` + `,` | Settings |
| Mouse wheel | Zoom |
| `V` | Cycle view mode: fit / fill / original |

---

## IP Webcam Endpoints Used

| Endpoint | Purpose |
|---|---|
| `rtsp://<ip>:8080/h264_aac.sdp` | H.264 video + AAC audio (primary) |
| `http://<ip>:8080/video` | MJPEG stream (fallback) |
| `http://<ip>:8080/shot.jpg` | Single snapshot (not used — snapshots come from the live frame) |
| `http://<ip>:8080/audio.wav` | Audio stream (V2 listen feature) |
| `http://<ip>:8080/sensors.json` | Sensors and battery (empty `{}` on the A06) |
| `http://<ip>:8080/status.json?show_avail=1` | Current camera settings + available options |
| `http://<ip>:8080/enabletorch` / `disabletorch` | Flashlight |
| `http://<ip>:8080/focus` / `nofocus` | Focus |
| `http://<ip>:8080/ptz?zoom=0…100` | Zoom (`50` = 5.5× on the A06) |
| `http://<ip>:8080/settings/<key>?set=<value>` | Quality, resolution, night vision, front camera (`ffc`), orientation, etc. |
