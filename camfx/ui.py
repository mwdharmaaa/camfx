"""GTK4 + Libadwaita studio interface for CamFX."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from camfx import APP_ID, APP_NAME, VIRTUAL_CAM_LABEL, VIRTUAL_CAM_NR
from camfx.pipeline import CameraPipeline, PipelineConfig, VideoDevice, discover_video_devices
from camfx.ui_sidebar import SidebarCallbacks, build_sidebar


class CamFXWindow(Adw.ApplicationWindow):
    """Main studio window displaying live preview, effect presets, and virtual camera controls."""

    def __init__(self, app: Adw.Application, initial_effect: str = "normal") -> None:
        super().__init__(application=app, title=f"{APP_NAME} - Custom Effect Camera")
        self.set_default_size(1160, 740)
        self.set_size_request(860, 560)

        self._config = PipelineConfig(effect_id=initial_effect)
        self._cameras: List[VideoDevice] = []
        self._virtual_cams: List[VideoDevice] = []
        self._effect_buttons: Dict[str, Gtk.ToggleButton] = {}
        self._updating_effect_buttons = False
        self._frame_lock = threading.Lock()
        self._pending_frame = None
        self._frame_scheduled = False

        self._pipeline = CameraPipeline(on_frame=self._on_pipeline_frame, on_error=self._on_pipeline_error)
        self._build_ui()
        self._refresh_devices(start_pipeline=True)
        self.connect("close-request", self._on_close_request)

    def _build_ui(self) -> None:
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=APP_NAME, subtitle="Custom Effect Virtual Camera"))
        root_box.append(header)

        self._source_dropdown = Gtk.DropDown()
        self._source_dropdown.set_tooltip_text("Select camera input source")
        self._source_dropdown.connect("notify::selected", self._on_source_changed)
        header.pack_start(self._source_dropdown)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Rescan physical cameras and v4l2loopback devices")
        refresh_btn.connect("clicked", lambda *_: self._refresh_devices(start_pipeline=True))
        header.pack_start(refresh_btn)

        snap_btn = Gtk.Button(label="Snapshot")
        snap_btn.set_icon_name("camera-photo-symbolic")
        snap_btn.set_tooltip_text("Save snapshot to ~/Pictures/CamFX")
        snap_btn.connect("clicked", self._on_snapshot_clicked)
        header.pack_end(snap_btn)

        vcam_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vcam_box.set_valign(Gtk.Align.CENTER)
        self._vcam_switch = Gtk.Switch()
        self._vcam_switch.set_valign(Gtk.Align.CENTER)
        self._vcam_switch.set_tooltip_text("Enable v4l2loopback output for Zoom, Meet, Chrome, and OBS")
        self._vcam_switch.connect("notify::active", self._on_vcam_toggled)
        vcam_box.append(Gtk.Label(label="Virtual Cam"))
        vcam_box.append(self._vcam_switch)
        header.pack_end(vcam_box)

        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        for edge in ("top", "bottom", "start", "end"):
            getattr(content_box, f"set_margin_{edge}")(12)
        content_box.set_vexpand(True)
        root_box.append(content_box)

        preview_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview_col.set_hexpand(True)
        preview_col.set_vexpand(True)
        content_box.append(preview_col)

        frame = Gtk.Frame(hexpand=True, vexpand=True)
        self._picture = Gtk.Picture()
        self._picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._picture.set_can_shrink(True)
        frame.set_child(self._picture)
        preview_col.append(frame)

        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._status_label = Gtk.Label(label="Starting camera...", xalign=0.0, hexpand=True)
        self._status_label.add_css_class("dim-label")
        self._vcam_status_label = Gtk.Label(label="Virtual Cam: OFF")
        self._vcam_status_label.add_css_class("dim-label")
        status_bar.append(self._status_label)
        status_bar.append(self._vcam_status_label)
        preview_col.append(status_bar)

        handles = build_sidebar(
            self._config,
            SidebarCallbacks(
                on_mirror_changed=lambda row, _p: self._pipeline.update_live_adjustments(mirror=row.get_active()),
                on_hud_changed=lambda row, _p: self._pipeline.update_live_adjustments(hud_enabled=row.get_active()),
                on_watermark_changed=lambda row: self._pipeline.update_live_adjustments(watermark_text=row.get_text()),
                on_sliders_changed=self._on_sliders_changed,
                on_effect_toggled=self._on_effect_toggled,
            ),
        )
        self._effect_buttons = handles.effect_buttons
        self._brightness_scale = handles.brightness_scale
        self._contrast_scale = handles.contrast_scale
        self._saturation_scale = handles.saturation_scale
        content_box.append(handles.widget)

    def _refresh_devices(self, start_pipeline: bool = False) -> None:
        self._cameras, self._virtual_cams = discover_video_devices()
        labels = [f"{cam.name} ({cam.path})" for cam in self._cameras] + ["Test Pattern (Simulation)"]
        self._source_dropdown.set_model(Gtk.StringList.new(labels))
        self._config.source = self._cameras[0].path if self._cameras else "videotest"
        self._source_dropdown.set_selected(0)

        if self._virtual_cams:
            self._config.virtual_device = self._virtual_cams[0].path
            self._vcam_switch.set_sensitive(True)
            self._vcam_status_label.set_text(f"Virtual Cam Ready: {self._config.virtual_device}")
        else:
            self._config.virtual_device = None
            self._config.virtual_cam_enabled = False
            self._vcam_switch.set_active(False)
            self._vcam_switch.set_sensitive(False)
            self._vcam_status_label.set_text(
                f"v4l2loopback inactive (sudo modprobe v4l2loopback video_nr={VIRTUAL_CAM_NR} card_label=\"{VIRTUAL_CAM_LABEL}\" exclusive_caps=1)"
            )

        if start_pipeline:
            self._restart_pipeline()

    def _restart_pipeline(self) -> None:
        try:
            self._pipeline.start(self._config)
            self._status_label.set_text(f"Active | Input: {self._config.source} | Effect: {self._config.effect_id}")
        except Exception as exc:
            self._status_label.set_text(f"Error: {exc}")

    def _on_source_changed(self, dropdown: Gtk.DropDown, _param) -> None:
        idx = dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION:
            return
        new_source = self._cameras[idx].path if idx < len(self._cameras) else "videotest"
        if new_source != self._config.source:
            self._config.source = new_source
            self._restart_pipeline()

    def _on_vcam_toggled(self, switch: Gtk.Switch, _param) -> None:
        active = switch.get_active()
        if active and not self._config.virtual_device:
            switch.set_active(False)
            return
        self._config.virtual_cam_enabled = active
        if active:
            self._vcam_status_label.set_text(f"Virtual Cam ON -> {self._config.virtual_device}")
        elif self._config.virtual_device:
            self._vcam_status_label.set_text(f"Virtual Cam OFF ({self._config.virtual_device})")
        self._restart_pipeline()

    def _on_effect_toggled(self, button: Gtk.ToggleButton, effect_id: str) -> None:
        if self._updating_effect_buttons:
            return
        if not button.get_active():
            if self._config.effect_id == effect_id:
                self._updating_effect_buttons = True
                button.set_active(True)
                self._updating_effect_buttons = False
            return
        self._updating_effect_buttons = True
        for eid, btn in self._effect_buttons.items():
            if eid != effect_id and btn.get_active():
                btn.set_active(False)
        self._updating_effect_buttons = False
        self._config.effect_id = effect_id
        self._restart_pipeline()

    def _on_sliders_changed(self, _scale: Gtk.Scale) -> None:
        self._pipeline.update_live_adjustments(
            brightness=self._brightness_scale.get_value(),
            contrast=self._contrast_scale.get_value(),
            saturation=self._saturation_scale.get_value(),
        )

    def _on_snapshot_clicked(self, _btn: Gtk.Button) -> None:
        saved = self._pipeline.save_snapshot()
        self._status_label.set_text(f"Snapshot saved: {saved}" if saved else "No camera frame available yet.")

    def _on_pipeline_frame(self, width: int, height: int, data: bytes, stride: int) -> None:
        with self._frame_lock:
            self._pending_frame = (width, height, data, stride)
            if self._frame_scheduled:
                return
            self._frame_scheduled = True
        GLib.idle_add(self._render_pending_frame)

    def _render_pending_frame(self) -> bool:
        with self._frame_lock:
            frame = self._pending_frame
            self._pending_frame = None
            self._frame_scheduled = False
        if frame is not None:
            width, height, data, stride = frame
            texture = Gdk.MemoryTexture.new(width, height, Gdk.MemoryFormat.R8G8B8A8, GLib.Bytes.new(data), stride)
            self._picture.set_paintable(texture)
        return False

    def _on_pipeline_error(self, message: str) -> None:
        GLib.idle_add(self._status_label.set_text, f"Pipeline Error: {message}")

    def _on_close_request(self, _win) -> bool:
        self._pipeline.stop()
        return False


class CamFXApplication(Adw.Application):
    """Libadwaita application wrapper for CamFX."""

    def __init__(self, initial_effect: str = "normal") -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._initial_effect = initial_effect
        self._window: Optional[CamFXWindow] = None

    def do_activate(self) -> None:
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        if self._window is None:
            self._window = CamFXWindow(self, initial_effect=self._initial_effect)
        self._window.present()


def run_gui(initial_effect: str = "normal") -> int:
    """Launch the GTK4/Libadwaita GUI."""
    return CamFXApplication(initial_effect=initial_effect).run([])
