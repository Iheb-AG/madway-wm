"""Capture actual madway/Kitty/Firefox/settings in an isolated, asset-free session."""
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
target=repo/'docs/screenshots';target.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='madway-capture-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    (config/'madway/settings.ini').write_text('[sounds]\nenabled=false\n[panel]\nmetrics=false\n[output:HEADLESS-1]\nmode=1600x1000@60000\n')
    profile=root/'firefox';profile.mkdir()
    (profile/'user.js').write_text('user_pref("browser.shell.checkDefaultBrowser",false);\nuser_pref("browser.aboutwelcome.enabled",false);\nuser_pref("browser.startup.homepage_override.mstone","ignore");\nuser_pref("datareporting.policy.dataSubmissionEnabled",false);\nuser_pref("toolkit.telemetry.enabled",false);\n')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','tests/desktop_capture_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    env=os.environ.copy();env.update(HOME=tmp,XDG_CONFIG_HOME=str(config),XDG_RUNTIME_DIR=str(runtime),WLR_BACKENDS='headless',WLR_RENDERER='pixman',
        MADWAY_SESSION='1',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',MOZ_ENABLE_WAYLAND='1',TZ='Africa/Tunis')
    for name in ('DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(name,None)
    # Audio rows are deterministic fixtures; never expose/control the host server.
    binaries=root/'bin';binaries.mkdir()
    pactl=binaries/'pactl'
    pactl.write_text('#!'+sys.executable+'\n'+"""
import json,sys
args=sys.argv[1:]
if args[-1]=='info':print(json.dumps(dict(default_sink_name='speakers',default_source_name='mic')))
elif 'list' in args:
    rows={'sinks':[(1,'speakers','Built-in speakers',55)],'sources':[(2,'mic','Built-in microphone',70)],
          'sink-inputs':[(3,'browser','Firefox · media playback',40)],'source-outputs':[]}[args[-1]]
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
        server=spawn('server',['./build/madway'],{**env,'LD_PRELOAD':str(probe),'MADWAY_CAPTURE_MENU':str(root/'menu'),'MADWAY_CAPTURE_AUDIO':str(root/'audio'),'MADWAY_CAPTURE_SWITCHER':str(root/'switcher')})
        wait(lambda:'desktop services ready' in server_text() and 'Desktop layer mapped: madway-panel' in server_text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',server_text()).group(1)
        spawn('terminal',['kitty','--config','NONE','--title','madway terminal','-o','linux_display_server=wayland','-o','font_size=11',
            '-o','background=#000000','-o','foreground=#c8c8c8','-o','cursor=#cccccc','-o','confirm_os_window_close=0',
            '/bin/sh','-c',
            'printf "\\033[38;5;250mmadway\\033[0m / workstation\\n\\n$ cmake --build build | tail -1\\n"; cmake --build build | tail -1; '
            'printf "\\n$ ./build/madway --version\\n"; ./build/madway --version; '
            'printf "\\n$ ls src\\n"; ls src; '
            'printf "\\nAlt+T float/tile   Alt+D applications\\nRight-click the desktop for utilities\\n\\n"; '
            'export PS1="madway $ "; exec /bin/sh -i'])
        wait(lambda:'Window mapped: madway terminal' in server_text())
        spawn('browser',['firefox','--no-remote','--profile',str(profile),f'http://127.0.0.1:{http.server_port}/overview.html'])
        wait(lambda:'Firefox' in server_text(),35)
        spawn('settings',['./scripts/madway-shell','settings'])
        wait(lambda:'Window mapped: madway — Settings' in server_text())
        time.sleep(3)
        subprocess.run(['grim','-o','HEADLESS-1',str(target/'workstation.png')],env=env,check=True,timeout=8)
        (root/'menu').touch()
        wait(lambda:'Desktop layer mapped: madway-menu' in server_text())
        time.sleep(.5)
        subprocess.run(['grim','-c','-o','HEADLESS-1',str(target/'desktop-menu.png')],env=env,check=True,timeout=8)
        count=server_text().count('Desktop layer mapped: madway-menu')
        (root/'audio').touch()
        wait(lambda:server_text().count('Desktop layer mapped: madway-menu')>count)
        time.sleep(.8)
        subprocess.run(['grim','-c','-o','HEADLESS-1',str(target/'panel-audio.png')],env=env,check=True,timeout=8)
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            endpoint=str(runtime/('madway-'+env['WAYLAND_DISPLAY'])/'control.sock')
            channel.sendto(json.dumps({'action':'close-menu'}).encode(),endpoint)
            channel.sendto(json.dumps({'action':'launcher'}).encode(),endpoint)
        wait(lambda:'Desktop layer mapped: wofi' in server_text())
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
        print('Captured actual Kitty, Firefox, settings, top bar, and desktop menu:',target)
    except BaseException:
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
