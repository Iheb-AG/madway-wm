"""Lock protocol and supervision tests on private headless outputs; no host auth."""
import configparser
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf

repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-lock-test-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    ini=config/'madway/settings.ini';ini.write_text('[notifications]\nenabled=false\n[wallpaper]\ntype=color\ncolor=#bb2222\n')
    protocol=Path('/usr/share/wayland-protocols/staging/ext-session-lock/ext-session-lock-v1.xml')
    subprocess.run(['wayland-scanner','client-header',str(protocol),str(root/'ext-session-lock-v1-client-protocol.h')],check=True)
    subprocess.run(['wayland-scanner','private-code',str(protocol),str(root/'protocol.c')],check=True)
    client=root/'lock-client'
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True).split()
    subprocess.run(['cc','-I'+str(root),'tests/lock_client.c',str(root/'protocol.c'),'-o',str(client),*flags],check=True)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','tests/lock_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    binaries=root/'bin';binaries.mkdir();locker=binaries/'swaylock';locker.symlink_to(client)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless',
        'WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman','MADWAY_SESSION':'1','LIBGL_ALWAYS_SOFTWARE':'1',
        'GIO_USE_VFS':'local','PATH':str(binaries)+':'+os.environ['PATH'],'MADWAY_TEST_LOCK_UNLOCK':str(root/'unlock'),
        'DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus')}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','LD_PRELOAD'):env.pop(key,None)
    processes=[];logs=[]
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        proc=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(proc);return proc
    def text():return (root/'server.log').read_text()
    def wait(predicate,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            assert processes[0].poll() is None,text()
            time.sleep(.03)
        raise AssertionError(text())
    def state():
        try:return json.loads((directory/'desktop.json').read_text())
        except (OSError,ValueError):return {}
    def send(name,**values):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
    def core(value):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(value.encode(),str(directory/'compositor.sock'))
    def command(number,marker):
        path=root/'command.tmp';path.write_text(str(number));path.replace(root/'command');wait(lambda:marker in text())
    def capture(output,blue=False,gray=False):
        path=root/(output+'.png');subprocess.run(['grim','-o',output,str(path)],env=env,check=True,timeout=5)
        pixbuf=GdkPixbuf.Pixbuf.new_from_file(str(path));pixels=pixbuf.get_pixels();stride=pixbuf.get_rowstride();channels=pixbuf.get_n_channels()
        for y in range(0,pixbuf.get_height(),7):
            for x in range(0,pixbuf.get_width(),7):
                pixel=tuple(pixels[y*stride+x*channels:y*stride+x*channels+3])
                if blue:
                    edge=x<4 or y<4 or x>=pixbuf.get_width()-4 or y>=pixbuf.get_height()-4
                    assert all(abs(a-b)<=3 for a,b in zip(pixel,(22,57,87))) or (edge and pixel[0]<=22 and pixel[1]<=57 and pixel[2]<=87),(output,pixel,x,y)
                if gray:assert pixel[0]==pixel[1]==pixel[2],(output,pixel,x,y)
    try:
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(probe)).lstrip(':')
        spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload,'MADWAY_LOCK_RELEASE_PRESENT':str(root/'release'),
            'MADWAY_LOCK_TEST_COMMAND':str(root/'command')})
        wait(lambda:'desktop services ready' in text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY'])
        normal=spawn('normal',['kitty','--config','NONE','--title','private-normal-window','-o','linux_display_server=wayland',
            '-o','confirm_os_window_close=0','/bin/sh','-c','sleep 60'])
        wait(lambda:state().get('title')=='private-normal-window')
        send('lock');wait(lambda:state().get('locked'))
        time.sleep(.4)
        assert not state().get('lock_ready') and not state().get('lock_client_pid'),state()
        assert 'TEST LOCKED' not in text(),'Lock acknowledgement preceded second output presentation'
        (root/'release').touch();wait(lambda:state().get('lock_client_pid') and 'TEST LOCKED' in text())
        pid=state()['lock_client_pid'];capture('HEADLESS-1',blue=True);capture('HEADLESS-2',blue=True)
        command(1,'LOCK SHORTCUTS INPUT FOCUS AND RIGHT CLICK ISOLATION PASS')
        wait(lambda:'TEST KEY 30 1' in text())
        core('prepare-sleep');wait(lambda:state().get('sleeping'))
        assert state().get('locked')
        core('resume');wait(lambda:not state().get('sleeping'))
        capture('HEADLESS-1',blue=True);capture('HEADLESS-2',blue=True)
        core('workspace 3');time.sleep(.1);assert state()['workspace']==0
        # A second lock request is rejected without disturbing the current owner.
        duplicate=spawn('duplicate',[str(client)]);duplicate.wait(timeout=4);assert duplicate.returncode==3
        assert state()['locked'] and state()['lock_client_pid']==pid
        command(2,'LOCK OUTPUT HOTPLUG ADDED');wait(lambda:text().count('TEST LOCK SURFACE')>=3)
        time.sleep(.2);capture('HEADLESS-3',blue=True)
        command(3,'LOCK OUTPUT HOTPLUG REMOVED')
        # Reconfigure and re-enable outputs while locked, exercising safe buffers.
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
        cfg['output:HEADLESS-1']={'enabled':'false'}
        with ini.open('w') as output:cfg.write(output)
        os.kill(processes[0].pid,signal.SIGHUP)
        wait(lambda:any(row['name']=='HEADLESS-1' and not row['enabled'] for row in json.loads((directory/'outputs.json').read_text())['outputs']))
        cfg['output:HEADLESS-1']={'enabled':'true','mode':'1024x768@60000','scale':'1.25','transform':'1'}
        with ini.open('w') as output:cfg.write(output)
        os.kill(processes[0].pid,signal.SIGHUP)
        wait(lambda:'TEST LOCK SURFACE 614x819' in text())
        time.sleep(.2);capture('HEADLESS-1',blue=True)
        # Stop automatic recovery temporarily to observe the crash fallback.
        locker.unlink();os.kill(pid,signal.SIGKILL)
        wait(lambda:state().get('locked') and not state().get('lock_client_pid'))
        capture('HEADLESS-1',gray=True);capture('HEADLESS-2',gray=True)
        forged=spawn('forged',[str(client)]);forged.wait(timeout=4);assert forged.returncode==3
        assert state()['locked'];capture('HEADLESS-2',gray=True)
        # The supervised PID is authorized to recover, then test protocol unlock.
        locker.symlink_to(client);send('lock');wait(lambda:state().get('lock_client_pid') and state()['lock_client_pid']!=pid)
        capture('HEADLESS-2',blue=True)
        command(4,'LOCK PASSWORD KEY HELD')
        (root/'unlock').touch();wait(lambda:not state().get('locked'))
        wait(lambda:'LOCK HELD PASSWORD KEY OMITTED ON DESKTOP ENTER' in text())
        command(5,'LOCK PASSWORD KEY RELEASE CONSUMED PASS')
        assert normal.poll() is None
        assert state().get('title')=='private-normal-window'
        print('PASS: presentation barrier on two outputs; exclusive input; blocked shortcuts/IPC; duplicate denial; hotplug; scale/rotation/disable/enable; crash fallback; rejected untrusted replacement; supervised recovery and protocol unlock.')
        # Real swaylock compatibility; never authenticate against the host account.
        actual=os.environ.get('MADWAY_TEST_SWAYLOCK') or shutil.which('swaylock')
        if actual:
            (root/'unlock').unlink();locker.unlink();locker.symlink_to(actual)
            time.sleep(.2);send('lock');wait(lambda:state().get('locked') and state().get('lock_client_pid'))
            assert state().get('lock_ready')
            print('PASS: real swaylock ext-session-lock compatibility and readiness; no password/authentication attempt.')
        assert 'Traceback (most recent call last)' not in text(),text()
        assert 'No free output buffer slot' not in text(),text()
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-14000:])
        raise
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:proc.terminate()
        for proc in reversed(processes):
            try:proc.wait(timeout=6)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        for log in logs:log.close()
