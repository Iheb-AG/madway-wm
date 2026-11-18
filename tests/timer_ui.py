"""Panel timer popup and real helper IPC on the private desktop test harness."""
import os
from pathlib import Path
import runpy
import subprocess
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib,Gdk
repo=Path(__file__).resolve().parent.parent
panel=runpy.run_path(str(repo/'scripts/madway-panel'));scope=panel['DesktopMenu'].__init__.__globals__
api=panel['api'];read=panel['read_state'];path=api['runtime_directory']()/'timer.json'
provider=Gtk.CssProvider();provider.load_from_data(api['theme_style'](panel['CSS'].decode()).encode())
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
utilities=Gtk.CssProvider();utilities.load_from_data(api['overlay_style']('utilities.css').encode())
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),utilities,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+3)
loop=GLib.MainLoop();errors=[];menu=None;bar=None;deadline=None;paused=None
monitor=Gdk.Display.get_default().get_monitor(0);bounds=monitor.get_geometry()

def close_menu():
 global menu
 if menu:menu.window.destroy();menu=None

def open_menu(edge='top',rect=bounds,point=None):
 global menu
 close_menu()
 x=rect.x+rect.width-2 if edge=='right' else rect.x+2
 y=rect.y+rect.height-20 if edge=='bottom' else rect.y+20
 if point:x,y=point
 menu=panel['DesktopMenu'](x,y,'Timer',edge=edge)
 menu.window.disconnect_by_func(Gtk.main_quit)
 return menu.timer

def shot(name):
 target=os.environ.get('MADWAY_TEST_ARTIFACTS')
 if target:
  Path(target).mkdir(parents=True,exist_ok=True)
  subprocess.run(['grim','-g',f'{bounds.x},{bounds.y} {bounds.width}x{bounds.height}',str(Path(target)/(name+'.png'))],check=True)

def step(stage=0):
 global bar,deadline,paused
 try:
  delay=200
  if stage==0:
   pane=open_menu();assert pane.readout.get_text()=='05:00'
   for widget,value in zip(pane.fields,(0,0,2)):widget.set_value(value)
   pane.primary.clicked()
  elif stage==1:
   model=read(path);assert model.view()['phase']=='running';deadline=model.deadline
   config=api['settings']();config['panel']['padding']=str(config.getint('panel','padding')+1);api['write_settings'](config)
   api['action']('apply');close_menu();delay=200
  elif stage==2:
   assert read(path).deadline==deadline,'Panel reload reset the countdown'
   pane=open_menu();pane.primary.clicked()
  elif stage==3:
   model=read(path);assert model.view()['phase']=='paused';paused=model.view()['label']
   shot('timer-popup');close_menu()
  elif stage==4:
   assert read(path).view()['label']==paused
   pane=open_menu();assert pane.primary.get_label()=='Resume';pane.primary.clicked();delay=1900
  elif stage==5:
   assert read(path).finished and read(path).view()['label']=='00:00'
   menu.timer.choice.set_active_id('stopwatch')
  elif stage==6:
   assert read(path).mode=='stopwatch';menu.timer.primary.clicked();delay=1100
  elif stage==7:
   assert read(path).view()['seconds']>=1
   bar=panel['TopBar']();bar.refresh()
   assert all(entry['timer'].get_label()==read(path).view()['label'] for entry in bar.bars)
   pane=open_menu();pane.primary.clicked()
  elif stage==8:
   assert read(path).view()['phase']=='paused';menu.timer.reset.clicked()
  elif stage==9:
   assert read(path).view()['label']=='00:00'
   close_menu()
  else:
   index=stage-10
   monitors=[Gdk.Display.get_default().get_monitor(i) for i in range(Gdk.Display.get_default().get_n_monitors())]
   combinations=[(monitor,edge) for monitor in monitors for edge in ('top','bottom','left','right')]
   if index>=len(combinations):
    bar.config['panel']['show_timer']='false';bar.refresh();assert all(not entry['timer'].get_visible() for entry in bar.bars)
    loop.quit();return False
   target,edge=combinations[index];rect=target.get_geometry();bar.config['panel']['position']=edge;bar.rebuild()
   assert all(entry['timer'].get_child().get_angle()==(90 if edge in ('left','right') else 0) for entry in bar.bars)
   # Exercise the real panel click's payload, then create that anchored popup.
   sent=[];original=scope['send'];scope['send']=lambda name,**values:sent.append((name,values))
   try:
    entry=next(row for row in bar.bars if row['monitor']==target);entry['timer'].clicked()
   finally:scope['send']=original
   assert sent[0][0]=='panel-menu' and sent[0][1]['page']=='Timer'
   values=sent[0][1];pane=open_menu(edge,rect,(values['x'],values['y']))
   def geometry():
    try:
     assert menu.window.get_allocated_width()<=280 and menu.window.get_allocated_height()<240
     assert panel['Layer'].get_margin(menu.window,panel['Layer'].Edge.LEFT)+menu.window.get_allocated_width()<=rect.width
     assert panel['Layer'].get_margin(menu.window,panel['Layer'].Edge.TOP)+menu.window.get_allocated_height()<=rect.height
     assert not pane.duration_box.get_visible(),'Stopwatch should hide countdown inputs'
     assert pane.watcher
    except BaseException as error:errors.append(error);loop.quit()
    return False
   GLib.timeout_add(100,geometry)
  GLib.timeout_add(delay,lambda:step(stage+1));return False
 except BaseException as error:errors.append(error);loop.quit();return False
GLib.timeout_add(100,step)
try:loop.run()
finally:
 close_menu()
 if bar:
  for entry in bar.bars:entry['window'].destroy()
if errors:raise AssertionError('Panel timer regression') from errors[0]
print('PASS: digit-only shared panel readouts, compact timer/stopwatch controls, real helper IPC, pause/resume/reset/expiry, panel reload survival, popup close/reopen and all output/edge placements.')
