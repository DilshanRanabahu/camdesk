# CamDesk — Performance

How smooth CamDesk is, how it was measured, and what was optimized. All numbers come from the real setup:
Samsung Galaxy A06 + IP Webcam 1.19 over 2.4 GHz Wi-Fi → Windows 11 PC (Intel UHD + MX230), 1920×1080 H.264 at 30 FPS.

Related: [decisions.md](decisions.md) · [architecture.md](architecture.md)

---

## 1. Where the time goes (profiling, 2026-11-24)

Measured for each frame: phone capture time (the stream's timestamps), packet arrival, decode, and the moment it was drawn.

| Stage | Gap between frames (sd) | Gaps > 50 ms in 25 s | Verdict |
|---|---|---|---|
| Phone camera capture | **0.0 ms** (exactly every 33.5 ms) | 0 | Perfect |
| Arrival over Wi-Fi | **±14.9 ms** (up to ~100 ms late) | 50 | ⚠️ the source of visible stutter |
| Decode (D3D11VA) | same as arrival | 51 | Adds nothing |
| Draw (OpenGL) | same as arrival | — | Adds nothing |

**Conclusion:** the phone is perfectly even; Wi-Fi delivers frames in bursts; CamDesk passed those bursts straight to the screen.
Lower quality and 720p did **not** reduce the bursts — see §4.

### Already efficient (no work needed)

| Metric | Result |
|---|---|
| Draw cost on the UI thread | 1.4 ms per frame (p99 ~4 ms) |
| CPU | ~3% of the PC (≈25% of one core) |
| Frames dropped by CamDesk | 2–3 of ~900 per 30 s |
| Garbage-collection pauses | 2 per 30 s, < 0.5 ms each |
| Memory | Stable over time (no leak) |
| Recording | No measurable effect on smoothness or CPU |

---

## 2. Optimizations made

### 2.1 Smooth playback (default)
`core/playout.py` — frames are shown on the **phone's clock** instead of the moment they arrive:

- each frame is scheduled at `capture time → local time + adaptive delay`;
- the delay is the 95th percentile of recent lateness (+8 ms), capped at 150 ms; it rises at once and decays slowly;
- the video widget paints **when the next frame is due** (precise timer), so each frame lands on its own display refresh;
- reconnects / timestamp jumps reset the schedule; "Lowest latency" in Settings keeps the old show-on-arrival behavior.

| On screen, 30 s (real phone) | Lowest latency | **Smooth** |
|---|---|---|
| Gaps > 100 ms (clear stutter) | 7 | **0** |
| Gaps > 50 ms | 54–61 | **1–12** |
| Timing variation (sd) | 13–14 ms | **4.4–7 ms** |
| Worst gap | 130–140 ms | **73–82 ms** |
| Added delay | — | **~57 ms** (max ~85 ms) |

The remaining 33 ↔ 50 ms steps are the 60 Hz display grid (a 30 FPS frame occasionally waits one more refresh).

### 2.2 1 ms timer resolution
Windows' default timer step (~15.6 ms) depends on *other* running apps. With the default, the playback timer and the UI event
loop were up to ~13 ms late in some runs and not others. CamDesk now requests 1 ms resolution while it runs (as browsers and
media players do) and releases it on exit.

| | Default timers (some runs) | 1 ms timers (two runs) |
|---|---|---|
| UI event-loop lag (mean) | ~11–13 ms | **0.4–1.0 ms** |
| Smooth gaps > 50 ms | 11–12 | **1–7** |

### 2.3 Faster drop detection
Network read timeout 3 s → 2 s (Wi-Fi gaps measured ≤ 0.27 s, so no false drops). Real Wi-Fi drop (phone Wi-Fi off via ADB):
**noticed after 4.5 s instead of 6.5 s**; video back ~4–5 s after Wi-Fi returns. The rest is Windows keeping the TCP
connection alive briefly — outside CamDesk.

### 2.4 Startup (CamDesk.exe)
Launch → first video frame, measured against the phone:

| Run | Time |
|---|---|
| From source (`uv run python -m camdesk`) | 2.8–3.1 s |
| `CamDesk.exe` (Nuitka standalone folder) | **2.1–2.2 s** |
| `CamDesk.exe`, very first launch | ~5 s (one-time Windows Defender scan) |

A one-file exe was not used: it unpacks itself to a temp folder on every launch (decision #51).

### 2.5 Earlier fixes found by measuring
- Repaint watchdog: a missed `update()` stalled the first frame for 3.4 s (step 4).
- "No picture" watchdog: packets but no decodable frames right after IP Webcam starts (step 6).
- Stale-status race undoing fast toggles (step 7).

---

## 3. Tried and rejected (measured, no gain)

| Idea | Result |
|---|---|
| `swapInterval 0` (no vsync wait on the UI thread) | No consistent difference — the UI lag came from timer resolution, not vsync. Kept `swapInterval 1`. |
| Repaint at every display refresh (60/s) in Smooth mode | Same smoothness, more CPU than painting at each frame's due time (30/s). |
| Zero-copy D3D11 → OpenGL, async texture uploads (PBO) | Not attempted: drawing already costs 1.4 ms/frame at ~3% CPU — no visible gain for the complexity. |

---

## 4. Facts about the phone stream that limit tuning

- **The H.264 stream has a fixed bitrate (~16 Mbps, ~67 KB per frame)** at every IP Webcam *quality* setting and at 720p too.
  The quality setting only affects the MJPEG backup stream. So: recordings are ~7 GB per hour regardless of the quality slider
  (now labelled "MJPEG quality"), and lowering quality does not reduce Wi-Fi bursts.
- Total delay camera → screen is ~240 ms in Lowest-latency mode (~300 ms in Smooth). CamDesk's own share is ~2 ms plus the
  Smooth buffer; the rest is the phone's encoder and Wi-Fi.

---

## 5. How to re-measure

The profiling scripts drive the real app with wrappers only (no app code changes) and use `psutil` for per-thread CPU,
loaded just for the run: `uv run --with psutil python <script>`. Measure **twice** — Windows timer resolution and Wi-Fi vary
between runs. Watch: on-screen gaps > 50 / > 100 ms, timing sd, UI event-loop lag (with a *precise* timer), CPU per thread.
