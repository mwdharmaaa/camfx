"""Capture action bar with Take Photo and Record Video buttons for CamFX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


@dataclass
class CaptureBarHandles:
    """References to capture action bar widgets."""

    widget: Gtk.Box
    photo_button: Gtk.Button
    record_button: Gtk.Button
    record_label: Gtk.Label


def _make_icon_label_button(icon_name: str, text: str) -> tuple[Gtk.Button, Gtk.Label]:
    btn = Gtk.Button()
    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    content.set_halign(Gtk.Align.CENTER)
    content.append(Gtk.Image.new_from_icon_name(icon_name))
    lbl = Gtk.Label(label=text)
    content.append(lbl)
    btn.set_child(content)
    return btn, lbl


def build_capture_bar(
    *,
    on_take_photo: Callable[[Gtk.Button], None],
    on_toggle_record: Callable[[Gtk.Button], None],
) -> CaptureBarHandles:
    """Build the prominent Take Photo and Record Video control bar."""
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    bar.set_halign(Gtk.Align.CENTER)
    bar.set_margin_top(2)
    bar.set_margin_bottom(2)

    photo_btn, _photo_lbl = _make_icon_label_button("camera-photo-symbolic", "Take Photo")
    photo_btn.add_css_class("suggested-action")
    photo_btn.add_css_class("pill")
    photo_btn.set_tooltip_text("Capture PNG photo to ~/Pictures/CamFX")
    photo_btn.connect("clicked", on_take_photo)

    record_btn, record_lbl = _make_icon_label_button("media-record-symbolic", "Record Video")
    record_btn.add_css_class("pill")
    record_btn.set_tooltip_text("Record MP4/WebM video to ~/Videos/CamFX")
    record_btn.connect("clicked", on_toggle_record)

    bar.append(photo_btn)
    bar.append(record_btn)
    return CaptureBarHandles(
        widget=bar,
        photo_button=photo_btn,
        record_button=record_btn,
        record_label=record_lbl,
    )
