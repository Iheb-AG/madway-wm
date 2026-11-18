"""Preset draft binding/customization and saved opening/maximize preferences."""
import configparser
import os
from pathlib import Path
import runpy
import subprocess
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
repo=Path(__file__).resolve().parent.parent;api=runpy.run_path(str(repo/'scripts/madway-shell'))
original=api['CONFIG'].read_text();errors=[];messages=[]
api['settings_window'].__globals__['action']=lambda name,**values:messages.append((name,values))
def descendants(widget):
 yield widget
 if isinstance(widget,Gtk.Container):
  for child in widget.get_children():yield from descendants(child)
def inspect():
 window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings')
 try:
  page=window.settings_browser.stack.get_child_by_name('Animations');grid=next(w for w in descendants(page) if isinstance(w,Gtk.Grid))
  def control(text):
   label=next(w for w in grid.get_children() if isinstance(w,Gtk.Label) and w.get_text()==text)
   return grid.get_child_at(1,grid.child_get_property(label,'top-attach'))
  names={'open_style':'Opening motion','open_ms':'Opening duration (ms)','open_curve':'Opening easing','open_scale':'Opening start size (%)','open_distance':'Opening travel (px)','open_fade':'Fade in opening windows',
         'maximize_style':'Maximize motion','maximize_ms':'Maximize duration (ms)','maximize_curve':'Maximize easing'}
  for preset_label,catalog in [('Opening preset',api['MOTION_PRESETS']['OPENING']),('Maximize preset',api['MOTION_PRESETS']['MAXIMIZE'])]:
   for identity,(_,values) in catalog.items():
    control(preset_label).set_active_id(identity)
    for key,value in values.items():
     widget=control(names[key]);actual=widget.get_active_id() if hasattr(widget,'get_active_id') else str(widget.get_value_as_int()) if hasattr(widget,'get_value_as_int') else str(widget.get_active()).lower()
     assert actual==value,(identity,key,actual,value)
    assert control(preset_label).get_active_id()==identity,'Preset selection turned into Custom'
  assert not control('Maximize duration (ms)').get_sensitive(),'Instant should disable unused timing'
  control('Opening motion').set_active_id('slide');control('Opening duration (ms)').set_value(500)
  control('Opening easing').set_active_id('linear');control('Opening travel (px)').set_value(42)
  control('Fade in opening windows').set_active(False)
  assert control('Opening preset').get_active_id()=='custom' and not control('Opening start size (%)').get_sensitive()
  control('Animate application opening').set_active(False);assert not control('Opening preset').get_sensitive()
  control('Animate application opening').set_active(True)
  control('Animate maximize / minimize').set_active(False);assert not control('Maximize preset').get_sensitive()
  assert control('Opening preset').get_sensitive(),'Opening must have its own enable switch'
  control('Animate maximize / minimize').set_active(True);control('Maximize preset').set_active_id('dissolve')
  control('Maximize duration (ms)').set_value(480);control('Maximize easing').set_active_id('linear')
  assert control('Maximize preset').get_active_id()=='custom'
  assert api['CONFIG'].read_text()==original,'Selecting presets saved drafts'
  next(w for w in descendants(window) if isinstance(w,Gtk.Button) and w.get_label()=='Apply').clicked()
  saved=configparser.ConfigParser(interpolation=None);saved.read(api['CONFIG'])
  assert saved.get('windows','open_style')=='slide' and saved.getint('windows','open_ms')==500 and saved.getint('windows','open_distance')==42
  assert not saved.getboolean('windows','open_fade') and saved.get('windows','open_preset')=='custom'
  assert saved.get('windows','maximize_style')=='dissolve' and saved.getint('windows','maximize_ms')==480 and saved.get('windows','maximize_curve')=='linear'
  assert saved.getint('windows','animation_ms')==360,'A maximize preset altered minimize duration'
  assert messages==[('apply',{})]
  folder=os.environ.get('MADWAY_TEST_ARTIFACTS')
  if folder:
   label=next(w for w in grid.get_children() if isinstance(w,Gtk.Label) and w.get_text()=='Animate application opening')
   page.get_vadjustment().set_value(max(0,label.get_allocation().y-22))
   def capture():
    try:
     Path(folder).mkdir(parents=True,exist_ok=True)
     subprocess.run(['grim','-o','HEADLESS-1',str(Path(folder)/'window-animations.png')],check=True)
    except BaseException as error:errors.append(error)
    window.destroy();return False
   GLib.timeout_add(180,capture);return False
 except BaseException as error:errors.append(error)
 window.destroy();return False
GLib.timeout_add(650,inspect)
try:api['settings_window']('Animations')
finally:api['CONFIG'].write_text(original)
if errors:raise AssertionError('Window motion settings regression') from errors[0]
print('PASS: all opening/maximize presets fill drafts, edits select Custom, irrelevant controls disable, independent enable switches, Apply persistence and retained minimize timing.')
