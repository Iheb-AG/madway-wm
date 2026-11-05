"""Frame-clock session overlays, with bounded snapshots and a software fade fallback."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import threading
import time
import cairo
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gtk,Gdk,GdkPixbuf,GLib,GtkLayerShell as Layer


def ease(progress):
    if progress<=0:return 0.
    if progress>=1:return 1.
    low=0.;high=1.
    for _ in range(18):
        t=(low+high)*.5;u=1-t
        if 3*u*u*t*.32+3*u*t*t*.18+t*t*t<progress:low=t
        else:high=t
    t=(low+high)*.5;return t*t*(3-2*t)


class ExitPane:
    def __init__(self,owner,monitor,snapshot):
        self.owner=owner;self.renderer=None;self.ready=False;self.fallback=False;self.snapshot=snapshot;self.tick=0
        self.window=Gtk.Window();self.window.set_decorated(False);self.window.get_style_context().add_class('exit-overlay')
        visual=self.window.get_screen().get_rgba_visual()
        if visual:self.window.set_visual(visual)
        Layer.init_for_window(self.window);Layer.set_namespace(self.window,'madway-session-exit')
        Layer.set_monitor(self.window,monitor);Layer.set_layer(self.window,Layer.Layer.OVERLAY);Layer.set_exclusive_zone(self.window,-1)
        Layer.set_keyboard_mode(self.window,Layer.KeyboardMode.EXCLUSIVE)
        for edge in (Layer.Edge.TOP,Layer.Edge.BOTTOM,Layer.Edge.LEFT,Layer.Edge.RIGHT):Layer.set_anchor(self.window,edge,True)
        self.overlay=Gtk.Overlay();self.window.add(self.overlay)
        self.label=Gtk.Label(label=('Preview · ' if owner.args.preview else '')+('Welcome' if owner.args.opening else {'logout':'Logging out…','reboot':'Restarting…','poweroff':'Shutting down…'}[owner.args.operation]))
        self.label.set_halign(Gtk.Align.CENTER);self.label.set_valign(Gtk.Align.CENTER);self.label.set_opacity(0)
        self.window.connect('key-press-event',self.key)
        self.window.connect('destroy',self.destroy)
        if owner.args.mode=='shader' and snapshot:
            self.canvas=Gtk.GLArea();self.canvas.set_use_es(True);self.canvas.set_required_version(2,0)
            self.canvas.set_has_alpha(False);self.canvas.set_auto_render(False)
            self.canvas.connect('realize',self.realize);self.canvas.connect('render',self.render);self.canvas.connect('unrealize',self.unrealize)
        else:self.canvas=self.drawing_area();self.fallback=True;self.ready=True
        self.overlay.add(self.canvas);self.overlay.add_overlay(self.label)
        self.window.show_all();self.tick=self.window.add_tick_callback(self.frame)

    def drawing_area(self):
        canvas=Gtk.DrawingArea();canvas.connect('draw',self.draw);return canvas

    def key(self,window,event):
        if Gdk.keyval_name(event.keyval)=='Escape':self.owner.stop(0 if self.owner.args.preview else 77);return True
        return True

    def realize(self,area):
        area.make_current()
        if area.get_error():GLib.idle_add(self.use_fallback,str(area.get_error()))

    def use_fallback(self,error):
        if self.owner.closed or self.fallback:return False
        print('madway: session shader unavailable; using fade: '+str(error),file=sys.stderr)
        self.fallback=True;self.ready=True
        old=self.canvas;self.overlay.remove(old);old.destroy();self.canvas=self.drawing_area();self.overlay.add(self.canvas);self.canvas.show()
        self.owner.maybe_start();return False

    def render(self,area,context):
        if self.owner.closed:return True
        try:
            if not self.renderer:
                source=runpy.run_path(str(Path(__file__).with_name('madway_gl.py')))
                self.renderer=source['ShaderRenderer']((self.owner.share/'shaders/session.vert').read_text(),
                    (self.owner.share/'shaders'/(self.owner.args.shader+'.frag')).read_text(),self.snapshot)
                self.ready=True
                print('madway: session shader ready: '+self.owner.args.shader,flush=True)
                self.owner.maybe_start()
            scale=area.get_scale_factor()
            self.renderer.draw(self.owner.progress,area.get_allocated_width()*scale,area.get_allocated_height()*scale)
        except Exception as error:GLib.idle_add(self.use_fallback,str(error))
        return True

    def unrealize(self,area):
        if self.renderer:
            area.make_current()
            if not area.get_error():self.renderer.close()
            self.renderer=None

    def draw(self,widget,cr):
        p=self.owner.progress
        cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint();cr.set_operator(cairo.OPERATOR_OVER)
        if self.snapshot:
            cr.save();cr.scale(widget.get_allocated_width()/self.snapshot.get_width(),widget.get_allocated_height()/self.snapshot.get_height())
            Gdk.cairo_set_source_pixbuf(cr,self.snapshot,0,0);cr.paint();cr.restore()
        cr.set_source_rgba(.018,.024,.033,p);cr.paint();return False

    def frame(self,widget,clock):
        if self.owner.closed:return False
        self.owner.advance(clock.get_frame_time()/1e6)
        self.label.set_opacity(ease((self.owner.progress-.55)/.45))
        if isinstance(self.canvas,Gtk.GLArea):self.canvas.queue_render()
        else:self.canvas.queue_draw()
        return True

    def destroy(self,*args):
        if self.tick:self.window.remove_tick_callback(self.tick);self.tick=0
        self.snapshot=None


class ExitOverlay:
    def __init__(self,args,api):
        self.args=args;self.api=api;self.share=api['SHARE'];self.directory=api['runtime_directory']()
        self.closed=False;self.code=0;self.panes=[];self.progress=1. if args.opening else 0.;self.started=None;self.sent=False
        self.duration=min(1600,max(160,args.duration))/1000
        self.display=Gdk.Display.get_default();self.display.connect('monitor-removed',lambda *a:self.stop(0 if args.preview else 77))
        self.display.connect('monitor-added',lambda *a:self.stop(0 if args.preview else 77))
        self.provider=Gtk.CssProvider();self.provider.load_from_data(b'window.exit-overlay { background: transparent; } .exit-overlay label { color: #ededed; background: transparent; font-family: sans-serif; font-size: 14px; font-weight: 500; text-shadow: 0 1px 4px black; }')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+10)
        self.poll=GLib.timeout_add(100,self.privacy)
        GLib.timeout_add(10000,lambda:self.stop())
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,self.stop)
        if self.privacy() is False:return
        try:outputs=json.loads((self.directory/'outputs.json').read_text()).get('outputs',[])
        except (OSError,ValueError):outputs=[]
        monitors=[self.display.get_monitor(i) for i in range(self.display.get_n_monitors())]
        if not monitors:self.stop(0 if args.preview else 77);return
        self.targets=[]
        for monitor in monitors:
            box=monitor.get_geometry();output=next((row for row in outputs if row.get('enabled') and row.get('x')==box.x and row.get('y')==box.y),None)
            self.targets.append((monitor,output,min(1.,1600/max(1,box.width,box.height))))
        if args.mode=='shader':threading.Thread(target=self.capture,daemon=True).start()
        else:self.build([None]*len(monitors))

    def capture(self):
        # One bounded snapshot per output, only in memory. All are captured before
        # any overlay maps, so a shader never samples another exit overlay.
        def grab(target):
            monitor,output,scale=target
            if not output:return None
            try:
                result=subprocess.run(['grim','-o',output['name'],'-s',str(scale),'-'],capture_output=True,timeout=1.5)
                return result.stdout if result.returncode==0 and len(result.stdout)<16*1024*1024 else None
            except (OSError,subprocess.TimeoutExpired):return None
        with ThreadPoolExecutor(max_workers=min(4,len(self.targets))) as pool:images=list(pool.map(grab,self.targets))
        GLib.idle_add(self.build,images)

    def build(self,images):
        if self.closed:return False
        budget=64*1024*1024
        for (monitor,output,scale),data in zip(self.targets,images):
            image=None
            if data:
                try:
                    loader=GdkPixbuf.PixbufLoader.new_with_type('png');loader.write(data);loader.close();image=loader.get_pixbuf()
                    size=image.get_width()*image.get_height()*4
                    if size>budget:image=None
                    else:budget-=size
                except GLib.Error:image=None
            self.panes.append(ExitPane(self,monitor,image))
        self.maybe_start();return False

    def maybe_start(self):
        if self.started is None and self.panes and len(self.panes)==len(self.targets) and all(pane.ready for pane in self.panes):
            # GTK's frame clock shares the monotonic clock; each output samples the
            # same start time while painting at its own refresh rate.
            self.started=GLib.get_monotonic_time()/1e6
            print('madway: session '+('opening' if self.args.opening else 'closing')+' started at %.6f'%self.started,flush=True)
            if not self.args.preview:
                try:self.api['action']('session-opening-started' if self.args.opening else 'session-effect-started',token=self.args.token)
                except OSError:self.stop()

    def advance(self,now):
        if self.started is None:return
        elapsed=max(0,now-self.started)
        self.progress=1-ease(elapsed/self.duration) if self.args.opening else ease(elapsed/self.duration)
        if elapsed<self.duration:return
        if self.args.opening:self.stop();return
        if self.args.preview:
            if elapsed>self.duration+.15:self.progress=1-ease((elapsed-self.duration-.15)/.3)
            if elapsed>self.duration+.45:self.stop()
        elif not self.sent and elapsed>=self.duration+.05:
            self.sent=True
            try:self.api['action']('session-exit-ready',token=self.args.token)
            except OSError:self.stop()
            # The parent may be gone or logind may reject/ignore the request. An
            # orphaned effect never covers a usable desktop indefinitely.
            GLib.timeout_add_seconds(7,self.stop)

    def privacy(self):
        if self.closed:return False
        try:state=json.loads((self.directory/'desktop.json').read_text())
        except (OSError,ValueError):state={}
        if state.get('locked') or state.get('sleeping'):
            self.poll=0;self.stop(0 if self.args.preview else 77);return False
        return True

    def stop(self,code=0):
        if self.closed:return False
        self.closed=True;self.code=code
        for pane in self.panes:pane.window.destroy()
        if Gtk.main_level():Gtk.main_quit()
        return False


def run(args):
    api=runpy.run_path(str(Path(__file__).with_name('madway-shell')))
    overlay=ExitOverlay(args,api)
    if not overlay.closed:Gtk.main()
    if overlay.poll:GLib.source_remove(overlay.poll)
    Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),overlay.provider)
    return overlay.code
