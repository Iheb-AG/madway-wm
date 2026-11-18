"""Deterministic clocks: pause/resume, suspend, reload, validation and one-shot expiry."""
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
api=runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway_timer.py'))
now=[1000.];model=api['TimerState'](seconds=5,now=lambda:now[0])
assert model.view()['label']=='00:05'
model.control('start');now[0]+=.25;assert model.view()['label']=='00:05'
now[0]+=1;model.control('pause');assert model.view()['phase']=='paused'
remaining=model.remaining;now[0]+=600;assert model.remaining==remaining and model.view()['label']=='00:04'
model.control('start');now[0]+=1
restored=api['TimerState'].restore(json.loads(json.dumps(model.snapshot())),lambda:now[0])
assert restored.view()==model.view()
now[0]+=300 # Laptop suspend advances BOOTTIME without GTK callbacks.
assert restored.poll() and not restored.poll() and restored.view()['phase']=='finished'
restored.control('reset',seconds=10);assert restored.view()['label']=='00:10'
restored.control('start');restored.control('start');assert restored.deadline==now[0]+10
restored.control('select','stopwatch');restored.control('start');now[0]+=2.2
assert restored.view()['label']=='00:02'
restored.control('pause');now[0]+=5;assert restored.view()['label']=='00:02'
restored.control('start');now[0]+=1;assert restored.view()['label']=='00:03'
restored.control('reset');assert restored.view()['label']=='00:00' and restored.anchor is None
now[0]+=3
assert restored.poll(),'Hidden countdown must still finish while stopwatch is selected'
for operation,mode,seconds in [('bad',None,None),('start','bad',None),('start','timer',0),('start','timer',True),('start','timer',1.5),('reset','timer',360000)]:
 before=restored.snapshot()
 try:restored.control(operation,mode,seconds)
 except ValueError:pass
 else:raise AssertionError((operation,mode,seconds))
 assert before==restored.snapshot()
assert api['format_time'](3661)=='1:01:01'
with tempfile.TemporaryDirectory(prefix='madway-timer-') as tmp:
 path=Path(tmp)/'timer.json';path.write_text('{broken')
 assert api['read_state'](path).view()['label']=='05:00'
 notifications=[];timers={};counter=[0]
 def timeout(interval,callback):counter[0]+=1;timers[counter[0]]=callback;return counter[0]
 import configparser
 config=configparser.ConfigParser();config.read_dict({'timer':{'mode':'timer','duration':'2'}})
 desktop=SimpleNamespace(config=config,directory=Path(tmp),GLib=SimpleNamespace(timeout_add=timeout,source_remove=lambda tag:timers.pop(tag,None)),notify=lambda *args,**kwargs:notifications.append(args))
 controller=api['TimerController'](desktop);controller.model.now=lambda:now[0]
 controller.control(dict(operation='start'));assert controller.watch and path.stat().st_mode&0o077==0
 now[0]+=3;assert controller.tick() is False and len(notifications)==1
 controller.control(dict(operation='select',mode='stopwatch'));assert len(notifications)==1
 controller.control(dict(operation='reset',mode='timer',seconds=1));controller.control(dict(operation='start'))
 now[0]+=2;controller.control(dict(operation='select',mode='stopwatch'));assert len(notifications)==2
 controller.close();assert not path.exists()
print('PASS: timer/stopwatch pause/resume/reset, fractional rounding, sleep catch-up, shared state reload, independent modes, invalid input rejection and single completion notification.')
