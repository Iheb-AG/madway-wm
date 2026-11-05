"""Actual GLES shader endpoint rendering and full-screen preview lifecycle."""
import ctypes as C
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import gi
gi.require_version('Gtk','3.0');gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gtk,GdkPixbuf,GLib
repo=Path(__file__).resolve().parent.parent;source=runpy.run_path(str(repo/'scripts/madway_gl.py'))
effects=runpy.run_path(str(repo/'scripts/madway_exit.py'))['SHADERS']
errors=[];window=Gtk.Window();area=Gtk.GLArea();area.set_use_es(True);area.set_required_version(2,0);area.set_size_request(96,64);window.add(area)
programs=[];results={}

def render(area,context):
    if len(results)==len(effects):return True
    try:
        image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,True,8,96,64);image.fill(0x804020ff)
        for effect in effects:
            renderer=source['ShaderRenderer']((repo/'share/madway/shaders/session.vert').read_text(),(repo/'share/madway/shaders'/(effect+'.frag')).read_text(),image)
            programs.append(renderer);frames=[]
            for progress in (0.,.5,1.):
                renderer.draw(progress,96,64);data=(C.c_ubyte*(96*64*4))()
                read=renderer.lib.glReadPixels;read.argtypes=[C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p]
                read(0,0,96,64,0x1908,0x1401,data);frames.append(bytes(data))
            assert max(abs(frames[0][i]-value) for i,value in enumerate((128,64,32,255)))<=2,(effect,frames[0][:4])
            assert max(frames[2][i] for i in range(0,len(frames[2]),4))<10,(effect,frames[2][:4])
            assert len(set(frames))==3,effect
            renderer.close();results[effect]=True
        print('PASS: all nine OpenGL programs compile/link and preserve the original frame at start, produce a distinct midpoint and settle to dark.',flush=True)
    except BaseException as error:errors.append(error)
    GLib.idle_add(lambda:(window.destroy(),Gtk.main_quit(),False)[2]);return True
area.connect('render',render);window.show_all()
def check_error():
    if area.get_error():errors.append(RuntimeError(str(area.get_error())));window.destroy();Gtk.main_quit()
    return False
GLib.timeout_add(200,check_error);Gtk.main()
if errors:raise AssertionError('GL shader regression') from errors[0]
assert len(results)==len(effects)
with tempfile.TemporaryDirectory(prefix='madway-shader-preview-') as tmp:
    for effect in effects:
        path=Path(tmp)/(effect+'.log')
        with path.open('w') as log:
            process=subprocess.Popen([sys.executable,str(repo/'scripts/madway_exit.py'),'--preview','--mode','shader','--shader',effect,'--duration','400'],stdout=log,stderr=log)
            deadline=time.monotonic()+5
            while 'session shader ready' not in path.read_text():
                assert process.poll() is None,path.read_text()
                assert time.monotonic()<deadline,path.read_text();time.sleep(.02)
            time.sleep(.1)
            folder=os.environ.get('MADWAY_TEST_ARTIFACTS')
            if folder:
                Path(folder).mkdir(parents=True,exist_ok=True);subprocess.run(['grim','-o','HEADLESS-1',str(Path(folder)/('exit-'+effect+'.png'))],check=True)
            assert process.wait(timeout=5)==0,path.read_text()
    for effect in ('vortex','aurora'):
        subprocess.run([sys.executable,str(repo/'scripts/madway_exit.py'),'--preview','--opening','--mode','shader','--shader',effect,'--duration','300'],check=True,timeout=6)
    with (Path(tmp)/'fallback.log').open('w+') as log:
        process=subprocess.run([sys.executable,str(repo/'scripts/madway_exit.py'),'--preview','--mode','shader','--duration','200'],env={**os.environ,'GDK_GL':'disable'},stdout=log,stderr=log,timeout=7)
        log.seek(0);text=log.read();assert process.returncode==0 and 'using fade' in text,text
print('PASS: all shader previews return to the desktop without a session action; unavailable GL falls back to a completed software fade.',flush=True)
