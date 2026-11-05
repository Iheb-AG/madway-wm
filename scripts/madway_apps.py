"""Resolve desktop applications and persistent dock pins without shell evaluation."""
import json
from pathlib import Path
import gi
from gi.repository import Gio


def pins(config):
    try:values=json.loads(config.get('dock','pinned',fallback='[]'))
    except (ValueError,TypeError):return []
    if not isinstance(values,list):return []
    return list(dict.fromkeys(value for value in values if isinstance(value,str) and len(value)>8 and value.endswith('.desktop') and
        '/' not in value and '\x00' not in value and len(value)<=512))


def resolve(value):
    if not isinstance(value,str) or not value or '/' in value or '\x00' in value:return None
    for name in (value,value+'.desktop'):
        try:app=Gio.DesktopAppInfo.new(name)
        except (TypeError,ValueError):app=None
        if app:return app
    key=value.removesuffix('.desktop').casefold()
    if not key:return None
    for app in Gio.AppInfo.get_all():
        if not isinstance(app,Gio.DesktopAppInfo):continue
        if key in aliases(app):return app
    return None


def aliases(app):
    values=[app.get_id(),app.get_id().removesuffix('.desktop'),app.get_startup_wm_class() or '',Path(app.get_executable() or '').name]
    return {value for value in values if value}|{value.casefold() for value in values if value}


def matches(app,row):
    return row.get('app_id','').casefold() in aliases(app)


def icon_css(icon,size,theme_name=''):
    if isinstance(icon,Gio.FileIcon):return 'url('+json.dumps(icon.get_file().get_uri())+')'
    if theme_name:
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk
        theme=Gtk.IconTheme.new();theme.set_custom_theme(theme_name)
        info=theme.lookup_by_gicon(icon or Gio.ThemedIcon.new('application-x-executable'),size,0)
        if info and info.get_filename():return 'url('+json.dumps(Path(info.get_filename()).as_uri())+')'
    names=icon.get_names() if isinstance(icon,Gio.ThemedIcon) else []
    return '-gtk-icontheme('+json.dumps(names[0] if names else 'application-x-executable')+')'
