"""Settings output selector/mute/route/test controls with fixture audio only."""
import copy
import importlib.util
import os
from pathlib import Path
import runpy
import sys
import tempfile
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
repo=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('madway_capture',repo/'scripts/madway_capture.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
state=dict(default='speakers',sinks=[dict(index=9,name='speakers',description='Laptop speakers',mute=False,
    ports=[dict(name='speaker',description='Speakers')],active_port='speaker'),
    dict(index=12,name='hdmi',description='External monitor HDMI')],streams=[dict(index=71,sink=9,mute=True,properties={'application.name':'Brave'})])
calls=[]
module.playback_snapshot=lambda:copy.deepcopy(state)
def control(operation,identity,value):
 calls.append((operation,identity,value))
 if operation=='mute':state['streams'][0]['mute']=value
module.playback_control=control
api=runpy.run_path(str(repo/'scripts/madway-shell'));errors=[]
def children(widget):
 yield widget
 if isinstance(widget,Gtk.Container):
  for child in widget.get_children():yield from children(child)
with tempfile.TemporaryDirectory(prefix='madway-playback-ui-') as tmp:
 fake=Path(tmp)/'pw-play';fake.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(10)\n');fake.chmod(0o700)
 os.environ['PATH']=tmp+':'+os.environ['PATH']
 def check(stage=0):
  window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings');browser=window.settings_browser
  pane=next(w for w in children(window) if isinstance(w,module.PlaybackPane))
  try:
   if stage==0:
    assert not calls and pane.choice.get_active_id()=='9'
    window.resize(640,480)
    next(w for w in children(pane.apps) if isinstance(w,Gtk.Button) and w.get_label()=='Unmute').clicked()
   elif stage==1:
    assert calls[-1]==('mute',71,False)
    pane.choice.set_active_id('12');pane.use.clicked()
   elif stage==2:
    assert calls[-1]==('default',12,None)
    route=next(w for w in children(pane.apps) if isinstance(w,Gtk.ComboBoxText));route.set_active_id('12')
   elif stage==3:
    assert calls[-1]==('route',71,'12')
    pane.choice.set_active_id('9');pane.test.clicked();assert pane.testing
    browser.stack.set_visible_child_name('Windows');assert not pane.testing and pane.process is None
    browser.stack.set_visible_child_name('Audio & brightness')
   else:
    folder=os.environ.get('MADWAY_TEST_ARTIFACTS')
    if folder:
     import subprocess
     Path(folder).mkdir(parents=True,exist_ok=True);subprocess.run(['grim','-o','HEADLESS-1',str(Path(folder)/'settings-audio.png')],check=True)
    assert window.get_allocated_width()<=650,window.get_allocated_width()
    window.destroy();return False
   GLib.timeout_add(400,lambda:check(stage+1));return False
  except BaseException as error:errors.append(error);window.destroy();return False
 GLib.timeout_add(700,check);api['settings_window']('Audio & brightness')
if errors:raise AssertionError('Playback settings regression') from errors[0]
print('PASS: output/port selection, explicit app unmute and rerouting, speaker-test process cleanup and compact audio geometry, without touching host audio.')
