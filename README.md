# CamDesk

A smooth, modern Windows desktop app to view, record and control an Android phone running the **IP Webcam** app over Wi-Fi.

> **Status: in development.** Version 1, build steps **1–4 of 10** done: live GPU-decoded video from the phone works.
> The full dark UI, camera controls and recording are next. See [progress](docs/README.md#project-status).

## Highlights

- **Smooth, low-CPU video:** H.264 decoded on the GPU (D3D11VA) and converted to RGB in an OpenGL shader.
  Measured on a Galaxy A06 → MX230 laptop: **1080p @ 30 FPS, ~2% CPU, 0 dropped frames**.
- **Never lags behind:** only the newest frame is kept, so delay can't build up.
- **Self-healing connection:** automatic reconnect with backoff, plus an MJPEG fallback stream.
- **Recording without re-encoding** (coming in step 8): H.264 + AAC saved straight to crash-safe MKV.
- **Private:** no telemetry; talks only to your phone on the local network. Passwords live in Windows Credential Manager.

## Requirements

- Windows 10/11
- [uv](https://docs.astral.sh/uv/): `winget install astral-sh.uv` (open a new terminal afterwards)
- Python 3.12 (uv installs it automatically if missing)
- An Android phone with [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam) on the same network. In the app, tap **Start server**.

## Quick start

```powershell
git clone https://github.com/DilshanRanabahu/camdesk.git
cd camdesk
uv sync                                         # install dependencies
uv run python -m camdesk --host 192.168.x.x     # first run: your phone's IP (shown in IP Webcam)
uv run python -m camdesk                        # later runs: the IP is remembered
uv run python -m camdesk --fake                 # no phone? built-in test pattern
```

The temporary preview window is replaced by the full UI with a connect screen in step 6.

| Key | Action |
|---|---|
| `Ctrl+D` | Debug overlay: FPS, CPU, decoder, bitrate, frame age |
| `F11` / `F` / double-click | Fullscreen (`Esc` exits) |
| `V` | View mode: fit / fill / original size |

**Picture sideways?** If the phone stands upright, set IP Webcam's video orientation to *portrait*. A rotate control is coming in step 7.

Recommended phone settings (resolution, Samsung battery settings, static IP): [docs/decisions.md § 4](docs/decisions.md#4-recommended-phone-setup-ip-webcam).

## Development

```powershell
uv run pytest            # 99 tests: no phone needed (fake camera + fake video + real OpenGL render checks)
uv run ruff check .      # lint
uv run ruff format .     # format
```

- Architecture, threads and folder layout: [docs/architecture.md](docs/architecture.md)
- Rules for AI coding agents: [AGENTS.md](AGENTS.md)
- All docs: [docs/README.md](docs/README.md)

## Tech stack

Python 3.12 · PySide6-Essentials (Qt 6) · PyAV (FFmpeg) · OpenGL shaders · httpx · keyring · uv · pytest · ruff

## Where CamDesk stores data

| Data | Location |
|---|---|
| Settings and logs | `%APPDATA%\CamDesk\` |
| Snapshots and recordings | `%USERPROFILE%\Videos\CamDesk\` |
| Camera passwords | Windows Credential Manager |
