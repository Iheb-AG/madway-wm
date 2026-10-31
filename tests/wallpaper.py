"""Slideshow selection, scheduling and failure recovery without real processes."""
import configparser
import json
from pathlib import Path
import runpy
import struct
import tempfile
import zlib

repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway_wallpaper.py'))
defaults=runpy.run_path(str(repo/'scripts/madway-shell'))['DEFAULTS']


def png(path,color):
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',2,2,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes(color)*2)*2))+chunk(b'IEND',b''))


class Timers:
    def __init__(self):self.active={};self.serial=0
    def timeout_add(self,delay,callback):
        self.serial+=1;self.active[self.serial]=(delay,callback);return self.serial
    def timeout_add_seconds(self,delay,callback):return self.timeout_add(delay*1000,callback)
    def source_remove(self,source):self.active.pop(source,None)
    def fire(self,source):
        callback=self.active[source][1]
        if not callback():self.active.pop(source,None)


class Process:
    def __init__(self,pid):self.pid=pid;self.code=None
    def poll(self):return self.code


class Desktop:
    def __init__(self,path):self.directory=path;self.GLib=Timers();self.children={};self.calls=[]
    def spawn(self,key,args):
        self.calls.append(args);process=Process(100+len(self.calls));self.children[key]=process;return process
    def terminate(self,key):
        process=self.children.pop(key,None)
        if process:process.code=0


with tempfile.TemporaryDirectory(prefix='madway-wallpaper-unit-') as tmp:
    root=Path(tmp);images=root/'photos';images.mkdir()
    shell=runpy.run_path(str(repo/'scripts/madway-shell'))
    legacy=root/'legacy.ini';legacy.write_text('[windows]\nanimation_ms=180\n[workspaces]\nanimation_ms=220\n[dock]\nanimation_ms=180\n')
    shell['settings'].__globals__['CONFIG']=legacy
    upgraded=shell['settings']()
    assert [upgraded.getint(section,'animation_ms') for section in ['windows','workspaces','dock']]==[360,420,240]
    legacy.write_text(legacy.read_text()+'\n[motion]\nversion=2\n')
    assert shell['settings']().getint('windows','animation_ms')==180,'Explicit new preferences must be retained'
    a=images/'01 red.png';b=images/'02 blue.png';png(a,(180,0,0));png(b,(0,0,180))
    (images/'invalid.png').write_text('not an image');(images/'subfolder').mkdir()
    config=configparser.ConfigParser(interpolation=None);config.read_dict(defaults)
    config['wallpaper'].update(type='slideshow',source='folder',folder=str(images),interval='3')
    assert api['slideshow_images'](config)==[a,b]
    api['validate'](config)
    config['wallpaper'].update(source='files',images=json.dumps([str(b),str(a),str(b),str(images/'absent')]))
    assert api['slideshow_images'](config)==[b,a]
    for interval in ('0','86401','wrong'):
        config['wallpaper']['interval']=interval
        try:api['validate'](config)
        except ValueError:pass
        else:raise AssertionError('Bad interval accepted')
    config['wallpaper'].update(source='folder',interval='3')
    desktop=Desktop(root);controller=api['WallpaperController'](desktop)
    controller.apply(config);assert controller.current==a and len(desktop.calls)==1
    controller.apply(config);assert len(desktop.calls)==1,'Unrelated settings must not restart wallpaper'
    old=desktop.children['wallpaper'];controller.next()
    new=desktop.children['wallpaper'];assert controller.current==b and old.poll() is None
    state=root/'desktop.json'
    state.write_text(json.dumps(dict(backgrounds=[dict(pid=old.pid,output='first'),dict(pid=old.pid,output='second'),dict(pid=new.pid,output='first')])))
    desktop.GLib.fire(controller.handoff);assert old.poll() is None,'Retired wallpaper before all monitors mapped'
    state.write_text(json.dumps(dict(backgrounds=[dict(pid=new.pid,output='first'),dict(pid=new.pid,output='second')])))
    desktop.GLib.fire(controller.handoff);assert old.poll()==0 and not controller.handoff
    # The explicit switch pauses rotation without discarding the selection/image.
    paused=configparser.ConfigParser(interpolation=None);paused.read_dict({s:dict(config.items(s)) for s in config.sections()})
    paused['wallpaper']['slideshow_enabled']='false'
    controller.apply(paused);assert controller.timer==0 and controller.current==b
    assert controller.next() is False and controller.current==b
    assert not json.loads((root/'wallpaper.json').read_text())['enabled']
    controller.apply(config);assert controller.timer and controller.current==b
    # A failed replacement must retain the last mapped wallpaper.
    controller.next();failed=desktop.children['wallpaper'];failed.code=1
    desktop.GLib.fire(controller.handoff)
    assert desktop.children['wallpaper'] is new and controller.current==b
    assert controller.error
    # Locks/sleep pause slideshow movement, while missing files degrade to color.
    state.write_text('{"locked":true}')
    a.unlink();b.unlink();calls=len(desktop.calls);controller.next();assert len(desktop.calls)==calls
    state.write_text('{}');controller.next();assert controller.current is None and controller.error
    assert '-i' not in desktop.calls[-1]
    # Rapid settings changes cancel a pending handoff and preserve the valid old process.
    plain=configparser.ConfigParser(interpolation=None);plain.read_dict(defaults);plain['wallpaper']['color']='#112233'
    controller.apply(plain);assert controller.timer==0 and '-i' not in desktop.calls[-1]
    controller.close();assert not desktop.GLib.active
print('PASS: folder/files, invalid images, order/deduplication, interval validation, retained background until all outputs map, failed handoff, pause/fallback and cleanup.')
