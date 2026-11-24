"""Map between what the user sees and the camera's own coordinates. Pure functions."""

from __future__ import annotations

# Clockwise order of IP Webcam's orientation values (as the rotate buttons step through them).
ORIENTATIONS = ("landscape", "portrait", "upsidedown", "upsidedown_portrait")


def rotate_orientation(current: str, steps: int, available: tuple[str, ...] = ()) -> str:
    """Next orientation after rotating `steps` quarter turns (+1 clockwise, -1 counter)."""
    order = [o for o in ORIENTATIONS if not available or o in available] or list(ORIENTATIONS)
    index = order.index(current) if current in order else 0
    return order[(index + steps) % len(order)]


def toggle_flip_mode(current: str, part: str) -> str:
    """Turn "mirror" or "flip" on/off inside IP Webcam's mirror_flip value."""
    parts = {p for p in current.split(",") if p in ("mirror", "flip")}
    parts ^= {part}
    return ",".join(p for p in ("mirror", "flip") if p in parts) or "none"


def focus_point(nx: float, ny: float, orientation: str, mirror_flip: str) -> tuple[int, int]:
    """Clicked point on the shown picture (0–1, origin top-left) → camera focus coordinates.

    The phone rotates/mirrors the picture before sending it, so undo that to get back to the
    sensor's landscape frame, then scale to Android's -1000…1000 focus-area range.
    Landscape is exact; the rotated cases follow IP Webcam's clockwise order (best effort).
    """
    if "mirror" in mirror_flip:
        nx = 1 - nx
    if "flip" in mirror_flip:
        ny = 1 - ny
    if orientation == "portrait":
        nx, ny = ny, 1 - nx
    elif orientation == "upsidedown":
        nx, ny = 1 - nx, 1 - ny
    elif orientation == "upsidedown_portrait":
        nx, ny = 1 - ny, nx
    return round(nx * 2000 - 1000), round(ny * 2000 - 1000)
