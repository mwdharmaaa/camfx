"""Sidebar adjustment widgets and categorized effect selector for CamFX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from camfx.devices import PipelineConfig
from camfx.effects import EFFECTS, list_categories


@dataclass
class SidebarCallbacks:
    """Event callbacks wired from the main studio window into sidebar controls."""

    on_mirror_changed: Callable[[Adw.SwitchRow, object], None]
    on_hud_changed: Callable[[Adw.SwitchRow, object], None]
    on_watermark_changed: Callable[[Adw.EntryRow], None]
    on_sliders_changed: Callable[[Gtk.Scale], None]
    on_effect_toggled: Callable[[Gtk.ToggleButton, str], None]


@dataclass
class SidebarHandles:
    """References to interactive sidebar controls needed by the main window."""

    widget: Gtk.ScrolledWindow
    effect_buttons: Dict[str, Gtk.ToggleButton]
    brightness_scale: Gtk.Scale
    contrast_scale: Gtk.Scale
    saturation_scale: Gtk.Scale


def _make_slider(
    parent: Gtk.Box,
    label_text: str,
    min_v: float,
    max_v: float,
    default_v: float,
    cb: Callable[[Gtk.Scale], None],
) -> Gtk.Scale:
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


def build_sidebar(config: PipelineConfig, callbacks: SidebarCallbacks) -> SidebarHandles:
    """Construct the scrollable right-hand adjustments and effects sidebar."""
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_size_request(360, -1)

    sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    sidebar.set_margin_end(4)
    scroll.set_child(sidebar)

    adj_group = Adw.PreferencesGroup(title="Adjustments & Overlay")
    sidebar.append(adj_group)

    mirror_row = Adw.SwitchRow(title="Mirror Horizontal", subtitle="Flip left and right like a mirror")
    mirror_row.set_active(config.mirror)
    mirror_row.connect("notify::active", callbacks.on_mirror_changed)
    adj_group.add(mirror_row)

    hud_row = Adw.SwitchRow(title="Studio REC HUD", subtitle="Show viewfinder brackets, clock, and effect badge")
    hud_row.set_active(config.hud_enabled)
    hud_row.connect("notify::active", callbacks.on_hud_changed)
    adj_group.add(hud_row)

    wm_row = Adw.EntryRow(title="Watermark Text")
    wm_row.connect("changed", callbacks.on_watermark_changed)
    adj_group.add(wm_row)

    sliders_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    sidebar.append(sliders_box)

    brightness_scale = _make_slider(sliders_box, "Brightness", -0.6, 0.6, config.brightness, callbacks.on_sliders_changed)
    contrast_scale = _make_slider(sliders_box, "Contrast", 0.4, 1.8, config.contrast, callbacks.on_sliders_changed)
    saturation_scale = _make_slider(sliders_box, "Saturation", 0.0, 2.0, config.saturation, callbacks.on_sliders_changed)

    def _reset_sliders(_btn: Gtk.Button) -> None:
        brightness_scale.set_value(0.0)
        contrast_scale.set_value(1.0)
        saturation_scale.set_value(1.0)

    reset_btn = Gtk.Button(label="Reset Adjustments")
    reset_btn.connect("clicked", _reset_sliders)
    sliders_box.append(reset_btn)

    effect_buttons: Dict[str, Gtk.ToggleButton] = {}
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
            btn.set_active(spec.id == config.effect_id)
            btn.connect("toggled", callbacks.on_effect_toggled, spec.id)
            effect_buttons[spec.id] = btn
            flow.append(btn)

    return SidebarHandles(
        widget=scroll,
        effect_buttons=effect_buttons,
        brightness_scale=brightness_scale,
        contrast_scale=contrast_scale,
        saturation_scale=saturation_scale,
    )
