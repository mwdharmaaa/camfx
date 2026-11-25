"""Effect catalog definitions and lookup helpers for CamFX."""

from dataclasses import dataclass
from typing import Dict, List

from camfx.shaders import (
    SHADER_CINEMA_WARM,
    SHADER_CRT,
    SHADER_CYBERPUNK,
    SHADER_GLITCH,
    SHADER_NIGHT_VISION,
    SHADER_PIXELATE,
)


@dataclass(frozen=True)
class EffectSpec:
    """Declarative specification for a real-time camera effect."""

    id: str
    name: str
    category: str
    description: str
    kind: str  # "none" | "gl_builtin" | "gl_shader" | "effectv"
    element: str = ""
    fragment: str = ""


EFFECTS: List[EffectSpec] = [
    EffectSpec("normal", "Normal", "Color & Cinema", "Original camera feed without color filters", "none"),
    EffectSpec("cinema_warm", "Cinema Warm", "Color & Cinema", "Cinematic teal and orange grading with vignette", "gl_shader", fragment=SHADER_CINEMA_WARM),
    EffectSpec("cyberpunk", "Cyberpunk Neon", "Color & Cinema", "Futuristic cyan-magenta tone with scanlines", "gl_shader", fragment=SHADER_CYBERPUNK),
    EffectSpec("noir", "Noir Sin City", "Color & Cinema", "High-contrast monochrome with red highlights", "gl_builtin", element="gleffects_sin"),
    EffectSpec("sepia", "Vintage Sepia", "Color & Cinema", "Warm classic brown film tone", "gl_builtin", element="gleffects_sepia"),
    EffectSpec("xpro", "Cross Process", "Color & Cinema", "Analog X-Pro high-contrast film look", "gl_builtin", element="gleffects_xpro"),
    EffectSpec("dream_glow", "Soft Glow", "Color & Cinema", "Soft studio bloom lighting effect", "gl_builtin", element="gleffects_glow"),
    EffectSpec("blur", "Soft Blur", "Color & Cinema", "Smooth full-frame Gaussian blur", "gl_builtin", element="gleffects_blur"),
    EffectSpec("glitch", "Glitch RGB", "Retro & Stylize", "Animated chromatic aberration and band glitch", "gl_shader", fragment=SHADER_GLITCH),
    EffectSpec("crt", "Retro CRT", "Retro & Stylize", "Curved CRT monitor with scanlines", "gl_shader", fragment=SHADER_CRT),
    EffectSpec("pixelate", "Pixel 8-Bit", "Retro & Stylize", "Retro mosaic pixels with color quantization", "gl_shader", fragment=SHADER_PIXELATE),
    EffectSpec("aging", "Old Film 1920s", "Retro & Stylize", "Vintage film grain, dust, and vertical scratches", "effectv", element="agingtv"),
    EffectSpec("night_vision", "Night Vision", "Art & Vision", "Green phosphor night-vision sensor simulation", "gl_shader", fragment=SHADER_NIGHT_VISION),
    EffectSpec("thermal", "Thermal Heat", "Art & Vision", "Infrared thermal heat-map simulation", "gl_builtin", element="gleffects_heat"),
    EffectSpec("xray", "X-Ray Negative", "Art & Vision", "Glowing inverted X-ray negative", "gl_builtin", element="gleffects_xray"),
    EffectSpec("neon_edge", "Neon Edge", "Art & Vision", "Illuminated contour edge detection", "effectv", element="edgetv"),
    EffectSpec("sketch", "Sketch Outline", "Art & Vision", "Laplacian edge-detection pencil sketch", "gl_builtin", element="gleffects_laplacian"),
    EffectSpec("fisheye", "Fisheye Lens", "Lens & Fun", "Wide-angle convex fisheye lens distortion", "gl_builtin", element="gleffects_fisheye"),
    EffectSpec("bulge", "Bulge Zoom", "Lens & Fun", "Center-frame convex bulge magnification", "gl_builtin", element="gleffects_bulge"),
    EffectSpec("twirl", "Twirl Vortex", "Lens & Fun", "Spiral vortex distortion around the center", "gl_builtin", element="gleffects_twirl"),
    EffectSpec("tunnel", "Light Tunnel", "Lens & Fun", "Circular kaleidoscope light tunnel", "gl_builtin", element="gleffects_tunnel"),
    EffectSpec("mirror_split", "Mirror Split", "Lens & Fun", "Vertical center symmetry mirror", "gl_builtin", element="gleffects_mirror"),
    EffectSpec("warp", "Warp Wave", "Lens & Fun", "Animated liquid wave distortion", "effectv", element="warptv"),
    EffectSpec("vertigo", "Vertigo Echo", "Lens & Fun", "Rotating motion-trail echo effect", "effectv", element="vertigotv"),
]

EFFECTS_BY_ID: Dict[str, EffectSpec] = {spec.id: spec for spec in EFFECTS}


def get_effect(effect_id: str) -> EffectSpec:
    """Return an EffectSpec by ID, falling back to 'normal'."""
    return EFFECTS_BY_ID.get(effect_id, EFFECTS_BY_ID["normal"])


def list_categories() -> List[str]:
    """Return ordered unique effect categories."""
    seen: List[str] = []
    for spec in EFFECTS:
        if spec.category not in seen:
            seen.append(spec.category)
    return seen
