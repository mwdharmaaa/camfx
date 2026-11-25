"""GTK4 + Libadwaita studio interface for CamFX."""

from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from camfx import APP_ID, APP_NAME, VIRTUAL_CAM_LABEL, VIRTUAL_CAM_NR, __version__
from camfx.effects import EFFECTS, list_categories
from camfx.pipeline import CameraPipeline, PipelineConfig, VideoDevice, discover_video_devices


class CamFXWindow(Adw.ApplicationWindow):
    """Main studio window displaying live preview, effect presets, and virtual camera controls."""

    def __init__(self, app: Adw.Application, initial_effect: str = "normal") -> None:
        super().__init__(application=app, title=f"{APP_NAME} — Custom Effect Camera")
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

        self._pipeline = CameraPipeline(
            on_frame=self._on_pipeline_frame,
            on_error=self._on_pipeline_error,
        )

        self._build_ui()
        self._refresh_devices(start_pipeline=True)

        self.connect("close-request", self._on_close_request)

    def _build_ui(self) -> None:
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        # Header Bar
        header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title=APP_NAME, subtitle="Custom Effect Virtual Camera")
        header.set_title_widget(title_widget)
        root_box.append(header)

        # Left header controls: Camera source dropdown + refresh
        self._source_dropdown = Gtk.DropDown()
        self._source_dropdown.set_tooltip_text("Pilih sumber kamera input")
        self._source_dropdown.connect("notify::selected", self._on_source_changed)
        header.pack_start(self._source_dropdown)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Scan ulang device kamera & v4l2loopback")
        refresh_btn.connect("clicked", lambda *_: self._refresh_devices(start_pipeline=True))
        header.pack_start(refresh_btn)

        # Right header controls: Snapshot + Virtual Cam switch
        snap_btn = Gtk.Button(label="Snapshot")
        snap_btn.set_icon_name("camera-photo-symbolic")
        snap_btn.set_tooltip_text("Simpan foto ke ~/Pictures/CamFX")
        snap_btn.connect("clicked", self._on_snapshot_clicked)
        header.pack_end(snap_btn)

        vcam_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vcam_box.set_valign(Gtk.Align.CENTER)
        vcam_label = Gtk.Label(label="Virtual Cam")
        self._vcam_switch = Gtk.Switch()
        self._vcam_switch.set_valign(Gtk.Align.CENTER)
        self._vcam_switch.set_tooltip_text("Aktifkan output ke v4l2loopback agar muncul di Zoom/Meet/Chrome")
        self._vcam_switch.connect("notify::active", self._on_vcam_toggled)
        vcam_box.append(vcam_label)
        vcam_box.append(self._vcam_switch)
        header.pack_end(vcam_box)

        # Main split area: Preview (left) + Effects & Controls (right)
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        content_box.set_vexpand(True)
        root_box.append(content_box)

        # Preview column
        preview_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview_col.set_hexpand(True)
        preview_col.set_vexpand(True)
        content_box.append(preview_col)

        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.set_vexpand(True)
        self._picture = Gtk.Picture()
        self._picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._picture.set_can_shrink(True)
        frame.set_child(self._picture)
        preview_col.append(frame)

        # Status bar
        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._status_label = Gtk.Label(label="Memulai kamera...", xalign=0.0)
        self._status_label.set_hexpand(True)
        self._status_label.add_css_class("dim-label")
        self._vcam_status_label = Gtk.Label(label="Virtual Cam: OFF")
        self._vcam_status_label.add_css_class("dim-label")
        status_bar.append(self._status_label)
        status_bar.append(self._vcam_status_label)
        preview_col.append(status_bar)

        # Sidebar (Effects & Adjustments)
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_size_request(360, -1)
        content_box.append(sidebar_scroll)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        sidebar.set_margin_end(4)
        sidebar_scroll.set_child(sidebar)

        # Quick Adjustments & HUD Group
        adj_group = Adw.PreferencesGroup(title="Adjustments & Overlay")
        sidebar.append(adj_group)

        mirror_row = Adw.SwitchRow(title="Mirror Horizontal", subtitle="Balik kanan-kiri seperti cermin")
        mirror_row.set_active(self._config.mirror)
        mirror_row.connect("notify::active", self._on_mirror_changed)
        adj_group.add(mirror_row)

        hud_row = Adw.SwitchRow(title="Studio REC HUD", subtitle="Tampilkan bingkai, jam, & badge efek")
        hud_row.set_active(self._config.hud_enabled)
        hud_row.connect("notify::active", self._on_hud_changed)
        adj_group.add(hud_row)

        wm_row = Adw.EntryRow(title="Watermark Text")
        wm_row.connect("changed", self._on_watermark_changed)
        adj_group.add(wm_row)

        # Sliders box
        sliders_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar.append(sliders_box)

        self._brightness_scale = self._make_slider(sliders_box, "Brightness", -0.6, 0.6, 0.0, self._on_sliders_changed)
        self._contrast_scale = self._make_slider(sliders_box, "Contrast", 0.4, 1.8, 1.0, self._on_sliders_changed)
        self._saturation_scale = self._make_slider(sliders_box, "Saturation", 0.0, 2.0, 1.0, self._on_sliders_changed)

        reset_adj_btn = Gtk.Button(label="Reset Adjustments")
        reset_adj_btn.connect("clicked", self._on_reset_adjustments)
        sliders_box.append(reset_adj_btn)

        # Effects Catalog grouped by category
        for category in list_categories():
            cat_label = Gtk.Label(label=category, xalign=0.0)
            cat_label.add_css_class("heading")
            cat_label.set_margin_top(4)
            sidebar.append(cat_label)

            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_max_children_per_line(2)
            flow.set_min_children_per_line(2)
            flow.set_column_spacing(6)
            flow.set_row_spacing(6)
            flow.set_homogeneous(True)
            sidebar.append(flow)

            for spec in [e for e in EFFECTS if e.category == category]:
                btn = Gtk.ToggleButton(label=spec.name)
                btn.set_tooltip_text(spec.description)
                btn.set_active(spec.id == self._config.effect_id)
                btn.connect("toggled", self._on_effect_toggled, spec.id)
                self._effect_buttons[spec.id] = btn
                flow.append(btn)

    def _make_slider(self, parent: Gtk.Box, label_text: str, min_v: float, max_v: float, default_v: float, cb) -> Gtk.Scale:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=label_text, xalign=0.0)
        lbl.set_size_request(86, -1)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_v, max_v, 0.05)
        scale.set_value(default_v)
        scale.set_hexpand(True)
        scale.set_draw_value(True)
        scale.connect("value-changed", cb)
        row.append(lbl)
        row.append(scale)
        parent.append(row)
        return scale

    def _refresh_devices(self, start_pipeline: bool = False) -> None:
        self._cameras, self._virtual_cams = discover_video_devices()

        labels = [f"{cam.name} ({cam.path})" for cam in self._cameras]
        labels.append("Test Pattern (Simulasi)")
        model = Gtk.StringList.new(labels)
        self._source_dropdown.set_model(model)

        if self._cameras:
            self._config.source = self._cameras[0].path
            self._source_dropdown.set_selected(0)
        else:
            self._config.source = "videotest"
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
                f"v4l2loopback belum aktif (sudo modprobe v4l2loopback video_nr={VIRTUAL_CAM_NR} card_label=\"{VIRTUAL_CAM_LABEL}\" exclusive_caps=1)"
            )

        if start_pipeline:
            self._restart_pipeline()

    def _restart_pipeline(self) -> None:
        try:
            self._pipeline.start(self._config)
            src_name = self._config.source
            self._status_label.set_text(f"Aktif • Input: {src_name} • Efek: {self._config.effect_id}")
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

    def _on_mirror_changed(self, row: Adw.SwitchRow, _param) -> None:
        self._pipeline.update_live_adjustments(mirror=row.get_active())

    def _on_hud_changed(self, row: Adw.SwitchRow, _param) -> None:
        self._pipeline.update_live_adjustments(hud_enabled=row.get_active())

    def _on_watermark_changed(self, row: Adw.EntryRow) -> None:
        self._pipeline.update_live_adjustments(watermark_text=row.get_text())

    def _on_sliders_changed(self, _scale: Gtk.Scale) -> None:
        self._pipeline.update_live_adjustments(
            brightness=self._brightness_scale.get_value(),
            contrast=self._contrast_scale.get_value(),
            saturation=self._saturation_scale.get_value(),
        )

    def _on_reset_adjustments(self, _btn: Gtk.Button) -> None:
        self._brightness_scale.set_value(0.0)
        self._contrast_scale.set_value(1.0)
        self._saturation_scale.set_value(1.0)

    def _on_snapshot_clicked(self, _btn: Gtk.Button) -> None:
        saved = self._pipeline.save_snapshot()
        if saved:
            self._status_label.set_text(f"Snapshot tersimpan: {saved}")
        else:
            self._status_label.set_text("Belum ada frame kamera untuk disimpan.")

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
            texture = Gdk.MemoryTexture.new(
                width,
                height,
                Gdk.MemoryFormat.R8G8B8A8,
                GLib.Bytes.new(data),
                stride,
            )
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
        style_mgr = Adw.StyleManager.get_default()
        style_mgr.set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        if self._window is None:
            self._window = CamFXWindow(self, initial_effect=self._initial_effect)
        self._window.present()


def run_gui(initial_effect: str = "normal") -> int:
    """Launch the GTK4/Libadwaita GUI."""
    app = CamFXApplication(initial_effect=initial_effect)
    return app.run([])
