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
        assert names == set(module["SETTINGS_PAGES"]), names
        grids=[widget for widget in children(stack) if isinstance(widget,Gtk.Grid)]
        assert all(grid.get_row_spacing()==9 for grid in grids if grid.get_parent().get_parent() in stack.get_children())
        assert window.settings_browser.list.get_children()
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

        control("Appearance", "Theme profile").set_active_id("amber")
        control("Wallpaper", "Background").set_active_id("color")
        control("Wallpaper", "Background color").set_text("#101012")
        control("Input", "Focus on hover").set_active(True)
        edges=control("Panel", "Screen edge")
        assert [row[1] for row in edges.get_model()]==["top","bottom","left","right"]
        assert "80%" in control("Power", "Power status").get_text()
        control("Power", "Low battery (%)").set_value(25)
        assert control("Power", "Critical battery (%)").get_value_as_int()==10
        assert control("Power", "Show battery in panel").get_active()
        assert control('Power','Closing the lid').get_active_id()=='suspend'
        assert control('Power','Lock before sleep').get_active()
        assert not control('Power','').get_sensitive(),'Nested settings must disable host sleep'
        control('Power','Closing the lid').set_active_id('auto')
        control('Panel','Panel name').set_text('Fixture user')
        tasks=control('Panel','Taskbar entries')
        assert tasks.get_active_id()=='icons';tasks.set_active_id('names')
        assert control('Mouse & touchpad','Tap to click').get_active()
        control('Mouse & touchpad','Tap dragging').set_active(False)
        assert control('Mouse & touchpad','Three-finger workspace swipe').get_active()
        control('Mouse & touchpad','Three-finger workspace swipe').set_active(False)
        control('Mouse & touchpad','Reverse workspace swipe').set_active(True)
        control('Mouse & touchpad','Swipe distance').set_value(180)
        assert not control('Mouse & touchpad','Reverse workspace swipe').get_sensitive()
        assert not control('Mouse & touchpad','Swipe distance').get_sensitive()
        control('Mouse & touchpad','Three-finger workspace swipe').set_active(True)
        assert 'left: previous; right: next' in control('Mouse & touchpad','Gestures').get_text()
        control('Mouse & touchpad','Three-finger workspace swipe').set_active(False)
        control('Mouse & touchpad','Touchpad: natural scrolling').set_active(True)
        control('Mouse & touchpad','Touchpad speed').set_value(.35)
        control('Mouse & touchpad','Left-handed buttons').set_active(True)
        assert control('Keyboard','Layout (XKB)').get_text()==''
        assert control('Audio & brightness','Output volume').get_value_pos()==Gtk.PositionType.RIGHT
        assert control('Animations','Animate maximize / minimize').get_active()
        assert control('Animations','Animate closing windows').get_active()
        control('Animations','Close animation (ms)').set_value(300)
        control("Windows", "New windows").set_active_id("tiled")
        combo=control('Windows','New windows')
        border=combo.get_style_context().get_border(Gtk.StateFlags.NORMAL)
        assert not any((border.top,border.bottom,border.left,border.right)),'Duplicate dropdown frame'
        spin=control('Windows','Title height (px)')
        # GtkSpinButton inherits GtkEntry; its widget context is the outer frame.
        border=spin.get_style_context().get_border(Gtk.StateFlags.NORMAL)
        assert (border.top,border.bottom,border.left,border.right)==(1,1,1,1),'Numeric field lost its single-pixel frame'
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
        assert config.get("appearance", "theme") == "amber"
        assert config.get("wallpaper", "type") == "color"
        assert config.get("wallpaper", "color") == "#101012"
        assert config.getboolean("input", "focus_follows_mouse")
        assert config.getint("power", "low_percent")==25
        assert config.getint("power", "critical_percent")==10
        assert config.getboolean("power", "show_battery")
        assert config.get('power','lid_action')=='auto'
        assert config.getboolean('locking','before_sleep')
        assert config.get('panel','label')=='Fixture user'
        assert config.get('panel','tasks')=='names'
        assert config.getboolean('touchpad','tap') and not config.getboolean('touchpad','tap_drag')
        assert config.getboolean('touchpad','natural_scroll') and abs(config.getfloat('touchpad','speed')-.35)<.01
        assert not config.getboolean('touchpad','workspace_swipe') and config.getboolean('touchpad','swipe_invert')
        assert config.getint('touchpad','swipe_threshold')==180
        assert config.getboolean('mouse','left_handed')
        assert config.get("windows", "default_mode") == "tiled"
        assert config.getint("windows", "master_percent") == 60
        assert config.getint("appearance", "title_height") == 14
        assert config.get("notifications", "anchor") == "bottom-left"
        assert config.getint("notifications", "width") == 360
        assert config.getint("notifications", "timeout") == 2500
        assert config.getint("controls", "volume_step") == 7
        assert config.getboolean('windows','close_animate') and config.getint('windows','close_ms')==300
        from types import SimpleNamespace
        from unittest.mock import patch
        confirmation=module['session_confirmation'];sent=[]
        with patch.dict(confirmation.__globals__,action=lambda name:sent.append(name)):
            for operation in ('poweroff','reboot'):
                for response in (Gtk.ResponseType.CANCEL,Gtk.ResponseType.DELETE_EVENT,Gtk.ResponseType.ACCEPT):
                    before=len(sent)
                    def respond(response=response):
                        dialog=next(widget for widget in Gtk.Window.list_toplevels() if widget.get_title()=='madway — Session')
                        assert dialog.get_focus().get_label()=='Cancel'
                        if response==Gtk.ResponseType.ACCEPT:
                            next(widget for widget in children(dialog) if isinstance(widget,Gtk.Button) and widget.get_label()!='Cancel').clicked()
                        else:dialog.destroy()
                        return False
                    GLib.timeout_add(60,respond);confirmation(operation,window)
                    assert len(sent)==before+(response==Gtk.ResponseType.ACCEPT)
                    if response==Gtk.ResponseType.ACCEPT:assert sent[-1]==operation
        calls=[];sounds=[];spawned=[]
        desktop=SimpleNamespace(sound=lambda *args,**kwargs:sounds.append(args),shutdown_played=False,
            spawn=lambda key,args:spawned.append((key,args)))
        perform=module['Desktop'].perform
        with patch.dict(perform.__globals__,run=lambda args:calls.append(args)):
            for operation in ('poweroff','reboot'):
                perform(desktop,{'action':'session-confirm','operation':operation})
                assert spawned[-1][1][-2:]==['confirm-session',operation] and not calls
            for operation in ('poweroff','reboot'):
                desktop.session_exit=SimpleNamespace(begin=lambda op:module['Desktop'].finish_session_operation(desktop,op))
                perform(desktop,{'action':operation})
                assert calls[-1]==['systemctl',operation] and desktop.shutdown_played
        assert not sounds,'Power commit must not replay synchronized audio'
        print('SESSION CONFIRMATION CANCEL DEFAULT AND MOCKED POWER ACTIONS PASS',flush=True)
        print("SETTINGS CATEGORIES AND FORM SAVE PASS", flush=True)
    except BaseException as error:
        errors.append(error)
    window.destroy()
    return False


GLib.timeout_add(500, inspect_settings)
module["settings_window"]()
if errors:
    raise AssertionError("Settings UI test failed") from errors[0]
