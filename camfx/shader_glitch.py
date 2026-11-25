"""LOCKED: Permanent Glitch RGB GLSL shader.

Do not modify, reformat, or remove SHADER_GLITCH without explicit user approval.
"""

SHADER_GLITCH = """#version 100
precision mediump float;
varying vec2 v_texcoord;
uniform sampler2D tex;
uniform float time;
void main() {
    float band = floor(v_texcoord.y * 28.0);
    float pulse = step(0.86, fract(sin(band * 78.233 + floor(time * 9.0) * 19.19) * 43758.5453));
    float jitter = (fract(sin(band * 12.9898 + time * 15.0) * 43758.5453) - 0.5) * 0.06 * pulse;
    float split = 0.007 + 0.012 * abs(sin(time * 3.5)) * pulse;
    vec2 uv = vec2(clamp(v_texcoord.x + jitter, 0.0, 1.0), v_texcoord.y);
    float r = texture2D(tex, vec2(clamp(uv.x + split, 0.0, 1.0), uv.y)).r;
    float g = texture2D(tex, uv).g;
    float b = texture2D(tex, vec2(clamp(uv.x - split, 0.0, 1.0), uv.y)).b;
    float scan = 0.92 + 0.08 * sin(v_texcoord.y * 420.0);
    gl_FragColor = vec4(vec3(r, g, b) * scan, 1.0);
}"""
