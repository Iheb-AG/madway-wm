"""Navigation, search, compact geometry and draft effect controls on a private display."""
import configparser
import os
from pathlib import Path
import runpy
import subprocess
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
repo=Path(__file__).resolve().parent.parent;api=runpy.run_path(str(repo/'scripts/madway-shell'))
errors=[];messages=[];original=api['CONFIG'].read_text()
api['settings_window'].__globals__['action']=lambda name,**values:messages.append((name,values))

def children(widget):
    yield widget
    if isinstance(widget,Gtk.Container):
        for child in widget.get_children():yield from children(child)

def check(stage=0):
    window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings')
    stack=window.settings_browser.stack;browser=window.settings_browser
    def control(page,label):
        grid=next(w for w in children(stack.get_child_by_name(page)) if isinstance(w,Gtk.Grid))
        caption=next(w for w in grid.get_children() if isinstance(w,Gtk.Label) and w.get_text()==label)
        return grid.get_child_at(1,grid.child_get_property(caption,'top-attach'))
    def shot(name):
        folder=os.environ.get('MADWAY_TEST_ARTIFACTS')
        if folder:
            Path(folder).mkdir(parents=True,exist_ok=True);subprocess.run(['grim','-o','HEADLESS-1',str(Path(folder)/(name+'.png'))],check=True)
    try:
        if stage==0:
            for group,button in browser.group_buttons.items():
                button.clicked()
                assert stack.get_visible_child_name() in api['SETTINGS_GROUPS'][group]
                assert {browser.page_for_row(row) for row in browser.list.get_children() if row.get_child_visible() and row.page is not None}==set(api['SETTINGS_GROUPS'][group])
            browser.search.set_text('shader');browser.search_changed();assert stack.get_visible_child_name()=='Session effects'
            browser.search.set_text('does-not-exist');browser.search_changed();assert 'No settings' in browser.description.get_text()
            browser.search.set_text('');browser.search_changed();stack.set_visible_child_name('Windows')
            control('Windows','Master width (%)').set_value(63)
            browser.group_buttons['Appearance'].clicked();stack.set_visible_child_name('Session effects')
            assert control('Windows','Master width (%)').get_value_as_int()==63,'Navigation lost unsaved changes'
            mode=control('Session effects','Exit animation');mode.set_active_id('none');assert not control('Session effects','Exit').get_sensitive()
            mode.set_active_id('shader');control('Session effects','Shader style').set_active_id('iris');control('Session effects','Duration (ms)').set_value(900)
            control('Session effects','Exit').clicked()
            assert messages==[('session-effect-preview',dict(mode='shader',shader='iris',duration=900))]
            assert api['CONFIG'].read_text()==original,'Preview saved unrelated settings'
            window.resize(640,480)
        elif stage==1:
            shot('settings-session-effects');stack.set_visible_child_name('Appearance')
        elif stage==2:
            shot('settings-appearance');stack.set_visible_child_name('Mouse & touchpad')
        elif stage==3:
            shot('settings-input');stack.set_visible_child_name('Sounds')
        elif stage==4:
            shot('settings-sounds')
            apply=next(w for w in children(window) if isinstance(w,Gtk.Button) and w.get_label()=='Apply');apply.clicked()
            cfg=configparser.ConfigParser(interpolation=None);cfg.read(api['CONFIG'])
            assert cfg.get('session_effects','mode')=='shader' and cfg.get('session_effects','shader')=='iris' and cfg.getint('session_effects','duration_ms')==900
            assert cfg.getint('windows','master_percent')==63
            stack.set_visible_child_name('Displays')
            refresh=control('Displays','Monitor list');refresh.clicked()
            grid=next(w for w in children(stack.get_child_by_name('Displays')) if isinstance(w,Gtk.Grid))
            last_row=grid.next_row;control('Displays','Monitor list').clicked();assert grid.next_row==last_row
        else:
            pages=list(api['SETTINGS_PAGES']);index=stage-5
            if index>=len(pages):window.destroy();return False
            page=pages[index];stack.set_visible_child_name(page)
            def geometry(page=page):
                try:
                    scroll=stack.get_child_by_name(page);grid=next(w for w in children(scroll) if isinstance(w,Gtk.Grid));width=grid.get_allocated_width()
                    rows={}
                    for child in grid.get_children():
                        if not child.get_visible():continue
                        box=child.get_allocation();assert box.x+box.width<=width+1,(page,box,width)
                        row=grid.child_get_property(child,'top-attach');rows.setdefault(row,[]).append(box)
                    for boxes in rows.values():
                        if len(boxes)==2:
                            a,b=sorted(boxes,key=lambda box:box.x);assert a.x+a.width<=b.x,(page,a,b)
                except BaseException as error:errors.append(error);window.destroy()
                return False
            GLib.timeout_add(45,geometry)
        GLib.timeout_add(100,lambda:check(stage+1));return False
    except BaseException as error:errors.append(error);window.destroy();return False

try:
    GLib.timeout_add(500,check);api['settings_window']('Windows')
finally:api['CONFIG'].write_text(original)
if errors:raise AssertionError('Settings redesign regression') from errors[0]
print('PASS: group navigation/search/no-results, retained drafts, preview without save, exit preferences persisted, every compact form stays within its grid and rows never overlap.')
