"""Exercise agent selection/lifetime with fake processes; no host authentication."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time
from unittest.mock import patch

repo = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('madway_auth', repo/'scripts/madway_auth.py')
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)
Desktop = runpy.run_path(str(repo/'scripts/madway-shell'))['Desktop']

if '--private-bus' in sys.argv:
    # Run this branch only under dbus-run-session; it owns a test name on that
    # private bus and never talks to the system authentication authority.
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    assert not auth.kde_agent_running()
    reply = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
        'org.freedesktop.DBus', 'RequestName', GLib.Variant('(su)', (auth.KDE_BUS_NAME, 4)),
        GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 1000, None)
    assert reply.unpack()[0] == 1 and auth.kde_agent_running()
    bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
        'org.freedesktop.DBus', 'ReleaseName', GLib.Variant('(s)', (auth.KDE_BUS_NAME,)),
        GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 1000, None)
    assert not auth.kde_agent_running()

with tempfile.TemporaryDirectory(prefix='madway-auth-test-') as tmp:
    root = Path(tmp)
    executable = root/'fake-agent'
    executable.write_text('''#!/usr/bin/env python3
import json,os,time
from pathlib import Path
Path(os.environ['MADWAY_AUTH_TEST_OUTPUT']).write_text(json.dumps({name:os.environ.get(name)
    for name in ('QT_QPA_PLATFORM','GDK_BACKEND','WAYLAND_DISPLAY','GIO_USE_VFS')}))
time.sleep(30)
''')
    executable.chmod(0o755)
    output = root/'environment.json'
    desktop = Desktop.__new__(Desktop)
    desktop.native = False
    desktop.children = {}
    # Nested sessions never even inspect the host's agent registration.
    with patch.object(auth, 'kde_agent_running', side_effect=AssertionError('host bus inspected')):
        auth.start_agent(desktop)
    desktop.native = True
    with patch.object(auth, 'kde_agent_running', return_value=True), \
         patch.object(auth, 'agent_path', side_effect=AssertionError('duplicate agent launched')):
        auth.start_agent(desktop)
    with patch.object(auth, 'kde_agent_running', return_value=False), \
         patch.object(auth, 'agent_path', return_value=None), contextlib.redirect_stderr(io.StringIO()) as errors:
        auth.start_agent(desktop)
        assert 'no Polkit authentication agent' in errors.getvalue()
    with patch.object(auth, 'AGENTS', (('not-on-path', (str(root/'absent'), str(executable))),)), \
         patch.object(auth.shutil, 'which', return_value=None), \
         patch.object(auth, 'kde_agent_running', return_value=False), \
         patch.dict(os.environ, {'MADWAY_AUTH_TEST_OUTPUT':str(output), 'QT_QPA_PLATFORM':'xcb',
                                'GDK_BACKEND':'x11', 'WAYLAND_DISPLAY':'wayland-fixture'}):
        assert auth.agent_path() == str(executable)
        try:
            auth.start_agent(desktop)
            process = desktop.children['authentication-agent']
            auth.start_agent(desktop)
            assert desktop.children['authentication-agent'] is process
            deadline = time.monotonic()+3
            while not output.exists() and time.monotonic()<deadline:
                time.sleep(.01)
            data = json.loads(output.read_text())
            assert data['QT_QPA_PLATFORM'] == data['GDK_BACKEND'] == 'wayland'
            assert data['WAYLAND_DISPLAY'] == 'wayland-fixture'
            assert data['GIO_USE_VFS'] == os.environ.get('GIO_USE_VFS')
            assert os.environ['QT_QPA_PLATFORM'] == 'xcb'
        finally:
            desktop.terminate('authentication-agent')
        assert process.poll() is not None and not desktop.children
    with patch.object(auth, 'AGENTS', (('on-path', ()),)), \
         patch.object(auth.shutil, 'which', return_value=str(executable)):
        assert auth.agent_path() == str(executable)
    with patch.object(auth, 'agent_path', return_value=str(executable)), \
         patch.object(auth, 'kde_agent_running', return_value=False), \
         patch.object(desktop, 'spawn', side_effect=PermissionError('fixture permission failure')), \
         contextlib.redirect_stderr(io.StringIO()) as errors:
        auth.start_agent(desktop)
        assert 'could not start Polkit' in errors.getvalue()
print('PASS: native-only authentication agent, existing-agent detection, discovery, Wayland environment, duplicate suppression, failure handling and child cleanup.')
