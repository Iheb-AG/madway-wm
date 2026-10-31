"""Actual Eau frames and menus on a private headless display; no host input."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import signal
import socket
import subprocess
import tempfile
import time

repo=Path(__file__).resolve().parent.parent
os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-eau-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_RUNTIME_DIR':str(runtime),
        'WLR_BACKENDS':'headless','WLR_RENDERER':'pixman','MADWAY_SESSION':'1','LIBGL_ALWAYS_SOFTWARE':'1',
        'GIO_USE_VFS':'local','MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery')}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(key,None)
    cfg=configparser.ConfigParser(interpolation=None)
    cfg.read_dict({'input':{'repeat_rate':'31'},'notifications':{'enabled':'false'},
        'output:HEADLESS-1':{'mode':'1280x800@60000'}})
    with (config/'madway/settings.ini').open('w') as output:cfg.write(output)
    subprocess.run(['scripts/madway-shell','preset','gershwin'],env=env,check=True)
    cfg.read(config/'madway/settings.ini')
    assert cfg.getint('input','repeat_rate')==31
    assert cfg.getint('panel','height')==22 and cfg.getint('appearance','title_height')==22
    image=Path(cfg.get('wallpaper','path'))
    assert image.is_file(),'This visual test requires the local Abstract Blue wallpaper; see docs/GERSHWIN.md.'
    assert hashlib.sha256(image.read_bytes()).hexdigest()=='7cd68b324a5759df01f267ac8fbd938ddcbf40a1c4e59335079fb24caf0c59d7'
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','tests/gershwin_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    processes=[];logs=[]
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
    def wait(predicate,timeout=15):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():return
            assert processes[0].poll() is None,(root/'server.log').read_text()
            time.sleep(.05)
        raise AssertionError((root/'server.log').read_text())
    def text():return (root/'server.log').read_text()
    try:
        spawn('server',['./build/madway'],{**env,'LD_PRELOAD':str(probe),'MADWAY_EAU_TEST_GO':str(root/'go')})
        wait(lambda:'desktop services ready' in text() and 'Desktop layer mapped: madway-panel' in text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        client=spawn('kitty',['kitty','--config','NONE','--title','eau-client','-o','linux_display_server=wayland',
            '-o','confirm_os_window_close=0','/bin/sh','-c','printf "Gershwin / Eau desktop preview\\n\\nAlt+Tab restores minimized windows\\n"; sleep 60'])
        wait(lambda:'Window mapped: eau-client' in text())
        time.sleep(1.2)
        screenshot=repo/'build/gershwin-preview.png'
        subprocess.run(['grim','-o','HEADLESS-1',str(screenshot)],env=env,check=True)
        # Test every edge with the actual 13px type and 22px panel.
        ui=root/'ui.py'
        ui.write_text('''import runpy
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
api=runpy.run_path(SCRIPT)
provider=Gtk.CssProvider();provider.load_from_data(api['api']['theme_style'](api['CSS'].decode()).encode())
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
bar=api['TopBar']();errors=[]
def inspect():
    try:
        for instance in bar.bars:
            window=instance['window'];vertical=instance['vertical']
            assert (window.get_allocated_width() if vertical else window.get_allocated_height())==22
            assert api['Layer'].get_exclusive_zone(window)==22
            for widget in instance['buttons']:
                if widget.get_visible():assert (widget.get_allocated_width() if vertical else widget.get_allocated_height())<=22
    except BaseException as error:errors.append(error)
    for instance in bar.bars:instance['window'].destroy()
    bar.bars.clear();Gtk.main_quit();return False
for position in ('top','bottom','left','right'):
    bar.config['panel']['position']=position;bar.rebuild()
    GLib.timeout_add(180,inspect);Gtk.main()
if errors:raise errors[0]
print('EAU FOUR EDGE PANEL DIMENSIONS PASS')
'''.replace('SCRIPT',repr(str(repo/'scripts/madway-panel'))))
        subprocess.run(['python3',str(ui)],env=env,check=True,timeout=12)
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(json.dumps(dict(action='panel-menu',page='Desktop',x=0,y=22,edge='top')).encode(),
                str(runtime/('madway-'+env['WAYLAND_DISPLAY'])/'control.sock'))
        wait(lambda:'Desktop layer mapped: madway-menu' in text())
        time.sleep(.3)
        subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build/gershwin-menu-preview.png')],env=env,check=True)
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(b'{"action":"close-menu"}',str(runtime/('madway-'+env['WAYLAND_DISPLAY'])/'control.sock'))
        settings=spawn('settings',['scripts/madway-shell','settings','--page','Appearance'])
        wait(lambda:'Window mapped: madway — Settings' in text())
        time.sleep(.6)
        subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build/gershwin-settings-preview.png')],env=env,check=True)
        settings.terminate();settings.wait(timeout=4)
        time.sleep(.3);(root/'go').touch()
        wait(lambda:'EAU TRANSPARENT CORNERS GRADIENT HOVER MINIMIZE ALTTAB MAXIMIZE AND CLOSE PASS' in text())
        client.wait(timeout=5);assert client.returncode==0
        assert 'Traceback (most recent call last)' not in text(),text()
        print('EAU PRESET, ORIGINAL WALLPAPER, FRAMES, MENUS, HOVER AND WINDOW CONTROLS PASS')
        print('Previews:',screenshot)
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-8000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.send_signal(signal.SIGTERM)
        for process in reversed(processes):
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
