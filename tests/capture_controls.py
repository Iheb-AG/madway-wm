"""Capture discovery/routing fixtures. Never contact the host audio or camera."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
repo=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('madway_capture',repo/'scripts/madway_capture.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
calls=[]
def run(argv):
    calls.append(argv)
    if argv[-1]=='info':return json.dumps(dict(default_source_name='laptop-mic'))
    if argv[-1]=='sources':return json.dumps([
        dict(index=1,name='laptop-mic',description='Laptop microphone',monitor_of_sink=None),
        dict(index=2,name='speakers.monitor',monitor_of_sink=0),
        dict(index=3,name='usb-mic',monitor_of_sink=4294967295)])
    if argv[-1]=='source-outputs':return json.dumps([dict(index=7,source=1,properties={'application.name':'Brave'})])
    if argv[-1]=='cards':return json.dumps([dict(index=4,active_profile='output:stereo',profiles={'duplex':dict(description='Duplex',available='yes')})])
    return ''
state=module.microphone_snapshot(run)
assert [row['index'] for row in state['sources']]==[1,3]
assert state['default']=='laptop-mic' and state['streams'][0]['index']==7
def output_run(argv):
    calls.append(argv)
    if argv[-1]=='info':return json.dumps(dict(default_sink_name='speakers'))
    if argv[-1]=='sinks':return json.dumps([dict(index=9,name='speakers'),dict(index=10,name='madway_exit_test')])
    if argv[-1]=='sink-inputs':return json.dumps([dict(index=71,sink=9,mute=True,properties={'application.name':'Brave'})])
    return ''
outputs=module.playback_snapshot(output_run)
assert [row['name'] for row in outputs['sinks']]==['speakers'] and outputs['streams'][0]['mute']
module.playback_control('default',9,run=output_run)
assert calls[-1]==['pactl','move-sink-input','71','9']
module.playback_control('mute',71,False,output_run);assert calls[-1]==['pactl','set-sink-input-mute','71','0']
module.playback_control('route',71,12,output_run);assert calls[-1]==['pactl','move-sink-input','71','12']
module.playback_control('port',9,'analog-output-speaker',output_run);assert calls[-1]==['pactl','set-sink-port','9','analog-output-speaker']
for operation,value,expected in [
    ('default',None,['set-default-source','1']),('mute',True,['set-source-mute','1','1']),
    ('volume',180,['set-source-volume','1','100%']),('port','internal-mic',['set-source-port','1','internal-mic']),
    ('profile','duplex',['set-card-profile','1','duplex']),('route',3,['move-source-output','1','3'])]:
    module.capture_control(operation,1,value,run);assert calls[-1]==['pactl',*expected]
for operation,identity,value in [('route',1,-1),('volume','1;touch /tmp/no',10),('port',1,'bad\nport'),('default',-1,None),('profile',1,None),('unknown',1,None)]:
    count=len(calls)
    try:module.capture_control(operation,identity,value,run)
    except (ValueError,TypeError):pass
    else:raise AssertionError((operation,identity,value))
    assert len(calls)==count
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);sysfs=root/'sys';dev=root/'dev';sysfs.mkdir();dev.mkdir()
    for name in ['video0','video1']:
        (sysfs/name).mkdir();(sysfs/name/'name').write_text('Fixture camera');(dev/name).touch()
    original=module.fcntl.ioctl
    def query(fd,request,data,mutate):
        path=Path('/proc/self/fd/'+str(fd)).resolve()
        struct.pack_into('II',data,84,0x80000000,1 if path.name=='video0' else 0x800000)
    module.fcntl.ioctl=query
    try:
        cameras=module.camera_snapshot(sysfs,dev)
        assert len(cameras)==1 and cameras[0]['usable'] and cameras[0]['path'].endswith('video0')
    finally:module.fcntl.ioctl=original
print('PASS: microphone discovery excludes playback monitors, routes active meetings, changes devices/ports/profiles safely, and camera discovery excludes metadata nodes.')
