"""Use an installed desktop authentication agent; never change system policy."""
import os
from pathlib import Path
import shutil
import sys


AGENTS = (
    ('polkit-kde-authentication-agent-1', (
        '/usr/lib/polkit-kde-authentication-agent-1',
        '/usr/libexec/polkit-kde-authentication-agent-1',
        '/usr/lib/x86_64-linux-gnu/libexec/polkit-kde-authentication-agent-1')),
    ('lxqt-policykit-agent', ()),
    ('polkit-mate-authentication-agent-1', (
        '/usr/lib/mate-polkit/polkit-mate-authentication-agent-1',
        '/usr/libexec/polkit-mate-authentication-agent-1')),
    ('polkit-gnome-authentication-agent-1', (
        '/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1',
        '/usr/libexec/polkit-gnome-authentication-agent-1')),
)
KDE_BUS_NAME = 'org.kde.polkit-kde-authentication-agent-1'


def agent_path():
    for name, paths in AGENTS:
        found = shutil.which(name)
        if found:
            return found
        for path in paths:
            if Path(path).is_file() and os.access(path, os.X_OK):
                return path
    return None


def kde_agent_running():
    from gi.repository import Gio, GLib
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', (KDE_BUS_NAME,)),
            GLib.VariantType.new('(b)'), Gio.DBusCallFlags.NONE, 1000, None)
        return result.unpack()[0]
    except GLib.Error:
        return False


def start_agent(desktop):
    # A nested compositor belongs to the host login session. Its authentication
    # agent must remain under the host desktop's control.
    if not desktop.native:
        return
    existing = desktop.children.get('authentication-agent')
    if (existing is not None and existing.poll() is None) or kde_agent_running():
        return
    executable = agent_path()
    if not executable:
        print('madway: no Polkit authentication agent found; install polkit-kde-agent '
              'or another supported Wayland agent for graphical password prompts.', file=sys.stderr)
        return
    environment = os.environ.copy()
    # Do not inherit an X11-only toolkit override from login configuration.
    environment.update(QT_QPA_PLATFORM='wayland', GDK_BACKEND='wayland')
    try:
        process = desktop.spawn('authentication-agent', [executable], env=environment)
        if process:
            print(f'madway: starting Polkit authentication agent: {executable}', flush=True)
    except OSError as error:
        print(f'madway: could not start Polkit authentication agent: {error}', file=sys.stderr)
    # Agent registration itself rejects duplicates, including agents without a
    # public bus name. Do not restart rejected agents or spawn several providers.
