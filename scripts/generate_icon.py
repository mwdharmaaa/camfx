#!/usr/bin/env python3
"""Generate CamFX application icons in standard PNG sizes."""

import math
import os
from PIL import Image, ImageDraw


def generate_camfx_icon(output_dir: str | None = None) -> None:
    """Create a 512x512 master icon and resized variants for Debian desktop integration."""
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded dark studio slate background (matches dark aesthetic like Commanda)
    margin = 24
    radius = 104
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=(18, 20, 28, 255),
        outline=(56, 189, 248, 220),
        width=10,
    )

    # Subtle inner camera body ring
    cx, cy = size // 2, size // 2
    outer_r = 148
    draw.ellipse(
        [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
        fill=(28, 32, 46, 255),
        outline=(99, 102, 241, 255),
        width=12,
    )

    # Lens gradient-like concentric rings
    mid_r = 102
    draw.ellipse(
        [cx - mid_r, cy - mid_r, cx + mid_r, cy + mid_r],
        fill=(15, 23, 42, 255),
        outline=(34, 211, 238, 255),
        width=8,
    )

    inner_r = 52
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill=(56, 189, 248, 255),
    )

    # Lens specular highlight
    draw.ellipse([cx - 32, cy - 34, cx - 6, cy - 8], fill=(224, 242, 254, 230))

    # Recording / FX status dot at top-right of lens housing
    dot_x, dot_y, dot_r = cx + 126, cy - 126, 20
    draw.ellipse(
        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
        fill=(244, 63, 94, 255),
        outline=(18, 20, 28, 255),
        width=4,
    )

    # FX four-point sparkle at bottom-left
    sx, sy, sr = cx - 124, cy + 122, 26
    points = []
    for i in range(8):
        angle = i * (math.pi / 4.0)
        r = sr if i % 2 == 0 else sr * 0.36
        points.append((sx + r * math.cos(angle), sy + r * math.sin(angle)))
    draw.polygon(points, fill=(250, 204, 21, 255))

    assets_dir = output_dir or os.path.join(os.path.dirname(__file__), "..", "assets", "logo")
    os.makedirs(assets_dir, exist_ok=True)

    master_path = os.path.join(assets_dir, "logo.png")
    img.save(master_path, "PNG")
    print(f"Saved: {master_path} ({size}x{size})")

    for s in [256, 128, 64, 48, 32, 16]:
        resized = img.resize((s, s), Image.Resampling.LANCZOS)
        resized.save(os.path.join(assets_dir, f"logo-{s}.png"), "PNG")


if __name__ == "__main__":
    generate_camfx_icon()
