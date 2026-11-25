"""GStreamer appsrc video recorder supporting H.264 MP4 and VP8 WebM output."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Optional, Tuple

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


def select_video_codec() -> Tuple[str, str]:
    """Select the best available GStreamer encoder/muxer pair and file extension."""
    if Gst.ElementFactory.find("x264enc") and Gst.ElementFactory.find("mp4mux"):
        return (
            "videoconvert ! video/x-raw,format=I420 "
            "! x264enc tune=zerolatency speed-preset=veryfast bitrate=2500 key-int-max=30 "
            "! video/x-h264,profile=baseline ! mp4mux",
            "mp4",
        )
    return (
        "videoconvert ! video/x-raw,format=I420 "
        "! vp8enc deadline=1 target-bitrate=2500000 ! webmmux",
        "webm",
    )


class VideoRecorder:
    """Encodes incoming RGBA video frames into an MP4 or WebM file via GStreamer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pipeline: Optional[Gst.Pipeline] = None
        self._appsrc: Optional[Gst.Element] = None
        self._output_path: Optional[str] = None
        self._start_mono: float = 0.0
        self._last_pts_ns: int = -1
        self._configured_size: Optional[Tuple[int, int]] = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._pipeline is not None

    @property
    def elapsed_seconds(self) -> float:
        with self._lock:
            if self._pipeline is None:
                return 0.0
            return max(0.0, time.monotonic() - self._start_mono)

    @property
    def output_path(self) -> Optional[str]:
        with self._lock:
            return self._output_path

    def start(self, output_dir: Optional[str] = None) -> str:
        """Initialize recording target path and start accepting frames."""
        self.stop()
        target_dir = output_dir or os.path.join(os.path.expanduser("~"), "Videos", "CamFX")
        os.makedirs(target_dir, exist_ok=True)
        codec_chain, ext = select_video_codec()
        out_path = os.path.join(target_dir, f"camfx_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")

        launch = (
            f"appsrc name=rec_src is-live=true format=time do-timestamp=false "
            f"! {codec_chain} ! filesink location=\"{out_path}\""
        )
        pipeline = Gst.parse_launch(launch)
        appsrc = pipeline.get_by_name("rec_src")
        if appsrc is None:
            raise RuntimeError("Failed to initialize GStreamer video recorder appsrc.")

        with self._lock:
            self._pipeline = pipeline
            self._appsrc = appsrc
            self._output_path = out_path
            self._start_mono = time.monotonic()
            self._last_pts_ns = -1
            self._configured_size = None
        return out_path

    def push_frame(self, width: int, height: int, data: bytes) -> None:
        """Push an RGBA frame into the active recording pipeline."""
        with self._lock:
            if self._pipeline is None or self._appsrc is None:
                return
            if self._configured_size != (width, height):
                caps = Gst.Caps.from_string(
                    f"video/x-raw,format=RGBA,width={width},height={height},framerate=30/1"
                )
                self._appsrc.set_property("caps", caps)
                if self._configured_size is None:
                    self._pipeline.set_state(Gst.State.PLAYING)
                self._configured_size = (width, height)

            pts_ns = max(0, int((time.monotonic() - self._start_mono) * Gst.SECOND))
            if pts_ns <= self._last_pts_ns:
                pts_ns = self._last_pts_ns + 1_000_000
            self._last_pts_ns = pts_ns
            appsrc = self._appsrc

        buf = Gst.Buffer.new_wrapped(data)
        buf.pts = pts_ns
        buf.dts = pts_ns
        buf.duration = Gst.SECOND // 30
        appsrc.emit("push-buffer", buf)

    def stop(self) -> Optional[str]:
        """Finalize the recording with EOS so the MP4/WebM header is cleanly written."""
        with self._lock:
            pipeline = self._pipeline
            appsrc = self._appsrc
            out_path = self._output_path
            configured = self._configured_size
            self._pipeline = None
            self._appsrc = None
            self._output_path = None
            self._configured_size = None

        if pipeline is None:
            return None

        if appsrc is not None and configured is not None:
            appsrc.emit("end-of-stream")
            bus = pipeline.get_bus()
            if bus is not None:
                bus.timed_pop_filtered(4 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        pipeline.set_state(Gst.State.NULL)
        return out_path if (out_path and os.path.exists(out_path) and os.path.getsize(out_path) > 0) else None
