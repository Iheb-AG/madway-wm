"""Real nested pointer events, confined to a private headless parent compositor."""
import configparser
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import tempfile
import time

repo=Path(__file__).resolve().parent.parent
os.chdir(repo)
binary=Path(os.environ.get('MADWAY_TEST_BUILD_DIR',repo/'build'))/'madway'
with tempfile.TemporaryDirectory(prefix='madway-nested-pointer-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','wayland-client','xkbcommon'],text=True).split()
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','tests/nested_pointer_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    config_parent=root/'parent-config';(config_parent/'madway').mkdir(parents=True)
    (config_parent/'madway/settings.ini').write_text('[input]\nmodifier=super\n')
    config_child=root/'child-config';config_child.mkdir()
    env=os.environ.copy();env.update(HOME=tmp,XDG_RUNTIME_DIR=str(runtime),WLR_RENDERER='pixman',GIO_USE_VFS='local',LIBGL_ALWAYS_SOFTWARE='1')
    for key in ('MADWAY_SESSION','MADWAY_NATIVE','DISPLAY','WAYLAND_SOCKET','LD_PRELOAD'):env.pop(key,None)
    processes=[];handles=[];serial=0
    def wait(predicate,timeout=8):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():return
            assert all(process.poll() is None for process in processes),'A test process exited'
            time.sleep(.02)
        raise AssertionError('Timed out waiting for nested input')
    def read(name):return json.loads((root/(name+'.json')).read_text())
    preload=(os.environ['MADWAY_TEST_LIBASAN']+':' if os.environ.get('MADWAY_TEST_LIBASAN') else '')+str(probe)
    def start(role,values):
        path=root/(role+'.log');log=path.open('w');handles.append(log)
        process=subprocess.Popen([str(binary)],env={**env,**values,'LD_PRELOAD':preload+(':'+os.environ['MADWAY_TEST_PRELOAD_EXTRA'] if os.environ.get('MADWAY_TEST_PRELOAD_EXTRA') else ''),
            'MADWAY_POINTER_TEST_DIR':tmp,'MADWAY_POINTER_TEST_ROLE':role},stdout=log,stderr=log)
        processes.append(process)
        wait(lambda:'Listening on WAYLAND_DISPLAY=' in path.read_text())
        return process,re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',path.read_text()).group(1)
    def command(code,x=0,y=0,state=0):
        global serial
        serial+=1
        temp=root/'command.tmp';temp.write_text(f'{serial} {code} {x} {y} {state}')
        temp.replace(root/'command')
        wait(lambda:(root/'ack').exists() and (root/'ack').read_text()==str(serial))
        time.sleep(.03)
    def move(output,local_x,local_y):
        host=next(view for view in read('parent')['views'] if view['surface']==output['surface'])
        # Enter the host surface, then emit motion within it (enter alone is not motion).
        command(0,host['x']+local_x+1,host['y']+local_y+1)
        command(0,host['x']+local_x,host['y']+local_y)
    def click(button=272):command(1,button,state=1);command(1,button,state=0)
    try:
        parent,host=start('parent',dict(WLR_BACKENDS='headless',XDG_CONFIG_HOME=str(config_parent)))
        child,display=start('child',dict(WLR_BACKENDS='wayland',WLR_WL_OUTPUTS='2',WAYLAND_DISPLAY=host,XDG_CONFIG_HOME=str(config_child)))
        wait(lambda:(root/'parent.json').exists() and (root/'child.json').exists() and len(read('parent')['views'])==2 and len(read('child')['outputs'])==2)
        clientlog=(root/'kitty.log').open('w');handles.append(clientlog)
        client=subprocess.Popen(['kitty','--config','NONE','--title','pointer-fixture','-o','linux_display_server=wayland',
            '-o','confirm_os_window_close=0','/bin/sh','-c','sleep 120'],env={**env,'WAYLAND_DISPLAY':display},stdout=clientlog,stderr=clientlog)
        processes.append(client)
        wait(lambda:len(read('child')['views'])==1)
        data=read('child');view=data['views'][0]
        occupied=next(output for output in data['outputs'] if output['name']==view['output'])
        empty=next(output for output in data['outputs'] if output['name']!=view['output'])
        # A click in the empty host window must never reach the other output.
        move(empty,80,80);click()
        data=read('child')
        expected=(empty['x']+80,empty['y']+80)
        assert math.dist(data['cursor'],expected)<.1,(data,expected)
        assert not data['views'][0]['focused'] and not data['views'][0]['pointer_focus'],data
        # Direct application hit-testing and an Alt-drag in its own host window.
        local_x=view['x']-occupied['x']+80;local_y=view['y']-occupied['y']+80
        move(occupied,local_x,local_y);click()
        wait(lambda:read('child')['views'][0]['pointer_focus'])
        assert read('child')['views'][0]['focused']
        # Enter another host window and click before it has sent motion.
        # That stale position must not start a drag on the occupied output.
        host_empty=next(item for item in read('parent')['views'] if item['surface']==empty['surface'])
        command(0,host_empty['x']+120,host_empty['y']+120)
        command(2,56,state=1);command(1,272,state=1)
        move(empty,140,140)
        command(1,272,state=0);command(2,56,state=0)
        assert read('child')['views'][0]['x']==view['x'] and read('child')['views'][0]['y']==view['y'],read('child')
        move(occupied,local_x,local_y);click()
        command(2,56,state=1) # Left Alt: parent uses Super, child uses Alt.
        command(1,272,state=1)
        move(occupied,local_x+90,local_y+45)
        command(1,272,state=0);command(2,56,state=0)
        wait(lambda:read('child')['views'][0]['x']==view['x']+90)
        assert read('child')['views'][0]['y']==view['y']+45
        for i in range(30):
            target=empty if i%2==0 else occupied
            move(target,100+i,120)
            current=read('child')
            assert math.dist(current['cursor'],(target['x']+100+i,target['y']+120))<.1,current
        move(empty,300,300)
        before=read('child')['cursor_updates']
        for i in range(25):move(empty,400+i,500)
        assert read('child')['cursor_updates']-before<=1,read('child')
        # Spawn another client under the pointer on the second output and resize it.
        second=subprocess.Popen(['kitty','--config','NONE','--title','pointer-fixture-2','-o','linux_display_server=wayland',
            '-o','confirm_os_window_close=0','/bin/sh','-c','sleep 120'],env={**env,'WAYLAND_DISPLAY':display},stdout=clientlog,stderr=clientlog)
        processes.append(second)
        wait(lambda:len(read('child')['views'])==2)
        other=read('child')['views'][1]
        assert other['output']==empty['name'],read('child')
        local_x=other['x']-empty['x']+80;local_y=other['y']-empty['y']+80
        move(empty,local_x,local_y);click()
        assert read('child')['views'][1]['pointer_focus']
        command(2,56,state=1);command(1,273,state=1)
        move(empty,local_x+64,local_y+32)
        command(1,273,state=0);command(2,56,state=0)
        wait(lambda:read('child')['views'][1]['width']>other['width'])
        assert read('child')['views'][1]['height']>other['height']
        # Reorder outputs without changing which host window delivers their input.
        profiles=configparser.ConfigParser(interpolation=None)
        profiles['output:'+occupied['name']]={'x':'1280','y':'0','scale':'1','transform':'0'}
        profiles['output:'+empty['name']]={'x':'0','y':'0','scale':'1','transform':'0'}
        (config_child/'madway').mkdir(exist_ok=True)
        with (config_child/'madway/settings.ini').open('w') as file:profiles.write(file)
        child.send_signal(signal.SIGHUP)
        wait(lambda:any(output['name']==empty['name'] and output['x']==0 for output in read('child')['outputs']))
        for output in read('child')['outputs']:
            move(output,100,100);click()
            assert math.dist(read('child')['cursor'],(output['x']+100,output['y']+100))<.1,read('child')
        print('PASS: a client on each output, second-output resize, and pointer mappings after layout reorder.')
        if shutil.which('wl-copy') and shutil.which('wl-paste'):
            clipenv={**env,'WAYLAND_DISPLAY':display}
            owner=subprocess.Popen(['wl-copy','--primary','--foreground','--paste-once','madway primary test'],env=clipenv,stdout=clientlog,stderr=clientlog)
            processes.append(owner)
            wait(lambda:read('child')['primary'])
            result=subprocess.check_output(['wl-paste','--primary','--no-newline'],env=clipenv,timeout=6,text=True)
            assert result=='madway primary test',result
            owner.wait(timeout=4);processes.remove(owner)
            print('PASS: primary selection transfer between real wl-copy/wl-paste clients.')
        for name in ('parent','child'):
            text=(root/(name+'.log')).read_text()
            for error in ('No free output buffer slot','runtime error:','ERROR: AddressSanitizer'):
                assert error not in text,(name,error)
        print('PASS: repeated background motion reuses the cursor image; no buffer-slot warnings in this test.')
        print('PASS: real nested pointer mapping, empty-output isolation, direct client focus, Alt-drag, and alternating input across both host windows.')
    except BaseException:
        for path in root.glob('*.json'):print(path.name+'\n'+path.read_text())
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-14000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=4)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for handle in handles:handle.close()
