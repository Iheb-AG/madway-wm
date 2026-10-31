"""Power policy with a fake logind connection; never requests real system sleep."""
import configparser
import json
import os
from pathlib import Path
import pwd
import runpy
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import gi
gi.require_version('Gio','2.0')
from gi.repository import Gio,GLib

repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway_power.py'))
shell=runpy.run_path(str(repo/'scripts/madway-shell'))
for policy in ('suspend','auto','ignore','system'):
    for external in (False,True):
        assert api['lid_decision'](policy,False,external) is None
        assert api['lid_decision'](policy,True,external)==('suspend' if policy=='suspend' or policy=='auto' and not external else None)
config=configparser.ConfigParser(interpolation=None);config.read_dict(shell['DEFAULTS'])
assert shell['panel_label'](config)==pwd.getpwuid(os.getuid()).pw_name
config['panel']['label']='groxiv';assert shell['panel_label'](config)=='groxiv'
config['panel']['label']='   ';assert shell['panel_label'](config)==pwd.getpwuid(os.getuid()).pw_name

class FakeBus:
    def __init__(self):self.calls=[];self.is_active=True;self.inhibit_fails=False;self.suspend_fails=False
    def signal_subscribe(self,*args):self.calls.append(('subscribe',args[2]));return 1
    def signal_unsubscribe(self,*args):pass
    def call_sync(self,name,path,interface,method,parameters,*args):
        self.calls.append((method,parameters.unpack()))
        if method=='GetSessionByPID':return GLib.Variant('(o)',('/org/freedesktop/login1/session/test',))
        assert method=='Get';return GLib.Variant('(v)',(GLib.Variant('b',self.is_active),))
    def call_with_unix_fd_list_sync(self,name,path,interface,method,parameters,*args):
        assert method=='Inhibit';self.calls.append((method,parameters.unpack()))
        if self.inhibit_fails:raise GLib.Error('inhibitor denied')
        read,write=os.pipe();fds=Gio.UnixFDList.new();index=fds.append(write);os.close(read);os.close(write)
        return GLib.Variant('(h)',(index,)),fds
    def call(self,name,path,interface,method,parameters,*args):
        assert method in ('Suspend','SetLockedHint');self.calls.append((method,parameters.unpack()))
        args[-1](self,None)
    def call_finish(self,result):
        if self.suspend_fails:raise GLib.Error('fake sleep rejected')
        return GLib.Variant('()',())

with tempfile.TemporaryDirectory(prefix='madway-power-unit-') as tmp,patch.dict(os.environ,MADWAY_NATIVE='1'):
    directory=Path(tmp);bus=FakeBus();commands=[];terminated=[];notifications=[];polls=[]
    config=configparser.ConfigParser(interpolation=None);config.read_dict(shell['DEFAULTS']);config['power']['lid_action']='auto'
    desktop=SimpleNamespace(Gio=Gio,GLib=GLib,system_bus=bus,parent=4242,directory=directory,config=config,
        compositor=commands.append,terminate=terminated.append,notify=lambda *args,**kwargs:notifications.append((args,kwargs)),poll_power=lambda:polls.append(True))
    desktop.locker=SimpleNamespace(ensure=lambda callback=None,**kwargs:callback(True) if callback else None)
    power=api['PowerManager'](desktop)
    state=dict(native=True,lid_present=True,lid_closed=False)
    def write():
        (directory/'desktop.json').write_text(json.dumps(state))
    outputs=[dict(name='eDP-1',enabled=True),dict(name='HDMI-A-1',enabled=True)]
    def output_write():(directory/'outputs.json').write_text(json.dumps(dict(outputs=outputs)))
    write();output_write();power.sync()
    assert power.lid_fd>=0 and commands==['lid-managed 1']
    owned=power.lid_fd;os.fstat(owned)
    state['lid_closed']=True;write();power.sync()
    assert not any(row[0]=='Suspend' for row in bus.calls),'Docked auto policy suspended'
    config['power']['lid_action']='suspend';power.sync()
    assert [row for row in bus.calls if row[0]=='Suspend']==[('Suspend',(True,))]
    power.sync();power.request_sleep()
    assert len([row for row in bus.calls if row[0]=='Suspend'])==1,'Repeated close events requested multiple sleeps'
    power.prepare_sleep(None,None,None,None,None,GLib.Variant('(b)',(True,)))
    assert commands[-1]=='prepare-sleep' and power.sleeping
    power.prepare_sleep(None,None,None,None,None,GLib.Variant('(b)',(False,)))
    assert 'resume' in commands and polls and not power.sleeping
    state['lid_closed']=False;write();power.sync()
    bus.is_active=False;power.sync()
    assert power.lid_fd==-1 and commands[-1]=='lid-managed 0'
    try:os.fstat(owned)
    except OSError:pass
    else:raise AssertionError('Lid inhibitor FD leaked')
    try:power.request_sleep()
    except RuntimeError:pass
    else:raise AssertionError('Inactive session requested sleep')
    bus.is_active=True;config['power']['lid_action']='system';power.sync();assert power.lid_fd==-1
    config['power']['lid_action']='ignore';power.sync();assert power.lid_owned
    state['lid_closed']=True;write();power.sync()
    assert len([row for row in bus.calls if row[0]=='Suspend'])==1,'Ignore policy requested sleep'
    state['native']=False;write();power.sync();assert power.lid_fd==-1
    commands.clear();power.prepare_sleep(None,None,None,None,None,GLib.Variant('(b)',(True,)))
    assert not commands,'Nested session responded to host sleep'
    try:power.request_sleep()
    except RuntimeError:pass
    else:raise AssertionError('Nested session requested host sleep')
    state.update(native=True,lid_closed=False);write();bus.inhibit_fails=True
    power.sync();assert power.lid_fd==-1
    attempts=len([row for row in bus.calls if row[0]=='Inhibit'])
    power.sync();assert len([row for row in bus.calls if row[0]=='Inhibit'])==attempts,'Inhibitor failure was not rate limited'
    bus.inhibit_fails=False;power.inhibit_retry_at=0;power.sync();assert power.lid_fd>=0
    bus.suspend_fails=True;power.request_sleep()
    assert notifications and not power.sleep_requested and power.request_timer==0,'Failed sleep prevented a later request'
    power.close();assert power.lid_fd==-1
    # Readiness is asynchronous: neither suspend nor inhibitor release may race it.
    bus.suspend_fails=False;callbacks=[]
    def pending_lock(callback=None,**kwargs):
        callbacks.append((callback,kwargs))
    desktop.locker=SimpleNamespace(ensure=pending_lock)
    power=api['PowerManager'](desktop);power.sync()
    assert power.delay_fd>=0
    count=lambda:len([row for row in bus.calls if row[0]=='Suspend'])
    previous=count();power.request_sleep()
    assert count()==previous and power.sleep_requested
    callback,options=callbacks.pop();callback(True)
    assert count()==previous+1
    delay=power.delay_fd
    power.prepare_sleep(None,None,None,None,None,GLib.Variant('(b)',(True,)))
    assert power.delay_fd==delay,'Delay inhibitor released before lock presentation'
    callback,options=callbacks.pop();assert options['emergency'];callback(True)
    assert power.delay_fd==-1 and commands[-1]=='prepare-sleep'
    power.prepare_sleep(None,None,None,None,None,GLib.Variant('(b)',(False,)))
    assert power.delay_fd>=0,'Sleep delay was not reacquired after resume'
    previous=count();power.request_sleep();callback,_=callbacks.pop();callback(False)
    assert count()==previous and not power.sleep_requested,'Failed locking allowed suspend'
    power.session_lock();assert callbacks.pop()[1]['emergency']
    config['locking']['before_sleep']='false';power.sync();assert power.delay_fd==-1
    power.request_sleep();assert count()==previous+1
    power.close()
print('PASS: username/custom label; lid policies; native/active guards; duplicate sleep suppression; prepare/resume; inhibitor ownership, fallback and cleanup. All sleep calls used fake logind.')
print('PASS: asynchronous lock-before-sleep, presentation-gated delay release, resume rearm, failed-lock cancellation and logind lock signal. No real suspend.')
