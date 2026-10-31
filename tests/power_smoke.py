"""Real compositor recovery using a fake native session, lid and headless screens."""
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
with tempfile.TemporaryDirectory(prefix='madway-power-smoke-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    settings=config/'madway/settings.ini'
    original='[power]\nlid_action=auto\n[notifications]\nenabled=false\n'
    settings.write_text(original)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','tests/power_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_RUNTIME_DIR':str(runtime),
        'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman','MADWAY_SESSION':'1',
        'GIO_USE_VFS':'local','LIBGL_ALWAYS_SOFTWARE':'1','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus')}
    # Never present this fake native session as eligible for real OS sleep.
    for name in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','LD_PRELOAD'):env.pop(name,None)
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
            time.sleep(.04)
        raise AssertionError(text())
    def core(command):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(command.encode(),str(directory/'compositor.sock'))
    def stage(number,message):
        pending=root/'command.tmp';pending.write_text(str(number));pending.replace(root/'command')
        wait(lambda:message in text())
    def state():return json.loads((directory/'desktop.json').read_text())
    try:
        spawn('server',['./build/madway'],{**env,'LD_PRELOAD':str(probe),'MADWAY_POWER_COMMAND':str(root/'command')})
        wait(lambda:'desktop services ready' in text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY'])
        client=spawn('client',['kitty','--config','NONE','--title','power-client','-o','linux_display_server=wayland',
            '-o','confirm_os_window_close=0','/bin/sh','-c','sleep 60'])
        wait(lambda:'Window mapped: power-client' in text())
        core('lid-managed 1');time.sleep(.15)
        stage(1,'POWER DOCKED LID CLOSE PASS')
        stage(2,'POWER LID REOPEN RESTORES SCREEN PASS')
        stage(3,'POWER EXTERNAL UNPLUG RECOVERY PASS')
        core('prepare-sleep');wait(lambda:state().get('sleeping'))
        stage(4,'POWER SESSION INACTIVE PASS')
        core('resume');stage(5,'POWER SESSION ACTIVE PASS')
        wait(lambda:not state().get('sleeping') and state().get('title')=='power-client')
        subprocess.run(['grim','-o','eDP-1',str(root/'resumed.png')],env=env,check=True,timeout=5)
        stage(6,'POWER LAST NATIVE OUTPUT REMOVED PASS')
        time.sleep(.25);assert processes[0].poll() is None,'Compositor exited on transient native output loss'
        stage(7,'POWER NATIVE OUTPUT RECONNECTED PASS')
        wait(lambda:'First scene frame committed on HDMI-A-1' in text())
        subprocess.run(['grim','-o','HDMI-A-1',str(root/'reconnected.png')],env=env,check=True,timeout=5)
        assert client.poll() is None
        stage(8,'POWER KEYBOARD FOCUS RESTORED PASS')
        assert settings.read_text()==original,'Runtime lid changes modified display preferences'
        assert 'Traceback (most recent call last)' not in text(),text()
        assert 'No free output buffer slot' not in text(),text()
        print('PASS: virtual lid close/reopen, docked screen blanking, unplug fallback, suspend/resume repaint/focus, native output loss/reconnect, retained client and unchanged profiles. No real sleep or VT switch.')
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-11000:])
        raise
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:proc.send_signal(signal.SIGTERM)
        for proc in reversed(processes):
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        for log in logs:log.close()
