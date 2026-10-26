"""Isolated desktop integration test; all hardware and playback commands are mocked."""
import configparser
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zlib

repo=Path(__file__).resolve().parent.parent
os.chdir(repo)
build=Path(os.environ.get("MADWAY_TEST_BUILD_DIR", repo / "build"))
with tempfile.TemporaryDirectory(prefix="mw-desktop-") as tmp:
    root=Path(tmp);runtime=root/"r";runtime.mkdir(mode=0o700)
    home=root/"home";home.mkdir()
    config_home=root/"config";(config_home/"madway").mkdir(parents=True)
    config_path=config_home/"madway/settings.ini"
    # Playback is mocked: these placeholders exercise explicit sound paths only.
    sounds=root/"sounds";sounds.mkdir()
    for event in ("startup", "logout", "shutdown"):
        (sounds/(event+".ogg")).write_bytes(b"mock audio fixture")
    config_path.write_text('[appearance]\ntitle_height=18\ntile_gap=2\n[sounds]\nenabled=true\nvolume=0.1\n'+
        ''.join(f'{event}={sounds / (event+".ogg")}\n' for event in ("startup", "logout", "shutdown")))
    bin_dir=root/"bin";bin_dir.mkdir()
    hardware=root/"hardware.json";hardware.write_text(json.dumps(dict(volume=50,mute=False,brightness=50)))
    audio_log=root/"audio.log"
    for name in ["wpctl","brightnessctl","pw-play","paplay"]:
        path=bin_dir/name
        path.write_text('#!'+sys.executable+'\n'+f'''
import json,sys
from pathlib import Path
name=Path(sys.argv[0]).name
p=Path({str(hardware)!r});state=json.loads(p.read_text());args=sys.argv[1:]
if name in ('pw-play','paplay'):
    with Path({str(audio_log)!r}).open('a') as log:log.write(' '.join(args)+'\\n')
elif name=='wpctl':
    if args[0]=='get-volume':print('Volume: %.2f'% (state['volume']/100)+(' [MUTED]' if state['mute'] else ''))
    elif args[0]=='set-mute':state['mute']=not state['mute']
    elif args[0]=='set-volume':
        value=args[-1]
        state['volume']=min(100,max(0,state['volume']+5 if value=='5%+' else state['volume']-5 if value=='5%-' else int(value.rstrip('%'))))
elif name=='brightnessctl':
    if args[0]=='get':print(state['brightness'])
    elif args[0]=='max':print(100)
    elif args[0]=='set':state['brightness']=int(args[-1].rstrip('%'))
p.write_text(json.dumps(state))
''')
        path.chmod(0o700)
    marker=root/"launched"
    fixture=bin_dir/"madway-fixture"
    fixture.write_text('#!/bin/sh\nprintf "%s\\n" "$WAYLAND_DISPLAY" >> "'+str(marker)+'"\n')
    fixture.chmod(0o700)
    data_home=root/"data";(data_home/"applications").mkdir(parents=True)
    (data_home/"applications/madway-fixture.desktop").write_text('[Desktop Entry]\nType=Application\nName=Madway Fixture\nExec='+str(fixture)+'\nTerminal=false\n')
    probe = root / "desktop-probe.so"
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs",
        "wlroots-0.20", "wayland-server", "xkbcommon"], text=True).split()
    subprocess.run([os.environ.get("CC", "cc"), "-shared", "-fPIC", "-DWLR_USE_UNSTABLE",
        "-Isrc", "-I" + str(build / "protocols"), "tests/desktop_probe.c", "-o", str(probe),
        *flags, "-ldl"], check=True)
    ready=root/"go"
    env=os.environ.copy()
    env.update(HOME=str(home),XDG_CONFIG_HOME=str(config_home),XDG_DATA_HOME=str(data_home),
        XDG_RUNTIME_DIR=str(runtime),WLR_BACKENDS='headless',WLR_RENDERER='pixman',MADWAY_SESSION='1',
        PATH=str(bin_dir)+':'+env['PATH'],MADWAY_LAUNCH_TEST_READY=str(ready))
    env.pop('DISPLAY',None)
    server_env=env.copy();server_env['LD_PRELOAD']=str(probe)
    if os.environ.get('MADWAY_TEST_LIBASAN'):
        server_env['LD_PRELOAD']=os.environ['MADWAY_TEST_LIBASAN']+':'+str(probe)
    log_path=root/"server.log";server=None
    def wait_for(predicate,seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return
            if server is not None and server.poll() is not None:break
            time.sleep(.03)
        raise AssertionError(log_path.read_text())
    def control(name,**values):
        command=[str(repo/'scripts/madway-shell'),'action',name]
        if 'value' in values:command+=['--value',str(values['value'])]
        subprocess.run(command,env=env,check=True,timeout=5)
    try:
        with log_path.open('w') as log:
            server=subprocess.Popen([str(build / 'madway')],env=server_env,stdout=log,stderr=log)
            wait_for(lambda:'desktop services ready' in log_path.read_text())
            match=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',log_path.read_text());assert match
            env['WAYLAND_DISPLAY']=match.group(1)
            wait_for(lambda:'Desktop layer mapped: wallpaper' in log_path.read_text())
            info=subprocess.check_output(['gdbus','call','--session','--dest','org.freedesktop.Notifications','--object-path','/org/freedesktop/Notifications','--method','org.freedesktop.Notifications.GetServerInformation'],env=env,text=True)
            assert 'mako' in info.lower(),info
            subprocess.run(['notify-send','madway application test','A real notification on the private session bus'],env=env,check=True,timeout=5)
            wait_for(lambda:'Desktop layer mapped: notifications' in log_path.read_text() or 'Desktop layer mapped: mako' in log_path.read_text())
            ready.touch()
            wait_for(lambda:'RUN LAUNCHER PASS' in log_path.read_text(),12)
            wait_for(lambda:'APP LAUNCHER PASS' in log_path.read_text(),12)
            wait_for(lambda:'SETTINGS WINDOW AND MEDIA KEYS PASS' in log_path.read_text(),12)
            wait_for(lambda:json.loads(hardware.read_text())['volume']==55 and json.loads(hardware.read_text())['brightness']==55)
            assert marker.read_text().splitlines()==[env['WAYLAND_DISPLAY']]*2
            control('volume-mute')
            wait_for(lambda:json.loads(hardware.read_text())['mute'])
            # A tiny test image exercises the external wallpaper process replacement.
            def chunk(name,data):return struct.pack('!I',len(data))+name+data+struct.pack('!I',zlib.crc32(name+data)&0xffffffff)
            png=root/'wallpaper.png'
            png.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',2,2,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes([34,68,102])*2)*2))+chunk(b'IEND',b''))
            config=configparser.ConfigParser(interpolation=None);config.read(config_path)
            config['appearance'].update(title_height='16',tile_gap='4')
            config['wallpaper']={'path':str(png),'mode':'fill','color':'#121418'}
            with config_path.open('w') as file:config.write(file)
            control('apply')
            wait_for(lambda:'LIVE SETTINGS RELOAD PASS' in log_path.read_text())
            wait_for(lambda:'OVERLAY FOCUS RESTORED PASS' in log_path.read_text())
            control('shutdown-sound')
            wait_for(lambda:audio_log.exists() and 'shutdown.ogg' in audio_log.read_text())
            assert 'startup.ogg' in audio_log.read_text()
            server.send_signal(signal.SIGTERM);server.wait(timeout=5)
            assert server.returncode==0,log_path.read_text()
            assert 'logout.ogg' in audio_log.read_text()
        print(log_path.read_text())
        print('PASS: private Mako notifications, swaybg, both Wofi launchers with keyboard input, real settings GUI, media-key indicators with mocked hardware, live config reload, and all three sound events with mocked playback.')
    finally:
        if server is not None and server.poll() is None:
            server.send_signal(signal.SIGTERM)
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        if server is not None and server.returncode:
            print(log_path.read_text())
