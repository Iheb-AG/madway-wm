"""Supervisor readiness/failure checks with fake processes, never host authentication."""
import configparser
import json
import os
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway_lock.py'))
shell=runpy.run_path(str(repo/'scripts/madway-shell'))
processes=[]
class FakeProcess:
    def __init__(self,args,pass_fds):
        self.pid=1234+len(processes);self.code=None;self.writer=os.dup(pass_fds[0]);processes.append(self)
        assert '--config' in args and '--ready-fd' in args and '--daemonize' not in args
    def poll(self):return self.code
    def terminate(self):self.code=1
    def kill(self):self.code=-9
    def wait(self,timeout=None):return self.code

with tempfile.TemporaryDirectory(prefix='madway-lock-unit-') as tmp:
    directory=Path(tmp);commands=[];completed=[]
    config=configparser.ConfigParser(interpolation=None);config.read_dict(shell['DEFAULTS'])
    desktop=SimpleNamespace(directory=directory,config=config,GLib=SimpleNamespace(timeout_add=lambda *args:1),
        compositor=commands.append,terminate=lambda name:None)
    state=dict(locked=True,lock_ready=True,lock_client_pid=55,lock_request=0)
    def write():(directory/'desktop.json').write_text(json.dumps(state))
    write()
    with patch('shutil.which',return_value='/fake/swaylock'),patch('subprocess.Popen',FakeProcess):
        lock=api['LockController'](desktop,repo/'share/madway')
        lock.ensure(completed.append);assert not completed,'Stale state satisfied a fresh lock request'
        state['lock_request']=lock.serial;write();lock.poll();assert completed==[True]
        lock.close()
        state.update(locked=False,lock_ready=False,lock_client_pid=0,lock_request=0);write();completed.clear()
        lock=api['LockController'](desktop,repo/'share/madway');lock.ensure(completed.append)
        state.update(locked=True,lock_ready=True,lock_request=lock.serial);write();lock.poll()
        child=processes[-1];state['lock_client_pid']=child.pid;write();lock.poll()
        assert not completed,'Compositor state bypassed the managed locker ready pipe'
        os.write(child.writer,b'\n');lock.poll();assert completed==[True]
        assert (directory/'swaylock.conf').read_text().splitlines()[0].endswith('ff'),'Locker background was not opaque'
        child.code=1;state['lock_client_pid']=0;write();lock.poll()
        assert state['locked'] and lock.process is None
        lock.retry_at=0;lock.poll();assert lock.process is not None and lock.process.pid!=child.pid
        completed.clear();lock.ensure(completed.append);lock.deadline=0;lock.poll()
        assert completed==[False] and state['locked'],'Readiness timeout unlocked the session'
        assert not any(command.startswith('unlock') for command in commands)
        lock.close()
    with patch('shutil.which',return_value=None):
        lock=api['LockController'](desktop,repo/'share/madway');completed.clear();before=len(commands)
        try:lock.ensure(completed.append)
        except RuntimeError:pass
        else:raise AssertionError('Missing swaylock was accepted')
        assert completed==[False] and len(commands)==before
        completed.clear();lock.ensure(completed.append,emergency=True)
        state.update(locked=True,lock_ready=True,lock_client_pid=0,lock_request=lock.serial);write();lock.poll()
        assert completed==[True] and state['locked'],'External sleep did not retain opaque protection'
        lock.close()
for process in processes:os.close(process.writer)
print('PASS: fresh nonce, dual compositor/ready-pipe confirmation, opaque configuration, process recovery, timeout protection, missing-locker cancellation and emergency blank fallback. No real processes or authentication.')
