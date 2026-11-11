"""Settings capture tests with fake PulseAudio/PCM and a synthetic camera only."""
import importlib.util
import json
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
capture=importlib.util.module_from_spec(spec);sys.modules[spec.name]=capture;spec.loader.exec_module(capture)
api=runpy.run_path(str(repo/'scripts/madway-shell'));calls=[];errors=[];original_path=os.environ['PATH']
state=dict(default='internal',sources=[dict(index=1,name='internal',description='Laptop microphone',mute=False,state='RUNNING',volume={'mono':{'value_percent':'65%'}},ports=[dict(name='internal-mic',description='Internal microphone')],active_port='internal-mic'),dict(index=2,name='usb',description='USB mic',mute=False,volume={})],streams=[dict(index=7,source=1,properties={'application.name':'Brave meeting'})],cards=[dict(index=3,name='Laptop sound',active_profile='duplex',profiles={'duplex':dict(description='Analog stereo duplex',available='yes')})])
capture.microphone_snapshot=lambda:state
original_control=capture.capture_control
capture.capture_control=lambda operation,identity,value=None:original_control(operation,identity,value,run=lambda argv:calls.append(argv))
capture.camera_snapshot=lambda:[dict(path='/dev/mock-camera',name='Synthetic camera',usable=True,error='')]
def pipeline(self,path):return self.Gst.parse_launch('videotestsrc is-live=true pattern=ball ! videoconvert ! video/x-raw,format=RGB,width=320,height=240 ! appsink name=preview emit-signals=true max-buffers=1 drop=true sync=false')
capture.CameraPane.make_pipeline=pipeline

def descendants(widget):
    yield widget
    if isinstance(widget,Gtk.Container):
        for child in widget.get_children():yield from descendants(child)

with tempfile.TemporaryDirectory(prefix='madway-capture-ui-') as tmp:
    root=Path(tmp);player=root/'parec'
    player.write_text('#!'+sys.executable+'\nimport math,struct,sys,time\ndata=b"".join(struct.pack("h",int(14000*math.sin(i*.2))) for i in range(512))\nwhile True:\n try:sys.stdout.buffer.write(data);sys.stdout.buffer.flush();time.sleep(.032)\n except BrokenPipeError:break\n')
    player.chmod(0o700);os.environ['PATH']=str(root)+':'+original_path
    def check(stage=0):
        window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='madway — Settings');stack=window.settings_browser.stack
        mic=next(w for w in descendants(window) if isinstance(w,capture.MicrophonePane));cam=next(w for w in descendants(window) if isinstance(w,capture.CameraPane))
        try:
            if stage==0:
                assert not calls and not mic.testing and not cam.testing,'Opening settings changed capture state'
                stack.set_visible_child_name('Microphone');window.resize(640,480)
                assert len(mic.sources)==2 and mic.choice.get_active_id()=='1'
                mic.control('default');assert mic.busy
            elif stage==1:
                assert calls[-1]==['pactl','set-default-source','1']
                mic.toggle_test();assert mic.testing
            elif stage==2:
                assert mic.meter.get_value()>.1,'Microphone meter failed'
                artifacts=os.environ.get('MADWAY_TEST_ARTIFACTS')
                if artifacts:
                    import subprocess
                    subprocess.run(['grim','-o','HEADLESS-1',str(Path(artifacts)/'settings-microphone.png')],check=True)
                stack.set_visible_child_name('Camera');assert not mic.testing and mic.process is None
                cam.toggle_test();assert cam.testing
            elif stage==3:
                assert cam.image.get_pixbuf() is not None,'Synthetic camera preview failed'
                artifacts=os.environ.get('MADWAY_TEST_ARTIFACTS')
                if artifacts:
                    import subprocess
                    subprocess.run(['grim','-o','HEADLESS-1',str(Path(artifacts)/'settings-camera.png')],check=True)
                stack.set_visible_child_name('Windows');assert not cam.testing and cam.pipeline is None
                # A privacy transition also stops a still-visible capture test.
                stack.set_visible_child_name('Microphone');mic.toggle_test();assert mic.testing
                directory=api['runtime_directory']();path=directory/'desktop.json';previous=path.read_text();private=json.loads(previous);private['locked']=True;path.write_text(json.dumps(private))
                try:mic.privacy();assert not mic.testing
                finally:path.write_text(previous)
                window.destroy();return False
            GLib.timeout_add(450,lambda:check(stage+1));return False
        except BaseException as error:errors.append(error);window.destroy();return False
    try:GLib.timeout_add(600,check);api['settings_window']('Microphone')
    finally:os.environ['PATH']=original_path
if errors:raise AssertionError('Capture UI regression') from errors[0]
print('PASS: meeting input controls, live PCM meter, synthetic camera preview, compact capture pages and automatic stop on navigation/locking, without using host capture hardware.')
