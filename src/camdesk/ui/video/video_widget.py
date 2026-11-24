"""VideoWidget — draws frames from the LatestFrameBuffer with OpenGL.

Per frame the UI thread only: takes the newest frame, uploads its planes as textures
(glTexSubImage2D, padding skipped with GL_UNPACK_ROW_LENGTH), and draws one quad.
YUV → RGB happens in the shader. Overlays are separate child widgets.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QMatrix3x3, QMouseEvent
from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QWidget

from camdesk.core.frames import NV12, LatestFrameBuffer, VideoFrame
from camdesk.ui.theme import tokens
from camdesk.ui.video import shaders
from camdesk.utils.timing import RateCounter

log = logging.getLogger(__name__)

# OpenGL constants (PySide6's QOpenGLFunctions takes plain ints)
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE0 = 0x84C0
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_LINEAR = 0x2601
GL_CLAMP_TO_EDGE = 0x812F
GL_UNPACK_ALIGNMENT = 0x0CF5
GL_UNPACK_ROW_LENGTH = 0x0CF2
GL_R8 = 0x8229
GL_RG8 = 0x822B
GL_RED = 0x1903
GL_RG = 0x8227
GL_UNSIGNED_BYTE = 0x1401
GL_COLOR_BUFFER_BIT = 0x4000
GL_TRIANGLE_STRIP = 0x0005

WATCHDOG_MS = 100


def _qmatrix(column_major: tuple[float, ...]) -> QMatrix3x3:
    """QMatrix3x3's constructor is row-major; the shader constants are column-major."""
    return QMatrix3x3(list(np.array(column_major, np.float32).reshape(3, 3).T.flatten()))


_MATRIX_601 = _qmatrix(shaders.BT601)
_MATRIX_709 = _qmatrix(shaders.BT709)


class ViewMode(Enum):
    FIT = "fit"  # whole picture visible, letterboxed
    FILL = "fill"  # fills the widget, edges cropped
    ORIGINAL = "original"  # 1 video pixel = 1 screen pixel


class VideoWidget(QOpenGLWidget):
    double_clicked = Signal()
    #: single click on the picture: (x, y) in 0–1 of the shown picture, and the widget point
    picture_clicked = Signal(float, float, QPoint)

    def __init__(self, buffer: LatestFrameBuffer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.buffer = buffer
        self.view_mode = ViewMode.FIT
        self.render_fps = RateCounter()
        self.last_frame_age_ms: float | None = None
        self.frames_drawn = 0
        self.gl_renderer = ""
        self._program: QOpenGLShaderProgram | None = None
        self._vao: QOpenGLVertexArrayObject | None = None
        self._textures = np.zeros(3, dtype=np.uintc)
        self._tex_shape: tuple[int, int, str] | None = None  # (w, h, format) allocated
        self._frame_info: tuple[int, int, str, bool, bool] | None = None
        self.setMinimumSize(320, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.first_frame_at: float | None = None
        # Safety net: frame_ready is sent once per *taken* frame. If a repaint request is
        # ever dropped (e.g. before the widget is exposed), nobody takes the frame and no new
        # signal comes. The watchdog notices a waiting frame and repaints.
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(WATCHDOG_MS)
        self._watchdog.timeout.connect(self._check_stalled)
        self._watchdog.start()
        self._pending_click: QPoint | None = None
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._emit_single_click)

    # -- public ------------------------------------------------------------

    @Slot()
    def on_frame_ready(self) -> None:
        """Connected to StreamService.frame_ready; schedules a repaint (vsync-paced)."""
        self.update()

    def set_view_mode(self, mode: ViewMode) -> None:
        self.view_mode = mode
        self.update()

    def clear(self) -> None:
        """Forget the current picture (e.g. after disconnect)."""
        self._frame_info = None
        self.update()

    @property
    def has_frame(self) -> bool:
        return self._frame_info is not None

    def _check_stalled(self) -> None:
        if self.buffer.has_new:
            self.update()

    def picture_point(self, pos: QPointF | QPoint) -> tuple[float, float] | None:
        """Widget position → (x, y) in 0–1 of the picture, or None outside it (letterbox)."""
        if self._frame_info is None:
            return None
        width, height = self._frame_info[0], self._frame_info[1]
        sx, sy = self._quad_scale(width, height)
        # The quad covers sx/sy of the -1…1 viewport, centered.
        nx = (pos.x() / max(1, self.width()) * 2 - 1) / sx
        ny = (pos.y() / max(1, self.height()) * 2 - 1) / sy
        px, py = (nx + 1) / 2, (ny + 1) / 2
        if not (0.0 <= px <= 1.0 and 0.0 <= py <= 1.0):
            return None
        return px, py

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # Wait out the double-click interval: a double click means fullscreen, not focus.
            self._pending_click = event.position().toPoint()
            self._click_timer.start(QApplication.doubleClickInterval())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: object) -> None:  # noqa: N802
        self._click_timer.stop()
        self._pending_click = None
        self.double_clicked.emit()

    def _emit_single_click(self) -> None:
        pos, self._pending_click = self._pending_click, None
        if pos is None:
            return
        point = self.picture_point(pos)
        if point is not None:
            self.picture_clicked.emit(point[0], point[1], pos)

    # -- OpenGL ------------------------------------------------------------

    def initializeGL(self) -> None:  # noqa: N802
        f = self.context().functions()
        self.gl_renderer = str(f.glGetString(0x1F01) or "")  # GL_RENDERER
        log.info("OpenGL renderer: %s", self.gl_renderer)

        program = QOpenGLShaderProgram(self)
        ok = program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, shaders.VERTEX)
        ok = ok and program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, shaders.FRAGMENT
        )
        if not ok or not program.link():
            log.error("Video shader failed: %s", program.log())
            return
        self._program = program
        self._vao = QOpenGLVertexArrayObject(self)
        self._vao.create()

        f.glGenTextures(3, self._textures)
        for tex in self._textures:
            f.glBindTexture(GL_TEXTURE_2D, int(tex))
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        self._tex_shape = None

    def paintGL(self) -> None:  # noqa: N802
        f = self.context().functions()
        r, g, b = tokens.hex_to_rgb_f(tokens.VIDEO_LETTERBOX)
        f.glClearColor(r, g, b, 1.0)
        f.glClear(GL_COLOR_BUFFER_BIT)
        if self._program is None:
            return

        frame = self.buffer.take()
        if frame is not None:
            self._upload(frame)
            self.render_fps.add()
            self.frames_drawn += 1
            if self.first_frame_at is None:
                self.first_frame_at = time.perf_counter()
                log.info("First frame on screen")
            self.last_frame_age_ms = (time.perf_counter() - frame.received_at) * 1000
        if self._frame_info is None:
            return

        width, height, fmt, full_range, bt709 = self._frame_info
        program = self._program
        program.bind()
        program.setUniformValue("scale", *self._quad_scale(width, height))
        program.setUniformValue1i("texY", 0)
        program.setUniformValue1i("texU", 1)
        program.setUniformValue1i("texV", 2)
        program.setUniformValue1i("nv12", 1 if fmt == NV12 else 0)
        program.setUniformValue1i("fullRange", 1 if full_range else 0)
        # NB: setUniformValueArray(…, 1, 9) silently uploads nothing for a mat3 in PySide6
        # (everything renders black) — a QMatrix3x3 works.
        program.setUniformValue("yuvToRgb", _MATRIX_709 if bt709 else _MATRIX_601)
        for unit, tex in enumerate(self._textures):
            f.glActiveTexture(GL_TEXTURE0 + unit)
            f.glBindTexture(GL_TEXTURE_2D, int(tex))
        self._vao.bind()
        f.glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        self._vao.release()
        program.release()

    # -- helpers -------------------------------------------------------------

    def _upload(self, frame: VideoFrame) -> None:
        f = self.context().functions()
        nv12 = frame.format == NV12
        # (texture index, plane index, bytes per texel, GL internal format, GL format)
        layout = (
            [(0, 0, 1, GL_R8, GL_RED), (1, 1, 2, GL_RG8, GL_RG)]
            if nv12
            else [(0, 0, 1, GL_R8, GL_RED), (1, 1, 1, GL_R8, GL_RED), (2, 2, 1, GL_R8, GL_RED)]
        )
        shape = (frame.width, frame.height, frame.format)
        allocate = shape != self._tex_shape
        f.glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        for tex_i, plane_i, bpp, internal, gl_format in layout:
            plane = frame.planes[plane_i]
            w = frame.row_bytes(plane_i) // bpp
            h = frame.plane_height(plane_i)
            data = plane if plane.flags["C_CONTIGUOUS"] else np.ascontiguousarray(plane)
            f.glPixelStorei(GL_UNPACK_ROW_LENGTH, data.shape[1] // bpp)  # skip row padding
            f.glActiveTexture(GL_TEXTURE0 + tex_i)
            f.glBindTexture(GL_TEXTURE_2D, int(self._textures[tex_i]))
            if allocate:
                f.glTexImage2D(
                    GL_TEXTURE_2D, 0, internal, w, h, 0, gl_format, GL_UNSIGNED_BYTE, data
                )
            else:
                f.glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, gl_format, GL_UNSIGNED_BYTE, data)
        f.glPixelStorei(GL_UNPACK_ROW_LENGTH, 0)
        if allocate:
            self._tex_shape = shape
            log.info("Video textures: %dx%d %s", *shape)
        self._frame_info = (frame.width, frame.height, frame.format, frame.full_range, frame.bt709)

    def _quad_scale(self, video_w: int, video_h: int) -> tuple[float, float]:
        """How much of the viewport (−1…1) the picture covers on each axis."""
        ratio = self.devicePixelRatioF()
        view_w, view_h = max(1.0, self.width() * ratio), max(1.0, self.height() * ratio)
        if self.view_mode is ViewMode.ORIGINAL:
            return video_w / view_w, video_h / view_h
        video_aspect = video_w / max(1, video_h)
        view_aspect = view_w / view_h
        if (video_aspect > view_aspect) == (self.view_mode is ViewMode.FIT):
            return 1.0, view_aspect / video_aspect
        return video_aspect / view_aspect, 1.0
