"""Ghost completion stays separate from input; test in the private test session."""
import os
from pathlib import Path
import runpy
import subprocess
from types import SimpleNamespace
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib

repo=Path(__file__).resolve().parent.parent
panel=runpy.run_path(str(repo/'scripts/madway-panel'))
source=runpy.run_path(str(repo/'scripts/madway_spotlight.py'))
sent=[];errors=[]
launcher=source['Spotlight'](panel['api'],panel['layer_window'],lambda name,**values:sent.append((name,values)))

def key(name):return SimpleNamespace(keyval=Gdk.keyval_from_name(name))
def check(stage=0):
    try:
        if stage==0:
            launcher.entry.set_text('Pin');launcher.entry.set_position(-1)
            assert launcher.completion=='nedFixture' and launcher.entry.get_text()=='Pin'
        elif stage==1:
            if os.environ.get('MADWAY_TEST_ARTIFACTS'):
                target=Path(os.environ['MADWAY_TEST_ARTIFACTS']);target.mkdir(parents=True,exist_ok=True)
                subprocess.run(['grim','-o','HEADLESS-1',str(target/'spotlight-completion.png')],check=True,timeout=5)
            assert not sent
            launcher.entry.set_position(1)
            assert launcher.draw_completion(launcher.entry,object()) is False,'Completion drew over an edited cursor'
            launcher.entry.set_position(-1);launcher.preedit_changed(launcher.entry,'i')
            assert launcher.draw_completion(launcher.entry,object()) is False,'Completion interfered with IME composition'
            launcher.preedit_changed(launcher.entry,'')
            assert launcher.key(None,key('Tab')) and launcher.entry.get_text()=='PinnedFixture'
            launcher.entry.set_text('Fixture');launcher.entry.set_position(-1)
            assert launcher.rows and not launcher.completion,'Substring search must not invent a prefix completion'
            launcher.entry.set_text('a nonexistent application qqqqq')
            launcher.key(None,key('Return'));assert not sent and not launcher.closed
            launcher.entry.set_text('Pin');launcher.entry.set_position(-1)
            launcher.key(None,key('Right'));assert launcher.entry.get_text()=='PinnedFixture'
            launcher.key(None,key('Return'))
            assert sent==[('launch-app',{'id':'org.madway.PinnedFixture.desktop'})] and launcher.closed
            return False
        GLib.timeout_add(150,lambda:check(stage+1))
    except BaseException as error:errors.append(error);launcher.window.destroy()
    return False

GLib.timeout_add(250,check);Gtk.main()
if errors:raise AssertionError('Spotlight completion regression') from errors[0]
print('PASS: faint completion is separate from typed text, respects cursor/IME, supports Tab/Right acceptance, substring/no-match search and Enter launch.',flush=True)
