# CamDesk

A smooth, modern Windows desktop app to view, record and control an Android phone running the **IP Webcam** app over Wi-Fi.

> Status: **in development** — Version 1, build steps 1 (project setup) and 2 (camera control client) done.

## Requirements

- Windows 10/11
- [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`)
- Python 3.12 (uv installs it automatically if missing)
- An Android phone with [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam) on the same Wi-Fi

## Quick start

```powershell
uv sync                          # install dependencies
uv run python -m camdesk         # run the app
uv run python -m camdesk --fake  # run with the built-in fake camera (no phone needed)
uv run pytest                    # run tests
uv run ruff check .              # lint
```

Phone setup (resolution, Samsung battery settings, static IP) is in [docs/decisions.md](docs/decisions.md#4-recommended-phone-setup-ip-webcam).

## Documentation

See [docs/README.md](docs/README.md). Rules for AI coding agents: [AGENTS.md](AGENTS.md).

## Where CamDesk stores data

| Data | Location |
|---|---|
| Settings and logs | `%APPDATA%\CamDesk\` |
| Snapshots and recordings | `%USERPROFILE%\Videos\CamDesk\` |
| Camera passwords | Windows Credential Manager |
