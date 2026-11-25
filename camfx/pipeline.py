"""GStreamer real-time camera effects and v4l2loopback virtual camera pipeline."""

from __future__ import annotations

import glob
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gst
from PIL import Image, ImageDraw, ImageFont

from camfx.effects import EFFECTS_BY_ID, EffectSpec, get_effect

Gst.init(None)


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


def discover_video_devices() -> Tuple[List[VideoDevice], List[VideoDevice]]:
    """Return (physical_cameras, virtual_cameras) discovered via sysfs."""
    physical: List[VideoDevice] = []
    virtual: List[VideoDevice] = []

    def _dev_num(sys_path: str) -> int:
        base = os.path.basename(sys_path)
        try:
            return int(base.replace("video", ""))
        except ValueError:
            return 999

    for sys_path in sorted(glob.glob("/sys/class/video4linux/video*"), key=_dev_num):
        dev_name_file = os.path.join(sys_path, "name")
        dev_index_file = os.path.join(sys_path, "index")
        dev_node = os.path.join("/dev", os.path.basename(sys_path))
        if not os.path.exists(dev_node):
            continue

        name = os.path.basename(sys_path)
        try:
            with open(dev_name_file, "r", encoding="utf-8", errors="ignore") as f:
                name = f.read().strip() or name
        except OSError:
            pass

        real_sys = os.path.realpath(sys_path)
        is_virtual = "/devices/virtual/" in real_sys or "loopback" in name.lower() or "camfx" in name.lower()

        if is_virtual:
            virtual.append(VideoDevice(path=dev_node, name=name, is_virtual=True))
            continue

        # USB webcams often expose index 0 (capture) and index 1 (metadata only).
        index_val = "0"
        try:
            with open(dev_index_file, "r", encoding="utf-8", errors="ignore") as f:
                index_val = f.read().strip()
        except OSError:
            pass
        if index_val == "0":
            physical.append(VideoDevice(path=dev_node, name=name, is_virtual=False))

    return physical, virtual


class CameraPipeline:
    """Manages a GStreamer pipeline with live effects, HUD overlay, preview, and v4l2sink."""

    def __init__(
        self,
        on_frame: Optional[Callable[[int, int, bytes, int], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.config = PipelineConfig()
        self._on_frame = on_frame
        self._on_error = on_error
        self._pipeline: Optional[Gst.Pipeline] = None
        self._balance: Optional[Gst.Element] = None
        self._flip: Optional[Gst.Element] = None
        self._lock = threading.Lock()
        self._latest_frame: Optional[Tuple[int, int, bytes, int]] = None
        self._running = False
        self._start_time = time.monotonic()

    @property
    def is_running(self) -> bool:
        return self._running

    def build_pipeline_string(self, cfg: PipelineConfig) -> str:
        """Build the GStreamer launch description string for a given PipelineConfig."""
        if cfg.source == "videotest" or not os.path.exists(cfg.source):
            src_stage = "videotestsrc is-live=true pattern=smpte ! video/x-raw,width=640,height=480,framerate=30/1"
        else:
            src_stage = f"v4l2src device={cfg.source} ! videoconvert ! videoscale ! video/x-raw,width=640,height=480"

        flip_method = "horizontal-flip" if cfg.mirror else "none"
        stages = [
            src_stage,
            "videoconvert",
            f"videoflip name=flip method={flip_method}",
        ]

        effect: EffectSpec = get_effect(cfg.effect_id)
        if effect.kind == "gl_builtin":
            stages.extend(["glupload", effect.element, "gldownload"])
        elif effect.kind == "gl_shader":
            stages.extend(["glupload", "glshader name=fx_shader", "gldownload"])
        elif effect.kind == "effectv":
            stages.extend(["videoconvert", effect.element, "videoconvert"])

        stages.extend([
            "videoconvert",
            (
                f"videobalance name=balance "
                f"brightness={cfg.brightness:.3f} "
                f"contrast={cfg.contrast:.3f} "
                f"saturation={cfg.saturation:.3f}"
            ),
            "videoconvert",
            "video/x-raw,format=RGBA",
            "identity name=hud_pad",
            "tee name=t",
        ])

        pipeline_str = " ! ".join(stages)

        if cfg.enable_preview:
            pipeline_str += (
                " t. ! queue leaky=downstream max-size-buffers=2 "
                "! videoconvert ! video/x-raw,format=RGBA "
                "! appsink name=preview_sink emit-signals=true max-buffers=1 drop=true sync=false"
            )

        if cfg.virtual_cam_enabled and cfg.virtual_device and os.path.exists(cfg.virtual_device):
            pipeline_str += (
                " t. ! queue leaky=downstream max-size-buffers=2 "
                f"! videoconvert ! video/x-raw,format=YUY2 ! v4l2sink name=vsink device={cfg.virtual_device} sync=false"
            )

        return pipeline_str

    def start(self, config: Optional[PipelineConfig] = None) -> None:
        """Start or restart the GStreamer pipeline with the supplied configuration."""
        if config is not None:
            self.config = config
        self.stop()

        pipeline_str = self.build_pipeline_string(self.config)
        pipeline = Gst.parse_launch(pipeline_str)

        effect = get_effect(self.config.effect_id)
        if effect.kind == "gl_shader":
            shader_el = pipeline.get_by_name("fx_shader")
            if shader_el is not None:
                shader_el.set_property("fragment", effect.fragment)

        self._balance = pipeline.get_by_name("balance")
        self._flip = pipeline.get_by_name("flip")

        hud_el = pipeline.get_by_name("hud_pad")
        if hud_el is not None:
            src_pad = hud_el.get_static_pad("src")
            if src_pad is not None:
                src_pad.add_probe(Gst.PadProbeType.BUFFER, self._on_hud_probe)

        sink_el = pipeline.get_by_name("preview_sink")
        if sink_el is not None:
            sink_el.connect("new-sample", self._on_new_sample)

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_bus_error)

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise RuntimeError("Gagal memulai pipeline kamera GStreamer.")

        self._pipeline = pipeline
        self._running = True
        self._start_time = time.monotonic()

    def stop(self) -> None:
        """Stop the active GStreamer pipeline cleanly."""
        if self._pipeline is not None:
            bus = self._pipeline.get_bus()
            if bus is not None:
                bus.remove_signal_watch()
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
        self._balance = None
        self._flip = None
        self._running = False

    def update_live_adjustments(
        self,
        *,
        brightness: Optional[float] = None,
        contrast: Optional[float] = None,
        saturation: Optional[float] = None,
        mirror: Optional[bool] = None,
        hud_enabled: Optional[bool] = None,
        watermark_text: Optional[str] = None,
    ) -> None:
        """Update color balance, mirror, and HUD overlay in real time without restarting."""
        if brightness is not None:
            self.config.brightness = max(-1.0, min(1.0, brightness))
            if self._balance is not None:
                self._balance.set_property("brightness", self.config.brightness)
        if contrast is not None:
            self.config.contrast = max(0.0, min(2.0, contrast))
            if self._balance is not None:
                self._balance.set_property("contrast", self.config.contrast)
        if saturation is not None:
            self.config.saturation = max(0.0, min(2.0, saturation))
            if self._balance is not None:
                self._balance.set_property("saturation", self.config.saturation)
        if mirror is not None:
            self.config.mirror = mirror
            if self._flip is not None:
                self._flip.set_property("method", "horizontal-flip" if mirror else "none")
        if hud_enabled is not None:
            self.config.hud_enabled = hud_enabled
        if watermark_text is not None:
            self.config.watermark_text = watermark_text

    def save_snapshot(self, output_dir: Optional[str] = None) -> Optional[str]:
        """Save the latest rendered frame as a PNG snapshot and return its path."""
        with self._lock:
            frame = self._latest_frame
        if frame is None:
            return None
        width, height, data, stride = frame
        target_dir = output_dir or os.path.join(os.path.expanduser("~"), "Pictures", "CamFX")
        os.makedirs(target_dir, exist_ok=True)
        filename = f"camfx_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        out_path = os.path.join(target_dir, filename)
        img = Image.frombytes("RGBA", (width, height), data, "raw", "RGBA", stride, 1)
        img.save(out_path, "PNG")
        return out_path

    def _on_new_sample(self, sink: Gst.Element) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        caps = sample.get_caps()
        struct = caps.get_structure(0)
        width = struct.get_value("width")
        height = struct.get_value("height")
        buf = sample.get_buffer()
        ok, map_info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK
        try:
            raw = bytes(map_info.data)
            stride = width * 4
            with self._lock:
                self._latest_frame = (width, height, raw, stride)
            if self._on_frame is not None:
                self._on_frame(width, height, raw, stride)
        finally:
            buf.unmap(map_info)
        return Gst.FlowReturn.OK

    def _on_hud_probe(self, pad: Gst.Pad, info: Gst.PadProbeInfo) -> Gst.PadProbeReturn:
        hud_on = self.config.hud_enabled
        watermark = self.config.watermark_text.strip()
        if not hud_on and not watermark:
            return Gst.PadProbeReturn.OK

        caps = pad.get_current_caps()
        if caps is None:
            return Gst.PadProbeReturn.OK
        struct = caps.get_structure(0)
        w = int(struct.get_value("width"))
        h = int(struct.get_value("height"))

        buf = info.get_buffer()
        if buf is None:
            return Gst.PadProbeReturn.OK
        ok, map_info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK
        try:
            img = Image.frombytes("RGBA", (w, h), bytes(map_info.data))
        finally:
            buf.unmap(map_info)

        draw = ImageDraw.Draw(img, "RGBA")
        font = ImageFont.load_default()

        if hud_on:
            pad_px = 18
            arm = 24
            cyan = (56, 189, 248, 225)
            # Viewfinder corner brackets
            draw.line([(pad_px, pad_px + arm), (pad_px, pad_px), (pad_px + arm, pad_px)], fill=cyan, width=3)
            draw.line([(w - pad_px - arm, pad_px), (w - pad_px, pad_px), (w - pad_px, pad_px + arm)], fill=cyan, width=3)
            draw.line([(pad_px, h - pad_px - arm), (pad_px, h - pad_px), (pad_px + arm, h - pad_px)], fill=cyan, width=3)
            draw.line([(w - pad_px - arm, h - pad_px), (w - pad_px, h - pad_px), (w - pad_px, h - pad_px - arm)], fill=cyan, width=3)

            # Top-left LIVE REC badge
            draw.rounded_rectangle([pad_px + 8, pad_px + 8, pad_px + 116, pad_px + 34], radius=6, fill=(15, 20, 30, 185))
            if math.sin(time.monotonic() * 4.0) > -0.2:
                draw.ellipse([pad_px + 16, pad_px + 15, pad_px + 28, pad_px + 27], fill=(244, 63, 94, 245))
            draw.text((pad_px + 34, pad_px + 15), "CAMFX LIVE", fill=(241, 245, 249, 245), font=font)

            # Top-right effect & clock badge
            fx_name = EFFECTS_BY_ID.get(self.config.effect_id, get_effect("normal")).name.upper()
            badge_text = f"{fx_name} | {datetime.now().strftime('%H:%M:%S')}"
            bbox = draw.textbbox((0, 0), badge_text, font=font)
            tw = bbox[2] - bbox[0]
            bx = w - pad_px - tw - 24
            draw.rounded_rectangle([bx, pad_px + 8, w - pad_px - 8, pad_px + 34], radius=6, fill=(15, 20, 30, 185))
            draw.text((bx + 8, pad_px + 15), badge_text, fill=cyan, font=font)

        if watermark:
            bbox = draw.textbbox((0, 0), watermark, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            wx = 26
            wy = h - 38
            draw.rounded_rectangle([wx - 8, wy - 6, wx + tw + 8, wy + th + 6], radius=6, fill=(12, 16, 24, 175))
            draw.text((wx, wy), watermark, fill=(255, 255, 255, 235), font=font)

        new_buf = Gst.Buffer.new_wrapped(img.tobytes())
        new_buf.pts = buf.pts
        new_buf.dts = buf.dts
        new_buf.duration = buf.duration
        info.set_buffer(new_buf)
        return Gst.PadProbeReturn.OK

    def _on_bus_error(self, _bus, msg) -> None:
        err, debug = msg.parse_error()
        text = f"{err.message}"
        if debug:
            text = f"{err.message} ({debug.splitlines()[0]})"
        if self._on_error is not None:
            self._on_error(text)
