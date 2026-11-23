"""Pick the best hardware decoder.

Measured on the target PC (MX230 + Intel iGPU) with the phone's 1080p30 H.264 stream:
D3D11VA 5% CPU · DXVA2 8% · software 33% · CUDA fails on this stream (not used).
"""

from __future__ import annotations

import logging

from av.codec.hwaccel import HWAccel, hwdevices_available

log = logging.getLogger(__name__)

PREFERRED = ("d3d11va", "dxva2")
LABELS = {"d3d11va": "D3D11VA (GPU)", "dxva2": "DXVA2 (GPU)", None: "Software (CPU)"}


def candidates() -> list[str | None]:
    """Hardware device types to try, best first, ending with None (= software)."""
    try:
        available = set(hwdevices_available())
    except Exception:  # FFmpeg built without hwaccel support
        log.warning("Could not list hardware decoders; using software decoding")
        available = set()
    return [d for d in PREFERRED if d in available] + [None]


def make(device_type: str | None) -> HWAccel | None:
    """HWAccel for av.open(). Software fallback stays on so odd streams still play."""
    if device_type is None:
        return None
    return HWAccel(device_type=device_type, allow_software_fallback=True)


def label(device_type: str | None, is_hw: bool) -> str:
    return LABELS.get(device_type, device_type or "") if is_hw else LABELS[None]
