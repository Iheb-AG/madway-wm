"""Real desktop icons and wl_data_device drags on a private headless output."""
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

repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-desktop-files-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    desktop=root/'Desktop';desktop.mkdir();(desktop/'Folder').mkdir();(desktop/'Notes.txt').write_text('desktop note')
    (desktop/'Another.txt').write_text('another');source=root/'Incoming.txt';source.write_text('dragged into desktop')
    config=root/'config';(config/'madway').mkdir(parents=True)
    (config/'user-dirs.dirs').write_text('XDG_DESKTOP_DIR="'+str(desktop)+'"\n')
    ini=config/'madway/settings.ini';ini.write_text('[appearance]\ntheme=gershwin-dark\ntitle_height=22\n[desktop]\nicons=true\nfolder='+str(desktop)+'\n[notifications]\nenabled=false\n[panel]\nheight=22\nmetrics=false\n[wallpaper]\ntype=color\ncolor=#31404c\n[output:HEADLESS-1]\nmode=1280x720@60000\n')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    probe=root/'probe.so';subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','-Ibuild/protocols','tests/dock_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
         'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_RENDERER':'pixman','MADWAY_SESSION':'1','LIBGL_ALWAYS_SOFTWARE':'1',
         'GDK_BACKEND':'wayland','GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),
         'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery'),'MADWAY_DOCK_TEST':tmp}
    for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','LD_PRELOAD']:env.pop(key,None)
    processes=[];logs=[]
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
    def text():return (root/'server.log').read_text()
    def read(path):
        try:return json.loads(path.read_text())
        except (ValueError,OSError):return {}
    def state():return read(directory/'desktop.json')
    def snapshot():return read(root/'probe.json')
    def wait(check,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if check():return
            assert processes[0].poll() is None,text();time.sleep(.02)
        raise AssertionError(text()+'\n'+str(snapshot()))
    def command(number):
        temp=root/'command.tmp';temp.write_text(str(number));temp.replace(root/'command')
        wait(lambda:snapshot().get('command')==number)
    point_command=25
    def motion(x,y):
        global point_command
        (root/'point').write_text(f'{x} {y}')
        point_command=20 if point_command==25 else 25;command(point_command)
    def send(name,**values):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
    def capture(name):subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build'/name)],env=env,check=True,timeout=5)
    try:
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(probe)).lstrip(':')
        spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload})
        wait(lambda:'Desktop layer mapped: madway-desktop' in text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY']);wait(lambda:snapshot().get('width',0)>0)
        time.sleep(.3);capture('desktop-icons.png')
        original=set(desktop.iterdir())
        motion(400,180);command(26);time.sleep(.15);command(34)
        def icons_enabled():
            config_state=configparser.ConfigParser(interpolation=None);config_state.read(ini)
            return config_state.getboolean('desktop','icons')
        wait(lambda:not icons_enabled() and snapshot().get('desktop_layers')==0)
        motion(410,180);command(26);wait(lambda:snapshot().get('menu'))
        time.sleep(.1);command(35)
        wait(lambda:icons_enabled() and snapshot().get('desktop_layers')==1)
        assert set(desktop.iterdir())==original
        print('PASS: empty-space Hide/Show actions persist the preference, restore the desktop and leave files untouched.')
        motion(400,180);command(26);time.sleep(.15);capture('desktop-file-menu.png')
        command(27);wait(lambda:state().get('title')=='New folder');time.sleep(.1);command(28)
        wait(lambda:(desktop/'New folder').is_dir());(desktop/'New folder').rmdir()
        wait(lambda:not state().get('has_window'))
        motion(400,180);command(26);time.sleep(.1);command(29)
        wait(lambda:state().get('title')=='New text file');time.sleep(.1);command(28)
        wait(lambda:(desktop/'Untitled.txt').is_file());(desktop/'Untitled.txt').unlink()
        print('PASS: native desktop right-click menu creates folders and files through compact dialogs.')
        send('settings-page',page='Windows');wait(lambda:state().get('title')=='madway — Settings')
        time.sleep(.2);capture('settings-compact.png');send('window-close')
        wait(lambda:not state().get('has_window'))
        program=root/'drag-client.py';program.write_text('''import gi,sys,json
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
window=Gtk.Window(title='drag-source');window.set_decorated(False);window.set_default_size(320,220)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.add(box)
source=Gtk.EventBox();source.add(Gtk.Label(label='Drag Incoming.txt to the desktop'))
source.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,[Gtk.TargetEntry.new('text/uri-list',0,0)],Gdk.DragAction.COPY)
source.connect('drag-data-get',lambda widget,context,data,info,time:data.set_uris([Path(sys.argv[1]).as_uri()]))
box.pack_start(source,True,True,0)
target=Gtk.EventBox();target.add(Gtk.Label(label='Drop a desktop file here'))
target.drag_dest_set(Gtk.DestDefaults.ALL,[Gtk.TargetEntry.new('text/uri-list',0,0)],Gdk.DragAction.COPY)
def received(widget,context,x,y,data,info,time):
 Path(sys.argv[2]).write_text(json.dumps(data.get_uris()));Gtk.drag_finish(context,True,False,time)
target.connect('drag-data-received',received);box.pack_start(target,True,True,0)
window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main()
''')
        client=spawn('drag-client',[sys.executable,str(program),str(source),str(root/'received.json')])
        wait(lambda:state().get('title')=='drag-source');command(24);time.sleep(.2)
        motion(450,200);command(26);wait(lambda:snapshot().get('desktop_menu_above'))
        capture('desktop-menu-over-window.png');command(23);time.sleep(.1)
        print('PASS: desktop context menus render and receive input above application windows.')
        motion(650,235);command(21);motion(630,235);wait(lambda:snapshot().get('drag'))
        motion(350,420);command(22)
        wait(lambda:(desktop/'Incoming.txt').exists() and not snapshot()['drag'])
        assert (desktop/'Incoming.txt').read_text()=='dragged into desktop' and source.exists()
        motion(650,235);command(21);motion(630,235);wait(lambda:snapshot()['drag'])
        motion(62,70);command(22);wait(lambda:(desktop/'Folder/Incoming.txt').exists() and not snapshot()['drag']);time.sleep(.2)
        print('PASS: real application-to-desktop Wayland URI drag copies a file.')
        # First item is the folder, second icon is Another.txt in the ordered grid.
        motion(166,70);command(21);motion(185,75);wait(lambda:snapshot()['drag'])
        motion(650,355);command(22)
        wait(lambda:(root/'received.json').exists() and not snapshot()['drag'])
        assert any(uri.startswith(desktop.as_uri()+'/') for uri in read(root/'received.json'))
        print('PASS: desktop-to-application Wayland URI drag delivers the selected file.')
        motion(166,70);command(21);command(22);command(31);time.sleep(.1);command(32)
        wait(lambda:(desktop/'Another (copy).txt').exists())
        assert (desktop/'Another (copy).txt').read_text()=='another'
        (desktop/'Another (copy).txt').unlink();time.sleep(.25)
        print('PASS: desktop copy/paste transfers file URIs through the Wayland clipboard without overwriting.')
        motion(166,70);command(26);time.sleep(.1);command(30)
        wait(lambda:not (desktop/'Another.txt').exists())
        assert any(p.read_text()=='another' for p in (root/'data/Trash/files').iterdir())
        print('PASS: native item menu moves a selected file into the private Trash.')
        time.sleep(.25)
        motion(166,70);command(21);motion(185,75);wait(lambda:snapshot()['drag'])
        motion(350,500);command(22)
        wait(lambda:(config/'madway/desktop-order.json').exists() and not snapshot()['drag'])
        assert read(config/'madway/desktop-order.json')[-1]=='Incoming.txt'
        print('PASS: dragging within the desktop reorders the grid and saves icon order.')
        before=set(desktop.iterdir())
        motion(650,235);command(21);motion(630,235);wait(lambda:snapshot()['drag']);command(23);command(22)
        wait(lambda:not snapshot()['drag']);assert set(desktop.iterdir())==before
        print('PASS: Escape cancels an active drag without performing a file drop.')
        motion(650,235);command(21);motion(630,235);wait(lambda:snapshot()['drag']);send('lock')
        wait(lambda:state().get('locked') and not snapshot()['drag']);command(22)
        assert set(desktop.iterdir())==before and client.poll() is None
        assert 'Traceback (most recent call last)' not in text(),text()
        print('PASS: locking cancels active drag before release; no hidden drop or client loss.')
    except BaseException:
        for path in root.glob('*.log'):print(path.name+'\n'+path.read_text()[-15000:])
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.send_signal(signal.SIGTERM)
        for process in reversed(processes):
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
