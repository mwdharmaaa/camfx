"""Studio REC HUD and custom watermark overlay renderer."""

from __future__ import annotations

import math
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from camfx.effects import EFFECTS_BY_ID, get_effect


def render_hud_overlay(
    image: Image.Image,
    *,
    effect_id: str,
    hud_enabled: bool,
    watermark_text: str,
    now_monotonic: float | None = None,
) -> Image.Image:
    """Draw Studio REC HUD brackets, badges, and watermark onto an RGBA frame."""
    watermark = watermark_text.strip()
    if not hud_enabled and not watermark:
        return image

    w, h = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default()

    if hud_enabled:
        pad_px = 18
        arm = 24
        cyan = (56, 189, 248, 225)
        for pts in (
            [(pad_px, pad_px + arm), (pad_px, pad_px), (pad_px + arm, pad_px)],
            [(w - pad_px - arm, pad_px), (w - pad_px, pad_px), (w - pad_px, pad_px + arm)],
            [(pad_px, h - pad_px - arm), (pad_px, h - pad_px), (pad_px + arm, h - pad_px)],
            [(w - pad_px - arm, h - pad_px), (w - pad_px, h - pad_px), (w - pad_px, h - pad_px - arm)],
        ):
            draw.line(pts, fill=cyan, width=3)

        draw.rounded_rectangle([pad_px + 8, pad_px + 8, pad_px + 116, pad_px + 34], radius=6, fill=(15, 20, 30, 185))
        blink_clock = time.monotonic() if now_monotonic is None else now_monotonic
        if math.sin(blink_clock * 4.0) > -0.2:
            draw.ellipse([pad_px + 16, pad_px + 15, pad_px + 28, pad_px + 27], fill=(244, 63, 94, 245))
        draw.text((pad_px + 34, pad_px + 15), "CAMFX LIVE", fill=(241, 245, 249, 245), font=font)

        fx_name = EFFECTS_BY_ID.get(effect_id, get_effect("normal")).name.upper()
        badge_text = f"{fx_name} | {datetime.now().strftime('%H:%M:%S')}"
        bbox = draw.textbbox((0, 0), badge_text, font=font)
        bx = w - pad_px - (bbox[2] - bbox[0]) - 24
        draw.rounded_rectangle([bx, pad_px + 8, w - pad_px - 8, pad_px + 34], radius=6, fill=(15, 20, 30, 185))
        draw.text((bx + 8, pad_px + 15), badge_text, fill=cyan, font=font)

    if watermark:
        wx, wy = 24, h - 34
        draw.text((wx + 1, wy + 1), watermark, fill=(0, 0, 0, 140), font=font)
        draw.text((wx, wy), watermark, fill=(255, 255, 255, 230), font=font)

    return image
