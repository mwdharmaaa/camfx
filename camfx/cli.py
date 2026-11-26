"""CLI and GUI launcher for CamFX."""

from __future__ import annotations

import argparse
import signal
import sys
import time

from camfx import APP_NAME, VIRTUAL_CAM_LABEL, VIRTUAL_CAM_NR, __version__
from camfx.effects import EFFECTS, EFFECTS_BY_ID
from camfx.pipeline import CameraPipeline, PipelineConfig, discover_video_devices


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="camfx",
        description="CamFX - Custom Effect Virtual Camera for Linux",
    )
    parser.add_argument("-v", "--version", action="store_true", help="Show application version")
    parser.add_argument("--list-effects", action="store_true", help="List all available effect IDs")
    parser.add_argument("--list-devices", action="store_true", help="List detected physical and virtual cameras")
    parser.add_argument("--effect", default="normal", help="Initial effect ID (default: normal)")
    parser.add_argument("--source", default="", help="Input camera device path (e.g. /dev/video0 or videotest)")
    parser.add_argument("--vcam-device", default="", help="Virtual camera output device (e.g. /dev/video10)")
    parser.add_argument("--headless", action="store_true", help="Run virtual camera in headless mode without GUI")
    parser.add_argument("--hud", action="store_true", help="Enable Studio REC HUD overlay")
    parser.add_argument("--watermark", default="", help="Custom watermark text overlay")
    parser.add_argument("--no-mirror", action="store_true", help="Disable horizontal mirror flip")
    parser.add_argument(
        "--no-scanline-glitch",
        action="store_true",
        help="Disable raw YUY2 scanline glitch and use clean MJPEG capture",
    )
    return parser


def run_headless(args: argparse.Namespace) -> int:
    """Run virtual camera output directly without a GUI window."""
    cameras, virtuals = discover_video_devices()
    source = args.source or (cameras[0].path if cameras else "videotest")
    vcam = args.vcam_device or (virtuals[0].path if virtuals else None)

    if not vcam:
        print(
            f"[ERROR] Virtual camera (v4l2loopback) device was not found.\n"
            f"Run: sudo modprobe v4l2loopback devices=1 video_nr={VIRTUAL_CAM_NR} "
            f"card_label=\"{VIRTUAL_CAM_LABEL}\" exclusive_caps=1",
            file=sys.stderr,
        )
        return 1

    cfg = PipelineConfig(
        source=source,
        effect_id=args.effect if args.effect in EFFECTS_BY_ID else "normal",
        mirror=not args.no_mirror,
        scanline_glitch=not args.no_scanline_glitch,
        hud_enabled=args.hud,
        watermark_text=args.watermark,
        virtual_device=vcam,
        virtual_cam_enabled=True,
        enable_preview=False,
    )

    running = True

    def _handle_sig(_sig, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    pipeline = CameraPipeline(on_error=lambda err: print(f"[ERROR] {err}", file=sys.stderr))
    pipeline.start(cfg)
    print(f"{APP_NAME} headless active: {source} -> {vcam} [effect={cfg.effect_id}] (Press Ctrl+C to stop)")
    try:
        while running:
            time.sleep(0.25)
    finally:
        pipeline.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"{APP_NAME} v{__version__}")
        return 0

    if args.list_effects:
        for spec in EFFECTS:
            print(f"{spec.id:14s} [{spec.category}] - {spec.name}: {spec.description}")
        return 0

    if args.list_devices:
        cameras, virtuals = discover_video_devices()
        print("Physical cameras:")
        for cam in cameras:
            print(f"  {cam.path}  {cam.name}")
        if not cameras:
            print("  (none detected)")
        print("Virtual cameras (v4l2loopback):")
        for vcam in virtuals:
            print(f"  {vcam.path}  {vcam.name}")
        if not virtuals:
            print("  (none active)")
        return 0

    if args.headless:
        return run_headless(args)

    from camfx.ui import run_gui

    effect_id = args.effect if args.effect in EFFECTS_BY_ID else "normal"
    return run_gui(initial_effect=effect_id, scanline_glitch=not args.no_scanline_glitch)


if __name__ == "__main__":
    sys.exit(main())
