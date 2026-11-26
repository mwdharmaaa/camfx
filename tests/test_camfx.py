"""Automated unit and GStreamer pipeline tests for CamFX."""

import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import gi
from PIL import Image

gi.require_version("Gst", "1.0")

from camfx.capture_clean import CleanSourceProfile, build_clean_capture_stage, probe_clean_source
from camfx.cli import build_parser
from camfx.devices import device_supports_mjpeg_640x480
from camfx.effects import EFFECTS, get_effect, list_categories
from camfx.hud import render_hud_overlay
from camfx.pipeline import CameraPipeline, PipelineConfig, discover_video_devices
from camfx.pipeline_builder import build_pipeline_string
from camfx.shader_glitch import SHADER_GLITCH


class TestCamFXEffects(unittest.TestCase):
    """Verify effect catalog completeness, HUD rendering, and GStreamer execution."""

    def test_catalog_non_empty_and_unique_ids(self) -> None:
        ids = [e.id for e in EFFECTS]
        self.assertGreaterEqual(len(ids), 24)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("Color & Cinema", list_categories())
        self.assertEqual(get_effect("nonexistent").id, "normal")

    def test_glitch_shader_locked_integrity(self) -> None:
        locked_sha256 = "7a13ca876338e401abe484cf177355e456072e0b20cc8f6f662839a8ed8764c4"
        digest = hashlib.sha256(SHADER_GLITCH.encode("utf-8")).hexdigest()
        self.assertEqual(digest, locked_sha256)
        self.assertEqual(get_effect("glitch").fragment, SHADER_GLITCH)

    def test_all_effects_render_frames_with_hud(self) -> None:
        """Every single defined effect must initialize, apply HUD, and emit RGBA frames."""
        for spec in EFFECTS:
            with self.subTest(effect=spec.id):
                got_frame = threading.Event()
                frame_stats: dict[str, int] = {}
                errors = []

                def on_frame(w: int, h: int, data: bytes, stride: int) -> None:
                    if w == 640 and h == 480 and len(data) == stride * h:
                        alphas = data[3::4]
                        frame_stats["min_a"] = min(alphas)
                        frame_stats["max_a"] = max(alphas)
                        frame_stats["max_rgb"] = max(max(data[0::4]), max(data[1::4]), max(data[2::4]))
                        got_frame.set()

                pipeline = CameraPipeline(on_frame=on_frame, on_error=errors.append)
                cfg = PipelineConfig(
                    source="videotest",
                    effect_id=spec.id,
                    mirror=True,
                    hud_enabled=True,
                    watermark_text="CamFX Test",
                    virtual_cam_enabled=False,
                    enable_preview=True,
                )
                pipeline.start(cfg)
                try:
                    self.assertTrue(got_frame.wait(timeout=3.0), f"Effect {spec.id} produced no frame; errors={errors}")
                    self.assertEqual(errors, [])
                    self.assertEqual(frame_stats.get("max_a"), 255, f"Effect {spec.id} produced zero max alpha")
                    self.assertGreaterEqual(frame_stats.get("min_a", 0), 140, f"Effect {spec.id} emitted transparent pixels")
                    self.assertGreater(frame_stats.get("max_rgb", 0), 0, f"Effect {spec.id} emitted blank RGB frame")
                finally:
                    pipeline.stop()

    def test_effectv_and_noir_emit_fully_opaque_frames(self) -> None:
        """EffecTV (RGBx) and gleffects_sin must emit alpha=255 without HUD enabled."""
        for effect_id in ("vertigo", "noir", "aging", "neon_edge", "warp"):
            with self.subTest(effect=effect_id):
                got_frame = threading.Event()
                frame_stats: dict[str, int] = {}

                def on_frame(w: int, h: int, data: bytes, stride: int) -> None:
                    if w == 640 and h == 480 and len(data) == stride * h:
                        alphas = data[3::4]
                        frame_stats["min_a"] = min(alphas)
                        frame_stats["max_rgb"] = max(max(data[0::4]), max(data[1::4]), max(data[2::4]))
                        got_frame.set()

                pipeline = CameraPipeline(on_frame=on_frame)
                pipeline.start(PipelineConfig(source="videotest", effect_id=effect_id, hud_enabled=False))
                try:
                    self.assertTrue(got_frame.wait(timeout=3.0), f"Effect {effect_id} produced no frame")
                    self.assertEqual(frame_stats.get("min_a"), 255, f"Effect {effect_id} leaked non-opaque alpha")
                    self.assertGreater(frame_stats.get("max_rgb", 0), 0, f"Effect {effect_id} emitted blank frame")
                finally:
                    pipeline.stop()

    def test_live_adjustments_clamping_and_snapshot(self) -> None:
        got_frame = threading.Event()
        pipeline = CameraPipeline(on_frame=lambda *_: got_frame.set())
        cfg = PipelineConfig(source="videotest", effect_id="cyberpunk", hud_enabled=True)
        pipeline.start(cfg)
        try:
            self.assertTrue(got_frame.wait(timeout=3.0))
            pipeline.update_live_adjustments(
                brightness=5.0,
                contrast=-1.0,
                saturation=9.0,
                mirror=False,
                hud_enabled=False,
                watermark_text="Studio",
            )
            self.assertEqual(pipeline.config.brightness, 1.0)
            self.assertEqual(pipeline.config.contrast, 0.0)
            self.assertEqual(pipeline.config.saturation, 2.0)
            self.assertFalse(pipeline.config.mirror)
            with tempfile.TemporaryDirectory() as tmpdir:
                snap = pipeline.save_snapshot(output_dir=tmpdir)
                self.assertIsNotNone(snap)
                self.assertTrue(os.path.exists(snap))
                self.assertGreater(os.path.getsize(snap), 1000)
        finally:
            pipeline.stop()

    def test_video_recording_across_effect_switch(self) -> None:
        frame_count = 0
        got_enough = threading.Event()

        def on_frame(*_args) -> None:
            nonlocal frame_count
            frame_count += 1
            if frame_count >= 12:
                got_enough.set()

        pipeline = CameraPipeline(on_frame=on_frame)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_target = pipeline.start_recording(output_dir=tmpdir)
            self.assertTrue(pipeline.is_recording)
            pipeline.start(PipelineConfig(source="videotest", effect_id="normal"))
            try:
                self.assertTrue(got_enough.wait(timeout=4.0), "Not enough frames received for recording")
                # Switch effect mid-recording; recording must continue seamlessly.
                frame_count = 0
                got_enough.clear()
                pipeline.start(PipelineConfig(source="videotest", effect_id="cyberpunk"))
                self.assertTrue(pipeline.is_recording)
                self.assertTrue(got_enough.wait(timeout=4.0), "Not enough post-switch frames received")
                time.sleep(0.1)
                saved = pipeline.stop_recording()
                self.assertEqual(saved, out_target)
                self.assertFalse(pipeline.is_recording)
                self.assertIsNotNone(saved)
                self.assertTrue(os.path.exists(saved))
                self.assertGreater(os.path.getsize(saved), 2048)
            finally:
                pipeline.stop()

    def test_hud_overlay_mutates_only_when_enabled(self) -> None:
        base = Image.new("RGBA", (320, 240), (0, 0, 0, 255))
        untouched = base.copy()
        render_hud_overlay(untouched, effect_id="cyberpunk", hud_enabled=False, watermark_text="   ")
        self.assertEqual(untouched.tobytes(), base.tobytes())

        annotated = base.copy()
        render_hud_overlay(annotated, effect_id="cyberpunk", hud_enabled=True, watermark_text="LIVE", now_monotonic=0.0)
        self.assertNotEqual(annotated.tobytes(), base.tobytes())

        wm_only = Image.new("RGBA", (320, 240), (200, 180, 50, 255))
        render_hud_overlay(wm_only, effect_id="normal", hud_enabled=False, watermark_text="CamFX")
        # Surrounding padding pixel above watermark must remain original background without dark box fill.
        self.assertEqual(wm_only.getpixel((20, 202)), (200, 180, 50, 255))

    def test_pipeline_string_builder_variants(self) -> None:
        pipeline = CameraPipeline()
        shader_str = pipeline.build_pipeline_string(PipelineConfig(source="videotest", effect_id="cyberpunk", mirror=False))
        self.assertIn("glshader name=fx_shader", shader_str)
        self.assertIn("method=none", shader_str)

        effectv_str = pipeline.build_pipeline_string(PipelineConfig(source="videotest", effect_id="warp", mirror=True))
        self.assertIn("warptv", effectv_str)
        self.assertIn("method=horizontal-flip", effectv_str)

        if os.path.exists("/dev/video0"):
            raw_v4l2 = pipeline.build_pipeline_string(PipelineConfig(source="/dev/video0", effect_id="sepia", scanline_glitch=True))
            self.assertIn("v4l2src device=/dev/video0 ! videoconvert ! videoscale ! video/x-raw,width=640,height=480", raw_v4l2)
            self.assertNotIn("pipewiresrc", raw_v4l2)
            self.assertNotIn("jpegdec", raw_v4l2)
            self.assertNotIn("deinterlace", raw_v4l2)

            clean_auto = build_pipeline_string(PipelineConfig(source="/dev/video0", effect_id="sepia", scanline_glitch=False))
            self.assertIn("deinterlace mode=interlaced fields=top method=linear", clean_auto)
            self.assertIn("videoscale method=bilinear", clean_auto)
            self.assertIn("leaky=downstream", clean_auto)

            clean_pw = build_clean_capture_stage(
                "/dev/video0",
                profile=CleanSourceProfile(pipewire_target="pw_node_0", mjpeg_size=(1600, 1200)),
                has_pipewiresrc=True,
                has_jpegdec=True,
                has_deinterlace=True,
            )
            self.assertIn("pipewiresrc target-object=pw_node_0 always-copy=true", clean_pw)
            self.assertIn("image/jpeg,width=1600,height=1200", clean_pw)
            self.assertIn("jpegdec", clean_pw)

            clean_raw_queue = build_pipeline_string(
                PipelineConfig(source="/dev/video0", effect_id="sepia", scanline_glitch=False),
                use_mjpeg=False,
            )
            self.assertIn("v4l2src device=/dev/video0", clean_raw_queue)
            self.assertIn("queue max-size-buffers=2 leaky=downstream", clean_raw_queue)
            self.assertNotIn("jpegdec", clean_raw_queue)
            self.assertIn("deinterlace mode=interlaced fields=top method=linear", clean_raw_queue)
            self.assertIsInstance(probe_clean_source("/dev/video0"), CleanSourceProfile)
            self.assertIsInstance(device_supports_mjpeg_640x480("/dev/video0"), bool)

    def test_deinterlace_eliminates_horizontal_scanline_combing(self) -> None:
        from gi.repository import Gst

        Gst.init(None)
        width, height = 64, 64
        combed = bytearray(width * height * 3)
        for y in range(height):
            val = 255 if y % 2 == 0 else 0
            row_start = y * width * 3
            combed[row_start : row_start + width * 3] = bytes([val]) * (width * 3)

        pipe = Gst.parse_launch(
            "appsrc name=src caps=video/x-raw,format=RGB,width=64,height=64,framerate=30/1 "
            "! videoconvert ! deinterlace mode=interlaced fields=top method=linear "
            "! videoconvert ! video/x-raw,format=RGB ! appsink name=sink"
        )
        src = pipe.get_by_name("src")
        sink = pipe.get_by_name("sink")
        pipe.set_state(Gst.State.PLAYING)
        try:
            buf = Gst.Buffer.new_wrapped(bytes(combed))
            src.emit("push-buffer", buf)
            src.emit("end-of-stream")
            sample = sink.emit("pull-sample")
            self.assertIsNotNone(sample)
            out_buf = sample.get_buffer()
            ok, map_info = out_buf.map(Gst.MapFlags.READ)
            self.assertTrue(ok)
            try:
                out_bytes = bytes(map_info.data)
            finally:
                out_buf.unmap(map_info)
            # Every alternating black/white scanline row must be normalized cleanly to 255.
            row_values = [out_bytes[y * width * 3] for y in range(4, height - 4)]
            self.assertEqual(set(row_values), {255})
        finally:
            pipe.set_state(Gst.State.NULL)

    def test_device_discovery_and_ui_import(self) -> None:
        physical, virtual = discover_video_devices()
        self.assertIsInstance(physical, list)
        self.assertIsInstance(virtual, list)
        import camfx.ui
        from camfx.ui_sidebar import SidebarCallbacks, build_sidebar

        self.assertTrue(hasattr(camfx.ui, "CamFXWindow"))

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk

        if Gtk.init_check():
            Adw.init()
            observed: list[bool] = []
            handles = build_sidebar(
                PipelineConfig(scanline_glitch=True),
                SidebarCallbacks(
                    on_mirror_changed=lambda *_: None,
                    on_hud_changed=lambda *_: None,
                    on_scanline_glitch_changed=lambda row, _p: observed.append(row.get_active()),
                    on_watermark_changed=lambda *_: None,
                    on_sliders_changed=lambda *_: None,
                    on_effect_toggled=lambda *_: None,
                ),
            )
            self.assertTrue(handles.scanline_glitch_row.get_active())
            handles.scanline_glitch_row.set_active(False)
            self.assertEqual(observed, [False])

    def test_cli_flags_and_parser(self) -> None:
        args = build_parser().parse_args(["--headless", "--effect", "cyberpunk", "--hud", "--watermark", "Live"])
        self.assertTrue(args.headless)
        self.assertEqual(args.effect, "cyberpunk")
        self.assertTrue(args.hud)
        self.assertEqual(args.watermark, "Live")
        self.assertFalse(args.no_scanline_glitch)

        clean_args = build_parser().parse_args(["--no-scanline-glitch"])
        self.assertTrue(clean_args.no_scanline_glitch)

        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        res_ver = subprocess.run([sys.executable, "-m", "camfx.cli", "--version"], env=env, capture_output=True, text=True, check=True)
        self.assertIn("CamFX v", res_ver.stdout)

        res_fx = subprocess.run([sys.executable, "-m", "camfx.cli", "--list-effects"], env=env, capture_output=True, text=True, check=True)
        self.assertIn("cyberpunk", res_fx.stdout)
        self.assertIn("glitch", res_fx.stdout)

        res_dev = subprocess.run([sys.executable, "-m", "camfx.cli", "--list-devices"], env=env, capture_output=True, text=True, check=True)
        self.assertIn("Physical cameras:", res_dev.stdout)


if __name__ == "__main__":
    unittest.main()
