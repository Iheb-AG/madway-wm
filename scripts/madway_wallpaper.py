"""Wallpaper/slideshow scheduling with a mapped-background handoff."""
import json
from pathlib import Path
import re
import time
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf,GLib


def selected_images(value):
    try:items=json.loads(value)
    except (ValueError,TypeError) as error:raise ValueError('Selected images must be a JSON list') from error
    if not isinstance(items,list) or any(not isinstance(item,str) for item in items):
        raise ValueError('Select image files for the slideshow')
    return items


def slideshow_images(config):
    source=config.get('wallpaper','source')
    if source=='folder':
        folder=Path(config.get('wallpaper','folder')).expanduser()
        if not config.get('wallpaper','folder').strip() or not folder.is_dir():return []
        try:items=sorted(folder.iterdir(),key=lambda item:item.name.casefold())
        except OSError:return []
    elif source=='files':items=[Path(item).expanduser() for item in selected_images(config.get('wallpaper','images'))]
    else:raise ValueError('Choose folder or selected files for the slideshow')
    result=[];seen=set()
    for item in items:
        try:
            path=item.resolve()
            if path in seen or not path.is_file():continue
            info=GdkPixbuf.Pixbuf.get_file_info(str(path))
            if not info or info[0] is None:continue
            seen.add(path);result.append(path)
        except (OSError,ValueError,GLib.Error):continue
    return result


def validate(config):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',config.get('wallpaper','color')):raise ValueError('Wallpaper color must be #RRGGBB')
    if config.get('wallpaper','mode') not in {'fill','fit','center','stretch','tile'}:raise ValueError('Unknown wallpaper mode')
    kind=config.get('wallpaper','type')
    if kind not in {'auto','color','image','slideshow'}:raise ValueError('Unknown background type')
    if (kind=='image' or (kind=='auto' and config.get('wallpaper','path').strip())) and not Path(config.get('wallpaper','path')).expanduser().is_file():raise ValueError('Wallpaper image does not exist')
    if kind=='slideshow' and config.getboolean('wallpaper','slideshow_enabled',fallback=True):
        if not 1<=config.getint('wallpaper','interval')<=86400:raise ValueError('Slideshow interval must be 1–86400 seconds')
        if not slideshow_images(config):raise ValueError('Choose a folder or selection containing readable images')


class WallpaperController:
    def __init__(self,desktop):
        self.desktop=desktop;self.GLib=desktop.GLib
        self.timer=0;self.handoff=0;self.signature=None;self.arguments=None
        self.current=None;self.files=[];self.error=''
        self.previous=None;self.previous_arguments=None

    def state(self):
        try:return json.loads((self.desktop.directory/'desktop.json').read_text())
        except (OSError,ValueError):return {}

    def publish(self):
        path=self.desktop.directory/'wallpaper.json';temporary=path.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(dict(path=str(self.current or ''),count=len(self.files),error=self.error,
                interval=self.config.getint('wallpaper','interval'),type=self.config.get('wallpaper','type'),
                enabled=self.config.getboolean('wallpaper','slideshow_enabled',fallback=True))))
            temporary.chmod(0o600);temporary.replace(path)
        except OSError:temporary.unlink(missing_ok=True)

    def cancel_handoff(self,restore=False):
        if self.handoff:self.GLib.source_remove(self.handoff);self.handoff=0
        old=self.desktop.children.get('wallpaper-old')
        if restore and old and old.poll() is None:
            self.desktop.terminate('wallpaper')
            self.desktop.children['wallpaper']=self.desktop.children.pop('wallpaper-old')
            self.current=self.previous;self.arguments=self.previous_arguments
        else:self.desktop.terminate('wallpaper-old')

    def show(self,path):
        arguments=['swaybg','-c',self.config.get('wallpaper','color')[1:]]
        if path:arguments+=['-i',str(path),'-m',self.config.get('wallpaper','mode')]
        process=self.desktop.children.get('wallpaper')
        if arguments==self.arguments and process and process.poll() is None:
            self.current=path;self.publish();return
        self.cancel_handoff(restore=True)
        self.previous=self.current;self.previous_arguments=self.arguments
        old=self.desktop.children.pop('wallpaper',None)
        new=self.desktop.spawn('wallpaper',arguments)
        if not new:
            if old:self.desktop.children['wallpaper']=old
            self.error='swaybg is unavailable';self.publish();return
        self.arguments=arguments;self.current=path
        if old and old.poll() is None:
            self.desktop.children['wallpaper-old']=old
            deadline=time.monotonic()+5
            def ready():
                if new.poll() is not None:
                    self.desktop.children['wallpaper']=self.desktop.children.pop('wallpaper-old',old)
                    self.current=self.previous;self.arguments=self.previous_arguments;self.error='New wallpaper could not be displayed';self.handoff=0;self.publish();return False
                state=self.state();outputs={item['output'] for item in state.get('backgrounds',[])}
                mapped={item['output'] for item in state.get('backgrounds',[]) if item['pid']==new.pid}
                if outputs and outputs<=mapped:
                    self.desktop.terminate('wallpaper-old');self.handoff=0;return False
                if time.monotonic()>=deadline:
                    self.desktop.terminate('wallpaper')
                    self.desktop.children['wallpaper']=self.desktop.children.pop('wallpaper-old',old)
                    self.current=self.previous;self.arguments=self.previous_arguments;self.error='Wallpaper readiness timed out; previous background retained'
                    self.handoff=0;self.publish();return False
                return True
            self.handoff=self.GLib.timeout_add(50,ready)
        self.publish()

    def apply(self,config):
        validate(config)
        signature=tuple(config.items('wallpaper'))
        current=self.desktop.children.get('wallpaper')
        if signature==self.signature and current and current.poll() is None:return
        if self.timer:self.GLib.source_remove(self.timer);self.timer=0
        self.signature=signature;self.config=config;self.error=''
        kind=config.get('wallpaper','type');self.files=slideshow_images(config) if kind=='slideshow' else []
        path=config.get('wallpaper','path').strip()
        image=self.current if self.current in self.files else self.files[0] if self.files else Path(path).expanduser() if path and kind!='color' else None
        self.show(image)
        if kind=='slideshow' and config.getboolean('wallpaper','slideshow_enabled',fallback=True):
            self.timer=self.GLib.timeout_add_seconds(config.getint('wallpaper','interval'),self.next)

    def next(self):
        if self.config.get('wallpaper','type')!='slideshow' or not self.config.getboolean('wallpaper','slideshow_enabled',fallback=True):return False
        if self.state().get('locked') or self.state().get('sleeping') or self.handoff:return True
        self.files=slideshow_images(self.config)
        if not self.files:
            self.error='No readable slideshow images; using the solid background color';self.show(None);return True
        self.error=''
        index=self.files.index(self.current)+1 if self.current in self.files else 0
        self.show(self.files[index%len(self.files)])
        return True

    def close(self):
        if self.timer:self.GLib.source_remove(self.timer);self.timer=0
        self.cancel_handoff()
        (self.desktop.directory/'wallpaper.json').unlink(missing_ok=True)
