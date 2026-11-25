"""Automated unit and GStreamer pipeline tests for CamFX."""

import os
import subprocess
import sys
import tempfile
import threading
import unittest

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

from camfx.effects import EFFECTS, get_effect, list_categories
from camfx.pipeline import CameraPipeline, PipelineConfig, discover_video_devices


class TestCamFXEffects(unittest.TestCase):
    """Verify effect catalog completeness and GStreamer execution for every effect."""

    def test_catalog_non_empty_and_unique_ids(self) -> None:
        ids = [e.id for e in EFFECTS]
        self.assertGreaterEqual(len(ids), 20)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("Color & Cinema", list_categories())
        self.assertEqual(get_effect("nonexistent").id, "normal")

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

    def test_live_adjustments_and_snapshot(self) -> None:
        got_frame = threading.Event()
        pipeline = CameraPipeline(on_frame=lambda *_: got_frame.set())
        cfg = PipelineConfig(source="videotest", effect_id="cyberpunk", hud_enabled=True)
        pipeline.start(cfg)
        try:
            self.assertTrue(got_frame.wait(timeout=3.0))
            pipeline.update_live_adjustments(
                brightness=0.2,
                contrast=1.3,
                saturation=1.4,
                mirror=False,
                hud_enabled=False,
                watermark_text="Studio",
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                snap = pipeline.save_snapshot(output_dir=tmpdir)
                self.assertIsNotNone(snap)
                self.assertTrue(os.path.exists(snap))
                self.assertGreater(os.path.getsize(snap), 1000)
        finally:
            pipeline.stop()

    def test_device_discovery_returns_lists(self) -> None:
        physical, virtual = discover_video_devices()
        self.assertIsInstance(physical, list)
        self.assertIsInstance(virtual, list)

    def test_cli_flags(self) -> None:
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
