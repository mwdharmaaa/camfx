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
                errors = []

                def on_frame(w: int, h: int, data: bytes, stride: int) -> None:
                    if w == 640 and h == 480 and len(data) == stride * h:
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
            mjpeg_str = build_pipeline_string(PipelineConfig(source="/dev/video0", effect_id="sepia"), use_mjpeg=True)
            self.assertIn("image/jpeg,width=640,height=480", mjpeg_str)
            self.assertIn("jpegdec", mjpeg_str)
            self.assertIn("leaky=downstream", mjpeg_str)
            self.assertIsInstance(device_supports_mjpeg_640x480("/dev/video0"), bool)

    def test_device_discovery_and_ui_import(self) -> None:
        physical, virtual = discover_video_devices()
        self.assertIsInstance(physical, list)
        self.assertIsInstance(virtual, list)
        import camfx.ui

        self.assertTrue(hasattr(camfx.ui, "CamFXWindow"))

    def test_cli_flags_and_parser(self) -> None:
        args = build_parser().parse_args(["--headless", "--effect", "cyberpunk", "--hud", "--watermark", "Live"])
        self.assertTrue(args.headless)
        self.assertEqual(args.effect, "cyberpunk")
        self.assertTrue(args.hud)
        self.assertEqual(args.watermark, "Live")

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
