# CamDesk — Features

A Windows desktop app to view, record and control an Android phone running the **IP Webcam** app.

Related docs: [decisions.md](decisions.md) · [ui-design.md](ui-design.md) · [architecture.md](architecture.md)

## Tech Stack

| Layer | Choice |
|---|---|
| UI | PySide6 (Qt 6) |
| Video decoding | PyAV (FFmpeg) — H.264 RTSP with D3D11VA hardware decode |
| Fallback stream | MJPEG decoded by PyAV (FFmpeg) |
| Rendering | QOpenGLWidget (GPU texture upload) |
| Recording | PyAV — remux H.264 + audio to MKV (no re-encoding) |
| Motion detection | OpenCV on downscaled grayscale frames |
| Camera control | httpx (async HTTP) |
| Packaging | Nuitka (native .exe) |

**Target PC:** Windows 11, NVIDIA MX230 2 GB (+ Intel iGPU)
**Target phone:** Samsung Galaxy A06 (Android 16), IP Webcam v1.19 — full details in [decisions.md](decisions.md#2-target-hardware)
**Performance goal:** 1080p @ 30 FPS (phone maximum), ~200 ms latency, < 10% CPU
**Network:** Same Wi-Fi only · **Language:** English only

---

## Version 1 — Core (build first)

### Connection
- [ ] 1. IP, port, optional username/password fields + **Connect** button
- [ ] 2. Connection status indicator (connected / connecting / lost)
- [ ] 3. Auto-reconnect when Wi-Fi drops (with backoff)
- [ ] 4. Remember the last camera used

### Live View
- [x] 5. Smooth live video with GPU decoding (RTSP H.264, MJPEG fallback)
- [x] 6. Fullscreen mode (double-click or F11)
- [x] 7. View modes: fit / fill / original size (`V` key for now; UI control in step 7)
- [ ] 8. On-screen FPS, resolution and latency
- [x] 8a. Debug overlay (`Ctrl+D`): CPU, FPS, latency, bitrate, decoder in use

### Capture
- [ ] 9. Snapshot (button or Space), saved with timestamp
- [ ] 10. Record to **MKV** (video + audio) without re-encoding, with recording timer
- [ ] 10a. Auto-split recordings into a new file every **30 minutes**
- [ ] 11. "Open captures folder" button

### Camera Controls (sent to the phone)
- [ ] 12. Flashlight on/off — **back camera only** (front has no flash; button disabled)
- [ ] 13. Switch front/back camera
- [ ] 14. Zoom slider, **1× – 10×** (digital zoom)
- [ ] 15. Tap-to-focus — **back camera only** (front is fixed focus; disabled)
- [ ] 16. Resolution and quality settings
- [ ] 17. Night vision on/off
- [ ] 18. Rotate / flip image

### Status Bar
- [ ] 19. Phone battery level
- [ ] 20. Recording status and free disk space

### UI
- [ ] Dark theme

---

## Version 2 — Smart Features

- [ ] 21. **Motion detection** — highlight changes, auto-save clips, Windows notification
- [ ] 22. Motion sensitivity and detection zones
- [ ] 23. **Timelapse** — snapshot every N seconds, combine into a video
- [ ] 24. **Listen to audio** from the phone's microphone
- [ ] 25. Exposure (−20 to +20), white balance and scene mode controls
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
| `F` / `F11` | Fullscreen |
| `T` | Flashlight |
| `C` | Switch camera |
| `+` / `-` | Zoom in / out |
| `Ctrl` + `D` | Debug overlay |

---

## IP Webcam Endpoints Used

| Endpoint | Purpose |
|---|---|
| `rtsp://<ip>:8080/h264_aac.sdp` | H.264 video + AAC audio (primary) |
| `http://<ip>:8080/video` | MJPEG stream (fallback) |
| `http://<ip>:8080/shot.jpg` | Single snapshot |
| `http://<ip>:8080/audio.wav` | Audio stream |
| `http://<ip>:8080/sensors.json` | Sensors and battery |
| `http://<ip>:8080/status.json?show_avail=1` | Current camera settings + available options |
| `http://<ip>:8080/enabletorch` / `disabletorch` | Flashlight |
| `http://<ip>:8080/focus` / `nofocus` | Focus |
| `http://<ip>:8080/settings/<key>?set=<value>` | Zoom, quality, resolution, night vision, front camera, orientation, etc. |
