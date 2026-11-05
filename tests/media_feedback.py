"""Slow hardware cannot block feedback; commands stay ordered and UI stays on main."""
import configparser
from pathlib import Path
import queue
import runpy
import threading
import time
from types import SimpleNamespace

repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway_media.py'))
shell=runpy.run_path(str(repo/'scripts/madway-shell'))
callbacks=queue.Queue();feedback=[];hardware=dict(volume=50,brightness=40,mute=False);threads=[]
gate=threading.Event();gate.set();entered=threading.Event();main=threading.get_ident()
def idle(callback,*args):callbacks.put((callback,args));return 1
def pump(check,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:callback,args=callbacks.get(timeout=.01);callback(*args)
        except queue.Empty:pass
        if check():return
    raise AssertionError('Media worker did not settle')
def run(args):
    threads.append(threading.get_ident());entered.set();assert gate.wait(2)
    if args[1]=='set-mute':hardware['mute']=not hardware['mute']
    else:
        value=args[-1]
        hardware['volume']=hardware['volume']+int(value[:-2]) if value.endswith('%+') else hardware['volume']-int(value[:-2]) if value.endswith('%-') else int(value.rstrip('%'))
def volume():threads.append(threading.get_ident());return hardware['volume'],hardware['mute']
def brightness():threads.append(threading.get_ident());return hardware['brightness']
def set_brightness(value):threads.append(threading.get_ident());hardware['brightness']=max(1,min(100,value))
def notify(*args,**kwargs):
    assert threading.get_ident()==main,'Hardware thread touched the UI'
    feedback.append((args,kwargs))
config=configparser.ConfigParser(interpolation=None);config.read_dict(shell['DEFAULTS'])
desktop=SimpleNamespace(GLib=SimpleNamespace(idle_add=idle),config=config,notify=notify)
controller=api['MediaController'](desktop,dict(run=run,volume=volume,brightness=brightness,set_brightness=set_brightness))
try:
    pump(lambda:len(controller.values)==2)
    gate.clear();start=time.monotonic();controller.request('volume-up',{})
    assert time.monotonic()-start<.03 and feedback[-1][1]['value']==55 and hardware['volume']==50
    assert entered.wait(1)
    controller.request('volume-up',{});assert feedback[-1][1]['value']==60 and hardware['volume']==50
    gate.set();pump(lambda:controller.values.get('volume')==(60,False) and hardware['volume']==60 and len(feedback)>=3)
    assert [kwargs['value'] for args,kwargs in feedback]==[55,60,60],'Stale confirmation rolled the indicator backward'
    controller.request('volume-mute',{});assert feedback[-1][0][1]=='Volume muted'
    pump(lambda:hardware['mute'] and controller.values['volume'][1])
    controller.request('brightness-up',{});assert feedback[-1][1]['value']==45
    pump(lambda:hardware['brightness']==45)
    assert all(identity!=main for identity in threads)
    controller.values.pop('volume');gate.clear();controller.request('volume-up',{})
    assert feedback[-1][1]['pending']
    before=len(feedback);controller.close();gate.set();controller.worker.join(timeout=2)
    while not callbacks.empty():callback,args=callbacks.get_nowait();callback(*args)
    assert len(feedback)==before and not controller.worker.is_alive()
finally:gate.set();controller.close();controller.worker.join(timeout=2)
print('PASS: immediate optimistic feedback with blocked hardware, serial commands, stale-result rejection, mute/brightness, main-thread-only UI and shutdown cancellation.')
