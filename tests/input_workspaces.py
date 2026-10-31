"""Native-config unit checks plus live keyboard/workspace behavior in isolation."""
import configparser
import json
import os
from pathlib import Path
import re
import signal
import statistics
import socket
import subprocess
import sys
import tempfile
import time
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf

repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-input-workspaces-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    ini=config/'madway/settings.ini'
    ini.write_text('[appearance]\ntheme=gershwin-dark\ntitle_height=22\n[panel]\nheight=22\nmetrics=false\n[notifications]\nenabled=false\n[workspaces]\nanimation_ms=500\n[wallpaper]\ntype=color\ncolor=#142034\n[output:HEADLESS-1]\nmode=1280x720@60000\nx=0\ny=0\n[output:HEADLESS-2]\nmode=800x600@60000\nx=1280\ny=0\n')
    if os.environ.get('MADWAY_TEST_REFRESH'):
        ini.write_text(ini.read_text().replace('1280x720@60000','1280x720@'+os.environ['MADWAY_TEST_REFRESH']))
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon','libinput'],text=True).split()
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-DWLR_USE_UNSTABLE','-Isrc','tests/device_settings.c','src/devices.c','-o',str(root/'device-settings'),*flags],check=True)
    subprocess.run([str(root/'device-settings')],check=True)
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','-Ibuild/protocols','tests/dock_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
         'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman','MADWAY_SESSION':'1',
         'LIBGL_ALWAYS_SOFTWARE':'1','GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),
         'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery'),'MADWAY_DOCK_TEST':tmp,'XKB_DEFAULT_LAYOUT':'us'}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(key,None)
    if os.environ.get('MADWAY_TEST_REFRESH'):env['MADWAY_FRAME_TEST']=str(root/'frames.jsonl')
    processes=[];logs=[]
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
    def text():return (root/'server.log').read_text()
    def read(path):
        try:return json.loads(path.read_text())
        except (OSError,ValueError):return {}
    def probe_state():return read(root/'probe.json')
    def state():return read(directory/'desktop.json')
    def wait(predicate,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            assert processes[0].poll() is None,text()
            time.sleep(.01)
        raise AssertionError(text()+'\nPROBE '+str(probe_state()))
    def send(name,**values):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
    def core(value):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(value.encode(),str(directory/'compositor.sock'))
    def apply():
        temporary=ini.with_suffix('.tmp')
        with temporary.open('w') as output:cfg.write(output)
        temporary.replace(ini)
        send('apply')
    def command(value):
        p=root/'command.tmp';p.write_text(str(value));p.replace(root/'command')
        wait(lambda:probe_state().get('command')==value)
    def colored_window(name,title,color):
        # A simple software-rendered GTK client avoids GPU/GLFW cursor-theme
        # behavior during synthetic fractional-scale output hotplug.
        program='''import sys,gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
window=Gtk.Window(title=sys.argv[1]);window.set_default_size(700,500)
canvas=Gtk.DrawingArea();window.add(canvas)
def draw(widget,cr):
 cr.set_source_rgb(*[float(value) for value in sys.argv[2].split(',')]);cr.paint()
canvas.connect('draw',draw);window.connect('destroy',Gtk.main_quit)
window.show_all();Gtk.main()
'''
        return spawn(name,[sys.executable,'-c',program,title,color],{**env,'GDK_BACKEND':'wayland'})
    try:
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(probe)).lstrip(':')
        spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload})
        wait(lambda:text().count('Desktop layer mapped: madway-dock')==2)
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY'])
        wait(lambda:probe_state().get('key_q')==ord('q'))
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
        cfg['keyboard']={'layout':'fr','variant':'','options':''};apply()
        wait(lambda:probe_state().get('key_q')==ord('a'))
        cfg['keyboard']['layout']='invalid_madway_layout';apply();wait(lambda:state().get('input_error'))
        assert probe_state()['key_q']==ord('a'),'Invalid layout discarded the working map'
        cfg['keyboard']['layout']='';apply()
        wait(lambda:probe_state().get('key_q')==ord('q') and not state().get('input_error'))
        print('PASS: capability-guarded native tap/mouse configuration; live keyboard layout, invalid-map fallback and original-map restore.')
        command(2)
        settings=spawn('settings',[str(repo/'scripts/madway-shell'),'settings','--page','Audio & brightness'])
        wait(lambda:state().get('title')=='madway — Settings');time.sleep(.25)
        subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build/settings-spacing.png')],env=env,check=True)
        settings.terminate();settings.wait(timeout=5)
        send('panel-menu',page='Desktop',x=0,y=22,edge='top')
        wait(lambda:probe_state().get('menu'));time.sleep(.15)
        assert probe_state()['menu_y']==22,probe_state()
        subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build/panel-menu-flush.png')],env=env,check=True)
        send('close-menu');wait(lambda:not probe_state()['menu'])
        command(2)
        first=colored_window('red','dock-fixture','.56,.12,.12')
        wait(lambda:state().get('title')=='dock-fixture')
        cfg['windows']={'animate':'true','animation_ms':'500'};apply();time.sleep(.15)
        send('window-maximize');wait(lambda:probe_state().get('motion'))
        initial=probe_state()['motion_width'];time.sleep(.08)
        assert probe_state()['motion_width']>initial and not probe_state()['view_enabled']
        wait(lambda:probe_state()['incoming'] or not probe_state()['motion'])
        assert probe_state()['incoming'],'Client-sized content was not captured during the zoom'
        wait(lambda:not probe_state()['motion']);assert probe_state()['view_enabled']
        send('window-maximize');wait(lambda:probe_state()['motion'])
        initial=probe_state()['motion_width'];time.sleep(.08)
        assert probe_state()['motion_width']<initial
        wait(lambda:not probe_state()['motion']);assert probe_state()['view_enabled']
        send('window-maximize');wait(lambda:probe_state()['motion']);time.sleep(.12)
        halfway=probe_state()['motion_width'];send('window-maximize');time.sleep(.03)
        assert probe_state()['motion'] and abs(probe_state()['motion_width']-halfway)<150,'Reversing maximize jumped to an endpoint'
        wait(lambda:not probe_state()['motion'])
        identity=state()['windows'][0]['id']
        send('window-minimize');wait(lambda:probe_state()['motion'])
        initial=probe_state()['motion_width'];time.sleep(.08)
        assert probe_state()['motion_width']<initial and state()['windows'][0]['minimized']
        wait(lambda:not probe_state()['motion']);assert not probe_state()['view_enabled']
        send('taskbar-toggle',id=identity);wait(lambda:probe_state()['motion'])
        core('focus '+str(identity));time.sleep(.04)
        assert probe_state()['motion'],'Follow-up activation canceled the restore animation'
        wait(lambda:not probe_state()['motion']);assert probe_state()['view_enabled'] and not state()['windows'][0]['minimized']
        send('window-maximize');wait(lambda:probe_state()['motion']);command(15)
        wait(lambda:not probe_state()['motion']);assert probe_state()['view_enabled']
        # Disabling animations applies immediately and restores live rendering.
        cfg['windows']['animate']='false';apply();time.sleep(.1)
        send('window-maximize');time.sleep(.1);assert not probe_state()['motion']
        cfg['windows']['animate']='true';apply();time.sleep(.1)
        print('PASS: maximize/restore grows and shrinks; minimize and panel restore animate; click cancellation preserves the live client.')
        send('workspace',value=1);wait(lambda:state().get('workspace')==1 and not probe_state().get('transition'))
        second=colored_window('blue','workspace-blue','.12,.12,.56')
        wait(lambda:state().get('title')=='workspace-blue');send('window-maximize')
        time.sleep(.15);send('workspace',value=0)
        wait(lambda:probe_state().get('transition') and state().get('workspace')==0)
        time.sleep(.2)  # Capture the middle of the gently accelerating slide.
        path=repo/'build/workspace-slide.png'
        subprocess.run(['grim','-o','HEADLESS-1',str(path)],env=env,check=True)
        image=GdkPixbuf.Pixbuf.new_from_file(str(path));pixels=image.get_pixels();stride=image.get_rowstride();channels=image.get_n_channels()
        colors=[]
        for x in range(10,image.get_width()-10,8):
            offset=(image.get_height()//2)*stride+x*channels;colors.append(pixels[offset:offset+3])
        assert any(p[0]>2*p[2] for p in colors) and any(p[2]>2*p[0] for p in colors),'Slide did not contain both workspaces'
        wait(lambda:not probe_state()['transition'])
        assert state()['title']=='dock-fixture'
        # Rapid switches converge on the final requested workspace.
        for number in (1,3,2,0):send('workspace',value=number)
        wait(lambda:state()['workspace']==0 and not probe_state()['transition'])
        send('workspace',value=1);wait(lambda:probe_state()['transition'])
        command(2);command(15);wait(lambda:not probe_state()['transition'])
        assert state()['workspace']==1 and first.poll() is None and second.poll() is None
        print('PASS: real two-workspace pixels slide with fixed panels, rapid switching resolves, and clicking cancels safely.')
        send('panel-menu',page='Workspaces',x=0,y=22,edge='top');wait(lambda:probe_state()['menu'])
        send('workspace',value=0);wait(lambda:probe_state()['transition'])
        send('close-menu');wait(lambda:not probe_state()['menu']);time.sleep(.06)
        assert probe_state()['transition'],'Closing the workspace menu cut the slide short'
        wait(lambda:not probe_state()['transition'])
        print('PASS: workspace slide survives dismissal of its panel menu.')
        # Output disable/rotation during a slide must drop buffers before reconfiguration.
        send('workspace',value=1);wait(lambda:probe_state()['transition'])
        cfg['output:HEADLESS-2']['enabled']='false';apply()
        wait(lambda:not probe_state()['transition'])
        cfg['output:HEADLESS-2'].update(enabled='true',scale='1.25',transform='1');apply()
        time.sleep(.3);assert processes[0].poll() is None
        assert first.poll() is None and second.poll() is None,('clients after output reconfiguration',first.poll(),second.poll())
        cfg['output:HEADLESS-1']['scale']='1.5';apply();time.sleep(.25)
        send('window-maximize');wait(lambda:probe_state()['motion'])
        assert probe_state()['motion_pixels']>probe_state()['motion_width']*1.3,'Snapshot lost the output scale'
        wait(lambda:not probe_state()['motion'])
        cfg['output:HEADLESS-1']['scale']='1';apply();time.sleep(.2)
        print('PASS: fractional-scale snapshots retain native pixel density.')
        cfg['workspaces'].update(animate='false');apply();time.sleep(.2)
        send('workspace',value=1);wait(lambda:state()['workspace']==1);assert not probe_state()['transition']
        cfg['workspaces']['animate']='true';apply();time.sleep(.2)
        send('workspace',value=0);wait(lambda:probe_state()['transition']);core('prepare-sleep')
        wait(lambda:state().get('sleeping') and not probe_state()['transition']);core('resume');wait(lambda:not state()['sleeping'])
        send('workspace',value=1);wait(lambda:not probe_state()['transition'] and state()['workspace']==1)
        send('window-maximize');wait(lambda:probe_state()['motion']);send('lock')
        wait(lambda:state().get('locked') and not probe_state()['transition'] and not probe_state()['motion'])
        assert not state()['windows'] and first.poll() is None and second.poll() is None,('lock',state(),first.poll(),second.poll())
        assert 'Traceback (most recent call last)' not in text(),text()
        if os.environ.get('MADWAY_TEST_REFRESH'):
            frames=[json.loads(line) for line in (root/'frames.jsonl').read_text().splitlines()]
            frames=[row for row in frames if row['output']=='HEADLESS-1']
            intervals=[b['time']-a['time'] for a,b in zip(frames,frames[1:]) if .001<b['time']-a['time']<.035]
            assert frames and all(row['refresh']==100000 for row in frames),frames[:3]
            median=statistics.median(intervals)
            assert median<.014,('Animation still appears capped at 60 Hz',median)
            print(f'PASS: 100 Hz headless animation commits: median interval {median*1000:.2f} ms across {len(intervals)} intervals.')
        print('PASS: output changes, animation off, simulated sleep/resume and lock immediately release transition snapshots. No real suspend/authentication.')
    except BaseException:
        for p in root.glob('*.log'):print(p.name+'\n'+p.read_text()[-13000:])
        raise
    finally:
        for p in reversed(processes):
            if p.poll() is None:p.send_signal(signal.SIGTERM)
        for p in reversed(processes):
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()
