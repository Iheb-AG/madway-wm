"""Animated dock, expanded taskbar, white controls and open-menu screenshots."""
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
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf

repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-dock-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    (config/'user-dirs.dirs').write_text('XDG_PICTURES_DIR="$HOME/Pictures"\n')
    ini=config/'madway/settings.ini'
    ini.write_text('[appearance]\ntheme=gershwin-dark\ntitle_height=22\n[panel]\nheight=22\nmetrics=false\n[notifications]\nenabled=false\n[dock]\nanimation_ms=300\n[wallpaper]\ntype=color\ncolor=#142034\n[output:HEADLESS-1]\nmode=1280x720@60000\nx=0\ny=0\n[output:HEADLESS-2]\nmode=800x600@60000\nx=1280\ny=0\n')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    flags+=['-I'+str(repo/'build/protocols')]
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','tests/dock_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    curve=root/'curve.c';curve.write_text('#include "dock.h"\n#include <assert.h>\nint main(void){assert(madway_dock_ease(0)==0 && madway_dock_ease(1)==1);assert(madway_dock_ease(.05)<.05 && madway_dock_ease(.5)>.65);double p=0;for(int i=0;i<=100;++i){double v=madway_dock_ease(i/100.);assert(v>=p && v<=1);p=v;}return 0;}\n')
    subprocess.run(['cc','-DWLR_USE_UNSTABLE','-Isrc','-ffunction-sections','-fdata-sections','src/dock.c','src/animation.c',str(curve),'-o',str(root/'curve'),*flags,'-Wl,--gc-sections'],check=True)
    subprocess.run([str(root/'curve')],check=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
         'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman','MADWAY_SESSION':'1',
         'LIBGL_ALWAYS_SOFTWARE':'1','GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),
         'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery'),'MADWAY_DOCK_TEST':tmp}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(key,None)
    processes=[];logs=[]
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
    def text():return (root/'server.log').read_text()
    def wait(check,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if check():return
            assert processes[0].poll() is None,text()
            time.sleep(.015)
        raise AssertionError(text()+'\nPROBE '+str(snapshot()))
    def snapshot():
        try:return json.loads((root/'probe.json').read_text())
        except (OSError,ValueError):return {}
    def state():return json.loads((directory/'desktop.json').read_text())
    def send(name,**values):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
            channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
    def command(number):
        path=root/'command.tmp';path.write_text(str(number));path.replace(root/'command')
        wait(lambda:snapshot().get('command')==number)
    def capture(name):subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build'/name)],env=env,check=True)
    try:
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(probe)).lstrip(':')
        spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload})
        wait(lambda:text().count('Desktop layer mapped: madway-dock')==2)
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY'])
        command(2)
        client=spawn('client',['kitty','--config','NONE','--title','dock-fixture','-o','linux_display_server=wayland','-o','confirm_os_window_close=0','/bin/sh','-c','sleep 120'])
        wait(lambda:state().get('title')=='dock-fixture')
        wait(lambda:snapshot().get('enabled') and snapshot().get('other')==1)
        command(3);wait(lambda:snapshot().get('glyphs')==7)
        command(2);time.sleep(.2);normal=snapshot()['usable']
        capture('midnight-expanded-taskbar.png')
        send('window-maximize')
        samples=[];end=time.monotonic()+1
        while time.monotonic()<end:
            value=snapshot();samples.append(value)
            if not value['enabled']:break
            time.sleep(.015)
        assert not snapshot()['enabled'],snapshot()
        assert any(v['enabled'] and 0<v['dy']<v['height'] for v in samples),samples
        assert snapshot()['usable']>normal+30 and snapshot()['other']==1,snapshot()
        command(1);wait(lambda:snapshot()['enabled'] and snapshot()['dy']==0)
        # Stay at the edge until fully revealed, then enter the actual dock.
        command(7);wait(lambda:snapshot()['tooltip_count']>0);assert snapshot()['tooltip_count']==snapshot()['tooltip_fits']
        assert snapshot()['enabled'] and snapshot()['dy']==0
        capture('midnight-revealed-dock.png')
        command(8);wait(lambda:not snapshot()['enabled'])
        send('window-maximize');wait(lambda:snapshot()['enabled'] and snapshot()['dy']==0 and snapshot()['usable']==normal)
        print('PASS: Bézier curve, intermediate slide frames, per-output maximize hide, released work area, edge reveal, hover hold, delayed hide and restore.')
        print('PASS: Midnight close/minimize/maximize glyphs stay white while hovered.')
        send('panel-menu',page='Desktop',x=20,y=22,edge='top');wait(lambda:snapshot()['menu'])
        menu=snapshot();command(4)
        pictures=root/'Pictures/Screenshots'
        wait(lambda:any(p.stat().st_size>8 for p in pictures.glob('*.png')))
        first=next(pictures.glob('*.png'));wait(lambda:str(first) in text())
        assert snapshot()['menu'],'Print dismissed the panel menu'
        image=GdkPixbuf.Pixbuf.new_from_file(str(first));pixels=image.get_pixels()
        x,y=menu['menu_x']+180,menu['menu_y']+12
        index=y*image.get_rowstride()+x*image.get_n_channels()
        pixel=tuple(pixels[index:index+3]);assert pixel!=(20,32,52),pixel
        time.sleep(.1);command(5)
        wait(lambda:len(list(pictures.glob('*.png')))==2)
        wait(lambda:all(str(path) in text() for path in pictures.glob('*.png')))
        wait(lambda:'image/png' in subprocess.run(['wl-paste','--list-types'],env=env,capture_output=True,text=True,timeout=3).stdout)
        assert snapshot()['menu'],'Ctrl+Print dismissed the panel menu'
        time.sleep(.15);previous=text().count('Desktop layer mapped: selection');command(6)
        wait(lambda:text().count('Desktop layer mapped: selection')>previous)
        command(9);time.sleep(.05);command(10)
        wait(lambda:len(list(pictures.glob('*.png')))==3)
        assert snapshot()['menu'],'Shift+Print dismissed the panel menu'
        capture('midnight-menu-screenshot.png')
        print('PASS: real Print/Ctrl+Print/Shift+Print keep the open menu, include it in PNG, and copy to clipboard.')
        send('close-menu');wait(lambda:not snapshot()['menu'])
        # Exercise slides on each edge and a setting that disables animation/autohide.
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
        for edge in ('left','right','top','bottom'):
            cfg['dock']['position']=edge
            before=text().count('Desktop layer mapped: madway-dock')
            with ini.open('w') as output:cfg.write(output)
            send('apply');wait(lambda:text().count('Desktop layer mapped: madway-dock')>=before+2)
            command(2);send('window-maximize');wait(lambda:not snapshot()['enabled'])
            command(1);wait(lambda:snapshot()['enabled'] and snapshot()['dx']==0 and snapshot()['dy']==0)
            command(8);wait(lambda:not snapshot()['enabled'])
            send('window-maximize');wait(lambda:snapshot()['enabled'] and snapshot()['dx']==0 and snapshot()['dy']==0)
        cfg['dock'].update(autohide='false',animate='false')
        before=text().count('Desktop layer mapped: madway-dock')
        with ini.open('w') as output:cfg.write(output)
        send('apply');wait(lambda:text().count('Desktop layer mapped: madway-dock')>=before+2)
        send('window-maximize');time.sleep(.4);assert snapshot()['enabled'] and snapshot()['dy']==0
        send('window-fullscreen');wait(lambda:not snapshot()['enabled'])
        send('window-fullscreen');wait(lambda:snapshot()['enabled'])
        assert client.poll() is None
        assert 'Traceback (most recent call last)' not in text(),text()
        print('PASS: four dock edges, option changes, fullscreen priority and client survival.')
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-11000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.send_signal(signal.SIGTERM)
        for process in reversed(processes):
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
