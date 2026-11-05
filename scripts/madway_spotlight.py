"""Application search with a non-editable, translucent inline completion."""
import json
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
gi.require_version('PangoCairo','1.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Pango,PangoCairo,GtkLayerShell as Layer


class Spotlight:
    def __init__(self,api,layer_window,send):
        self.api=api;self.send=send;self.config=api['settings']();self.closed=False;self.preedit='';self.completion=''
        self.apps=sorted((app for app in Gio.AppInfo.get_all() if app.get_id() and app.should_show()),key=lambda app:app.get_display_name().casefold())
        display=Gdk.Display.get_default();monitor=display.get_monitor(0)
        try:
            state=json.loads((api['runtime_directory']()/'desktop.json').read_text())
            monitor=display.get_monitor_at_point(state.get('output_x',0),state.get('output_y',0)) or monitor
        except (OSError,ValueError):pass
        bounds=monitor.get_geometry()
        self.window=layer_window('madway-launcher',monitor,Layer.Layer.OVERLAY,Layer.KeyboardMode.EXCLUSIVE)
        Layer.set_exclusive_zone(self.window,-1);self.window.set_resizable(False)
        self.window.get_style_context().add_class('spotlight-window')
        self.window.set_size_request(min(max(240,self.config.getint('launcher','width')),max(160,bounds.width-40)),-1)
        self.provider=Gtk.CssProvider();self.provider.load_from_data(api['overlay_style']('wofi.css',self.config).encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0);outer.set_name('outer-box')
        outer.set_margin_start(10);outer.set_margin_end(10);outer.set_margin_top(10);outer.set_margin_bottom(10);self.window.add(outer)
        self.entry=Gtk.Entry();self.entry.set_name('input');self.entry.set_placeholder_text('Search applications…')
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY,'edit-find-symbolic')
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,'edit-clear-symbolic')
        self.entry.connect('icon-press',lambda entry,position,event:entry.set_text('') if position==Gtk.EntryIconPosition.SECONDARY else None)
        self.entry.set_tooltip_text('Tab or Right accepts the faint completion; Enter opens the selected application.')
        self.entry.connect('changed',lambda widget:self.filter())
        self.entry.connect('key-press-event',self.key)
        self.entry.connect('notify::cursor-position',lambda *args:self.entry.queue_draw())
        self.entry.connect('notify::selection-bound',lambda *args:self.entry.queue_draw())
        self.entry.connect('preedit-changed',self.preedit_changed)
        self.entry.connect_after('draw',self.draw_completion)
        outer.pack_start(self.entry,False,False,0)
        self.scroll=Gtk.ScrolledWindow();self.scroll.set_name('scroll')
        self.scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_propagate_natural_height(True)
        row_height=max(44,self.config.getint('launcher','icon_size')+14 if self.config.getboolean('launcher','icons') else 44)
        self.lines=min(max(1,self.config.getint('launcher','lines')),max(1,int((bounds.height-150)//row_height)))
        self.scroll.set_max_content_height(self.lines*row_height)
        self.list=Gtk.ListBox();self.list.set_name('inner-box');self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.set_activate_on_single_click(True);self.list.connect('row-activated',lambda widget,row:self.launch(row))
        self.list.connect('row-selected',lambda *args:self.complete())
        self.scroll.add(self.list);outer.pack_start(self.scroll,True,True,0)
        self.window.connect('key-press-event',self.key);self.window.connect('destroy',self.finish)
        self.filter();self.window.show_all();self.entry.grab_focus()

    def filter(self):
        query=self.entry.get_text().strip().casefold();words=query.split()
        matches=[]
        for app in self.apps:
            name=app.get_display_name();keywords=app.get_keywords() if isinstance(app,Gio.DesktopAppInfo) else []
            text=' '.join([name,app.get_id(),app.get_executable() or '',app.get_description() or '',*(keywords or [])]).casefold()
            if all(word in text for word in words):
                rank=0 if name.casefold().startswith(query) else 1 if query in name.casefold() else 2
                matches.append((rank,name.casefold(),app))
        self.rows=[]
        for child in self.list.get_children():child.destroy()
        for _,_,app in sorted(matches,key=lambda entry:(entry[0],entry[1]))[:100]:
            row=Gtk.ListBoxRow();row.set_name('entry');row.app=app
            line=Gtk.Box(spacing=10)
            if self.config.getboolean('launcher','icons'):
                image=Gtk.Image.new_from_gicon(app.get_icon() or Gio.ThemedIcon.new('application-x-executable'),Gtk.IconSize.DIALOG)
                image.set_pixel_size(min(48,max(16,self.config.getint('launcher','icon_size'))));image.set_name('img')
                line.pack_start(image,False,False,0)
            label=Gtk.Label(label=app.get_display_name(),xalign=0);label.set_name('text');label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_width_chars(1);line.pack_start(label,True,True,0);row.add(line)
            row.set_tooltip_text(app.get_description() or app.get_display_name());self.list.add(row);self.rows.append(row)
        if not self.rows:
            empty=Gtk.Label(label='No matching applications',xalign=0);empty.set_margin_start(10);empty.set_margin_top(8);empty.set_margin_bottom(8)
            self.list.add(empty)
        self.list.show_all()
        if self.rows:self.list.select_row(self.rows[0])
        self.complete();self.window.resize(self.window.get_size()[0],1)

    def complete(self):
        text=self.entry.get_text();row=self.list.get_selected_row();self.completion=''
        if self.config.getboolean('launcher','autocomplete',fallback=True) and text and row and hasattr(row,'app'):
            name=row.app.get_display_name()
            if name[:len(text)].casefold()==text.casefold():self.completion=name[len(text):]
        self.entry.queue_draw()

    def preedit_changed(self,entry,text):
        self.preedit=text;entry.queue_draw()

    def draw_completion(self,entry,cr):
        text=entry.get_text();selection=entry.get_selection_bounds()
        if not self.completion or self.preedit or entry.get_position()!=len(text) or (selection and selection[-2]!=selection[-1]) or entry.get_direction()==Gtk.TextDirection.RTL:return False
        layout=entry.get_layout();position=layout.index_to_pos(len(text.encode('utf-8')))
        x,y=entry.get_layout_offsets();x+=position.x/Pango.SCALE
        ghost=entry.create_pango_layout(self.completion)
        width=max(0,entry.get_allocated_width()-x-32)
        ghost.set_width(int(width*Pango.SCALE));ghost.set_ellipsize(Pango.EllipsizeMode.END)
        color=self.api['palette'](self.config)['muted'];alpha=min(.65,max(.15,self.config.getint('launcher','completion_opacity',fallback=38)/100))
        cr.save();cr.rectangle(x,y,width,entry.get_allocated_height());cr.clip()
        neutral=sum(int(color[index:index+2],16)/255 for index in (1,3,5))/3
        cr.set_source_rgba(neutral,neutral,neutral,alpha)
        cr.move_to(x,y);PangoCairo.show_layout(cr,ghost);cr.restore();return False

    def key(self,window,event):
        key=Gdk.keyval_name(event.keyval)
        if key=='Escape':self.window.destroy();return True
        if key in {'Down','Up'}:
            if self.rows:
                current=self.list.get_selected_row();index=self.rows.index(current) if current in self.rows else 0
                self.list.select_row(self.rows[(index+(1 if key=='Down' else -1))%len(self.rows)])
                GLib.idle_add(self.reveal)
            return True
        if key in {'Tab','Right'} and self.completion and self.entry.get_position()==len(self.entry.get_text()) and not self.preedit:
            self.entry.set_text(self.entry.get_text()+self.completion);self.entry.set_position(-1);return True
        if key in {'Return','KP_Enter'}:self.launch(self.list.get_selected_row());return True
        return False

    def reveal(self):
        row=self.list.get_selected_row()
        if row and not self.closed:
            adjustment=self.scroll.get_vadjustment();point=row.translate_coordinates(self.list,0,0)
            if point:
                top=point[1];bottom=top+row.get_allocated_height();value=adjustment.get_value()
                if top<value:value=top
                elif bottom>value+adjustment.get_page_size():value=bottom-adjustment.get_page_size()
                adjustment.set_value(max(0,min(value,adjustment.get_upper()-adjustment.get_page_size())))
        return False

    def launch(self,row):
        if row and hasattr(row,'app'):
            self.send('launch-app',id=row.app.get_id());self.window.destroy()

    def finish(self,*args):
        self.closed=True;Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),self.provider);Gtk.main_quit()
