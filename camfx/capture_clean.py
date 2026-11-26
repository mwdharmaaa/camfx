"""Dedicated clean capture pipeline builder for Scanline Glitch OFF mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

# Prefer full-sensor 4:3 MJPEG resolutions downscaled cleanly to 640x480.
PREFERRED_4_3_MJPEG_SIZES: tuple[tuple[int, int], ...] = (
    (1600, 1200),
    (800, 600),
    (640, 480),
)


@dataclass(frozen=True)
class CleanSourceProfile:
    """Resolved PipeWire node and MJPEG resolution capabilities for clean capture."""

    pipewire_target: Optional[str] = None
    mjpeg_size: Optional[Tuple[int, int]] = None


def _ensure_gst_init() -> None:
    if not Gst.is_initialized():
        Gst.init(None)


def _best_mjpeg_size(caps: Optional[Gst.Caps]) -> Optional[Tuple[int, int]]:
    if caps is None:
        return None
    for width, height in PREFERRED_4_3_MJPEG_SIZES:
        target = Gst.Caps.from_string(f"image/jpeg,width={width},height={height}")
        if caps.can_intersect(target):
            return (width, height)
    return None


def probe_clean_source(device_path: str) -> CleanSourceProfile:
    """Discover PipeWire target and best 4:3 MJPEG size for a V4L2 camera path."""
    _ensure_gst_init()
    if not device_path or device_path == "videotest":
        return CleanSourceProfile()

    monitor = Gst.DeviceMonitor()
    monitor.add_filter("Video/Source", None)
    if not monitor.start():
        return CleanSourceProfile()

    pw_target: Optional[str] = None
    pw_mjpeg: Optional[Tuple[int, int]] = None
    v4l2_mjpeg: Optional[Tuple[int, int]] = None
    try:
        for dev in monitor.get_devices():
            props = dev.get_properties()
            if props is None:
                continue
            v4l2_path = props.get_string("api.v4l2.path") or props.get_string("device.path")
            if v4l2_path != device_path:
                continue
            caps = dev.get_caps()
            if "PipeWire" in type(dev).__name__:
                pw_target = props.get_string("node.name") or props.get_string("object.serial")
                pw_mjpeg = _best_mjpeg_size(caps)
            elif v4l2_mjpeg is None:
                v4l2_mjpeg = _best_mjpeg_size(caps)
    finally:
        monitor.stop()

    return CleanSourceProfile(
        pipewire_target=pw_target,
        mjpeg_size=pw_mjpeg or v4l2_mjpeg,
    )


def build_clean_capture_stage(
    device_path: str,
    *,
    profile: Optional[CleanSourceProfile] = None,
    has_pipewiresrc: Optional[bool] = None,
    has_jpegdec: Optional[bool] = None,
    has_deinterlace: Optional[bool] = None,
) -> str:
    """Build the isolated glitch-free capture pipeline stage for Scanline Glitch OFF."""
    _ensure_gst_init()
    resolved = profile if profile is not None else probe_clean_source(device_path)
    pw_ok = has_pipewiresrc if has_pipewiresrc is not None else (Gst.ElementFactory.find("pipewiresrc") is not None)
    jpeg_ok = has_jpegdec if has_jpegdec is not None else (Gst.ElementFactory.find("jpegdec") is not None)
    deint_ok = has_deinterlace if has_deinterlace is not None else (Gst.ElementFactory.find("deinterlace") is not None)

    if pw_ok and resolved.pipewire_target:
        source_el = f"pipewiresrc target-object={resolved.pipewire_target} always-copy=true"
    else:
        source_el = f"v4l2src device={device_path}"

    stages = [source_el]
    if jpeg_ok and resolved.mjpeg_size is not None:
        w, h = resolved.mjpeg_size
        stages.extend(
            [
                f"image/jpeg,width={w},height={h}",
                "queue max-size-buffers=2 leaky=downstream",
                "jpegdec",
            ]
        )
    else:
        stages.append("queue max-size-buffers=2 leaky=downstream")

    stages.extend(["videoconvert", "videoscale method=bilinear", "video/x-raw,width=640,height=480"])
    if deint_ok:
        stages.extend(["videoconvert", "deinterlace mode=interlaced fields=top method=linear"])
    return " ! ".join(stages)
