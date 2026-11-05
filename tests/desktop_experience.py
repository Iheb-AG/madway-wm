"""Independent outputs, layer fades, media feedback and persistent dock pinning."""
import configparser
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf
repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-experience-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True);desktop=root/'Desktop';desktop.mkdir()
    for i in range(16):(desktop/(f'{i:02d} '+('a much longer filename which wraps.txt' if i%3==0 else 'short.txt'))).touch()
    ini=config/'madway/settings.ini'
    ini.write_text('[appearance]\ntheme=argent-dark\n[desktop]\nicons=true\n[notifications]\nenabled=true\n[panel]\nmetrics=false\n[windows]\nanimate=false\n[workspaces]\nanimation_ms=500\n[output:HEADLESS-1]\nmode=800x600@100000\nx=0\ny=0\n[output:HEADLESS-2]\nmode=800x600@60000\nx=800\n')
    data=root/'data';(data/'applications').mkdir(parents=True)
    for app in ('org.madway.PinnedFixture','org.madway.OtherFixture'):
        (data/'applications'/(app+'.desktop')).write_text(f'[Desktop Entry]\nType=Application\nName={app.split(".")[-1]}\nExec=/bin/true\nIcon=utilities-terminal\nStartupWMClass={app}\n')
    binaries=root/'bin';binaries.mkdir()
    hardware=root/'hardware.json';hardware.write_text(json.dumps(dict(volume=50,brightness=40)))
    for tool in ('wpctl','brightnessctl'):
        script=binaries/tool
        script.write_text('#!'+sys.executable+'\n'+'''import json,sys
from pathlib import Path
path=Path('''+repr(str(hardware))+''');state=json.loads(path.read_text());args=sys.argv[1:]
if Path(sys.argv[0]).name=='wpctl':
 if args[0]=='get-volume':print('Volume: %.2f'%(state['volume']/100))
 elif args[0]=='set-volume':state['volume']=min(100,state['volume']+5)
else:
 if args[0]=='get':print(state['brightness'])
 elif args[0]=='max':print(100)
 elif args[0]=='set':state['brightness']=int(args[-1].rstrip('%'))
path.write_text(json.dumps(state))
''');script.chmod(0o700)
    program=root/'client.py';program.write_text('''import gi,sys
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
GLib.set_prgname(sys.argv[2]);window=Gtk.Window(title=sys.argv[1]);window.set_default_size(450,300)
canvas=Gtk.DrawingArea();window.add(canvas)
def draw(widget,cr):
 cr.set_source_rgb(*[float(value) for value in sys.argv[3].split(',')]);cr.paint()
canvas.connect('draw',draw);window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main()
''')
    with ini.open('a') as out:out.write('\n[session_effects]\nopening=false\n')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','-Ibuild/protocols','tests/dock_probe.c','-o',str(root/'probe.so'),*flags,'-ldl'],check=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(data),'XDG_CACHE_HOME':str(root/'cache'),
        'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman',
        'PATH':str(binaries)+':'+os.environ['PATH'],'MADWAY_SESSION':'1','GDK_BACKEND':'wayland','GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),
        'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery'),'MADWAY_DOCK_TEST':tmp}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','LD_PRELOAD'):env.pop(key,None)
    processes=[];logs=[]
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
    def text():return (root/'server.log').read_text()
    def read(path):
        try:return json.loads(path.read_text())
        except (OSError,ValueError):return {}
    def state():return read(directory/'desktop.json')
    def probe():return read(root/'probe.json')
    def wait(check,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            assert processes[0].poll() is None,text()
            if check():return
            time.sleep(.01)
        raise AssertionError(text()+'\nSTATE '+str(state())+'\nPROBE '+str(probe()))
    def send(action,**values):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(json.dumps(dict(action=action,**values)).encode(),str(directory/'control.sock'))
    def core(command):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(command.encode(),str(directory/'compositor.sock'))
    def command(number):
        path=root/'command.tmp';path.write_text(str(number));path.replace(root/'command');wait(lambda:probe().get('command')==number)
    point=25
    def motion(x,y):
        global point
        (root/'point').write_text(f'{x} {y}');point=20 if point==25 else 25;command(point)
    def heads():return {row['name']:row for row in probe().get('outputs',[])}
    def rows():return {row['title']:row for row in state().get('all_windows',[])}
    def effect(name):return next((row for row in probe().get('effects',[]) if row['namespace']==name),{})
    def capture(name,output='HEADLESS-1'):
        if os.environ.get('MADWAY_TEST_ARTIFACTS'):
            target=Path(os.environ['MADWAY_TEST_ARTIFACTS']);target.mkdir(parents=True,exist_ok=True)
            subprocess.run(['grim','-o',output,str(target/(name+'.png'))],env=env,check=True,timeout=5)
    def apply():
        with ini.open('w') as output:cfg.write(output)
        send('apply')
    try:
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(root/'probe.so')).lstrip(':')
        spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload})
        wait(lambda:'desktop services ready' in text());env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text())[1]
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY']);cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
        wait(lambda:len(heads())==2 and probe().get('desktop_layers')==2)
        assert not effect('madway-osd'),'Resident feedback flashed at startup'
        time.sleep(.2);capture('desktop-grid','HEADLESS-2')
        motion(15,10);command(21);command(22);wait(lambda:probe().get('menu'))
        motion(15,10);command(21);command(22);wait(lambda:not probe().get('menu'))
        time.sleep(.15);assert not probe().get('menu'),'Second panel click reopened its menu'
        motion(15,10);command(21);command(22);wait(lambda:probe().get('menu'))
        motion(780,10);command(21);command(22);wait(lambda:probe().get('menu'))
        motion(780,10);command(21);command(22);wait(lambda:not probe().get('menu'))
        motion(15,10);command(21);command(22);wait(lambda:probe().get('menu'))
        motion(400,10);command(21);command(22);wait(lambda:not probe().get('menu'))
        print('PASS: real panel clicks toggle the same menu and replace it when another button is clicked.',flush=True)
        def panels():return sum(row['namespace']=='madway-panel' for row in probe().get('effects',[]))
        wait(lambda:panels()==2);usable=probe()['usable']
        motion(15,10);command(21);command(22);wait(lambda:probe().get('menu'))
        command(45);wait(lambda:panels()==0 and not probe().get('menu'))
        assert probe()['usable']==usable+cfg.getint('panel','height',fallback=18),('Hidden panel still reserved window space',usable,probe()['usable'])
        saved=configparser.ConfigParser(interpolation=None);saved.read(ini);assert not saved.getboolean('panel','enabled')
        motion(200,180);command(45);wait(lambda:panels()==2 and probe()['usable']==usable)
        saved.read(ini);assert saved.getboolean('panel','enabled')
        cfg['input']={'modifier':'super'};apply();wait(lambda:probe().get('use_super'))
        command(46);wait(lambda:panels()==0)
        command(45);time.sleep(.15);assert panels()==0,'Alt binding remained active with Super configured'
        command(46);wait(lambda:panels()==2)
        cfg['input']['modifier']='alt';apply();wait(lambda:not probe().get('use_super'))
        print('PASS: Alt/Super+B hides/restores both panels, persists the preference, closes menus and releases/restores reserved space.',flush=True)
        motion(200,180);spawn('red',[sys.executable,str(program),'A-zero','org.madway.PinnedFixture','.65,.1,.1']);wait(lambda:'A-zero' in rows())
        send('window-maximize');time.sleep(.2)
        motion(1100,200);spawn('blue',[sys.executable,str(program),'B-zero','org.madway.OtherFixture','.1,.1,.65']);wait(lambda:'B-zero' in rows())
        assert rows()['A-zero']['output']=='HEADLESS-1' and rows()['B-zero']['output']=='HEADLESS-2',(rows(),heads(),state().get('outputs'))
        core('workspace 1 HEADLESS-1');wait(lambda:heads()['HEADLESS-1']['transition'])
        time.sleep(.15);assert heads()['HEADLESS-1']['transition'] and heads()['HEADLESS-2']['workspace']==0
        assert rows()['B-zero']['visible_workspace'] and not rows()['A-zero']['visible_workspace']
        wait(lambda:not heads()['HEADLESS-1']['transition'])
        motion(200,180);spawn('green',[sys.executable,str(program),'A-one','org.madway.PinnedFixture','.1,.65,.1']);wait(lambda:'A-one' in rows())
        for title in ('A-one','B-zero'):send('window-floating',id=rows()[title]['id'])
        wait(lambda:not rows()['A-one']['floating'] and not rows()['B-zero']['floating'])
        core('focus '+str(rows()['A-one']['id']));wait(lambda:rows()['A-one']['focused'])
        before=[row['id'] for row in state()['all_windows']]
        send('tile-swap',id=rows()['B-zero']['id']);time.sleep(.1)
        assert [row['id'] for row in state()['all_windows']]==before and rows()['A-one']['focused']
        send('tile-swap',id=rows()['A-zero']['id']);time.sleep(.1)
        assert [row['id'] for row in state()['all_windows']]==before and heads()['HEADLESS-1']['workspace']==1
        for title in ('A-one','B-zero'):send('window-floating',id=rows()[title]['id'])
        wait(lambda:rows()['A-one']['floating'] and rows()['B-zero']['floating'])
        print('PASS: tile swaps reject another monitor and hidden workspace without changing focus or workspace.',flush=True)
        core('workspace 0 HEADLESS-1');wait(lambda:heads()['HEADLESS-1']['transition']);time.sleep(.12)
        assert heads()['HEADLESS-1']['transition'],'Application/layout commits cancelled the slide'
        wait(lambda:not heads()['HEADLESS-1']['transition'])
        core('workspace 1 HEADLESS-1');wait(lambda:heads()['HEADLESS-1']['transition']);motion(1100,200)
        core('workspace 1 HEADLESS-2');wait(lambda:heads()['HEADLESS-2']['transition'])
        assert heads()['HEADLESS-1']['transition'],'Switching the second output cancelled the first slide'
        wait(lambda:not any(row['transition'] for row in heads().values()))
        core('workspace 0 HEADLESS-2');wait(lambda:heads()['HEADLESS-2']['workspace']==0)
        assert heads()['HEADLESS-1']['workspace']==1 and rows()['A-one']['visible_workspace']
        print('PASS: independent output workspaces/focus, maximized-window slides and simultaneous per-output transitions.',flush=True)
        motion(200,180);send('launcher');wait(lambda:effect('madway-launcher').get('active') and 0<effect('madway-launcher').get('opacity',0)<1)
        wait(lambda:effect('madway-launcher').get('opacity')==1 and effect('madway-launcher').get('cache'))
        capture('launcher')
        send('launcher');wait(lambda:probe().get('closing',0)>0);wait(lambda:not probe()['closing'])
        assert not effect('madway-launcher')
        for index,color in enumerate((0x802020ff,0x202080ff)):
            image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,8,8);image.fill(color);image.savev(str(root/f'wallpaper{index}.png'),'png',[],[])
        cfg['wallpaper']={'type':'image','path':str(root/'wallpaper0.png'),'color':'#000000','mode':'fill'};apply()
        wait(lambda:any(row.get('fading') for row in state().get('backgrounds',[])))
        wait(lambda:len(state().get('backgrounds',[]))==2 and not any(row.get('fading') for row in state()['backgrounds']))
        cfg['wallpaper']['path']=str(root/'wallpaper1.png');apply()
        wait(lambda:any(row.get('fading') for row in state().get('backgrounds',[])))
        assert len(state()['backgrounds'])>=3,'Old background retired before the fade completed'
        wait(lambda:len(state()['backgrounds'])==2 and not any(row.get('fading') for row in state()['backgrounds']))
        print('PASS: launcher fade/slide in and cached fade-out; wallpaper crossfade retains old pixels until all outputs finish.',flush=True)
        requested=time.monotonic();send('volume-up');wait(lambda:bool(effect('madway-osd')))
        first_latency=time.monotonic()-requested;media_pid=effect('madway-osd')['pid']
        assert effect('madway-osd')['opacity']==1 and not effect('madway-osd')['active'],'Media feedback waited on entrance animation'
        wait(lambda:read(hardware).get('volume')==55)
        time.sleep(.25);capture('media-feedback')
        send('brightness-up');wait(lambda:read(hardware).get('brightness')==45)
        wait(lambda:not effect('madway-osd'),timeout=4)
        requested=time.monotonic();command(40);wait(lambda:bool(effect('madway-osd')))
        next_latency=time.monotonic()-requested
        assert effect('madway-osd')['pid']==media_pid,'The media indicator restarted instead of staying warm'
        assert max(first_latency,next_latency)<.3,(first_latency,next_latency)
        motion(1100,180);command(40);wait(lambda:effect('madway-osd').get('x',0)>800)
        assert effect('madway-osd')['pid']==media_pid,'Changing monitor restarted the warm indicator'
        motion(200,180)
        print(f'PASS: warm media feedback appears immediately without entrance fading ({first_latency*1000:.0f}/{next_latency*1000:.0f} ms on mocked hardware).',flush=True)
        subprocess.run([sys.executable,str(repo/'tests/experience_ui.py')],env=env,check=True,timeout=10)
        subprocess.run([sys.executable,str(repo/'tests/spotlight_ui.py')],env=env,check=True,timeout=10)
        subprocess.run([sys.executable,str(repo/'tests/customization_ui.py')],env=env,check=True,timeout=15)
        core('activate '+str(rows()['A-one']['id']));send('window-fullscreen');wait(lambda:probe().get('focused_fullscreen'))
        def first_panel():return next(row for row in probe()['effects'] if row['namespace']=='madway-panel' and row['x']==0)
        wait(lambda:not first_panel()['visible'])
        for iteration in range(4):
            subprocess.run(['notify-send','--expire-time=120','Private fullscreen regression',str(iteration)],env=env,check=True,timeout=4)
            send('volume-up');time.sleep(.12)
            assert probe()['focused_fullscreen'] and not first_panel()['visible'],'Overlay commits re-enabled a fullscreen panel'
        time.sleep(.4);assert not first_panel()['visible']
        send('window-fullscreen');wait(lambda:not probe()['focused_fullscreen'] and first_panel()['visible'])
        print('PASS: notification and media map/update/unmap events cannot reveal the panel over a fullscreen application.',flush=True)
        motion(probe()['x']+probe()['width']-22,probe()['y']+probe()['height']/2)
        command(44);wait(lambda:probe().get('menu'))
        send('close-menu');wait(lambda:not probe()['menu'])
        identity='org.madway.PinnedFixture.desktop';send('dock-pin',app_id=identity)
        def pinned():
            current=configparser.ConfigParser(interpolation=None);current.read(ini)
            return json.loads(current.get('dock','pinned',fallback='[]'))
        wait(lambda:identity in pinned())
        wait(lambda:any(value.startswith('custom/pin') for value in read(directory/'dock.json').get('modules-center',[])))
        dock=read(directory/'dock.json')
        assert any(value.startswith('custom/pin') for value in dock['modules-center'])
        pin=next(value for value in dock['modules-center'] if value.startswith('custom/pin'))
        assert dock[pin]['on-click-right'].endswith(identity) and dock['wlr/taskbar']['on-click-right']=='activate'
        wait(lambda:text().count('Using configuration file')>=2 and len([row for row in probe()['effects'] if row['namespace']=='madway-dock'])==2)
        time.sleep(.25)
        click_x=probe()['x']+probe()['width']-22;click_y=probe()['y']+probe()['height']/2
        motion(click_x,click_y);command(44);wait(lambda:probe().get('menu'))
        assert abs(state()['pointer_x']-click_x)<=1 and abs(state()['pointer_y']-click_y)<=1,'Pinned context used stale pointer coordinates'
        send('close-menu');wait(lambda:not probe()['menu'])
        send('application-menu',id=rows()['A-one']['id'],x=200,y=22);wait(lambda:probe().get('menu'))
        send('close-menu');wait(lambda:not probe()['menu'])
        send('dock-launch',app_id=identity);wait(lambda:state().get('app_id')=='org.madway.PinnedFixture')
        send('dock-unpin',app_id=identity);wait(lambda:not pinned())
        print('PASS: pins persist, produce Waybar launch/context modules, activate existing clients, and unpin cleanly.',flush=True)
        cfg['appearance'].update(font='monospace',title_font_size='11',custom_colors='true',icon_theme='Adwaita')
        cfg['colors']={'active':'#225577'};apply()
        wait(lambda:probe().get('style_custom') and probe().get('style_title_size')==11 and probe().get('style_active')==0x225577)
        print('PASS: native compositor reloads the saved custom palette and title font size.',flush=True)
        cfg['windows']['close_ms']='500';apply();time.sleep(.2)
        def closing_client(name):
            motion(200,180)
            process=spawn(name,[sys.executable,str(program),name,'org.madway.OtherFixture','.7,.05,.7'])
            wait(lambda:name in rows());time.sleep(.08);return process
        def image_pixels(name):
            path=root/(name+'.png');subprocess.run(['grim','-o','HEADLESS-1',str(path)],env=env,check=True,timeout=5)
            if os.environ.get('MADWAY_TEST_ARTIFACTS'):(Path(os.environ['MADWAY_TEST_ARTIFACTS'])/(name+'.png')).write_bytes(path.read_bytes())
            return GdkPixbuf.Pixbuf.new_from_file(str(path))
        closing=closing_client('closing-fixture');before=image_pixels('close-before');pixels=before.get_pixels();stride=before.get_rowstride();channels=before.get_n_channels()
        points=[(x,y) for y in range(before.get_height()) for x in range(before.get_width()) if pixels[y*stride+x*channels]>140 and pixels[y*stride+x*channels+1]<40 and pixels[y*stride+x*channels+2]>140]
        assert points,'Closing fixture did not paint its content'
        center=((min(x for x,y in points)+max(x for x,y in points))//2,(min(y for x,y in points)+max(y for x,y in points))//2)
        closing.terminate();wait(lambda:probe().get('window_closing',0)==1 and 'closing-fixture' not in rows())
        after=image_pixels('close-during');offset=center[1]*after.get_rowstride()+center[0]*after.get_n_channels();color=after.get_pixels()[offset:offset+3]
        assert color[0]>40 and color[2]>40,('Application pixels disappeared before the closing animation',center,list(color),probe().get('window_closing'))
        motion(*center);command(21);command(22);assert state().get('title')=='A-one','Closing snapshot intercepted input'
        wait(lambda:not probe().get('window_closing'))
        closing=closing_client('closing-workspace');closing.terminate();wait(lambda:probe().get('window_closing')==1)
        core('workspace 2 HEADLESS-1');wait(lambda:not probe().get('window_closing'));core('workspace 1 HEADLESS-1');wait(lambda:not heads()['HEADLESS-1']['transition'])
        cfg['windows']['close_animate']='false';apply();time.sleep(.2)
        closing=closing_client('closing-disabled');closing.terminate();wait(lambda:'closing-disabled' not in rows());assert not probe().get('window_closing')
        cfg['windows']['close_animate']='true';apply();time.sleep(.2)
        core('activate '+str(rows()['B-zero']['id']));send('window-close');wait(lambda:probe().get('window_closing')==1)
        command(55);wait(lambda:len(heads())==1);assert not probe().get('window_closing')
        print('PASS: closing retains application pixels after exit, passes input through, honors its toggle, and cleans up on workspace switch/output removal.',flush=True)
        closing=closing_client('closing-lock');closing.terminate();wait(lambda:probe().get('window_closing')==1)
        send('launcher');wait(lambda:effect('madway-launcher').get('active'));core('lock-blank')
        wait(lambda:state().get('locked'));assert not probe().get('closing')
        assert not any(row['active'] for row in probe().get('effects',[]))
        assert not probe().get('window_closing')
        before=ini.read_text();command(45);time.sleep(.15);assert ini.read_text()==before,'Panel shortcut ran while locked'
        print('PASS: locking clears layer animation caches and transient closing images.',flush=True)
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-7000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
