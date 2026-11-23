"""The VideoSource interface. RTSP, MJPEG and the fake source all implement it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from typing import Any

from camdesk.core.frames import VideoFrame

# read() yields decoded frames and, for sources that have them, raw compressed packets
# (av.Packet) for the recorder. Consumers check the type.
SourceItem = VideoFrame | Any
SourceFactory = Callable[[], "VideoSource"]


class VideoSource(ABC):
    """A one-shot connection to a video stream. Create a new one to reconnect."""

    #: "rtsp", "mjpeg" or "fake" — shown in the status bar / debug overlay
    transport: str = ""

    @property
    def decoder(self) -> str:
        """Human-readable decoder in use, e.g. "D3D11VA (GPU)". Valid after the first frame."""
        return ""

    @abstractmethod
    def open(self) -> None:
        """Connect. Raises StreamError on failure."""

    @abstractmethod
    def read(self) -> Iterator[SourceItem]:
        """Yield frames/packets until the stream ends (returns) or breaks (raises StreamError)."""

    @abstractmethod
    def close(self) -> None:
        """Release everything. Safe to call more than once, from the reading thread."""
