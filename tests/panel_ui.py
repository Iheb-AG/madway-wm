"""Exercise compact bar menu routing on desktop_smoke.py's private display."""
from pathlib import Path
import runpy
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

api=runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway-panel'))
scope=api['TopBar'].__init__.__globals__
messages=[]
scope['action']=lambda name,**values: messages.append((name,values))
provider=Gtk.CssProvider();provider.load_from_data(api['CSS'])
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
for name in api['api']['themes']().sections():
    cfg=api['api']['settings']();cfg['appearance']['theme']=name
    themed=Gtk.CssProvider();themed.load_from_data(api['api']['theme_style'](api['CSS'].decode(),cfg).encode())
bar=api['TopBar']()
errors=[]
audio_rows = [('Outputs', [dict(kind='sink', id=3, name='test', label='Test output', volume=45, mute=False, default=True, adjustable=True)]),
              ('Applications · playback', [dict(kind='sink-input', id=8, name='8', label='Test player', volume=30, mute=False, default=False, adjustable=True)])]
scope['api']['audio_snapshot'] = lambda:audio_rows


def inspect():
    try:
        expected=['Desktop','Workspaces','Window','Status','Audio','Clock','Session']
        assert bar.bars
        for instance in bar.bars:
            buttons=instance['buttons']
            assert len(buttons)==len(expected)
            assert not any(widget.get_label() in ('Apps','Run','Settings') for widget in buttons)
            for button,page in zip(buttons,expected):
                button.clicked()
                name,values=messages[-1]
                assert name=='panel-menu' and values['page']==page,(name,values)
                assert 'x' in values and 'y' in values
        print('COMPACT PANEL MENU ROUTING PASS',flush=True)
    except BaseException as error:
        errors.append(error)
    for instance in bar.bars:instance['window'].destroy()
    bar.bars.clear()
    Gtk.main_quit()
    return False

GLib.timeout_add(350,inspect)
Gtk.main()
if errors:raise AssertionError('Panel UI test failed') from errors[0]
# Exercise the live GTK layout and popup coordinates for the other three edges.
Layer=api['Layer']
for position in ('bottom','left','right'):
    bar=api['TopBar']()
    bar.config['panel']['position']=position;bar.rebuild()
    def inspect_edge(position=position,bar=bar):
        try:
            vertical=position in ('left','right')
            for instance in bar.bars:
                window=instance['window'];bounds=instance['monitor'].get_geometry()
                thickness=bar.config.getint('panel','height')
                assert Layer.get_exclusive_zone(window)==thickness
                assert window.get_allocated_width()==thickness if vertical else window.get_allocated_height()==thickness
                assert Layer.get_anchor(window,{'bottom':Layer.Edge.BOTTOM,'left':Layer.Edge.LEFT,'right':Layer.Edge.RIGHT}[position])
                for button in instance['buttons']:
                    button.clicked();name,values=messages[-1]
                    assert name=='panel-menu' and values['edge']==position
                    if position=='bottom':assert values['y']==bounds.y+bounds.height-thickness
                    if position=='left':assert values['x']==bounds.x+thickness
                    if position=='right':assert values['x']==bounds.x+bounds.width-thickness
            print('PANEL '+position.upper()+' GEOMETRY AND MENU ROUTING PASS',flush=True)
        except BaseException as error:errors.append(error)
        for instance in bar.bars:instance['window'].destroy()
        bar.bars.clear();Gtk.main_quit();return False
    GLib.timeout_add(150,inspect_edge);Gtk.main()
if errors:raise AssertionError('Panel edge test failed') from errors[0]
# Bottom/right popups open inward and stay clear of their panel edge.
for edge in ('bottom','right'):
    monitor=Gdk.Display.get_default().get_monitor(0);bounds=monitor.get_geometry()
    menu=api['DesktopMenu'](bounds.x+bounds.width-22,bounds.y+bounds.height-22,'Clock','',edge)
    def inspect_popup(menu=menu,edge=edge,bounds=bounds):
        try:
            if edge=='bottom':assert Layer.get_margin(menu.window,Layer.Edge.TOP)+menu.window.get_allocated_height()<=bounds.height-22
            else:assert Layer.get_margin(menu.window,Layer.Edge.LEFT)+menu.window.get_allocated_width()<=bounds.width-22
        except BaseException as error:errors.append(error)
        menu.window.destroy();return False
    GLib.timeout_add(100,inspect_popup);Gtk.main()
if errors:raise AssertionError('Popup positioning failed') from errors[0]
# Each menu section builds real GTK/layer-shell content, not a direct action.
for page in api['MENU_PAGES']:
    menu=api['DesktopMenu'](20,20,page,'CPU 5% RAM 1.0G')
    def inspect_menu(menu=menu,page=page):
        try:
            assert menu.page==page and menu.buttons
            labels=[button.get_label() for button in menu.buttons]
            if page=='Desktop':assert 'Applications ›' in labels and 'Run command…' in labels and 'Settings ›' in labels
            if page=='Audio':assert hasattr(menu, 'mixer') and 'Audio options…' in labels
            if page=='Clock':assert 'Clock options…' in labels
            if page=='Audio':
                assert ('sink',3) in menu.mixer.rows and ('sink-input',8) in menu.mixer.rows
                slider,_,mute,_,_=menu.mixer.rows[('sink-input',8)]
                assert menu.window.get_allocated_width()>=300
                assert menu.mixer.scroll.get_min_content_height()>50
                assert slider.get_allocated_height()>10
                assert round(slider.get_value())==30
                slider.grab_focus()
                event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.keyval=Gdk.KEY_Left
                assert not menu.key(menu.window,event) and menu.page=='Audio'
                slider.set_value(62)
                menu.mixer.release(('sink-input',8))
                mute.set_active(True)
                menu.mixer.update(audio_rows,None)
                assert round(slider.get_value())==62, 'Polling overwrote a user edit'
            if page=='Desktop':
                menu.open_submenu('Settings')
                assert menu.submenu is not None and menu.box.get_children()[1].get_label()=='Applications ›'
                assert any(button.get_label()=='Displays' for button in menu.buttons)
                menu.open_submenu('Applications')
                assert any(button.get_label()=='Search applications…' for button in menu.buttons)
                menu.close_submenu()
                assert menu.page=='Desktop' and menu.submenu is None
                button=next(button for button in menu.buttons if button.get_label()=='Settings ›')
                button.emit('enter-notify-event', Gdk.Event.new(Gdk.EventType.ENTER_NOTIFY))
                def verify_hover():
                    try:
                        assert menu.submenu is not None and menu.page=='Settings'
                        assert menu.box.get_children()[1].get_label()=='Applications ›'
                        event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.keyval=Gdk.KEY_Left
                        assert menu.key(menu.window,event) and menu.page=='Desktop'
                        print('HOVER CASCADE AND KEYBOARD RETURN PASS',flush=True)
                    except BaseException as error:errors.append(error)
                    menu.window.destroy();return False
                GLib.timeout_add(200,verify_hover)
                return False
        except BaseException as error:errors.append(error)
        menu.window.destroy();return False
    GLib.timeout_add(60,inspect_menu)
    Gtk.main()
    if page=='Audio':
        assert any(name=='audio-control' and values.get('operation')=='volume' and values.get('value')==62 for name,values in messages)
        assert any(name=='audio-control' and values.get('operation')=='mute' and values.get('value') is True for name,values in messages)
if errors:raise AssertionError('Menu page test failed') from errors[0]
print('ALL PANEL DROPDOWN PAGES PASS',flush=True)
