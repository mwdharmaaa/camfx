"""GLSL fragment shaders for real-time OpenGL GStreamer camera effects."""

SHADER_CINEMA_WARM = """#version 100
precision mediump float;
varying vec2 v_texcoord;
uniform sampler2D tex;
void main() {
    vec4 c = texture2D(tex, v_texcoord);
    float luma = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    vec3 shadows = vec3(0.06, 0.16, 0.22);
    vec3 highlights = vec3(1.06, 0.94, 0.80);
    vec3 graded = mix(c.rgb * (1.0 - 0.18) + shadows * 0.18, c.rgb * highlights, smoothstep(0.2, 0.85, luma));
    graded = clamp((graded - 0.5) * 1.12 + 0.5, 0.0, 1.0);
    vec2 d = v_texcoord - 0.5;
    float vig = smoothstep(0.85, 0.25, dot(d, d));
    gl_FragColor = vec4(graded * mix(0.62, 1.0, vig), c.a);
}"""

SHADER_CYBERPUNK = """#version 100
precision mediump float;
varying vec2 v_texcoord;
uniform sampler2D tex;
uniform float time;
void main() {
    vec2 off = vec2(0.0025, 0.0);
    float r = texture2D(tex, clamp(v_texcoord + off, 0.0, 1.0)).r;
    float g = texture2D(tex, v_texcoord).g;
    float b = texture2D(tex, clamp(v_texcoord - off, 0.0, 1.0)).b;
    vec3 col = vec3(r, g, b);
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    vec3 shadowTint = vec3(0.06, 0.24, 0.42);
    vec3 highTint = vec3(0.95, 0.18, 0.72);
    vec3 neon = mix(col + shadowTint * (1.0 - luma) * 0.45, col * 0.7 + highTint * 0.55, smoothstep(0.35, 0.9, luma));
    float scan = 0.95 + 0.05 * sin(v_texcoord.y * 360.0 + time * 4.0);
    gl_FragColor = vec4(clamp(neon * scan, 0.0, 1.0), 1.0);
}"""

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

SHADER_CRT = """#version 100
precision mediump float;
varying vec2 v_texcoord;
uniform sampler2D tex;
void main() {
    vec2 uv = v_texcoord * 2.0 - 1.0;
    uv *= 1.0 + 0.08 * dot(uv, uv);
    uv = uv * 0.5 + 0.5;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        gl_FragColor = vec4(0.02, 0.02, 0.03, 1.0);
        return;
    }
    vec2 px = vec2(0.002, 0.0);
    float r = texture2D(tex, clamp(uv + px, 0.0, 1.0)).r;
    float g = texture2D(tex, uv).g;
    float b = texture2D(tex, clamp(uv - px, 0.0, 1.0)).b;
    float scan = 0.82 + 0.18 * sin(uv.y * 480.0);
    vec2 d = uv - 0.5;
    float vig = smoothstep(0.85, 0.2, dot(d, d));
    gl_FragColor = vec4(vec3(r, g, b) * scan * mix(0.55, 1.0, vig), 1.0);
}"""

SHADER_PIXELATE = """#version 100
precision mediump float;
varying vec2 v_texcoord;
uniform sampler2D tex;
void main() {
    vec2 grid = vec2(80.0, 60.0);
    vec2 uv = (floor(v_texcoord * grid) + 0.5) / grid;
    vec3 col = texture2D(tex, uv).rgb;
    col = floor(col * 8.0 + 0.5) / 8.0;
    gl_FragColor = vec4(col, 1.0);
}"""

SHADER_NIGHT_VISION = """#version 100
precision mediump float;
varying vec2 v_texcoord;
uniform sampler2D tex;
uniform float time;
void main() {
    vec3 col = texture2D(tex, v_texcoord).rgb;
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    float noise = (fract(sin(dot(v_texcoord * (1.0 + fract(time)), vec2(12.9898, 78.233))) * 43758.5453) - 0.5) * 0.12;
    float boosted = clamp(pow(luma, 0.78) * 1.25 + noise, 0.0, 1.0);
    vec2 d = v_texcoord - 0.5;
    float vig = smoothstep(0.75, 0.18, dot(d, d));
    vec3 green = vec3(boosted * 0.25, boosted * 1.0, boosted * 0.35) * mix(0.35, 1.0, vig);
    gl_FragColor = vec4(clamp(green, 0.0, 1.0), 1.0);
}"""
