"""Real window previews, task display modes and wallpaper rotation in isolation."""
import configparser
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import tempfile
import time
import zlib
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf

repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
def png(path,color):
    def chunk(k,d):return struct.pack('!I',len(d))+k+d+struct.pack('!I',zlib.crc32(k+d)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',2,2,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes(color)*2)*2))+chunk(b'IEND',b''))
with tempfile.TemporaryDirectory(prefix='madway-preview-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
    config=root/'config';(config/'madway').mkdir(parents=True)
    images=root/'slides';images.mkdir();red=images/'01 red.png';blue=images/'02 blue.png'
    png(red,(180,20,20));png(blue,(20,20,180));(images/'invalid.png').write_text('bad image')
    ini=config/'madway/settings.ini'
    ini.write_text('[appearance]\ntheme=gershwin-dark\ntitle_height=22\n[panel]\nheight=22\nmetrics=false\n[notifications]\nenabled=false\n[wallpaper]\ntype=slideshow\nsource=folder\nfolder='+str(images)+'\ninterval=1\n')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
    probe=root/'probe.so'
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','-Ibuild/protocols','tests/dock_probe.c','-o',str(probe),*flags,'-ldl'],check=True)
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
         'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_RENDERER':'pixman','MADWAY_SESSION':'1','GIO_USE_VFS':'local',
         'LIBGL_ALWAYS_SOFTWARE':'1','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery'),'MADWAY_DOCK_TEST':tmp}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(key,None)
    processes=[];logs=[]
    def spawn(name,args,environment=env):
        log=(root/(name+'.log')).open('w');logs.append(log)
        p=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(p);return p
    def text():return (root/'server.log').read_text()
    def wait(check,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if check():return
            assert processes[0].poll() is None,text()
            time.sleep(.025)
        raise AssertionError(text())
    def read(path):
        try:return json.loads(path.read_text())
        except (OSError,ValueError):return {}
    def state():return read(directory/'desktop.json')
    def wallpaper():return read(directory/'wallpaper.json')
    def send(name,**values):
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
    def command(number):
        p=root/'command.tmp';p.write_text(str(number));p.replace(root/'command')
        wait(lambda:read(root/'probe.json').get('command')==number)
    def apply_config():
        temporary=ini.with_suffix('.tmp')
        with temporary.open('w') as output:cfg.write(output)
        temporary.replace(ini)
        send('apply');time.sleep(.2)
    def pixel(path):
        image=GdkPixbuf.Pixbuf.new_from_file(str(path));x=image.get_width()//2;y=image.get_height()//2
        offset=y*image.get_rowstride()+x*image.get_n_channels();return tuple(image.get_pixels()[offset:offset+3])
    try:
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(probe)).lstrip(':')
        spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload})
        wait(lambda:'desktop services ready' in text())
        env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
        directory=runtime/('madway-'+env['WAYLAND_DISPLAY'])
        wait(lambda:wallpaper().get('count')==2)
        first=wallpaper()['path'];wait(lambda:wallpaper().get('path')!=first)
        wait(lambda:len(state().get('backgrounds',[]))==1)
        assert wallpaper()['path'] in {str(red),str(blue)}
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
        cfg['wallpaper'].update(source='files',images=json.dumps([str(blue),str(red)]),interval='2')
        apply_config();before=wallpaper()['path'];send('wallpaper-next')
        wait(lambda:wallpaper().get('path')!=before)
        wait(lambda:len(state().get('backgrounds',[]))==1)
        assert wallpaper()['count']==2
        # Removing a selected image is tolerated; all missing files fall back to color.
        blue.unlink();send('wallpaper-next');wait(lambda:wallpaper().get('path')==str(red))
        red.unlink();wait(lambda:wallpaper().get('error') and not wallpaper().get('path'))
        png(red,(180,20,20));png(blue,(20,20,180));send('wallpaper-next')
        wait(lambda:wallpaper().get('path') and not wallpaper().get('error'))
        print('PASS: real folder and selected-image rotation, interval/manual next, mapped handoff, deletion fallback and recovery.')
        for title,color in [('dock-fixture','#802020'),('dock-two','#202080'),('dock-three','#208020')]:
            spawn(title,['kitty','--config','NONE','--title',title,'-o','linux_display_server=wayland','-o','background='+color,'-o','confirm_os_window_close=0','/bin/sh','-c','sleep 120'])
        wait(lambda:len(state().get('windows',[]))==3)
        rows={row['title']:row for row in state()['windows']}
        identity=rows['dock-three']['id'];send('switcher-select',id=identity);send('window-minimize')
        wait(lambda:any(row['id']==identity and row['minimized'] for row in state()['windows']))
        command(11);wait(lambda:state().get('switcher'))
        wait(lambda:all(row.get('preview') for row in state()['windows']))
        expected={'dock-fixture':0,'dock-two':2,'dock-three':1}
        for row in state()['windows']:
            path=directory/'previews'/f"{row['id']}.png"
            assert path.exists() and path.stat().st_mode&0o077==0
            color=pixel(path);channel=expected[row['title']]
            assert color[channel]>80 and color[channel]>2*max(value for index,value in enumerate(color) if index!=channel),(row,color)
        wait(lambda:'Desktop layer mapped: madway-switcher' in text())
        time.sleep(.4)
        subprocess.run(['grim','-o','HEADLESS-1',str(repo/'build/window-previews.png')],env=env,check=True)
        command(12);command(13);wait(lambda:not state()['switcher'])
        print('PASS: independent image content for covered/minimized windows, private PNGs and real preview switcher cycling.')
        ui=root/'tasks.py';ui.write_text('''import runpy,gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
api=runpy.run_path(SCRIPT);bar=api['TopBar']();errors=[]
def check(mode):
 try:
  for item in bar.bars:
   for button in item['minimized_box'].get_children():
    if mode=='icons':assert button.get_label()=='' and button.get_image() is not None
    else:assert button.get_image() is None and 'kitty' in button.get_label().lower() and 'dock-' not in button.get_label()
 except BaseException as error:errors.append(error)
 if mode=='icons':
  bar.config['panel']['tasks']='names';bar.rebuild();GLib.timeout_add(180,lambda:check('names'))
 else:
  for item in bar.bars:item['window'].destroy()
  bar.bars.clear();Gtk.main_quit()
 return False
GLib.timeout_add(180,lambda:check('icons'));Gtk.main()
if errors:raise errors[0]
shell=api['api']
def walk(widget):
 yield widget
 if isinstance(widget,Gtk.Container):
  for child in widget.get_children():yield from walk(child)
class ImageDialog:
 def __init__(self,**kwargs):pass
 def add_buttons(self,*args):pass
 def set_select_multiple(self,value):assert value
 def add_filter(self,value):pass
 def run(self):return Gtk.ResponseType.OK
 def get_filenames(self):return IMAGES
 def destroy(self):pass
Gtk.FileChooserDialog=ImageDialog
def inspect_settings():
 import configparser,json
 window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings')
 try:
  stack=next(w for w in walk(window) if isinstance(w,Gtk.Stack))
  def field(page,label):
   grid=next(w for w in walk(stack.get_child_by_name(page)) if isinstance(w,Gtk.Grid))
   for widget in grid.get_children():
    if isinstance(widget,Gtk.Label) and widget.get_text()==label:return grid.get_child_at(1,grid.child_get_property(widget,'top-attach'))
   raise AssertionError(label)
  field('Appearance','Background').set_active_id('slideshow')
  enabled=field('Appearance','Enable slideshow');assert enabled.get_active()
  field('Appearance','Slideshow source').set_active_id('files')
  field('Appearance','Change image every (seconds)').set_value(3)
  selection=field('Appearance','Slideshow images')
  next(w for w in walk(selection) if isinstance(w,Gtk.Button) and w.get_label()=='Clear').clicked()
  next(w for w in walk(selection) if isinstance(w,Gtk.Button) and w.get_label()=='Add images…').clicked()
  assert len(next(w for w in walk(selection) if isinstance(w,Gtk.ListBox)).get_children())==2
  apply=next(w for w in walk(window) if isinstance(w,Gtk.Button) and w.get_label()=='Apply');apply.clicked()
  cfg=configparser.ConfigParser(interpolation=None);cfg.read(shell['CONFIG'])
  assert cfg.get('wallpaper','source')=='files' and cfg.getint('wallpaper','interval')==3
  assert json.loads(cfg.get('wallpaper','images'))==IMAGES
  enabled.set_active(False);apply.clicked();cfg.read(shell['CONFIG'])
  assert not cfg.getboolean('wallpaper','slideshow_enabled') and json.loads(cfg.get('wallpaper','images'))==IMAGES
  assert not field('Appearance','Preview slideshow').get_sensitive()
  enabled.set_active(True);apply.clicked();cfg.read(shell['CONFIG']);assert cfg.getboolean('wallpaper','slideshow_enabled')
  field('Appearance','Slideshow source').set_active_id('folder')
  next(w for w in walk(field('Appearance','Slideshow folder')) if isinstance(w,Gtk.Entry)).set_text(FOLDER)
  apply.clicked();cfg.read(shell['CONFIG']);assert cfg.get('wallpaper','source')=='folder' and cfg.get('wallpaper','folder')==FOLDER
 except BaseException as error:errors.append(error)
 window.destroy();return False
GLib.timeout_add(250,inspect_settings);shell['settings_window']('Appearance')
if errors:raise errors[0]
'''.replace('SCRIPT',repr(str(repo/'scripts/madway-panel'))).replace('IMAGES',repr([str(red),str(blue)])).replace('FOLDER',repr(str(images))))
        subprocess.run(['python3',str(ui)],env=env,check=True,timeout=8)
        print('PASS: GTK task buttons use icons or app names; settings save selected images/folder and interval.')
        # Stop slideshow scheduling by choosing a solid background.
        cfg['wallpaper'].update(type='color',color='#123456');apply_config()
        wait(lambda:wallpaper().get('type')=='color');count=text().count('Desktop layer mapped: wallpaper')
        time.sleep(2.2);assert text().count('Desktop layer mapped: wallpaper')==count
        command(11);wait(lambda:state()['switcher']);command(14);wait(lambda:not state()['switcher'])
        send('lock');wait(lambda:state().get('locked') and state().get('lock_ready'))
        wait(lambda:not list((directory/'previews').glob('*.png')))
        assert not state()['windows']
        assert 'Traceback (most recent call last)' not in text(),text()
        print('PASS: slideshow timer stops on solid mode, switcher cancel works, and lock deletes all previews.')
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
