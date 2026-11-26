"""GStreamer launch pipeline builder and HUD buffer probe helpers."""

from __future__ import annotations

import os

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst
from PIL import Image

from camfx.capture_clean import CleanSourceProfile, build_clean_capture_stage
from camfx.devices import PipelineConfig
from camfx.effects import get_effect
from camfx.hud import render_hud_overlay


def build_pipeline_string(
    cfg: PipelineConfig,
    *,
    clean_profile: CleanSourceProfile | None = None,
    use_mjpeg: bool | None = None,
) -> str:
    """Build the GStreamer launch description string for a given PipelineConfig."""
    if cfg.source == "videotest" or not os.path.exists(cfg.source):
        src_stage = "videotestsrc is-live=true pattern=smpte ! video/x-raw,width=640,height=480,framerate=30/1"
    elif cfg.scanline_glitch:
        # LOCKED: Preserve raw v4l2src capture pipeline when Scanline Glitch is ON.
        src_stage = f"v4l2src device={cfg.source} ! videoconvert ! videoscale ! video/x-raw,width=640,height=480"
    else:
        # Separate clean capture backend (PipeWire HD MJPEG + bilinear downscale + deinterlace).
        override_profile = clean_profile
        if override_profile is None and use_mjpeg is not None:
            override_profile = CleanSourceProfile(mjpeg_size=(640, 480) if use_mjpeg else None)
        src_stage = build_clean_capture_stage(cfg.source, profile=override_profile)

    flip_method = "horizontal-flip" if cfg.mirror else "none"
    stages = [src_stage, "videoconvert", f"videoflip name=flip method={flip_method}"]

    effect = get_effect(cfg.effect_id)
    if effect.kind == "gl_builtin":
        stages.extend(["glupload", effect.element, "gldownload"])
    elif effect.kind == "gl_shader":
        stages.extend(["glupload", "glshader name=fx_shader", "gldownload"])
    elif effect.kind == "effectv":
        stages.extend(["videoconvert", effect.element, "videoconvert"])

    balance = (
        f"videobalance name=balance brightness={cfg.brightness:.3f} "
        f"contrast={cfg.contrast:.3f} saturation={cfg.saturation:.3f}"
    )
    # Strip uninitialized/zeroed padding alpha (e.g. EffecTV RGBx, gleffects_sin) so GTK4/PNG render opaque.
    stages.extend(
        [
            "videoconvert",
            balance,
            "videoconvert",
            "video/x-raw,format=RGB",
            "videoconvert",
            "video/x-raw,format=RGBA",
            "identity name=hud_pad",
            "tee name=t",
        ]
    )
    pipeline_str = " ! ".join(stages)

    if cfg.enable_preview:
        pipeline_str += (
            " t. ! queue leaky=downstream max-size-buffers=2 ! videoconvert ! video/x-raw,format=RGBA "
            "! appsink name=preview_sink emit-signals=true max-buffers=1 drop=true sync=false"
        )
    if cfg.virtual_cam_enabled and cfg.virtual_device and os.path.exists(cfg.virtual_device):
        pipeline_str += (
            " t. ! queue leaky=downstream max-size-buffers=2 ! videoconvert ! video/x-raw,format=YUY2 "
            f"! v4l2sink name=vsink device={cfg.virtual_device} sync=false"
        )
    return pipeline_str


def apply_hud_probe(pad: Gst.Pad, info: Gst.PadProbeInfo, cfg: PipelineConfig) -> Gst.PadProbeReturn:
    """Apply Studio REC HUD and watermark onto the GStreamer pad buffer."""
    if not cfg.hud_enabled and not cfg.watermark_text.strip():
        return Gst.PadProbeReturn.OK
    caps = pad.get_current_caps()
    buf = info.get_buffer()
    if caps is None or buf is None:
        return Gst.PadProbeReturn.OK
    struct = caps.get_structure(0)
    w, h = int(struct.get_value("width")), int(struct.get_value("height"))
    ok, map_info = buf.map(Gst.MapFlags.READ)
    if not ok:
        return Gst.PadProbeReturn.OK
    try:
        img = Image.frombytes("RGBA", (w, h), bytes(map_info.data))
    finally:
        buf.unmap(map_info)

    render_hud_overlay(
        img,
        effect_id=cfg.effect_id,
        hud_enabled=cfg.hud_enabled,
        watermark_text=cfg.watermark_text,
    )
    new_buf = Gst.Buffer.new_wrapped(img.tobytes())
    new_buf.pts, new_buf.dts, new_buf.duration = buf.pts, buf.dts, buf.duration
    info.set_buffer(new_buf)
    return Gst.PadProbeReturn.OK
