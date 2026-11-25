"""GStreamer real-time camera effects and v4l2loopback virtual camera pipeline."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Callable, Optional, Tuple

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst
from PIL import Image

from camfx.devices import PipelineConfig, VideoDevice, discover_video_devices
from camfx.effects import get_effect
from camfx.pipeline_builder import apply_hud_probe, build_pipeline_string
from camfx.recorder import VideoRecorder

Gst.init(None)

__all__ = ["CameraPipeline", "PipelineConfig", "VideoDevice", "discover_video_devices"]


class CameraPipeline:
    """Manages a GStreamer pipeline with live effects, HUD overlay, recording, and v4l2sink."""

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
        self._recorder = VideoRecorder()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_recording(self) -> bool:
        return self._recorder.is_recording

    @property
    def recording_elapsed(self) -> float:
        return self._recorder.elapsed_seconds

    def build_pipeline_string(self, cfg: PipelineConfig) -> str:
        """Build the GStreamer launch description string for a given PipelineConfig."""
        return build_pipeline_string(cfg)

    def start(self, config: Optional[PipelineConfig] = None) -> None:
        """Start or restart the GStreamer pipeline without interrupting active recording."""
        if config is not None:
            self.config = config
        self._stop_gst_pipeline()

        pipeline = Gst.parse_launch(self.build_pipeline_string(self.config))
        effect = get_effect(self.config.effect_id)
        if effect.kind == "gl_shader":
            shader_el = pipeline.get_by_name("fx_shader")
            if shader_el is not None:
                shader_el.set_property("fragment", effect.fragment)

        self._balance = pipeline.get_by_name("balance")
        self._flip = pipeline.get_by_name("flip")

        hud_el = pipeline.get_by_name("hud_pad")
        if hud_el is not None and (src_pad := hud_el.get_static_pad("src")) is not None:
            src_pad.add_probe(Gst.PadProbeType.BUFFER, lambda pad, info: apply_hud_probe(pad, info, self.config))

        if (sink_el := pipeline.get_by_name("preview_sink")) is not None:
            sink_el.connect("new-sample", self._on_new_sample)

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_bus_error)

        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise RuntimeError("Failed to start GStreamer camera pipeline.")

        self._pipeline = pipeline
        self._running = True

    def _stop_gst_pipeline(self) -> None:
        if self._pipeline is not None:
            if (bus := self._pipeline.get_bus()) is not None:
                bus.remove_signal_watch()
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
        self._balance = None
        self._flip = None
        self._running = False

    def stop(self) -> None:
        """Stop the active GStreamer pipeline and finalize any active recording."""
        self.stop_recording()
        self._stop_gst_pipeline()

    def start_recording(self, output_dir: Optional[str] = None) -> str:
        """Start recording processed camera frames into an MP4 or WebM file."""
        return self._recorder.start(output_dir=output_dir)

    def stop_recording(self) -> Optional[str]:
        """Stop video recording and return the finalized output file path."""
        return self._recorder.stop()

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
        out_path = os.path.join(target_dir, f"camfx_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        Image.frombytes("RGBA", (width, height), data, "raw", "RGBA", stride, 1).convert("RGB").save(out_path, "PNG")
        return out_path

    def _on_new_sample(self, sink: Gst.Element) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        struct = sample.get_caps().get_structure(0)
        width, height = struct.get_value("width"), struct.get_value("height")
        buf = sample.get_buffer()
        ok, map_info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK
        try:
            raw = bytes(map_info.data)
            stride = len(raw) // height if (height > 0 and len(raw) % height == 0) else width * 4
            with self._lock:
                self._latest_frame = (width, height, raw, stride)
            if self._recorder.is_recording:
                self._recorder.push_frame(width, height, raw)
            if self._on_frame is not None:
                self._on_frame(width, height, raw, stride)
        finally:
            buf.unmap(map_info)
        return Gst.FlowReturn.OK

    def _on_bus_error(self, _bus, msg) -> None:
        err, debug = msg.parse_error()
        text = f"{err.message} ({debug.splitlines()[0]})" if debug else f"{err.message}"
        if self._on_error is not None:
            self._on_error(text)
