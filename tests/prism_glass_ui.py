"""Real glass client alpha, opaque labels, all style providers and live captures."""
import os
from pathlib import Path
import runpy
import subprocess
import cairo
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
repo=Path(__file__).resolve().parent.parent;api=runpy.run_path(str(repo/'scripts/madway-shell'))
errors=[];config=api['settings']();config['appearance']['theme']='prism-glass'
# A local test background makes alpha visible in the capture without distributing
# someone else's wallpaper or changing the real user's desktop.
wallpaper=api['CONFIG'].parent/'glass-test.png'
surface=cairo.ImageSurface(cairo.FORMAT_RGB24,1280,720);cr=cairo.Context(surface)
paint=cairo.LinearGradient(0,0,1280,720)
for offset,color in [(0,(.05,.28,.42)),(.5,(.15,.45,.47)),(1,(.52,.24,.13))]:paint.add_color_stop_rgb(offset,*color)
cr.set_source(paint);cr.paint();cr.set_line_width(100)
for y in (110,360,610):
 cr.set_source_rgba(.62,.76,.86,.25);cr.move_to(-100,y);cr.curve_to(350,y-240,700,y+260,1400,y-80);cr.stroke()
surface.write_to_png(str(wallpaper))
config['wallpaper'].update(type='image',path=str(wallpaper),mode='fill')
api['write_settings'](config);api['action']('apply')
panel=runpy.run_path(str(repo/'scripts/madway-panel'))
styles=[api['theme_style'](panel['CSS'].decode(),config),api['theme_style']((api['SHARE']/'dock.css').read_text(),config)]
styles += [api['overlay_style'](name,config) for name in ('wofi.css','audio.css','utilities.css','switcher.css','osd.css')]
for style in styles:
 provider=Gtk.CssProvider();issues=[];provider.connect('parsing-error',lambda p,s,e:issues.append(str(e)))
 provider.load_from_data(style.encode());assert not issues,issues

def inspect():
 window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings')
 try:
  browser=window.settings_browser
  assert window.get_visual().get_depth()==32
  bg=window.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
  assert .8<bg.alpha<1,bg.alpha
  text=browser.heading.get_style_context().get_color(Gtk.StateFlags.NORMAL)
  assert text.alpha==1 and min(text.red,text.green,text.blue)>.8
  assert browser.heading.get_opacity()==1
  # Paint the actual client over two backdrops. Backgrounds must respond to
  # the backdrop, rather than lowering the whole window/text opacity.
  values=[]
  for shade in (0,1):
   surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,window.get_allocated_width(),window.get_allocated_height())
   cr=cairo.Context(surface);cr.set_source_rgb(shade,shade,shade);cr.paint();window.draw(cr);surface.flush()
   data=surface.get_data();stride=surface.get_stride();offset=10*stride+10*4
   values.append(tuple(data[offset:offset+3]))
  assert values[0]!=values[1],values
  target=repo/'build/reference-settings-review';target.mkdir(parents=True,exist_ok=True)
  subprocess.run(['grim','-o','HEADLESS-1',str(target/'prism-glass.png')],check=True)
 except BaseException as error:errors.append(error)
 window.destroy();return False
GLib.timeout_add(2000,inspect);api['settings_window']('Appearance')
if errors:raise errors[0]
print('PASS: Prism styles parse, true RGBA client transparency reacts to backdrop, labels retain full opacity, native glass chrome and real desktop capture.')
