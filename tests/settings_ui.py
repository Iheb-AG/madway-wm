"""Run by desktop_smoke.py on its private display/HOME, never the host session."""
import configparser
from pathlib import Path
import runpy
import socket
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

module = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts/madway-shell"))
errors = []


def children(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from children(child)


def inspect_settings():
    window = next(window for window in Gtk.Window.list_toplevels() if window.get_title() == "madway — Settings")
    try:
        assert not window.get_decorated(), "Settings must request the compositor's compact frame"
        stack = next(widget for widget in children(window) if isinstance(widget, Gtk.Stack))
        names = {stack.child_get_property(page, "name") for page in stack.get_children()}
        assert names == {"Windows", "Displays", "Appearance", "Input", "Notifications", "Audio & brightness", "Session", "Panel"}, names
        for name in names:
            stack.set_visible_child_name(name)
            assert stack.get_visible_child_name() == name

        def control(page, label):
            grid = next(widget for widget in children(stack.get_child_by_name(page)) if isinstance(widget, Gtk.Grid))
            for widget in grid.get_children():
                if isinstance(widget, Gtk.Label) and widget.get_text() == label:
                    row = grid.child_get_property(widget, "top-attach")
                    return grid.get_child_at(1, row)
            raise AssertionError("Missing setting: " + label)

        control("Windows", "New windows").set_active_id("tiled")
        control("Windows", "Title height (px)").set_value(14)
        control("Windows", "Master width (%)").set_value(60)
        control("Notifications", "Position").set_active_id("bottom-left")
        control("Notifications", "Popup width (px)").set_value(360)
        control("Notifications", "Default timeout (ms)").set_value(2500)
        control("Audio & brightness", "Volume key step (%)").set_value(7)
        # Switching categories through the desktop menu must preserve unsaved edits.
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
            channel.sendto(b"Panel", str(module["runtime_directory"]() / f"settings-{os.getpid()}.sock"))
        for _ in range(20):Gtk.main_iteration_do(False)
        assert stack.get_visible_child_name() == "Panel"
        assert control("Windows", "Title height (px)").get_value_as_int() == 14
        apply_button = next(widget for widget in children(window) if isinstance(widget, Gtk.Button) and widget.get_label() == "Apply")
        apply_button.clicked()
        config = configparser.ConfigParser(interpolation=None)
        config.read(module["CONFIG"])
        assert config.get("windows", "default_mode") == "tiled"
        assert config.getint("windows", "master_percent") == 60
        assert config.getint("appearance", "title_height") == 14
        assert config.get("notifications", "anchor") == "bottom-left"
        assert config.getint("notifications", "width") == 360
        assert config.getint("notifications", "timeout") == 2500
        assert config.getint("controls", "volume_step") == 7
        print("SETTINGS CATEGORIES AND FORM SAVE PASS", flush=True)
    except BaseException as error:
        errors.append(error)
    window.destroy()
    return False


GLib.timeout_add(500, inspect_settings)
module["settings_window"]()
if errors:
    raise AssertionError("Settings UI test failed") from errors[0]
