"""Real Waybar, task protocol, SNI tray, dark Eau and screenshots in isolation."""
import configparser
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import tempfile
import time

repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-features-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    ini=config/'madway/settings.ini'
    (config/'user-dirs.dirs').write_text('XDG_PICTURES_DIR="$HOME/Pictures"\n')
    ini.write_text('[appearance]\ntheme=gershwin-dark\ntitle_height=22\n[panel]\nheight=22\nmetrics=false\n[notifications]\nenabled=false\n[wallpaper]\ntype=color\ncolor=#142034\n')
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
         'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_RENDERER':'pixman','MADWAY_SESSION':'1','GIO_USE_VFS':'local',
         'LIBGL_ALWAYS_SOFTWARE':'1','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),'MADWAY_TEST_TRAY_FILE':str(root/'tray')}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','LD_PRELOAD'):env.pop(key,None)
    protocol=repo/'protocols/wlr-foreign-toplevel-management-unstable-v1.xml'
    subprocess.run(['wayland-scanner','client-header',str(protocol),str(root/'wlr-foreign-toplevel-management-unstable-v1-client-protocol.h')],check=True)
    subprocess.run(['wayland-scanner','private-code',str(protocol),str(root/'protocol.c')],check=True)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True).split()
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-I'+str(root),'tests/taskbar_client.c',str(root/'protocol.c'),'-o',str(root/'taskbar-client'),*flags],check=True)
    processes=[];logs=[]
    def spawn(name,args,environment=env,**kwargs):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(args,env=environment,stdout=log,stderr=log,**kwargs);processes.append(process);return process
    def text():return (root/'server.log').read_text()
    def wait(predicate,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            assert processes[0].poll() is None,text()
            time.sleep(.04)
        raise AssertionError(text())
    def send(name,**values):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
    def state():return json.loads((directory/'desktop.json').read_text())
    def fixture():return next((row for row in state()['windows'] if row['title']=='dock-fixture'),{})
    def apply_config():
        previous=text().count('Desktop layer mapped: madway-dock')
        with ini.open('w') as output:cfg.write(output)
        send('apply')
        wait(lambda:text().count('Desktop layer mapped: madway-dock')>previous)
    def grab(name):subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build'/name)],env=env,check=True,timeout=5)
    try:
        spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))])
        wait(lambda:'Desktop layer mapped: madway-dock' in text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY'])
        send('terminal');wait(lambda:state().get('app_id')=='org.kde.konsole')
        spawn('fixture',['kitty','--config','NONE','--title','dock-fixture','-o','linux_display_server=wayland','-o','confirm_os_window_close=0','/bin/sh','-c','sleep 120'])
        wait(lambda:fixture().get('focused'))
        protocol_client=spawn('taskbar',[str(root/'taskbar-client')],stdin=subprocess.PIPE,text=True)
        wait(lambda:'TASK dock-fixture' in (root/'taskbar.log').read_text())
        def command(value):protocol_client.stdin.write(value+'\n');protocol_client.stdin.flush()
        command('minimize');wait(lambda:fixture().get('minimized'))
        command('restore');wait(lambda:fixture().get('focused') and not fixture().get('minimized'))
        command('maximize');time.sleep(.2);assert 'TASK dock-fixture kitty 5' in (root/'taskbar.log').read_text()
        command('unmaximize');time.sleep(.2)
        identity=fixture()['id'];send('taskbar-toggle',id=identity);wait(lambda:fixture().get('minimized'))
        send('taskbar-toggle',id=identity);wait(lambda:fixture().get('focused') and not fixture().get('minimized'))
        # The protocol can restore an application from another workspace.
        send('workspace',value=1);wait(lambda:state()['workspace']==1)
        command('restore');wait(lambda:state()['workspace']==0 and fixture().get('focused'))
        print('PASS: foreign taskbar identity/state, minimize/restore/maximize, workspace activation and task buttons.')
        spawn('tray',['python3','tests/tray_fixture.py'])
        wait(lambda:(root/'tray').exists() and (root/'tray.properties').exists())
        registered=subprocess.check_output(['gdbus','call','--session','--dest','org.kde.StatusNotifierWatcher','--object-path','/StatusNotifierWatcher',
            '--method','org.freedesktop.DBus.Properties.Get','org.kde.StatusNotifierWatcher','RegisteredStatusNotifierItems'],env=env,text=True)
        assert '/StatusNotifierItem' in registered,registered
        print('PASS: Waybar StatusNotifier watcher registers app and requests its icon/tooltip properties.')
        time.sleep(.5);grab('gershwin-midnight-dock.png')
        send('screenshot');wait(lambda:any(path.stat().st_size>8 for path in (root/'Pictures/Screenshots').glob('*.png')))
        captures=list((root/'Pictures/Screenshots').glob('*.png'));assert captures[0].read_bytes().startswith(b'\x89PNG')
        wait(lambda:str(captures[0]) in text());time.sleep(.1)
        copied=subprocess.check_output(['wl-paste','--type','image/png'],env=env,timeout=4)
        assert copied==captures[0].read_bytes(),'Print screenshot must copy automatically'
        send('screenshot-clipboard');wait(lambda:len(list((root/'Pictures/Screenshots').glob('*.png')))==2)
        wait(lambda:subprocess.run(['wl-paste','--list-types'],env=env,capture_output=True,text=True,timeout=3).stdout.find('image/png')>=0)
        copied=subprocess.check_output(['wl-paste','--type','image/png'],env=env,timeout=4);assert copied.startswith(b'\x89PNG')
        print('PASS: real PNG screenshot saved with private mode and copied through Wayland clipboard.')
        assert captures[0].stat().st_mode&0o077==0
        # Deterministic selection/cancel helpers; grim itself still captures real pixels.
        binaries=root/'bin';binaries.mkdir();selector=binaries/'slurp'
        selector.write_text('#!/bin/sh\nprintf "10,10 256x128\\n"\n');selector.chmod(0o700)
        region_env={**env,'PATH':str(binaries)+':'+env['PATH']}
        region=subprocess.check_output(['scripts/madway-screenshot','--region'],env=region_env,text=True).strip()
        import struct
        assert struct.unpack('>II',Path(region).read_bytes()[16:24])==(256,128)
        assert subprocess.check_output(['wl-paste','--type','image/png'],env=region_env,timeout=4)==Path(region).read_bytes()
        selector.write_text('#!/bin/sh\nexit 1\n')
        count=len(list((root/'Pictures/Screenshots').glob('*.png')))
        subprocess.run(['scripts/madway-screenshot','--region'],env=region_env,check=True)
        assert len(list((root/'Pictures/Screenshots').glob('*.png')))==count
        print('PASS: region PNG dimensions and cancelled selection leaves no file.')
        selector.write_text('#!/usr/bin/env python3\nimport os,time\nfrom pathlib import Path\nPath('+repr(str(root/'selector.pid'))+').write_text(str(os.getpid()))\ntime.sleep(60)\n')
        pending=spawn('selection',['scripts/madway-screenshot','--region'],region_env)
        wait(lambda:(root/'selector.pid').exists())
        child_pid=int((root/'selector.pid').read_text())
        pending.terminate();pending.wait(timeout=3)
        wait(lambda:not Path('/proc',str(child_pid)).exists())
        assert len(list((root/'Pictures/Screenshots').glob('*.png')))==count
        print('PASS: interrupted screenshot selector is reaped without an orphan or partial file.')
        # Live dark/light and every dock edge must survive layout changes.
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
        for theme in ('gershwin','gershwin-dark'):
            cfg['appearance']['theme']=theme
            for edge in ('top','left','right','bottom'):
                cfg['dock']={'enabled':'true','position':edge,'icons_only':'true','icon_size':'32','tray':'true'}
                apply_config()
                wait(lambda:json.loads((directory/'dock.json').read_text())['position']==edge)
                assert processes[0].poll() is None
        grab('gershwin-dock-preview.png')
        command('close');wait(lambda:not fixture())
        assert 'CLOSED dock-fixture' in (root/'taskbar.log').read_text()
        assert 'Traceback (most recent call last)' not in text(),text()
        assert 'Error parsing css' not in text() and 'Failed to load CSS' not in text(),text()
        print('PASS: light/dark dock on four edges and protocol close/unmap cleanup.')
        send('lock');wait(lambda:state().get('locked') and state().get('lock_ready'))
        wait(lambda:'CLOSED madway-wm' in (root/'taskbar.log').read_text())
        before=len(list((root/'Pictures/Screenshots').glob('*.png')))
        denied=subprocess.run(['scripts/madway-screenshot'],env=env,capture_output=True,text=True)
        assert denied.returncode==1 and 'while locked' in denied.stderr
        assert len(list((root/'Pictures/Screenshots').glob('*.png')))==before
        print('PASS: lock withdraws foreign window metadata and screenshot UI refuses capture; no authentication attempted.')
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-10000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.send_signal(signal.SIGTERM)
        for process in reversed(processes):
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
