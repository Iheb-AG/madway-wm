"""Native XP/Vista chrome plus real shell/settings captures in a private session."""
import os
from pathlib import Path
import runpy
import subprocess
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
repo=Path(__file__).resolve().parent.parent;api=runpy.run_path(str(repo/'scripts/madway-shell'));errors=[]
config=api['settings']();theme=config.get('appearance','theme')
assert theme in ('windows-xp','windows-vista')
panel=runpy.run_path(str(repo/'scripts/madway-panel'))
for kind in ('windows-xp','windows-vista','argent','argent-dark'):
 config['appearance']['theme']=kind
 provider=Gtk.CssProvider();issues=[];provider.connect('parsing-error',lambda p,s,e:issues.append(str(e)))
 provider.load_from_data(api['theme_style'](panel['CSS'].decode(),config).encode());assert not issues,(kind,issues)
def inspect():
 try:
  window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings')
  browser=window.settings_browser
  assert {'windows-xp','windows-vista'}<=set(api['themes']().sections())
  assert len([row for row in browser.list.get_children() if row.page and row.get_child_visible()])==len(api['SETTINGS_PAGES'])
  target=repo/'build/latest-review';target.mkdir(parents=True,exist_ok=True)
  subprocess.run(['grim','-o','HEADLESS-1',str(target/(theme+'.png'))],check=True)
 except BaseException as error:errors.append(error)
 window.destroy();return False
GLib.timeout_add(1200,inspect);api['settings_window']('Appearance')
if errors:raise errors[0]
print('PASS: '+theme+' native chrome, panel/Waybar styles, all-category settings navigation and actual desktop capture.')
