"""Window preview popups and centered, palette-aware session confirmations."""
import json
import math
import cairo
from pathlib import Path
import time
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gtk,Gdk,GdkPixbuf,GLib,GtkLayerShell as Layer


def task_click(button,enabled=True):
    """A frame-clock icon press/rebound, with no change to task-button geometry."""
    image=button.get_image()
    if not enabled or not image:return
    previous=getattr(button,'click_tick',0)
    if previous:button.remove_tick_callback(previous)
    size=getattr(button,'click_size',image.get_pixel_size());button.click_size=size
    origin=image.get_pixel_size();opacity=image.get_opacity();image.set_size_request(size,size)
    start=GLib.get_monotonic_time()
    def frame(widget,clock):
        progress=min(1,max(0,(clock.get_frame_time()-start)/180000))
        pulse=math.sin(math.pi*progress)
        image.set_pixel_size(max(size-3,round(origin+(size-origin)*progress-3*pulse)))
        image.set_opacity(opacity+(1-opacity)*progress-.15*pulse)
        if progress>=1:button.click_tick=0;return False
        return True
    button.click_tick=button.add_tick_callback(frame)


class TaskPreview:
    """A noninteractive layer popup, independent of global GTK tooltip settings."""
    def __init__(self,widget,identity,directory,send,bar=None):
        self.widget=widget;self.identity=identity;self.directory=directory;self.send=send;self.bar=bar
        self.window=None;self.delay=0;self.timer=0;self.last=0;self.signature=None
        widget.set_has_tooltip(False)
        widget.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
        widget.connect('enter-notify-event',self.enter);widget.connect('leave-notify-event',self.leave)
        widget.connect('button-press-event',self.leave);widget.connect('unmap',self.leave);widget.connect('destroy',self.leave)

    def row(self):
        try:
            state=json.loads((self.directory()/'desktop.json').read_text())
            if state.get('locked') or state.get('sleeping'):return None
            rows=state.get('all_windows',state.get('windows',[]))
            row=next((row for row in rows if row['id']==self.identity and row.get('visible_workspace',True)),None)
            if row and any(other.get('fullscreen') and not other.get('minimized') and other.get('visible_workspace',True) and other.get('output')==row.get('output') for other in rows):return None
            return row
        except (OSError,ValueError):return None

    def prefetch(self,*args):
        if self.row() and time.monotonic()-self.last>.5:
            self.last=time.monotonic();self.send('window-preview',id=self.identity)
        return False

    def enter(self,widget,event):
        if event.detail==Gdk.NotifyType.INFERIOR:return False
        self.prefetch()
        if not self.delay and not self.window:self.delay=GLib.timeout_add(280,self.show)
        return False

    def leave(self,*args):
        if len(args)>1 and isinstance(args[1],Gdk.EventCrossing) and args[1].detail==Gdk.NotifyType.INFERIOR:return False
        if self.delay:GLib.source_remove(self.delay);self.delay=0
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if self.window:self.window.destroy();self.window=None
        return False

    def show(self):
        self.delay=0
        if not self.widget.get_mapped() or not self.row():return False
        parent=self.widget.get_toplevel();display=parent.get_display()
        monitor=self.bar['monitor'] if self.bar else display.get_monitor_at_window(parent.get_window())
        bounds=monitor.get_geometry();width=min(254,max(80,bounds.width-12));height=min(178,max(60,bounds.height-12))
        self.window=Gtk.Window();self.window.set_decorated(False);self.window.set_resizable(False)
        self.window.get_style_context().add_class('task-preview-window')
        Layer.init_for_window(self.window);Layer.set_namespace(self.window,'madway-task-preview')
        Layer.set_monitor(self.window,monitor);Layer.set_layer(self.window,Layer.Layer.OVERLAY)
        Layer.set_keyboard_mode(self.window,Layer.KeyboardMode.NONE);Layer.set_exclusive_zone(self.window,-1)
        for edge in (Layer.Edge.TOP,Layer.Edge.LEFT):Layer.set_anchor(self.window,edge,True)
        x,y=self.widget.translate_coordinates(parent,0,0) or (0,0)
        position=self.bar['position'] if self.bar else 'top'
        if position=='bottom':y=bounds.height-parent.get_allocated_height()-height-4
        elif position=='right':x=bounds.width-parent.get_allocated_width()-width-4
        elif position=='left':x=parent.get_allocated_width()+4
        else:y=parent.get_allocated_height()+4
        if position in ('top','bottom'):x+=self.widget.get_allocated_width()/2-width/2
        else:y+=self.widget.get_allocated_height()/2-height/2
        Layer.set_margin(self.window,Layer.Edge.LEFT,int(max(6,min(bounds.width-width-6,x))))
        Layer.set_margin(self.window,Layer.Edge.TOP,int(max(6,min(bounds.height-height-6,y))))
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5,margin=6)
        box.get_style_context().add_class('task-preview');self.window.add(box)
        self.image=Gtk.Image();self.image.set_size_request(width-14,height-35);box.pack_start(self.image,True,True,0)
        self.title=Gtk.Label(max_width_chars=32);self.title.set_ellipsize(3);box.pack_start(self.title,False,False,0)
        self.window.connect('realize',lambda w:w.get_window().input_shape_combine_region(cairo.Region(),0,0))
        self.signature=None
        if not self.refresh() or self.window is None:return False
        self.window.show_all();self.timer=GLib.timeout_add(100,self.refresh)
        return False

    def refresh(self):
        row=self.row()
        if not row or not self.widget.get_mapped():self.leave();return False
        self.prefetch();scale=self.widget.get_scale_factor()
        signature=(row.get('preview',0),row.get('title'),row.get('minimized'))
        if signature!=self.signature:
            self.signature=signature
            try:
                if not row.get('preview'):raise ValueError('No snapshot')
                width,height=self.image.get_size_request()
                pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(self.directory()/'previews'/f'{self.identity}.png'),width*scale,height*scale,True)
                self.image.set_from_surface(Gdk.cairo_surface_create_from_pixbuf(pixbuf,scale,None))
            except (GLib.Error,OSError,ValueError):self.image.set_from_icon_name('application-x-executable',Gtk.IconSize.DIALOG)
            self.title.set_text(('Restore · ' if row.get('minimized') else '')+(row.get('title') or 'Untitled'))
        return True


class SessionConfirmation:
    def __init__(self,operation,api,parent=None):
        labels={'poweroff':('Shut down','system-shutdown-symbolic','All applications on this computer will close.'),
                'reboot':('Restart','system-reboot-symbolic','This computer will restart and close all applications.'),
                'logout':('Log out','system-log-out-symbolic','Your madway session and its applications will close.')}
        if operation not in labels:raise ValueError('Unknown session operation')
        self.operation=operation;self.accepted=False;self.loop=GLib.MainLoop();self.api=api
        display=Gdk.Display.get_default()
        try:state=json.loads((api['runtime_directory']()/'desktop.json').read_text())
        except (OSError,ValueError):state={}
        monitor=display.get_monitor_at_point(state.get('output_x',0),state.get('output_y',0)) or display.get_monitor(0)
        self.window=Gtk.Window(title='madway — Session');self.window.set_decorated(False);self.window.set_resizable(False)
        Layer.init_for_window(self.window);Layer.set_namespace(self.window,'madway-session-dialog')
        Layer.set_monitor(self.window,monitor);Layer.set_layer(self.window,Layer.Layer.OVERLAY)
        Layer.set_keyboard_mode(self.window,Layer.KeyboardMode.EXCLUSIVE);Layer.set_exclusive_zone(self.window,-1)
        self.window.get_style_context().add_class('session-dialog')
        visual=self.window.get_screen().get_rgba_visual()
        if visual:self.window.set_visual(visual)
        label,icon,description=labels[operation]
        card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin=12);card.get_style_context().add_class('session-card');self.window.add(card)
        header=Gtk.Box(spacing=10);image=Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.DIALOG);image.set_pixel_size(28);header.pack_start(image,False,False,0)
        title=Gtk.Label(label=label+'?',xalign=0);title.get_style_context().add_class('session-title');header.pack_start(title,True,True,0);card.add(header)
        message=Gtk.Label(label=description+' Save your work before continuing.',xalign=0,wrap=True,max_width_chars=40);message.set_size_request(min(340,max(140,monitor.get_geometry().width-80)),-1);card.add(message)
        buttons=Gtk.Box(spacing=8);card.add(buttons)
        self.cancel=Gtk.Button(label='Cancel');self.cancel.connect('clicked',lambda w:self.finish(False));buttons.pack_start(self.cancel,True,True,0)
        self.accept=Gtk.Button(label=label);self.accept.get_style_context().add_class('session-accept');self.accept.connect('clicked',lambda w:self.finish(True));buttons.pack_start(self.accept,True,True,0)
        self.window.connect('key-press-event',self.key);self.window.connect('delete-event',lambda *a:self.finish(False))
        self.window.connect('destroy',lambda *a:self.loop.quit())
        self.provider=Gtk.CssProvider();self.provider.load_from_data(api['overlay_style']('utilities.css').encode())
        Gtk.StyleContext.add_provider_for_screen(self.window.get_screen(),self.provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+5)
        self.window.show_all();self.cancel.grab_focus()
        self.poll=GLib.timeout_add(100,self.privacy)
    def key(self,window,event):
        if Gdk.keyval_name(event.keyval)=='Escape':self.finish(False);return True
        return False
    def privacy(self):
        try:state=json.loads((self.api['runtime_directory']()/'desktop.json').read_text())
        except (OSError,ValueError):return True
        if state.get('locked') or state.get('sleeping'):self.poll=0;self.finish(False);return False
        return True
    def finish(self,accept):
        self.accepted=accept;self.window.destroy();return True
    def run(self):
        try:self.loop.run();return self.accepted
        finally:
            if self.poll:GLib.source_remove(self.poll);self.poll=0
            Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),self.provider)
