# CamDesk Documentation

Planning and design documents for CamDesk, a Windows desktop app that views, records and controls an Android phone running IP Webcam.

| Document | What it covers |
|---|---|
| [decisions.md](decisions.md) | Approved decisions, target PC and phone hardware, phone setup. **Start here.** |
| [feature.md](feature.md) | Feature list for V1, V2 and V3, with checkboxes, shortcuts and IP Webcam endpoints |
| [ui-design.md](ui-design.md) | Dark UI design: colors, fonts, layout, screens, components, animations, shortcuts |
| [architecture.md](architecture.md) | Layers, threads, video pipeline, folder structure, dependencies, build order |

Rules for AI coding agents are in [../AGENTS.md](../AGENTS.md) at the project root.

## Project status

| Build step (Version 1) | Status |
|---|---|
| 1. Project setup | ✅ |
| 2. Camera control client | ✅ verified on the phone |
| 3. Video stream service | ✅ GPU decode, reconnect, MJPEG fallback |
| 4. Live OpenGL preview + debug overlay | ✅ 30 FPS, ~2% CPU |
| 5. AppState + AppController | ✅ optimistic, capability-aware, throttled zoom |
| 6. UI shell (main window, connect screen) | ✅ custom title bar, connect screen, status bar |
| 7. Controls (dock + side panel) | next |
| 8. Snapshots + MKV recording | |
| 9. Polish (toasts, reconnect UI, shortcuts) | |
| 10. `CamDesk.exe` build | |

Measurements from the real phone are in [decisions.md § 5](decisions.md#5-verified-on-the-real-phone-2026-11-23).

## Keeping docs up to date
- When a decision changes, update [decisions.md](decisions.md) and any document it affects in the same change.
- Tick a feature's checkbox in [feature.md](feature.md) when it is done.
- Keep links relative so they work in the editor and on GitHub.
