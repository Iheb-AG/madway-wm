"""Exit sequencing with fake processes, clocks and power actions; no GTK or logind."""
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway-shell'))
module=runpy.run_path(str(repo/'scripts/madway_exit.py'))
class Clock:
    def __init__(self):self.sources={};self.serial=0
    def timeout_add(self,ms,callback):self.serial+=1;self.sources[self.serial]=callback;return self.serial
    def source_remove(self,source):self.sources.pop(source,None)
class Process:
    def __init__(self):self.code=None
    def poll(self):return self.code
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'desktop.json').write_text('{}')
    calls=[];spawns=[];notes=[];config=api['settings']();clock=Clock();children={}
    def spawn(key,args):
        process=Process();children[key]=process;spawns.append((key,args));return process
    def terminate(key):
        process=children.pop(key,None)
        if process:process.code=-15
    desktop=SimpleNamespace(config=config,GLib=clock,children=children,directory=root,spawn=spawn,terminate=terminate,
        finish_session_operation=lambda operation:calls.append(operation),notify=lambda *args:notes.append(args),sound=lambda *args:None)
    controller=module['SessionExitController'](desktop)
    controller.begin('reboot');token=controller.token
    controller.begin('poweroff');assert len(spawns)==1 and not calls
    controller.ready('stale');assert not calls
    controller.ready(token);controller.ready(token);assert calls==['reboot']
    controller.cancel()
    audio=Process();events=[];desktop.sound=lambda event:(events.append(event),audio)[1]
    controller.begin('reboot');token=controller.token;controller.started(token)
    assert events==['shutdown'] and len(calls)==1
    controller.ready(token);assert len(calls)==1,'Exit discarded a running sound'
    audio.code=0;controller.poll();assert calls==['reboot','reboot'] and events==['shutdown']
    calls.pop();desktop.sound=lambda *args:None
    controller.cancel();controller.begin('logout');process=controller.process
    # A child reaper may remove the process before our privacy poll sees it.
    process.code=77;children.pop('session-exit');controller.poll();assert calls==['reboot'] and not controller.operation
    controller.begin('poweroff');controller.process.code=1;controller.poll();assert calls[-1]=='poweroff'
    controller.begin('reboot');controller.deadline=0;controller.poll();assert calls[-1]=='reboot'
    controller.begin('logout');(root/'desktop.json').write_text('{"locked":true}')
    controller.ready(controller.token);assert calls==['reboot','poweroff','reboot'] and not controller.operation
    (root/'desktop.json').write_text('{}');config['motion']['effects']='false';controller.begin('logout')
    assert calls[-1]=='logout' and controller.watch==0;controller.cancel()
    config['motion']['effects']='true';config['session_effects']['duration_ms']='bad'
    assert module['options'](config)[2]==600
    config['session_effects']['duration_ms']='9999';assert module['options'](config)[2]==1600
    def fail(operation):raise RuntimeError('mock logind failure')
    desktop.finish_session_operation=fail;controller.begin('reboot')
    try:controller.ready(controller.token)
    except RuntimeError:pass
    else:raise AssertionError('Expected rejected operation')
    assert not controller.operation and 'session-exit' not in children
    before=len(calls);controller.preview('shader','iris',700)
    assert '--preview' in spawns[-1][1] and len(calls)==before;controller.close()
print('PASS: single exit operation, stale-token rejection, cancellation/reaper race, renderer failure/watchdog fallback, lock cancellation, disabled effects, bounded durations, rejected-action recovery and harmless previews.')
