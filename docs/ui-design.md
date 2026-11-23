# CamDesk — UI/UX Design

Modern, minimal, dark interface. The video is the hero; everything else stays out of the way until needed.

Related docs: [feature.md](feature.md) · [decisions.md](decisions.md) · [architecture.md](architecture.md)

Language: **English only**. All user-facing text lives in one module (`ui/strings.py`) so wording stays consistent.

> **Implementation status (step 4):** design tokens (`ui/theme/tokens.py`), the OpenGL video area and the `Ctrl+D` debug overlay are built. A temporary bare preview window stands in for the main window until step 6; the title bar, connect screen, control dock, side panel, status bar and toasts come in steps 6–9.

---

## 1. Design Principles

1. **Video first** — the live feed fills the window. Controls float over it or sit in a slim side panel.
2. **Calm by default** — neutral dark surfaces, one accent color, color only when it means something (recording = red, connected = green).
3. **Smart, not busy** — controls auto-hide when the mouse is idle; advanced settings live behind one click.
4. **Instant feedback** — every action shows a response within 100 ms (button state, toast, or animation).
5. **Keyboard friendly** — every main action has a shortcut and shows it in its tooltip.

---

## 2. Color Palette

### Surfaces
| Token | Hex | Use |
|---|---|---|
| `bg-base` | `#0E0F12` | Window background, behind video |
| `bg-surface` | `#16181D` | Side panel, top bar, status bar |
| `bg-elevated` | `#1E2128` | Cards, inputs, dropdowns |
| `bg-hover` | `#262A33` | Hover state |
| `bg-overlay` | `rgba(14,15,18,0.72)` | Floating controls over video (with blur) |
| `border` | `#2A2E37` | Dividers, input borders |

### Text
| Token | Hex | Use |
|---|---|---|
| `text-primary` | `#E8EAED` | Main text |
| `text-secondary` | `#9AA0AA` | Labels, hints |
| `text-disabled` | `#5C626C` | Disabled items |

### Accent & Status
| Token | Hex | Use |
|---|---|---|
| `accent` | `#4C8DFF` | Primary buttons, active toggles, slider fill, focus ring |
| `accent-hover` | `#6BA1FF` | Accent hover |
| `success` | `#3DD68C` | Connected, saved |
| `warning` | `#F5B544` | Reconnecting, low battery |
| `danger` | `#FF4D5E` | Recording, errors, disconnected |

---

## 3. Typography

- **Font:** Segoe UI Variable (native on Windows 11), fallback Segoe UI
- **Numbers (FPS, timer, battery):** Cascadia Mono / Consolas, so digits don't jump

| Style | Size | Weight | Use |
|---|---|---|---|
| Title | 15 px | Semibold | Window/section titles |
| Body | 13 px | Regular | Most text, buttons |
| Label | 12 px | Medium | Control labels |
| Caption | 11 px | Regular | Status bar, hints |
| Mono | 12 px | Regular | FPS, latency, timer |

---

## 4. Spacing, Shape & Icons

- **Spacing scale:** 4 · 8 · 12 · 16 · 24 · 32 px
- **Corner radius:** 6 px (inputs, buttons), 10 px (cards, panels), 999 px (pills, round buttons)
- **Icons:** Lucide (SVG, 1.75 px stroke), 18 px in panels, 22 px on video overlay
- **Shadows:** only on floating elements — `0 8px 24px rgba(0,0,0,0.45)`

---

## 5. Main Window Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ ◉ CamDesk    [● Galaxy A06 · 192.168.8.105 ▾]     ⚙   ─  □  ✕   │  Top bar (44 px)
├────────────────────────────────────────────────┬─────────────────┤
│ ● REC 00:12                     30 fps · 180ms │  CAMERA         │
│                                                │  ┌───────────┐  │
│                                                │  │🔦 Torch  ◯│  │
│                                                │  │🌙 Night  ◯│  │
│                LIVE VIDEO                      │  └───────────┘  │
│                                                │  Zoom           │
│                                                │  ───────●────   │
│                                                │  Quality        │
│                                                │  ─────────●──   │
│         ┌─────────────────────────────┐        │  Resolution     │
│         │  📸   ⏺   🔄   🔍   ⛶       │        │  [1920×1080 ▾]  │
│         └─────────────────────────────┘        │                 │
│                                                │  ▸ Advanced     │
├────────────────────────────────────────────────┴─────────────────┤
│ ● Connected · 🔋 78% · 💾 120 GB free · H.264 GPU            ◧   │  Status bar (28 px)
└──────────────────────────────────────────────────────────────────┘
```

| Area | Details |
|---|---|
| **Top bar** | App logo, camera selector pill (status dot + name + IP), settings, window buttons. Custom frameless title bar. |
| **Video area** | Fills remaining space, black letterbox. Overlays: REC badge (top-left), FPS/latency (top-right), control dock (bottom-center). |
| **Control dock** | Floating pill, glass effect: Snapshot · Record · Switch camera · Focus · Fullscreen. Auto-hides after 3 s of no mouse movement. |
| **Side panel** | 260 px, collapsible (`◧` button or `Tab`). Grouped cards: Camera, Image, Advanced (collapsed by default). |
| **Status bar** | Connection, battery (only when the phone reports it), disk space, decoder in use. |

**Minimum window size:** 960 × 600. Below 1100 px wide, the side panel collapses automatically.

---

## 6. Screens & States

### 6.1 First Launch / Connect Screen
```
┌──────────────────────────────────────┐
│              ◉ CamDesk               │
│     Connect to your phone camera     │
│                                      │
│  IP address      Port                │
│  [192.168.8.105]  [8080]             │
│                                      │
│  ▸ Login (optional)                  │
│                                      │
│  [        Connect         ]          │
│                                      │
│  Recent: ● Galaxy A06 · 192.168.8.105│
│                                      │
│  ⓘ Open IP Webcam → Start server     │
└──────────────────────────────────────┘
```
- Centered card on `bg-base`, 380 px wide
- IP field validates as you type (red border + hint if invalid)
- Recent cameras: one click to reconnect
- Help hint at bottom for first-time users

### 6.2 Connection States
| State | Video area | Status dot |
|---|---|---|
| Connecting | Skeleton shimmer + "Connecting to 192.168.8.105…" | 🟡 pulsing |
| Connected | Live video fades in (200 ms) | 🟢 |
| Reconnecting | Last frame dimmed + blurred, "Reconnecting… (attempt 2)" | 🟡 pulsing |
| Failed | Icon + message + **Retry** and **Change camera** buttons | 🔴 |
| Camera not found | "Can't find Galaxy A06 at 192.168.8.105. Is IP Webcam running? The phone's IP may have changed." + IP field to edit | 🔴 |

### 6.3 Recording State
- Record button turns into a red filled circle with a soft pulse
- `● REC 00:12` badge top-left (red pill, mono timer)
- After the first 30-minute split, the badge shows the part: `● REC 00:31:05 · Part 2`
- Thin red line along the top edge of the video
- Stop → toast: "Saved recording_2026-11-23_21-04.mkv · Open folder"

### 6.4 Snapshot Feedback
- Quick white flash on video (80 ms, 30% opacity)
- Thumbnail slides into bottom-right for 2 s; click to open

### 6.5 Fullscreen
- Only video + auto-hiding control dock + small top-right info
- `Esc` or double-click to exit

---

## 7. Components

| Component | Spec |
|---|---|
| **Primary button** | `accent` fill, white text, 36 px high, radius 6. Hover: `accent-hover`. Press: scale 0.97. |
| **Ghost button** | Transparent, `text-primary`, hover `bg-hover`. |
| **Icon button (dock)** | 44 px circle, hover `rgba(255,255,255,0.08)`, tooltip with shortcut ("Snapshot · Space"). |
| **Toggle switch** | 36×20 px, off `#3A3F4A`, on `accent`, knob slides 150 ms. |
| **Slider** | 4 px track `#2E323C`, fill `accent`, 14 px knob, shows value bubble while dragging. Zoom slider: 1.0× – 10.0×, bubble shows e.g. "2.5×". |
| **Disabled control** | 40% opacity, no hover, tooltip explains why (e.g. "Not available on the front camera"). |
| **Input** | `bg-elevated`, 1 px `border`, focus: 2 px `accent` ring. |
| **Dropdown** | Same as input + chevron; menu uses `bg-elevated` + shadow. |
| **Card** | `bg-elevated`, radius 10, 12 px padding, section title in Label style. |
| **Toast** | Bottom-center, `bg-elevated`, icon + message + optional action, auto-dismiss 3 s. |
| **Tooltip** | `#2A2E37`, 12 px text, 400 ms delay. |

---

## 8. Motion & Animation

| Interaction | Duration | Easing |
|---|---|---|
| Hover color change | 120 ms | ease-out |
| Toggle / button press | 150 ms | ease-out |
| Control dock show / hide | 200 ms | ease-in-out (fade + 8 px slide) |
| Side panel collapse | 220 ms | ease-in-out |
| Toast in / out | 200 ms | ease-out |
| Recording pulse | 1.5 s loop | ease-in-out |

Animations never touch the video widget — only overlays — so playback stays smooth.

---

## 9. Smart UX Behaviors

- **Auto-hide controls** in fullscreen and when idle for 3 s; any mouse movement brings them back.
- **Auto-reconnect** quietly in the background; only show an error after repeated failures.
- **Remember everything** — last camera, window size/position, panel open/closed, settings.
- **Low battery warning** — toast when phone battery < 20% (only if the phone reports battery).
- **Low disk warning** — before and during recording when free space < 2 GB.
- **Tap-to-focus** — click on the video shows a focus ring animation at that spot.
- **Scroll to zoom** — mouse wheel over the video changes zoom.
- **Optimistic controls** — toggles update instantly; revert with a toast if the phone rejects the change.
- **Camera-aware controls** — on the front camera, Flashlight and tap-to-focus are disabled (Galaxy A06 front camera has no flash and fixed focus). Controls come from what the phone reports, not hard-coded.
- **Debug overlay** (`Ctrl+D`) — ✅ built. Small mono panel top-right: render FPS, stream FPS, resolution, decoder, source, bitrate, frame age, dropped frames, CPU (% of PC and of one core).

---

## 10. Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Snapshot |
| `R` | Start / stop recording |
| `F` / `F11` / double-click | Fullscreen |
| `Esc` | Exit fullscreen |
| `T` | Flashlight |
| `N` | Night vision |
| `C` | Switch camera |
| `+` / `-` / mouse wheel | Zoom |
| `Tab` | Toggle side panel |
| `Ctrl + ,` | Settings |
| `Ctrl + D` | Debug overlay |
| `V` | Cycle view mode (fit / fill / original) |

---

## 11. Accessibility

- Text contrast ≥ 4.5:1 on all surfaces
- Visible `accent` focus ring for keyboard navigation
- Status never shown by color alone (dot + text label)
- Respects Windows "reduce animations" setting
- Scales correctly at 100–200% Windows display scaling

---

## 12. Implementation Notes (Qt)

- Colors and sizes defined once as tokens in `theme.py`, used to build a single **QSS** stylesheet
- Frameless window with custom title bar; Windows 11 **Mica** backdrop where available
- Overlay controls are separate translucent widgets on top of the `QOpenGLWidget` — never paint over the video texture
- Icons: Lucide SVGs, recolored at runtime to match theme tokens
- App icon + wordmark: `src/camdesk/resources/` (`app.ico` is set as the window/taskbar icon; the wordmark goes on the connect screen)
- Animations via `QPropertyAnimation` (opacity, geometry)
