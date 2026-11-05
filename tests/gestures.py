"""Native gesture routing on private outputs; no host devices or session actions."""
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

repo=Path(__file__).resolve().parent.parent
os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-gestures-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    ini=config/'madway/settings.ini'
    ini.write_text('[output:HEADLESS-1]\nmode=800x600@100000\n[output:HEADLESS-2]\nmode=800x600@60000\nx=800\n')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-DWLR_USE_UNSTABLE','-Isrc','tests/gesture_probe.c','-o',str(root/'probe.so'),*flags,'-ldl'],check=True)
    sources=[]
    for name,source in [('xdg-shell','/usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml'),
                        ('pointer-gestures',str(repo/'protocols/pointer-gestures-unstable-v1.xml'))]:
        subprocess.run(['wayland-scanner','client-header',source,str(root/(name+'-client-protocol.h'))],check=True)
        code=root/(name+'.c');sources.append(str(code))
        subprocess.run(['wayland-scanner','private-code',source,str(code)],check=True)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True).split()
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-I'+str(root),'tests/gesture_client.c',*sources,'-o',str(root/'client'),*flags],check=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_RUNTIME_DIR':str(runtime),
         'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman','MADWAY_GESTURE_TEST':tmp}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_SESSION','MADWAY_NATIVE','LD_PRELOAD'):env.pop(key,None)
    processes=[];logs=[];sequence=0
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
    def text(name='server'):return (root/(name+'.log')).read_text()
    def state():
        try:return json.loads((root/'state.json').read_text())
        except (OSError,ValueError):return {}
    def wait(predicate,timeout=8):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            assert processes[0].poll() is None,text()
            if predicate():return
            time.sleep(.01)
        raise AssertionError(text()+'\n'+str(state()))
    def inject(op,x=0,y=0,fingers=3,device=0):
        global sequence
        sequence+=1
        path=root/'command.tmp';path.write_text(f'{sequence} {op} {x} {y} {fingers} {device}')
        path.replace(root/'command');wait(lambda:state().get('command')==sequence)
    def core(command):
        endpoint=runtime/('madway-'+env['WAYLAND_DISPLAY'])/'compositor.sock'
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(command.encode(),str(endpoint))
    def workspace(value):core(f'workspace {value}');wait(lambda:state()['workspace']==value)
    def swipe(dx,dy=0,cancelled=False,fingers=3):
        before=state()['workspace'];inject('sb',fingers=fingers);inject('su',dx/2,dy/2,fingers)
        inject('su',dx/2,dy/2,fingers);assert state()['workspace']==before,'Changed workspace before release'
        inject('se',int(cancelled))
    def reload(**values):
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
        if 'touchpad' not in cfg:cfg['touchpad']={}
        cfg['touchpad'].update({key:str(value).lower() for key,value in values.items()})
        with ini.open('w') as output:cfg.write(output)
        server.send_signal(signal.SIGHUP)
        expected={'workspace_swipe':'enabled','swipe_invert':'invert','swipe_threshold':'threshold'}
        wait(lambda:all(state().get(expected[key])==value for key,value in values.items()))
    try:
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(root/'probe.so')).lstrip(':')
        server=spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload})
        wait(lambda:'Listening on WAYLAND_DISPLAY=' in text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        client=spawn('client',[str(root/'client')]);other=spawn('other',[str(root/'client'),'gesture-other'])
        wait(lambda:'Window mapped: gesture-fixture' in text() and 'Window mapped: gesture-other' in text())
        wait(lambda:state().get('threshold')==120 and state()['enabled'])
        swipe(240);assert state()['workspace']==0
        inject('focus',1);swipe(-240);assert state()['workspace']==1 and state()['transition']
        assert 'swipe_begin' not in text('client'),'Compositor swipe leaked to a client'
        inject('se');assert state()['workspace']==1
        swipe(240);assert state()['workspace']==0
        workspace(8);swipe(-240);assert state()['workspace']==8
        workspace(3)
        for dx,dy,cancel in [(-70,0,False),(-140,220,False),(-160,130,False),(-240,0,True)]:
            swipe(dx,dy,cancel);assert state()['workspace']==3
        inject('sb');inject('su',-240);inject('su',240);inject('se');assert state()['workspace']==3
        inject('sb');inject('su',-240,fingers=4);inject('se');assert state()['workspace']==3
        print('PASS: three-finger direction, one switch on release, animation, boundaries, threshold, diagonals, reversal and cancelled/finger-change gestures.',flush=True)
        inject('sb');inject('su',-240);inject('escape');inject('se');assert state()['workspace']==3
        inject('sb');inject('su',-240);inject('button',1);inject('button',0);inject('se');assert state()['workspace']==3
        inject('button',1);swipe(-240);inject('button',0);assert state()['workspace']==3
        inject('sb');inject('su',-240);workspace(4);inject('se');assert state()['workspace']==4
        inject('sb');inject('su',-240);core('prepare-sleep');wait(lambda:state()['sleeping'])
        core('resume');wait(lambda:not state()['sleeping']);inject('se');assert state()['workspace']==4
        inject('sb');inject('su',-240);inject('remove');inject('add');inject('se');assert state()['workspace']==4
        inject('sb');inject('su',-240,device=1);inject('se',device=1);inject('se');assert state()['workspace']==4
        inject('sb');inject('su',-240);inject('sb',device=1);inject('se',device=1);inject('se');assert state()['workspace']==5
        print('PASS: Escape/click, held buttons, external workspace switch, sleep/resume, device removal and simultaneous-device isolation.',flush=True)
        reload(swipe_invert=True);swipe(-240);assert state()['workspace']==4
        reload(swipe_invert=False,swipe_threshold=300);swipe(-240);assert state()['workspace']==4
        swipe(-400);assert state()['workspace']==5
        inject('sb');inject('su',-400);reload(workspace_swipe=False);inject('se');assert state()['workspace']==5
        workspace(0);inject('focus',1)
        before=text('client').count('swipe_end');swipe(-400)
        wait(lambda:text('client').count('swipe_end')>before)
        assert 'swipe_begin 3' in text('client') and 'swipe_end 0' in text('client') and state()['workspace']==0
        reload(workspace_swipe=True,swipe_threshold=120)
        inject('focus',1);swipe(-200,fingers=4);wait(lambda:'swipe_begin 4' in text('client'))
        inject('pb',fingers=2);inject('pu',1.5,15,fingers=2);inject('pe')
        wait(lambda:'pinch_update 2.00 3.00 1.50 15.00' in text('client') and 'pinch_end 0' in text('client'))
        inject('hb',fingers=2);inject('he');wait(lambda:'hold_begin 2' in text('client') and 'hold_end 0' in text('client'))
        before=text('client').count('pinch_end');other_before=text('other')
        inject('pb',fingers=2);inject('focus',2);inject('pu',1.2,0,fingers=2);inject('pe')
        wait(lambda:text('client').count('pinch_end')>before)
        assert text('client').rstrip().endswith('pinch_end 1') and text('other')==other_before
        inject('focus',1);inject('hb',fingers=2);inject('pb',fingers=2);inject('pe')
        wait(lambda:'hold_end 1' in text('client'))
        print('PASS: live enable/reverse/distance settings; real client swipe, pinch scale/rotation and hold delivery; focus cancellation stays with the original client.',flush=True)
        inject('sb');inject('su',-240);core('lock-blank');wait(lambda:state()['locked']);inject('se')
        before=text('client');swipe(-240);inject('pb',fingers=2);inject('pu',1.5,fingers=2);inject('pe')
        assert state()['workspace']==0 and text('client')==before
        print('PASS: lock cancels an active swipe and blocks workspace changes and application gesture delivery.',flush=True)
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-6000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
