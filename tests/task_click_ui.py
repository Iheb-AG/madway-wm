"""Actual GTK frame-clock press feedback, retargeting and stable task geometry."""
from pathlib import Path
import runpy
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
api=runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway_widgets.py'))
window=Gtk.Window();button=Gtk.Button();image=Gtk.Image.new_from_icon_name('utilities-terminal',Gtk.IconSize.MENU);image.set_pixel_size(16);button.set_image(image);window.add(button);window.show_all();errors=[];width=[]
def check(stage=0):
 try:
  if stage==0:
   width.append(button.get_allocated_width());api['task_click'](button)
  elif stage==1:
   assert 13<=image.get_pixel_size()<16
   assert button.get_allocated_width()==width[0]
   current=image.get_pixel_size();api['task_click'](button);assert image.get_pixel_size()==current
  else:
   assert image.get_pixel_size()==16 and abs(image.get_opacity()-1)<.001
   assert button.get_allocated_width()==width[0]
   api['task_click'](button,False);assert not button.click_tick
   window.destroy();Gtk.main_quit();return False
  GLib.timeout_add(65 if stage==0 else 250,lambda:check(stage+1))
 except BaseException as error:errors.append(error);window.destroy();Gtk.main_quit()
 return False
GLib.timeout_add(100,check);Gtk.main()
if errors:raise errors[0]
print('PASS: panel task press/rebound follows frame cadence, retargets smoothly, restores original icon appearance and keeps button geometry fixed.')
