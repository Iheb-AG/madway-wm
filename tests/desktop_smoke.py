"""Isolated desktop integration test; all hardware and playback commands are mocked."""
import configparser
import json
import os
from pathlib import Path
import re
import signal
import socket
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
    config_path.write_text('[desktop]\nicons=false\n[dock]\nenabled=false\n[appearance]\ntitle_height=18\ntile_gap=2\n[sounds]\nenabled=true\nvolume=0.1\n'+
        ''.join(f'{event}={sounds / (event+".ogg")}\n' for event in ("startup", "logout", "shutdown")))
    bin_dir=root/"bin";bin_dir.mkdir()
    hardware=root/"hardware.json";hardware.write_text(json.dumps(dict(volume=50,mute=False,brightness=50)))
    power_root=root/'power';power_root.mkdir()
    def power_device(name,**values):
        path=power_root/name;path.mkdir(exist_ok=True)
        for key,value in values.items():(path/key).write_text(str(value))
    power_device('AC',type='Mains',online=0)
    power_device('BAT0',type='Battery',present=1,capacity=80,status='Discharging',energy_now=8000000,energy_full=10000000,power_now=1000000)
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
    pactl=bin_dir/'pactl'
    pactl.write_text('#!'+sys.executable+'\n'+"""
import json,sys
args=sys.argv[1:]
if args[-1]=='info':print(json.dumps(dict(default_sink_name='fixture',default_source_name='fixture')))
elif 'list' in args:
    print(json.dumps([dict(index=7,name='fixture',description='Fixture audio',properties={'application.name':'Fixture player'},
        volume={'mono':{'value_percent':'50%'}},mute=False)]))
else:
    from pathlib import Path
    path=Path(HARDWARE)
    state=json.loads(path.read_text());state['audio_command']=args;path.write_text(json.dumps(state))
""")
    pactl.write_text(pactl.read_text().replace('HARDWARE',repr(str(hardware))))
    pactl.chmod(0o700)
    kitty=bin_dir/"konsole"
    kitty.write_text('#!/bin/sh\nexec /usr/bin/kitty --config NONE --title floating-fixture -o linux_display_server=wayland -o confirm_os_window_close=0 /bin/sh -c "sleep 30"\n')
    kitty.chmod(0o700)
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
        XDG_RUNTIME_DIR=str(runtime),WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman',LIBGL_ALWAYS_SOFTWARE='1',MADWAY_SESSION='1',
        PATH=str(bin_dir)+':'+env['PATH'],MADWAY_POWER_SUPPLY_PATH=str(power_root),MADWAY_LAUNCH_TEST_READY=str(ready),MADWAY_TEST_HOTPLUG=str(root/'hotplug'),MADWAY_TEST_MENU_READY=str(root/'menu-ready'),MADWAY_TEST_FEATURES_READY=str(root/'features-ready'))
    env.pop('DISPLAY',None)
    env.pop('MADWAY_NATIVE',None)
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
        if any(key != 'value' for key in values):
            path=runtime/('madway-'+env['WAYLAND_DISPLAY'])/'control.sock'
            with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
                channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(path))
            return
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
            wait_for(lambda:any(path.stat().st_size>8 for path in home.rglob('madway-*.png')))
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
            wait_for(lambda:'FLOATING DEFAULT AND SHORTCUTS PASS' in log_path.read_text(),12)
            config['input']={'modifier':'super','repeat_rate':'40','repeat_delay':'250'}
            with config_path.open('w') as file:config.write(file)
            control('apply')
            wait_for(lambda:'LIVE INPUT SETTINGS PASS' in log_path.read_text())
            outputs_file=runtime/('madway-'+env['WAYLAND_DISPLAY'])/'outputs.json'
            def outputs():return json.loads(outputs_file.read_text())
            initial=outputs()['outputs'];assert len(initial)==2
            first,second=[output['name'] for output in initial]
            config['output:'+first]={'enabled':'true','x':'0','y':'0','scale':'1','transform':'0','mode':'640x480@60000'}
            config['output:'+second]={'enabled':'true','x':'640','y':'0','scale':'1','transform':'0','mode':'800x600@60000'}
            def apply_config():
                with config_path.open('w') as file:config.write(file)
                control('apply')
            apply_config()
            wait_for(lambda:all(item['width'] in (640,800) for item in outputs()['outputs']))
            assert not outputs()['error'],outputs()
            config['output:'+second].update(scale='2',transform='1',x='0',y='480')
            apply_config()
            wait_for(lambda:any(item['name']==second and item['scale']==2 and item['transform']==1 and item['y']==480 for item in outputs()['outputs']))
            config['output:'+first]['enabled']='false'
            apply_config()
            wait_for(lambda:sum(item['enabled'] for item in outputs()['outputs'])==1)
            config['output:'+second]['enabled']='false'
            apply_config()
            wait_for(lambda:bool(outputs()['error']))
            assert sum(item['enabled'] for item in outputs()['outputs'])==1
            config['output:'+first]['enabled']='true'
            config['output:'+second].update(enabled='true',scale='1',transform='0',x='640',y='0')
            apply_config()
            wait_for(lambda:sum(item['enabled'] for item in outputs()['outputs'])==2 and not outputs()['error'])
            (root/'hotplug').touch()
            wait_for(lambda:len(outputs()['outputs'])==3)
            config['output:'+first]['enabled']='false'
            config['output:'+second]['enabled']='false'
            apply_config()
            wait_for(lambda:sum(item['enabled'] for item in outputs()['outputs'])==1 and not outputs()['error'])
            (root/'hotplug').unlink()
            wait_for(lambda:'OUTPUT HOTPLUG AND WINDOW RECOVERY PASS' in log_path.read_text())
            wait_for(lambda:len(outputs()['outputs'])==2)
            assert any(item['enabled'] for item in outputs()['outputs'])
            config['output:'+first]['enabled']='true'
            config['output:'+second]['enabled']='true'
            apply_config()
            wait_for(lambda:sum(item['enabled'] for item in outputs()['outputs'])==2)
            print('PASS: two monitor profiles, modes, positions, scale/rotation, disable/re-enable, and rejection of all-disabled configuration.')
            subprocess.run([sys.executable,str(repo/'tests/settings_ui.py')],env=env,check=True,timeout=12)
            wait_for(lambda:'NEW WINDOW POLICY SETTINGS PASS' in log_path.read_text(),12)
            mako_config=outputs_file.parent/'mako.conf'
            wait_for(lambda:'anchor=bottom-left' in mako_config.read_text() and 'width=360' in mako_config.read_text())
            wait_for(lambda:'DESKTOP MENU ACTION AND FULLSCREEN PANEL PASS' in log_path.read_text())
            control('workspace',value=1)
            desktop_file=outputs_file.parent/'desktop.json'
            wait_for(lambda:json.loads(desktop_file.read_text())['workspace']==1)
            control('workspace',value=0)
            wait_for(lambda:json.loads(desktop_file.read_text())['workspace']==0)
            assert 'Traceback (most recent call last)' not in log_path.read_text(),log_path.read_text()
            config.read(config_path)
            config['panel']['enabled']='false';apply_config()
            wait_for(lambda:'PANEL TOGGLE OFF PASS' in log_path.read_text())
            config['panel'].update(enabled='true',height='22');apply_config()
            wait_for(lambda:'PANEL HEIGHT RELOAD PASS' in log_path.read_text())
            print('PASS: desktop right-click menu/window action, fullscreen panel hiding, and workspace controls.')
            subprocess.run([sys.executable,str(repo/'tests/panel_ui.py')],env=env,check=True,timeout=20)
            rows=json.loads(desktop_file.read_text())['windows']
            assert rows, 'Expected a real application for minimize/restore'
            identity=rows[0]['id']
            control('switcher-select',id=identity)
            wait_for(lambda:any(row['id']==identity and row['focused'] for row in json.loads(desktop_file.read_text())['windows']))
            control('window-minimize')
            wait_for(lambda:any(row['id']==identity and row['minimized'] for row in json.loads(desktop_file.read_text())['windows']))
            control('switcher-select',id=identity)
            wait_for(lambda:any(row['id']==identity and row['focused'] and not row['minimized'] for row in json.loads(desktop_file.read_text())['windows']))
            print('PASS: real application minimize and panel restoration action.')
            for values, expected in [
                (dict(kind='sink-input',id=7,operation='volume',value=160), ['set-sink-input-volume','7','100%']),
                (dict(kind='source',id=7,operation='mute',value=True), ['set-source-mute','7','1']),
                (dict(kind='sink',id=7,operation='default'), ['set-default-sink','7'])]:
                control('audio-control',**values)
                wait_for(lambda:json.loads(hardware.read_text()).get('audio_command')==expected)
            print('PASS: mixer IPC volume limiting, microphone mute and default-output selection (mocked server).')
            (root/'menu-ready').touch()
            control('panel-menu',page='Audio',x=10,y=24)
            wait_for(lambda:'AUDIO DROPDOWN IPC PASS' in log_path.read_text())
            time.sleep(.15)
            control('panel-menu',page='Clock',x=10,y=24)
            wait_for(lambda:'CLOCK DROPDOWN IPC PASS' in log_path.read_text())
            assert 'Traceback (most recent call last)' not in log_path.read_text(),log_path.read_text()
            script=root/'workflow.madway'
            script.write_text('theme terminal\nbackground color #102030\nset input.focus_follows_mouse true\n')
            subprocess.run([str(repo/'scripts/madway-script'),str(script),'--check'],env=env,check=True)
            subprocess.run([str(repo/'scripts/madway-script'),str(script)],env=env,check=True)
            wait_for(lambda:'#b8dac0' in mako_config.read_text() and '#102030' in config_path.read_text())
            config.read(config_path)
            assert config['appearance']['theme']=='terminal'
            assert config['wallpaper']['type']=='color' and config['wallpaper']['color']=='#102030'
            (root/'features-ready').touch()
            wait_for(lambda:'VISIBLE SWITCHER CYCLE CANCEL AND COMMIT PASS' in log_path.read_text(),12)
            assert 'DIRECTIONAL TILE SHORTCUTS PASS' in log_path.read_text()
            assert 'OPTIONAL POINTER FOCUS AND REBASE GUARD PASS' in log_path.read_text()
            print('PASS: theme/background scripting, directional tiling, optional hover focus and visible window switcher.')
            wait_for(lambda:'TILED SHARED EDGE AND MODIFIER RESIZE PASS' in log_path.read_text(),12)
            assert 'KEEP ABOVE STACKING INPUT FULLSCREEN AND WORKSPACE PASS' in log_path.read_text()
            control('window-above');wait_for(lambda:json.loads(desktop_file.read_text()).get('keep_above') is True)
            control('window-above');wait_for(lambda:json.loads(desktop_file.read_text()).get('keep_above') is False)
            for position in ('top','bottom','left','right','top'):
                config.read(config_path);config['panel']['position']=position;apply_config()
                wait_for(lambda:'PANEL EDGE '+position+' RESERVATION PASS' in log_path.read_text())
            print('PASS: always-above stacking/input/fullscreen, tiled resizing, and all four panel-edge reservations.')
            # Real Mako receives power alerts; only the private fake sysfs is modified.
            power_file=outputs_file.parent/'power.json'
            def power_summary():
                return subprocess.check_output(['makoctl','list'],env=env,text=True)
            power_device('BAT0',capacity=18,energy_now=1800000)
            control('power-refresh')
            wait_for(lambda:json.loads(power_file.read_text()).get('percent')==18)
            wait_for(lambda:'Battery low' in power_summary())
            power_device('BAT0',capacity=9,energy_now=900000)
            control('power-refresh')
            wait_for(lambda:'Battery critical' in power_summary())
            power_device('AC',online=1);power_device('BAT0',status='Charging')
            control('power-refresh')
            wait_for(lambda:json.loads(power_file.read_text()).get('status')=='Charging')
            try:wait_for(lambda:'Battery critical' not in power_summary())
            except AssertionError:
                print('POWER NOTIFICATIONS STILL OPEN:',power_summary())
                raise
            print('PASS: live battery snapshot, real low/critical notifications and dismissal on charging using fake power supplies.')
            control('shutdown-sound')
            wait_for(lambda:audio_log.exists() and 'shutdown.ogg' in audio_log.read_text())
            assert 'startup.ogg' in audio_log.read_text()
            server.send_signal(signal.SIGTERM);server.wait(timeout=5)
            assert server.returncode==0,log_path.read_text()
            assert 'logout.ogg' in audio_log.read_text()
        print(log_path.read_text())
        # Restart the same temporary session to verify saved monitor profiles.
        (config_home/'madway/startup.madway').write_text('exec madway-fixture\n')
        restart_path=root/'restart.log'
        with restart_path.open('w') as restart_log:
            server=subprocess.Popen([str(build/'madway')],env=env,stdout=restart_log,stderr=restart_log)
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if outputs_file.exists() and 'desktop services ready' in restart_path.read_text():break
                assert server.poll() is None,restart_path.read_text()
                time.sleep(.03)
            else:raise AssertionError(restart_path.read_text())
            wait_for(lambda:len(marker.read_text().splitlines())==3)
            restored=json.loads(outputs_file.read_text())
            assert not restored['error'] and len(restored['outputs'])==2,restored
            by_name={output['name']:output for output in restored['outputs']}
            assert by_name[first]['width']==640 and by_name[first]['x']==0
            assert by_name[second]['width']==800 and by_name[second]['x']==640
            server.send_signal(signal.SIGTERM);server.wait(timeout=5)
            assert server.returncode==0,restart_path.read_text()
        print('PASS: monitor profiles restored and opt-in startup script executed after compositor restart.')
        print('PASS: private Mako notifications, swaybg, both Wofi launchers with keyboard input, real settings GUI, media-key indicators with mocked hardware, live config reload, and all three sound events with mocked playback.')
    finally:
        if server is not None and server.poll() is None:
            server.send_signal(signal.SIGTERM)
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        if server is not None and server.returncode:
            print(log_path.read_text())
