"""V4L2 video device discovery and pipeline configuration contracts."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


@dataclass(frozen=True)
class VideoDevice:
    """Represents a V4L2 physical or virtual video device."""

    path: str
    name: str
    is_virtual: bool


@dataclass
class PipelineConfig:
    """Current camera, effect, adjustment, and output configuration."""

    source: str = "/dev/video0"
    effect_id: str = "normal"
    mirror: bool = True
    brightness: float = 0.0   # -1.0 .. 1.0
    contrast: float = 1.0     # 0.0 .. 2.0
    saturation: float = 1.0   # 0.0 .. 2.0
    hud_enabled: bool = False
    watermark_text: str = ""
    virtual_device: Optional[str] = None
    virtual_cam_enabled: bool = False
    enable_preview: bool = True


def _device_index_number(sys_path: str) -> int:
    base = os.path.basename(sys_path)
    try:
        return int(base.replace("video", ""))
    except ValueError:
        return 999


def _read_sysfs_text(path: str, fallback: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip() or fallback
    except OSError:
        return fallback


def device_supports_mjpeg_640x480(device_path: str) -> bool:
    """Return True when the V4L2 camera exposes image/jpeg at 640x480."""
    if not device_path or device_path == "videotest":
        return False
    target = Gst.Caps.from_string("image/jpeg,width=640,height=480")
    monitor = Gst.DeviceMonitor()
    monitor.add_filter("Video/Source", None)
    if not monitor.start():
        return False
    try:
        for dev in monitor.get_devices():
            props = dev.get_properties()
            v4l2_path = props.get_string("api.v4l2.path") if props else None
            if v4l2_path != device_path:
                continue
            caps = dev.get_caps()
            if caps is not None and caps.can_intersect(target):
                return True
    finally:
        monitor.stop()
    return False


def discover_video_devices() -> Tuple[List[VideoDevice], List[VideoDevice]]:
    """Return (physical_cameras, virtual_cameras) discovered via sysfs."""
    physical: List[VideoDevice] = []
    virtual: List[VideoDevice] = []

    for sys_path in sorted(glob.glob("/sys/class/video4linux/video*"), key=_device_index_number):
        dev_name = os.path.basename(sys_path)
        dev_node = os.path.join("/dev", dev_name)
        if not os.path.exists(dev_node):
            continue

        name = _read_sysfs_text(os.path.join(sys_path, "name"), dev_name)
        real_sys = os.path.realpath(sys_path)
        is_virtual = (
            "/devices/virtual/" in real_sys
            or "loopback" in name.lower()
            or "camfx" in name.lower()
        )
        if is_virtual:
            virtual.append(VideoDevice(path=dev_node, name=name, is_virtual=True))
            continue

        # USB webcams often expose index 0 (capture) and index 1 (metadata only).
        index_val = _read_sysfs_text(os.path.join(sys_path, "index"), "0")
        if index_val == "0":
            physical.append(VideoDevice(path=dev_node, name=name, is_virtual=False))

    return physical, virtual
