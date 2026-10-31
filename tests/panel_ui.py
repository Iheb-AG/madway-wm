"""Exercise compact bar menu routing on desktop_smoke.py's private display."""
from pathlib import Path
import runpy
import json
import tempfile
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
power_fixture=dict(present=True,percent=54,status='Charging',on_ac=True,seconds=3600,batteries=[])
scope['api']['power_snapshot']=lambda:power_fixture
fixture=tempfile.TemporaryDirectory(prefix='madway-panel-state-')
state_file=Path(fixture.name)/'desktop.json'
state=dict(workspace=0,windows=[dict(id=101,title='Minimized terminal',minimized=True),
                              dict(id=102,title='Minimized editor',minimized=True),
                              dict(id=105,title='Another minimized application',minimized=True),
                              dict(id=103,title='Visible window',minimized=False)])
state_file.write_text(json.dumps(state))
scope['runtime_directory']=lambda:Path(fixture.name)
bar=api['TopBar']()
bar.config['panel']['tasks']='icons';bar.rebuild()
errors=[]
audio_rows = [('Outputs', [dict(kind='sink', id=3, name='test', label='Test output', volume=45, mute=False, default=True, adjustable=True)]),
              ('Applications · playback', [dict(kind='sink-input', id=8, name='8', label='Test player', volume=30, mute=False, default=False, adjustable=True)])]
scope['api']['audio_snapshot'] = lambda:audio_rows


def inspect():
    try:
        expected=['Desktop','Workspaces','Window','Status','Audio','Battery','Clock','Session']
        assert bar.bars
        for instance in bar.bars:
            buttons=instance['buttons']
            restores=instance['minimized_box'].get_children()
            assert instance['minimized'].get_visible() and len(restores)==4
            children=instance['workspace'].get_parent().get_children()
            assert children[children.index(instance['workspace'])+1] is instance['minimized']
            assert instance['minimized'].get_parent().child_get_property(instance['minimized'],'expand')
            adjustment=instance['minimized'].get_hadjustment()
            assert all(button.get_label()=='' and button.get_image() is not None for button in restores)
            for button,identity in zip(restores,(101,102,105,103)):
                button.clicked()
                assert messages[-1]==('taskbar-toggle',dict(id=identity))
            assert api['api']['panel_label'](bar.config) in buttons[0].get_label()
            assert len(buttons)==len(expected)
            assert not any(widget.get_label() in ('Apps','Run','Settings') for widget in buttons)
            for button,page in zip(buttons,expected):
                button.clicked()
                name,values=messages[-1]
                assert name=='panel-menu' and values['page']==page,(name,values)
                assert 'x' in values and 'y' in values
        for instance in bar.bars:
            assert instance['battery'].get_visible() and '54%' in instance['battery'].get_label()
        power_fixture.update(percent=18,status='Discharging',on_ac=False);bar.refresh()
        assert all(instance['battery'].get_style_context().has_class('battery-low') for instance in bar.bars)
        power_fixture['percent']=5;bar.refresh()
        assert all(instance['battery'].get_style_context().has_class('battery-critical') for instance in bar.bars)
        power_fixture.update(status='Charging',on_ac=True);bar.refresh()
        assert not any(instance['battery'].get_style_context().has_class('battery-critical') for instance in bar.bars)
        bar.config['power']['show_battery']='false';bar.refresh()
        assert not any(instance['battery'].get_visible() for instance in bar.bars)
        bar.config['power']['show_battery']='true';power_fixture['present']=False;bar.refresh()
        assert not any(instance['battery'].get_visible() for instance in bar.bars)
        power_fixture.update(present=True,percent=None);bar.refresh()
        assert all('?' in instance['battery'].get_label() for instance in bar.bars)
        power_fixture['percent']=54;bar.refresh()
        state['windows'][0]['title']='Renamed minimized terminal'
        state['windows'][1]['minimized']=False
        state['windows'][2]['minimized']=False
        state_file.write_text(json.dumps(state));bar.refresh()
        for instance in bar.bars:
            restores=instance['minimized_box'].get_children()
            assert len(restores)==4 and 'Renamed' in restores[0].get_tooltip_text()
            assert not restores[1].get_style_context().has_class('minimized')
        state['windows']=[];state_file.write_text(json.dumps(state));bar.refresh()
        assert not any(instance['minimized'].get_visible() for instance in bar.bars)
        state['windows']=[dict(id=104,title='Vertical restore',minimized=True)]
        state_file.write_text(json.dumps(state))
        print('RUNNING AND MINIMIZED TASKBAR ICONS TOGGLE UPDATE AND REMOVAL PASS',flush=True)
        print('BATTERY PANEL LEVEL CHARGING WARNINGS AND VISIBILITY PASS',flush=True)
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
                restores=instance['minimized_box'].get_children()
                assert instance['minimized'].get_visible() and len(restores)==1
                restores[0].clicked()
                assert messages[-1]==('taskbar-toggle',dict(id=104))
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
            margin=menu.box.get_style_context().get_margin(Gtk.StateFlags.NORMAL)
            assert not any((margin.top,margin.bottom,margin.left,margin.right)), 'Menu theme leaves a gap at the panel edge'
            labels=[button.get_label() for button in menu.buttons]
            if page=='Desktop':assert 'Applications ›' in labels and 'Run command…' in labels and 'Settings ›' in labels
            if page=='Audio':assert hasattr(menu, 'mixer') and 'Audio options…' in labels
            if page=='Battery':assert 'Power settings…' in labels and 'Refresh' in labels
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

# Cascades keep each menu's natural height, including above a bottom panel.
for theme in ('black','gershwin','gershwin-dark'):
    cfg=api['api']['settings']();cfg['appearance']['theme']=theme
    themed=Gtk.CssProvider();themed.load_from_data(api['api']['theme_style'](api['CSS'].decode(),cfg).encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),themed,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
    for edge in ('top','bottom','left','right'):
        bounds=Gdk.Display.get_default().get_monitor(0).get_geometry()
        menu=api['DesktopMenu'](bounds.x+22,bounds.y+(bounds.height-22 if edge=='bottom' else 22),'Desktop','',edge)
        root_height=[]
        def check(stage=0):
            try:
                height=menu.box.get_allocated_height()
                if stage==0:
                    root_height.append(height);menu.open_submenu('Applications')
                else:
                    assert height==root_height[0],(theme,edge,stage,height,root_height)
                    assert height==menu.box.get_preferred_height()[1], 'Root menu stretched'
                    if edge=='bottom':
                        assert menu.box.get_allocation().y+height==menu.container.get_allocated_height()
                        assert Layer.get_margin(menu.window,Layer.Edge.TOP)+menu.window.get_allocated_height()==bounds.height-22
                    if stage==1:
                        assert menu.submenu.get_allocated_height()==menu.submenu.get_preferred_height()[1]
                        menu.open_submenu('Session')
                    elif stage==2:
                        assert menu.submenu.get_allocated_height()==menu.submenu.get_preferred_height()[1]
                        assert menu.window.get_allocated_height()==max(height,menu.submenu.get_allocated_height())
                        menu.close_submenu()
                    else:
                        assert menu.window.get_allocated_height()==height
                        menu.window.destroy();return False
                GLib.timeout_add(100,lambda:check(stage+1))
            except BaseException as error:
                errors.append(error);menu.window.destroy()
            return False
        GLib.timeout_add(100,check);Gtk.main()
    # Long Bluetooth/app names must not collide with mute/default controls or sliders.
    audio_rows[0][1][0]['label']='Bluetooth headphones — very long device name ' * 4
    menu=api['DesktopMenu'](20,30,'Audio')
    def inspect_audio():
        try:
            assert menu.window.get_allocated_width()<=bounds.width
            for slider,_,mute,_,default in menu.mixer.rows.values():
                card=slider.get_parent();label,line,scale=card.get_children()
                a,b,c=(widget.get_allocation() for widget in (label,line,scale))
                assert a.y+a.height<=b.y and b.y+b.height<=c.y,(theme,a,b,c)
                if default:
                    d,m=default.get_allocation(),mute.get_allocation()
                    assert d.x+d.width<=m.x,(theme,d,m)
            if theme=='gershwin-dark':
                import subprocess
                subprocess.run(['grim',str(Path(__file__).resolve().parent.parent/'build/audio-midnight-preview.png')],check=True)
        except BaseException as error:errors.append(error)
        menu.window.destroy();return False
    GLib.timeout_add(200,inspect_audio);Gtk.main()
    Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),themed)
if errors:raise AssertionError('Cascade sizing regression') from errors[0]
print('BLACK AND EAU FOUR EDGE CASCADE HEIGHT AND SHRINK PASS',flush=True)
fixture.cleanup()
