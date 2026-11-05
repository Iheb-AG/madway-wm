"""GTK editors for display geometry and ordered dock launchers."""
import re
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,Gio


class DisplayLayout(Gtk.DrawingArea):
    def __init__(self,rows,palette):
        super().__init__();self.rows=rows;self.palette=palette;self.boxes=[];self.drag=None;self.selected=None
        self.set_size_request(240,180);self.set_hexpand(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('draw',self.draw);self.connect('button-press-event',self.press)
        self.connect('motion-notify-event',self.motion);self.connect('button-release-event',self.release)
        self.set_tooltip_text('Drag monitors to arrange them. Edges snap together. Changes apply only when you press Apply.')

    @staticmethod
    def geometry(row):
        match=re.fullmatch(r'(\d+)x(\d+)@\d+',row['mode'].get_active_id() or '')
        w,h=map(int,match.groups()) if match else row.get('pixels',(1920,1080))
        if int(row['transform'].get_active_id() or 0)%2:w,h=h,w
        scale=max(.5,row['scale'].get_value())
        return row['x'].get_value(),row['y'].get_value(),w/scale,h/scale

    def layout(self):
        if not self.rows:self.boxes=[];return
        rects=[self.geometry(row) for row in self.rows]
        left=min(r[0] for r in rects);top=min(r[1] for r in rects)
        width=max(r[0]+r[2] for r in rects)-left;height=max(r[1]+r[3] for r in rects)-top
        self.factor=max(.001,min((self.get_allocated_width()-32)/max(1,width),(self.get_allocated_height()-32)/max(1,height)))
        self.offset=((self.get_allocated_width()-width*self.factor)/2-left*self.factor,
                     (self.get_allocated_height()-height*self.factor)/2-top*self.factor)
        self.boxes=[(row,(self.offset[0]+x*self.factor,self.offset[1]+y*self.factor,w*self.factor,h*self.factor)) for row,(x,y,w,h) in zip(self.rows,rects)]

    def draw(self,widget,cr):
        palette=self.palette()
        def color(key,alpha=1):
            value=palette[key];cr.set_source_rgba(*[int(value[i:i+2],16)/255 for i in (1,3,5)],alpha)
        color('surface');cr.paint()
        if not self.drag:self.layout()
        cr.select_font_face('sans-serif');cr.set_font_size(11)
        for index,(row,(x,y,w,h)) in enumerate(self.boxes):
            enabled=row['enabled'].get_active();color('accent' if row is self.selected else 'border',.25 if enabled else .1)
            cr.rectangle(x+2,y+2,max(1,w-4),max(1,h-4));cr.fill_preserve()
            color('accent' if row is self.selected else 'border');cr.set_line_width(2 if row is self.selected else 1);cr.stroke()
            cr.save();cr.rectangle(x+5,y+5,max(1,w-10),max(1,h-10));cr.clip()
            color('text' if enabled else 'muted')
            captions=[(0,str(index+1)+(' ×' if not enabled else ''))] if w<90 or h<60 else [(0,f'{index+1} · {row["name"]}'),(16,f'{round(self.geometry(row)[2])} × {round(self.geometry(row)[3])}' if enabled else 'Disabled')]
            for offset,text in captions:
                cr.move_to(x+10,y+h/2-3+offset);cr.show_text(text)
            cr.restore()
        return False

    def press(self,widget,event):
        if event.button!=1:return False
        self.layout()
        for row,(x,y,w,h) in reversed(self.boxes):
            if x<=event.x<x+w and y<=event.y<y+h:
                self.selected=row;self.drag=(row,event.x,event.y,row['x'].get_value(),row['y'].get_value(),self.factor)
                self.queue_draw();return True
        return False

    def motion(self,widget,event):
        if not self.drag:return False
        row,px,py,ox,oy,factor=self.drag
        x=ox+(event.x-px)/factor;y=oy+(event.y-py)/factor;_,_,w,h=self.geometry(row)
        xs=[];ys=[]
        for other in self.rows:
            if other is row or not other['enabled'].get_active():continue
            a,b,c,d=self.geometry(other)
            xs.extend([a,a+c,a-w,a+c-w]);ys.extend([b,b+d,b-h,b+d-h])
        if xs and abs(min(xs,key=lambda v:abs(v-x))-x)*factor<=10:x=min(xs,key=lambda v:abs(v-x))
        if ys and abs(min(ys,key=lambda v:abs(v-y))-y)*factor<=10:y=min(ys,key=lambda v:abs(v-y))
        row['x'].set_value(round(x));row['y'].set_value(round(y))
        self.boxes=[(entry,(self.offset[0]+a*self.factor,self.offset[1]+b*self.factor,c*self.factor,d*self.factor)) for entry in self.rows for a,b,c,d in [self.geometry(entry)]]
        self.queue_draw();return True

    def release(self,widget,event):
        if event.button!=1 or not self.drag:return False
        self.drag=None;self.queue_draw();return True

    def arrange(self,vertical=False):
        cursor=0
        for row in self.rows:
            if not row['enabled'].get_active():continue
            row['x'].set_value(0 if vertical else cursor);row['y'].set_value(cursor if vertical else 0)
            _,_,w,h=self.geometry(row);cursor+=h if vertical else w
        self.queue_draw()


class DockPins(Gtk.Box):
    def __init__(self,identities,apps):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        self.identities=list(identities);self.apps=apps
        self.items=Gtk.ListBox();self.items.set_selection_mode(Gtk.SelectionMode.NONE)
        self.items.get_style_context().add_class('dock-pin-list')
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(80);scroll.set_max_content_height(180);scroll.set_propagate_natural_height(True)
        scroll.add(self.items);self.pack_start(scroll,True,True,0)
        self.search=Gtk.SearchEntry(placeholder_text='Search installed applications…')
        self.pack_start(self.search,False,False,0)
        self.choices=Gtk.ComboBoxText();self.available=[]
        for renderer in self.choices.get_cells():
            if isinstance(renderer,Gtk.CellRendererText):renderer.set_property('ellipsize',3);renderer.set_property('max-width-chars',24)
        for app in Gio.AppInfo.get_all():
            if app.get_id() and app.should_show():self.available.append((app.get_id(),app.get_display_name()))
        self.available.sort(key=lambda pair:pair[1].casefold())
        def filter_apps(*args):
            query=self.search.get_text().casefold();self.choices.remove_all()
            for identity,title in self.available:
                if query in title.casefold() or query in identity.casefold():self.choices.append(identity,title)
            self.choices.set_active(0)
        self.search.connect('search-changed',filter_apps);filter_apps()
        line=Gtk.Box(spacing=4);line.pack_start(self.choices,True,True,0)
        add=Gtk.Button(label='Add');add.connect('clicked',lambda widget:self.add(self.choices.get_active_id()))
        line.pack_start(add,False,False,0);self.pack_start(line,False,False,0);self.refresh()

    def add(self,identity):
        if identity and identity not in self.identities:self.identities.append(identity);self.refresh()

    def change(self,identity,delta=None):
        index=self.identities.index(identity)
        if delta is None:self.identities.remove(identity)
        elif 0<=index+delta<len(self.identities):self.identities[index],self.identities[index+delta]=self.identities[index+delta],self.identities[index]
        self.refresh()

    def refresh(self):
        for child in self.items.get_children():child.destroy()
        if not self.identities:self.items.add(Gtk.Label(label='No pinned applications',xalign=0))
        for index,identity in enumerate(self.identities):
            line=Gtk.Box(spacing=4);app=self.apps['resolve'](identity)
            label=Gtk.Label(label=app.get_display_name() if app else identity+' (unavailable)',xalign=0)
            label.set_ellipsize(3);label.set_width_chars(1);label.set_max_width_chars(25);label.set_tooltip_text(identity)
            line.pack_start(label,True,True,0)
            for text,delta,enabled in [('↑',-1,index>0),('↓',1,index+1<len(self.identities)),('×',None,True)]:
                button=Gtk.Button(label=text);button.set_sensitive(enabled)
                button.set_tooltip_text('Remove' if delta is None else 'Move up' if delta<0 else 'Move down')
                button.connect('clicked',lambda widget,identity=identity,delta=delta:self.change(identity,delta))
                line.pack_start(button,False,False,0)
            self.items.add(line)
        self.items.show_all()


PAGE_DESCRIPTIONS={
    'Appearance':'Theme, typography and shared colors.',
    'Wallpaper':'Solid backgrounds, pictures and timed slideshows.',
    'Animations':'Window, workspace and desktop motion.',
    'Session effects':'Choose how the desktop leaves your screen.',
    'Panel':'Placement, task buttons and status information.',
    'Dock':'Pinned applications, running windows and dock behavior.',
    'Desktop':'Desktop files, icons and label spacing.',
    'Launcher':'Application search and inline suggestions.',
    'Windows':'Floating windows, frames and tiled placement.',
    'Displays':'Arrange monitors, scaling, rotation and resolution.',
    'Input':'Focus behavior and the shortcut modifier.',
    'Keyboard':'Typing repeat, keyboard layouts and shortcuts.',
    'Mouse & touchpad':'Buttons, pointer motion, tapping and gestures.',
    'Network':'Wi-Fi, Ethernet and saved VPN connections.',
    'Bluetooth':'Adapter power and paired devices.',
    'Default applications':'Applications used for links, files and folders.',
    'Notifications':'Application notifications and media feedback.',
    'Audio & brightness':'Output level, mute and display brightness.',
    'Sounds':'Startup, login and exit sounds.',
    'Power':'Battery warnings, lid behavior and locking before sleep.',
    'Date & time':'Local time, timezone and the system time editor.',
    'Session':'Lock, sleep, logout and optional local overlays.',
    'About':'Operating system and session information.',
}


class SettingsBrowser:
    """One group at a time, searchable pages, and a stable page heading."""
    def __init__(self,stack,sidebar,groups,search,tabs,heading,description):
        self.stack=stack;self.sidebar=sidebar;self.groups=groups;self.search=search
        self.heading=heading;self.description=description;self.group=None;self.syncing=False
        self.titles={stack.child_get_property(child,'title'):stack.child_get_property(child,'name') for child in stack.get_children()}
        self.pages={stack.child_get_property(child,'name'):child for child in stack.get_children()}
        self.group_buttons={};self.last={};self.rows={};self.headers={}
        self.index={}
        for name,page in self.pages.items():
            words=[name,PAGE_DESCRIPTIONS.get(name,'')]
            for widget in self.descendants(page):
                if isinstance(widget,Gtk.Label):words.append(widget.get_text())
                tip=widget.get_tooltip_text()
                if tip:words.append(tip)
                if isinstance(widget,Gtk.ComboBoxText):words.extend(str(row[0]) for row in widget.get_model())
            self.index[name]=' '.join(words).casefold()
        self.list=Gtk.ListBox();self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.get_style_context().add_class('settings-source-list');sidebar.add(self.list)
        for group,pages in groups.items():
            row=Gtk.ListBoxRow();row.group=group;row.page=None;row.set_selectable(False)
            row.get_style_context().add_class('settings-nav-heading')
            button=Gtk.ToggleButton(label=group);button.set_relief(Gtk.ReliefStyle.NONE)
            button.get_child().set_xalign(0)
            button.get_style_context().add_class('settings-nav-group');button.connect('clicked',self.choose_group,group)
            row.add(button);self.list.add(row);self.group_buttons[group]=button;self.headers[group]=row
            for name in pages:
                row=Gtk.ListBoxRow();row.page=name;row.group=group
                label=Gtk.Label(label=stack.child_get_property(self.pages[name],'title'),xalign=0)
                label.set_ellipsize(3);label.set_max_width_chars(24);row.add(label)
                self.list.add(row);self.rows[name]=row
        self.list.set_filter_func(self.filter_row)
        self.list.connect('row-selected',self.select_row)
        self.stack.connect('notify::visible-child-name',self.update)
        self.search.connect('search-changed',self.search_changed)
        self.update()

    @staticmethod
    def descendants(widget):
        if isinstance(widget,Gtk.Container):
            for child in widget.get_children():
                yield child;yield from SettingsBrowser.descendants(child)

    def page_for_row(self,row):return getattr(row,'page',None)

    def filter_row(self,row):
        name=row.page;query=self.search.get_text().strip().casefold()
        if name is None:
            return not query or any(all(word in self.index[page] for word in query.split()) for page in self.groups[row.group])
        return all(word in self.index[name] for word in query.split()) if query else row.group==self.group

    def select_row(self,widget,row):
        if row and row.page and not self.syncing:self.stack.set_visible_child_name(row.page)

    def choose_group(self,button,group):
        if self.syncing:return
        self.search.set_text('');self.group=group
        self.stack.set_visible_child_name(self.last.get(group,self.groups[group][0]));self.update()

    def update(self,*args):
        page=self.stack.get_visible_child_name()
        if page is None:return
        self.group=next((group for group,pages in self.groups.items() if page in pages),next(iter(self.groups)))
        self.last[self.group]=page;self.syncing=True
        for group,button in self.group_buttons.items():
            button.set_active(group==self.group);button.set_label(('▾  ' if group==self.group or self.search.get_text().strip() else '▸  ')+group)
        self.list.select_row(self.rows[page])
        self.syncing=False;self.heading.set_text(self.stack.child_get_property(self.pages[page],'title'))
        self.description.set_text(PAGE_DESCRIPTIONS.get(page,''));self.list.invalidate_filter()

    def search_changed(self,*args):
        query=self.search.get_text().strip().casefold()
        matches=[name for name,text in self.index.items() if all(word in text for word in query.split())]
        self.list.invalidate_filter()
        if query and matches and self.stack.get_visible_child_name() not in matches:self.stack.set_visible_child_name(matches[0])
        if query and not matches:self.description.set_text('No settings match your search.')
        elif not query:self.update()
        for page in self.pages.values():
            for widget in self.descendants(page):
                if not isinstance(widget,Gtk.Label):continue
                context=widget.get_style_context()
                if query and query in widget.get_text().casefold():context.add_class('settings-match')
                else:context.remove_class('settings-match')
