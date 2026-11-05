"""Real settings widgets on desktop_experience.py's disposable display/profile."""
import configparser
import os
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway-shell'));errors=[];sent=[]
api['settings_window'].__globals__['action']=lambda name,**values:sent.append((name,values))
original=api['CONFIG'].read_text()


def children(widget):
    yield widget
    if isinstance(widget,Gtk.Container):
        for child in widget.get_children():yield from children(child)


def check(stage=0):
    window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings')
    try:
        stack=next(w for w in children(window) if isinstance(w,Gtk.Stack))
        def control(page,label):
            grid=next(w for w in children(stack.get_child_by_name(page)) if isinstance(w,Gtk.Grid))
            caption=next(w for w in grid.get_children() if isinstance(w,Gtk.Label) and w.get_text()==label)
            return grid.get_child_at(1,grid.child_get_property(caption,'top-attach'))
        def shot(name):
            if os.environ.get('MADWAY_TEST_ARTIFACTS'):
                target=Path(os.environ['MADWAY_TEST_ARTIFACTS']);target.mkdir(parents=True,exist_ok=True)
                subprocess.run(['grim','-o','HEADLESS-1',str(target/(name+'.png'))],check=True,timeout=5)
        editors=sys.modules['madway_settings']
        canvas=next(w for w in children(stack) if isinstance(w,editors.DisplayLayout))
        apply=next(w for w in children(window) if isinstance(w,Gtk.Button) and w.get_label()=='Apply')
        if stage==0:
            names=[stack.child_get_property(page,'name') for page in stack.get_children()]
            assert names==list(api['SETTINGS_PAGES']),names
            assert list(window.settings_browser.group_buttons)==list(api['SETTINGS_GROUPS'])
            canvas.layout();assert len(canvas.boxes)==2
            row,box=canvas.boxes[-1];x,y,w,h=box;previous=row['y'].get_value()
            event=SimpleNamespace(button=1,x=x+w/2,y=y+h/2)
            assert canvas.press(canvas,event)
            assert canvas.motion(canvas,SimpleNamespace(x=event.x+max(40,125*canvas.factor),y=event.y+max(40,90*canvas.factor)))
            assert canvas.release(canvas,event) and row['y'].get_value()!=previous
            assert api['CONFIG'].read_text()==original,'Preview applied an unsaved layout'
            canvas.rows[0]['scale'].set_value(2);canvas.rows[0]['transform'].set_active_id('1')
            assert tuple(round(v) for v in canvas.geometry(canvas.rows[0])[2:])==(300,400)
            canvas.arrange(True)
            assert canvas.rows[1]['x'].get_value()==0 and canvas.rows[1]['y'].get_value()==400
            control('Appearance','UI font family').set_text('monospace')
            control('Appearance','Title text size (0 = theme)').set_value(10)
            control('Appearance','Icon theme').set_text('Adwaita')
            control('Appearance','Override theme colors').set_active(True)
            color=next(w for w in children(control('Appearance','Active color')) if isinstance(w,Gtk.Entry))
            color.set_text('bad color');apply.clicked();assert not sent and api['CONFIG'].read_text()==original
            color.set_text('#225577')
            for label in children(window):
                if isinstance(label,Gtk.Label) and label.get_text()=='Theme colors must be #RRGGBB or empty':label.set_text('')
            control('Panel','Edge padding (px)').set_value(18)
            control('Panel','Item spacing (px)').set_value(3)
            control('Panel','Active window title').set_active(False)
            control('Panel','Clock format').set_text('%H:%M')
            control('Dock','Files shortcut').set_active(False)
            control('Dock','Running applications').set_active(False)
            control('Dock','Screen margin (px)').set_value(8)
            pins=next(w for w in children(stack) if isinstance(w,editors.DockPins))
            a='org.madway.PinnedFixture.desktop';b='org.madway.OtherFixture.desktop'
            pins.add(a);pins.add(a);pins.add(b);assert pins.identities==[a,b]
            pins.change(b,-1);assert pins.identities==[b,a]
            pins.change(a);assert pins.identities==[b]
            control('Desktop','Cell width (px)').set_value(104)
            control('Desktop','Icon spacing (px)').set_value(10)
            control('Desktop','Show icon labels').set_active(False)
            control('Desktop','Open with a single click').set_active(True)
            control('Launcher','Search width (px)').set_value(420)
            control('Launcher','Visible results').set_value(4)
            control('Launcher','Application icons').set_active(False)
        elif stage==1:
            shot('display-layout');stack.set_visible_child_name('Dock')
        elif stage==2:
            pins=next(w for w in children(stack) if isinstance(w,editors.DockPins))
            color=pins.items.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
            assert max(color.red,color.green,color.blue)<.3,'Dark-theme pin list inherited a white background'
            shot('dock-settings');stack.set_visible_child_name('Appearance')
        else:
            shot('appearance-settings');apply.clicked()
            cfg=configparser.ConfigParser(interpolation=None);cfg.read(api['CONFIG'])
            assert sent==[('apply',{})],sent
            assert cfg.get('colors','active')=='#225577' and cfg.getboolean('appearance','custom_colors')
            assert cfg.get('appearance','font')=='monospace' and cfg.getint('appearance','title_font_size')==10
            assert cfg.get('appearance','icon_theme')=='Adwaita'
            assert cfg.getint('panel','padding')==18 and not cfg.getboolean('panel','show_title')
            assert cfg.get('panel','clock_format')=='%H:%M'
            assert not cfg.getboolean('dock','show_files') and cfg.getint('dock','margin')==8
            assert cfg.get('dock','pinned')=='["org.madway.OtherFixture.desktop"]'
            assert cfg.getint('desktop','cell_width')==104 and cfg.getboolean('desktop','single_click') and not cfg.getboolean('desktop','labels')
            assert cfg.getint('launcher','width')==420 and cfg.getint('launcher','lines')==4 and not cfg.getboolean('launcher','icons')
            name=canvas.rows[1]['name'];assert cfg.getint('output:'+name,'x')==0 and cfg.getint('output:'+name,'y')==400
            window.destroy();return False
        GLib.timeout_add(180,lambda:check(stage+1))
    except BaseException as error:errors.append(error);window.destroy()
    return False


try:
    GLib.timeout_add(500,check);api['settings_window']('Displays')
finally:api['CONFIG'].write_text(original)
if errors:raise AssertionError('Customization UI regression') from errors[0]
print('PASS: grouped settings, draggable/scaled/rotated monitor preview, deferred layout apply, palette validation, dock pin editing and persisted customization.',flush=True)
