"""Window preview tooltips and centered, palette-aware session confirmations."""
import json
from pathlib import Path
import time
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gtk,Gdk,GdkPixbuf,GLib,GtkLayerShell as Layer


class TaskPreview:
    def __init__(self,widget,identity,directory,send):
        self.widget=widget;self.identity=identity;self.directory=directory;self.send=send;self.last=0
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,margin=7)
        self.box.get_style_context().add_class('task-preview')
        self.image=Gtk.Image();self.image.set_size_request(240,135);self.box.add(self.image)
        self.title=Gtk.Label(max_width_chars=34);self.title.set_ellipsize(3);self.box.add(self.title)
        widget.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        widget.connect('enter-notify-event',self.prefetch);widget.connect('query-tooltip',self.query)
        widget.connect('destroy',lambda *a:self.box.destroy())
        widget.set_has_tooltip(True)
    def row(self):
        try:
            state=json.loads((self.directory()/'desktop.json').read_text())
            if state.get('locked') or state.get('sleeping'):return None
            return next((row for row in state.get('all_windows',state.get('windows',[])) if row['id']==self.identity and row.get('visible_workspace',True)),None)
        except (OSError,ValueError):return None
    def prefetch(self,*args):
        if self.row() and time.monotonic()-self.last>.4:
            self.last=time.monotonic();self.send('window-preview',id=self.identity)
        return False
    def query(self,widget,x,y,keyboard,tooltip):
        row=self.row()
        if not row:return False
        if keyboard:self.prefetch()
        scale=widget.get_scale_factor()
        try:
            if not row.get('preview'):raise ValueError('No snapshot')
            pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(self.directory()/'previews'/f'{self.identity}.png'),240*scale,135*scale,True)
            self.image.set_from_surface(Gdk.cairo_surface_create_from_pixbuf(pixbuf,scale,None))
        except (GLib.Error,OSError,ValueError):
            self.image.set_from_icon_name('application-x-executable',Gtk.IconSize.DIALOG)
        self.title.set_text(('Restore · ' if row.get('minimized') else '')+(row.get('title') or 'Untitled'))
        # GTK owns the tooltip, so place the custom widget in it only on demand.
        tooltip.set_custom(self.box);self.box.show_all();return True


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
