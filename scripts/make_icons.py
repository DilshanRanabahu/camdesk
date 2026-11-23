"""Prepare CamDesk logo assets from the source images.

    uv run python scripts/make_icons.py <icon.png> <wordmark.png>

Writes to src/camdesk/resources/:
- icon.png      1024×1024, transparent outside the rounded square, solid inside
- app.ico       16, 20, 24, 32, 40, 48, 64, 128, 256 px (PNG-compressed entries)
- wordmark.png  "CamDesk" logo cropped to its content with an even margin
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage

RESOURCES = Path(__file__).resolve().parents[1] / "src" / "camdesk" / "resources"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.width(), 4).copy()


def from_array(arr: np.ndarray) -> QImage:
    h, w, _ = arr.shape
    data = np.ascontiguousarray(arr)
    return QImage(data.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def prepare_icon(src: Path) -> QImage:
    arr = to_array(QImage(str(src)))
    alpha = arr[..., 3]
    # AI background removal left the inside ~98% opaque: make it solid, keep soft edges.
    alpha[alpha >= 200] = 255
    alpha[alpha <= 20] = 0  # drop near-invisible specks outside the icon
    ys, xs = np.where(alpha > 0)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    side = max(x1 - x0, y1 - y0)
    pad = round(side * 0.03)
    canvas = np.zeros((side + 2 * pad, side + 2 * pad, 4), np.uint8)
    oy = pad + (side - (y1 - y0)) // 2
    ox = pad + (side - (x1 - x0)) // 2
    canvas[oy : oy + (y1 - y0), ox : ox + (x1 - x0)] = arr[y0:y1, x0:x1]
    return from_array(canvas).scaled(
        1024, 1024, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


def prepare_wordmark(src: Path) -> QImage:
    arr = to_array(QImage(str(src)))
    rgb = arr[..., :3].astype(np.int16)
    background = np.median(arr[:20, :20, :3].reshape(-1, 3), axis=0)
    content = np.abs(rgb - background).sum(axis=2) > 60
    ys, xs = np.where(content)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    pad = round((y1 - y0) * 0.35)  # even margin around the logo
    h, w = arr.shape[:2]
    crop = arr[max(0, y0 - pad) : min(h, y1 + pad), max(0, x0 - pad) : min(w, x1 + pad)]
    return from_array(crop)


def write_ico(icon: QImage, path: Path) -> None:
    images = [
        png_bytes(
            icon.scaled(
                s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        for s in ICO_SIZES
    ]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = io.BytesIO()
    for size, data in zip(ICO_SIZES, images, strict=True):
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries.write(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    path.write_bytes(header + entries.getvalue() + b"".join(images))


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write(__doc__ or "")
        return 2
    _app = QGuiApplication([])
    RESOURCES.mkdir(parents=True, exist_ok=True)
    icon = prepare_icon(Path(sys.argv[1]))
    icon.save(str(RESOURCES / "icon.png"))
    write_ico(icon, RESOURCES / "app.ico")
    wordmark = prepare_wordmark(Path(sys.argv[2]))
    wordmark.save(str(RESOURCES / "wordmark.png"))
    for name in ("icon.png", "app.ico", "wordmark.png"):
        f = RESOURCES / name
        sys.stdout.write(f"{f.relative_to(RESOURCES.parents[2])}  {f.stat().st_size // 1024} KB\n")
    sys.stdout.write(f"wordmark: {wordmark.width()}x{wordmark.height()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
