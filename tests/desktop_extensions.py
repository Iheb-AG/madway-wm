"""Focused settings/calendar/confirmation tests in a disposable Wayland session."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
repo=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='madway-extensions-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    (config/'madway/settings.ini').write_text('[session_effects]\nopening=false\n[appearance]\ntheme=argent-dark\n[dock]\nenabled=false\n[desktop]\nicons=false\n[notifications]\nenabled=false\n[wallpaper]\ntype=color\ncolor=#131820\n')
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
        'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_RENDERER':'pixman','MADWAY_SESSION':'1',
        'LIBGL_ALWAYS_SOFTWARE':'1','GDK_BACKEND':'wayland','GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),
        'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery')}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','LD_PRELOAD'):env.pop(key,None)
    with (root/'server.log').open('w') as log:
        server=subprocess.Popen([os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],env=env,stdout=log,stderr=log)
        try:
            deadline=time.monotonic()+10
            while True:
                text=(root/'server.log').read_text()
                assert server.poll() is None,text
                if 'desktop services ready' in text:break
                if time.monotonic()>deadline:raise AssertionError(text)
                time.sleep(.03)
            env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text)[1]
            subprocess.run([sys.executable,str(repo/'tests'/os.environ.get('MADWAY_EXTENSION_UI','desktop_extensions_ui.py'))],env=env,check=True,timeout=35)
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        assert server.returncode==0,(root/'server.log').read_text()
