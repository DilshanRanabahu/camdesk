"""GLSL shaders: draw a frame as a textured quad, converting YUV → RGB on the GPU.

Converting on the GPU (not with NumPy/FFmpeg on the CPU) is the single biggest CPU saving
for video in Python. Both decoder outputs are supported:
- NV12   (GPU decoders): texY = Y,  texU = interleaved UV (RG texture)
- YUV420P (software):    texY = Y,  texU = U, texV = V
"""

from __future__ import annotations

VERTEX = """
#version 330 core
// Full-screen quad from gl_VertexID (no vertex buffer needed), triangle strip order.
uniform vec2 scale;   // fraction of the viewport the picture covers (aspect fit/fill)
out vec2 uv;
void main() {
    vec2 corner = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1));
    uv = vec2(corner.x, 1.0 - corner.y);  // image row 0 is the top
    gl_Position = vec4((corner * 2.0 - 1.0) * scale, 0.0, 1.0);
}
"""

FRAGMENT = """
#version 330 core
in vec2 uv;
out vec4 color;
uniform sampler2D texY;
uniform sampler2D texU;
uniform sampler2D texV;
uniform int nv12;          // 1 = NV12 (UV interleaved in texU.rg), 0 = YUV420P
uniform int fullRange;     // 1 = JPEG/full range (0–255), 0 = TV/limited range (16–235)
uniform mat3 yuvToRgb;     // BT.601 or BT.709 matrix

void main() {
    float y = texture(texY, uv).r;
    vec2 c = nv12 == 1 ? texture(texU, uv).rg : vec2(texture(texU, uv).r, texture(texV, uv).r);
    if (fullRange == 0) {
        y = (y - 16.0 / 255.0) * (255.0 / 219.0);
        c = (c - 128.0 / 255.0) * (255.0 / 224.0);
    } else {
        c = c - 128.0 / 255.0;
    }
    color = vec4(clamp(yuvToRgb * vec3(y, c), 0.0, 1.0), 1.0);
}
"""

# Column-major (as OpenGL expects) matrices mapping (Y, Cb, Cr) → (R, G, B).
BT601 = (
    1.0, 1.0, 1.0,
    0.0, -0.344136, 1.772,
    1.402, -0.714136, 0.0,
)  # fmt: skip
BT709 = (
    1.0, 1.0, 1.0,
    0.0, -0.187324, 1.8556,
    1.5748, -0.468124, 0.0,
)  # fmt: skip
