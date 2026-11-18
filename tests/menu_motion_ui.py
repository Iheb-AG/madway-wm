"""Real frame-clock popup motion on private 100 Hz Wayland outputs."""
import os
from pathlib import Path
import runpy
import subprocess
import time
import threading
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
repo=Path(__file__).resolve().parent.parent;panel=runpy.run_path(str(repo/'scripts/madway-panel'))
scope=panel['DesktopMenu'].__init__.__globals__;api=panel['api'];config=api['settings']()
config['motion'].update(effects='true',menu_ms='240')
import json
outputs=json.loads((api['runtime_directory']()/'outputs.json').read_text())['outputs']
for output in outputs:config['output:'+output['name']]={'mode':f"{output['width']}x{output['height']}@100000",'x':str(output['x']),'y':str(output['y'])}
api['write_settings'](config);api['action']('apply');scope['settings']=lambda:config
api['audio_snapshot']=lambda:[('Outputs',[dict(kind='sink',id=1,name='fixture',label='Speakers',volume=40,mute=False,default=True,adjustable=True)])]
for style,priority in [(api['theme_style'](panel['CSS'].decode(),config),Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION),
                       (api['overlay_style']('utilities.css',config),Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+3)]:
 provider=Gtk.CssProvider();provider.load_from_data(style.encode());Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,priority)
loop=GLib.MainLoop();errors=[];menu=None;case=0;old=None
cases=[('Desktop','top'),('Clock','bottom'),('Audio','left'),('Timer','right'),('Session','top'),('Workspaces','bottom'),('Battery','right'),('Status','left')]

def create(page='Desktop',edge='top'):
 global menu
 if menu:menu.window.destroy()
 display=Gdk.Display.get_default();monitor=display.get_monitor(case%display.get_n_monitors());bounds=monitor.get_geometry()
 x=bounds.x+bounds.width-2 if edge=='right' else bounds.x+2
 y=bounds.y+bounds.height-18 if edge=='bottom' else bounds.y+18
 menu=panel['DesktopMenu'](x,y,page,edge=edge);menu.window.disconnect_by_func(Gtk.main_quit)
 return menu,bounds

def fail(error):
 errors.append(error);loop.quit();return False

def next_case():
 global case
 try:
  if case>=len(cases):submenu();return False
  page,edge=cases[case];current,bounds=create(page,edge);samples=[]
  def drawn(widget,cr):
   samples.append((time.monotonic(),widget.progress,widget.get_opacity(),widget.get_allocated_width(),widget.get_allocated_height(),widget.clip_rect()))
   if page=='Desktop' and widget.progress<.5:
    if current.visible_input.contains_point(widget.get_allocated_width()-1,widget.get_allocated_height()-1):
     return fail(AssertionError('Unrevealed menu area accepted input'))
   return False
  current.motion.connect_after('draw',drawn)
  def inspect():
   global case
   try:
    assert current.motion.progress==1 and current.motion.tick_id==0
    assert current.motion.get_opacity()==1 and current.motion.frames>=10,(page,current.motion.frames)
    assert len({round(row[1],3) for row in samples})>=8,(page,samples)
    assert samples[0][1]<.2 and samples[0][2]<.5,(page,samples[0])
    assert all(a[1]<=b[1] for a,b in zip(samples,samples[1:])),page
    assert .20<=samples[-1][0]-samples[0][0]<.8,(page,samples[-1][0]-samples[0][0])
    if page!='Audio':assert len({row[3:5] for row in samples})==1,(page,[row[3:5] for row in samples])
    for _,_,_,w,h,(x,y,cw,ch) in samples:
     assert x>=0 and y>=0 and x+cw<=w and y+ch<=h
     if edge=='bottom':assert y+ch==h
     if edge=='right':assert x+cw==w
    assert panel['Layer'].get_margin(current.window,panel['Layer'].Edge.LEFT)+current.window.get_allocated_width()<=bounds.width
    assert panel['Layer'].get_margin(current.window,panel['Layer'].Edge.TOP)+current.window.get_allocated_height()<=bounds.height
    assert current.visible_input.contains_point(current.box.get_allocated_width()//2,current.box.get_allocated_height()//2)
    current.window.destroy();assert current.motion.tick_id==0
    case+=1;GLib.timeout_add(40,next_case)
   except BaseException as error:return fail(error)
   return False
  GLib.timeout_add(350,inspect)
  if case==0 and os.environ.get('MADWAY_TEST_ARTIFACTS'):
   folder=Path(os.environ['MADWAY_TEST_ARTIFACTS']);folder.mkdir(parents=True,exist_ok=True)
   geometry=f'{bounds.x},{bounds.y} {bounds.width}x{bounds.height}'
   def capture(name):
    threading.Thread(target=lambda:subprocess.run(['grim','-g',geometry,str(folder/name)],check=True),daemon=True).start()
    return False
   GLib.timeout_add(60,lambda:capture('menu-opening.png'));GLib.timeout_add(290,lambda:capture('menu-settled.png'))
 except BaseException as error:return fail(error)
 return False

def submenu():
 global old
 try:
  current,_=create();current.motion.finish();current.open_submenu('Settings');old=current.submenu_motion
  def replace():
   try:
    assert 0<=old.progress<1 and old.tick_id
    current.open_submenu('Workspaces');assert old.tick_id==0
    replacement=current.submenu_motion
    def settled():
     try:
      assert replacement.progress==1 and replacement.frames>=8
      assert current.box.get_allocated_height()==current.box.get_preferred_height()[1],'Submenu stretched the root menu'
      current.close_submenu();assert replacement.tick_id==0 and current.submenu is None
      current.open_submenu('Settings');discarded=current.submenu_motion;current.window.destroy();assert discarded.tick_id==0
      corner()
     except BaseException as error:return fail(error)
     return False
    GLib.timeout_add(300,settled)
   except BaseException as error:return fail(error)
   return False
  GLib.timeout_add(40,replace)
 except BaseException as error:return fail(error)

def corner():
 global menu
 try:
  monitor=Gdk.Display.get_default().get_monitor(0);rect=monitor.get_geometry()
  menu=panel['DesktopMenu'](rect.x+rect.width-210,rect.y+18,'Desktop',edge='top')
  menu.window.disconnect_by_func(Gtk.main_quit)
  def open_child():
   try:
    origin=panel['Layer'].get_margin(menu.window,panel['Layer'].Edge.LEFT)+menu.box.translate_coordinates(menu.window,0,0)[0]
    menu.open_submenu('Settings');assert menu.submenu_left
    def compare():
     try:
      after=panel['Layer'].get_margin(menu.window,panel['Layer'].Edge.LEFT)+menu.box.translate_coordinates(menu.window,0,0)[0]
      assert after==origin,('Cascade moved the parent',origin,after)
      menu.window.destroy();disabled()
     except BaseException as error:return fail(error)
     return False
    GLib.timeout_add(300,compare)
   except BaseException as error:return fail(error)
   return False
  GLib.timeout_add(300,open_child)
 except BaseException as error:return fail(error)

def disabled():
 try:
  config['motion']['effects']='false';current,_=create('Clock','bottom')
  assert current.motion.progress==1 and current.motion.tick_id==0 and current.motion.get_opacity()==1
  current.window.destroy()
  config['motion']['effects']='true';current,_=create('Timer','top')
  event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.keyval=Gdk.keyval_from_name('Tab')
  current.key(current.window,event);assert current.motion.progress==1 and not current.motion.tick_id
  current.window.destroy();loop.quit()
 except BaseException as error:return fail(error)

attempts=0
def begin():
 global attempts
 attempts+=1
 rates=[Gdk.Display.get_default().get_monitor(i).get_refresh_rate() for i in range(Gdk.Display.get_default().get_n_monitors())]
 if min(rates)<90000:
  if attempts<25:return True
  return fail(AssertionError(('100 Hz modes not applied',rates)))
 next_case();return False
GLib.timeout_add(100,begin)
try:loop.run()
finally:
 if menu:menu.window.destroy()
if errors:raise AssertionError('Menu animation regression') from errors[0]
print('PASS: 100 Hz frame-clock reveals for all panel menus and edges, stable text/layout, eased intermediate frames, bounded geometry, rapid submenu replacement/cleanup, immediate keyboard completion and effects-disabled behavior.')
