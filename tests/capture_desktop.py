"""Capture actual madway/Konsole/Firefox/settings in an isolated, asset-free session."""
import argparse
import cairo
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
import json
import socket
import sys
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
import time

repo=Path(__file__).resolve().parent.parent
os.chdir(repo)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--theme',choices=('argent','argent-dark','prism-glass'),default='argent-dark')
parser.add_argument('--output-dir',type=Path,default=repo/'docs/screenshots')
parser.add_argument('--hero-only',action='store_true',help='Capture only the workstation composition')
args=parser.parse_args()
target=args.output_dir.resolve();target.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='madway-capture-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    # Original generated fixture, never the user's ignored wallpaper/media.
    wallpaper=root/'background.png'
    surface=cairo.ImageSurface(cairo.FORMAT_RGB24,1600,1000);cr=cairo.Context(surface)
    gradient=cairo.LinearGradient(0,0,1600,1000)
    stops=((0,(.12,.29,.40)),(.5,(.17,.39,.43)),(1,(.33,.24,.38)))
    for offset,color in stops:gradient.add_color_stop_rgb(offset,*color)
    cr.set_source(gradient);cr.paint();cr.set_line_width(160)
    for y in (180,520,860):
        cr.move_to(-160,y);cr.curve_to(370,y-280,930,y+300,1760,y-140)
        cr.set_source_rgba(.62,.83,.88,.10);cr.stroke()
    surface.write_to_png(str(wallpaper))
    (config/'madway/settings.ini').write_text(f"""[appearance]
 theme={args.theme}
 title_height=22
[session_effects]
 opening=false
[sounds]
 enabled=false
[desktop]
 icons=false
[notifications]
 enabled=false
[power]
 show_battery=false
[panel]
 metrics=false
 height=22
 label=madway
[dock]
 enabled=true
 autohide=false
 tray=false
[wallpaper]
 type=image
 path={wallpaper}
 mode=fill
[output:HEADLESS-1]
 mode=1600x1000@60000
""".replace('\n ','\n'))
    profile=root/'firefox';profile.mkdir()
    (profile/'user.js').write_text('user_pref("browser.shell.checkDefaultBrowser",false);\nuser_pref("browser.aboutwelcome.enabled",false);\nuser_pref("browser.startup.homepage_override.mstone","ignore");\nuser_pref("datareporting.policy.dataSubmissionEnabled",false);\nuser_pref("toolkit.telemetry.enabled",false);\n')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','tests/desktop_capture_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    env=os.environ.copy();env.update(HOME=tmp,XDG_CONFIG_HOME=str(config),XDG_RUNTIME_DIR=str(runtime),WLR_BACKENDS='headless',WLR_RENDERER='pixman',
        MADWAY_SESSION='1',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',MOZ_ENABLE_WAYLAND='1',TZ='Africa/Tunis',
        XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XDG_STATE_HOME=str(root/'state'),
        DBUS_SYSTEM_BUS_ADDRESS='unix:path='+str(root/'no-system-bus'),MADWAY_POWER_SUPPLY_PATH=str(root/'no-battery'),
        GDK_BACKEND='wayland',QT_QPA_PLATFORM='wayland',WLR_HEADLESS_OUTPUTS='1')
    for name in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(name,None)
    # Audio rows are deterministic fixtures; never expose/control the host server.
    binaries=root/'bin';binaries.mkdir()
    pactl=binaries/'pactl'
    pactl.write_text('#!'+sys.executable+'\n'+"""
import json,sys
args=sys.argv[1:]
if args[-1]=='info':print(json.dumps(dict(default_sink_name='speakers',default_source_name='mic')))
elif 'list' in args:
    rows={'sinks':[(1,'speakers','Built-in speakers',55)],'sources':[(2,'mic','Built-in microphone',70)],
          'sink-inputs':[(3,'browser','Firefox · media playback',40)],'source-outputs':[],'cards':[]}[args[-1]]
    print(json.dumps([dict(index=i,name=n,description=d,properties={},volume={'mono':{'value_percent':str(v)+'%'}},mute=False) for i,n,d,v in rows]))
else:raise SystemExit('Capture audio is read-only')
""")
    pactl.chmod(0o700)
    env['PATH']=str(binaries)+':'+env['PATH']
    processes=[];logs=[]
    def spawn(name,arguments,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(arguments,env=environment,stdout=log,stderr=log);processes.append(process);return process
    def wait(predicate,timeout=20):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():return
            assert processes[0].poll() is None,(root/'server.log').read_text()
            time.sleep(.1)
        raise AssertionError((root/'server.log').read_text())
    def server_text():return (root/'server.log').read_text()
    http=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(repo/'tests/fixtures')))
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
        server=spawn('server',['./build/madway'],{**env,'LD_PRELOAD':str(probe),'MADWAY_CAPTURE_MENU':str(root/'menu'),'MADWAY_CAPTURE_QUERY':str(root/'query'),'MADWAY_CAPTURE_SWITCHER':str(root/'switcher')})
        wait(lambda:'desktop services ready' in server_text() and 'Desktop layer mapped: madway-panel' in server_text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',server_text()).group(1)
        spawn('terminal',['konsole','--separate','--builtin-profile','--hide-menubar','--hide-toolbars','--hide-tabbar',
            '-p','LocalTabTitleFormat=madway terminal','-p','Font=DejaVu Sans Mono,10',
            '-p','ColorScheme='+('BreezeLight' if args.theme=='argent' else 'Breeze'),
            '-e','/bin/sh','-c',
            'printf "madway / workstation\\n\\n$ ./build/madway --version\\n"; ./build/madway --version; '
            'printf "\\n$ ls src\\n"; ls -C -w 84 src; '
            'printf "\\nAlt+T float/tile   Alt+D applications\\nNine workspaces per monitor. Native Wayland clients.\\n\\n"; '
            'export PS1="madway $ "; exec /bin/sh -i'])
        wait(lambda:'Window mapped:' in server_text())
        spawn('browser',['firefox','--no-remote','--profile',str(profile),f'http://127.0.0.1:{http.server_port}/overview.html?theme={args.theme}'])
        wait(lambda:'Firefox' in server_text(),35)
        spawn('settings',['./scripts/madway-shell','settings','--page','Appearance'])
        wait(lambda:'Window mapped: madway — Settings' in server_text())
        time.sleep(3)
        subprocess.run(['grim','-o','HEADLESS-1',str(target/'workstation.png')],env=env,check=True,timeout=8)
        if args.hero_only:
            print('Captured',args.theme,'workstation:',target/'workstation.png')
            raise SystemExit(0)
        endpoint=str(runtime/('madway-'+env['WAYLAND_DISPLAY'])/'control.sock')
        (root/'menu').touch()
        wait(lambda:'Desktop layer mapped: madway-menu' in server_text())
        time.sleep(.5)
        subprocess.run(['grim','-c','-o','HEADLESS-1',str(target/'desktop-menu.png')],env=env,check=True,timeout=8)
        count=server_text().count('Desktop layer mapped: madway-menu')
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(json.dumps({'action':'panel-menu','page':'Audio','edge':'top','x':1420,'y':22}).encode(),endpoint)
        wait(lambda:server_text().count('Desktop layer mapped: madway-menu')>count)
        time.sleep(.8)
        subprocess.run(['grim','-c','-o','HEADLESS-1',str(target/'panel-audio.png')],env=env,check=True,timeout=8)
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            endpoint=str(runtime/('madway-'+env['WAYLAND_DISPLAY'])/'control.sock')
            channel.sendto(json.dumps({'action':'close-menu'}).encode(),endpoint)
            channel.sendto(json.dumps({'action':'launcher'}).encode(),endpoint)
        wait(lambda:'Desktop layer mapped: madway-launcher' in server_text())
        time.sleep(.3)
        (root/'query').touch()
        time.sleep(.5)
        subprocess.run(['grim','-o','HEADLESS-1',str(target/'launcher.png')],env=env,check=True,timeout=8)
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(json.dumps({'action':'launcher'}).encode(),endpoint)
        time.sleep(.2)
        (root/'switcher').touch()
        wait(lambda:'Desktop layer mapped: madway-switcher' in server_text())
        time.sleep(.3)
        subprocess.run(['grim','-o','HEADLESS-1',str(target/'switcher.png')],env=env,check=True,timeout=8)
        (root/'switcher').unlink()
        state_file=runtime/('madway-'+env['WAYLAND_DISPLAY'])/'desktop.json'
        wait(lambda:not json.loads(state_file.read_text()).get('switcher'))
        for position in ('left','bottom'):
            count=server_text().count('Desktop layer mapped: madway-panel')
            with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
                channel.sendto(json.dumps({'action':'script-config','updates':{'panel.position':position}}).encode(),endpoint)
            wait(lambda:server_text().count('Desktop layer mapped: madway-panel')>count)
            time.sleep(.5)
            subprocess.run(['grim','-o','HEADLESS-1',str(target/('panel-'+position+'.png'))],env=env,check=True,timeout=8)
        assert 'Traceback (most recent call last)' not in server_text(),server_text()
        print('Captured actual Konsole, Firefox, settings, top bar, and desktop menu:',target)
    except Exception:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-6000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=6)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
        http.shutdown();http.server_close()
