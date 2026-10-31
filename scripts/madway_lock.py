"""Supervise swaylock; the compositor alone owns the locked/unlocked state."""
import configparser
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time


class LockController:
    def __init__(self,desktop,share):
        self.desktop=desktop;self.share=Path(share)
        self.process=None;self.ready_fd=-1;self.ready_notified=False
        self.callbacks=[];self.serial=0;self.deadline=0
        self.attempts=0;self.retry_at=0;self.emergency=False
        self.closed=False;self.error_reported=False
        self.desktop.GLib.timeout_add(100,self.poll)

    def state(self):
        try:return json.loads((self.desktop.directory/'desktop.json').read_text())
        except (OSError,ValueError):return {}

    def config_file(self):
        themes=configparser.ConfigParser(interpolation=None);themes.read(self.share/'themes.ini')
        name=self.desktop.config.get('appearance','theme')
        palette=themes[name if name in themes else 'black']
        lines=['color='+palette['background'][1:]+'ff','inside-color='+palette['surface'][1:]+'ff',
            'ring-color='+palette['accent'][1:]+'ff','text-color='+palette['text'][1:]+'ff',
            'ring-ver-color='+palette['active'][1:]+'ff','ring-wrong-color=b52b20ff',
            'font='+('Inter' if name in {'gershwin','gershwin-dark'} else 'monospace'),'font-size=12',
            'indicator-radius=26','indicator-thickness=3','indicator-idle-visible',
            'show-failed-attempts','ignore-empty-password','show-keyboard-layout']
        path=self.desktop.directory/'swaylock.conf';path.write_text('\n'.join(lines)+'\n');return path

    def close_ready(self):
        if self.ready_fd>=0:os.close(self.ready_fd);self.ready_fd=-1

    def start(self):
        binary=shutil.which('swaylock')
        if not binary:raise RuntimeError('Install swaylock to lock the session')
        self.close_ready();self.ready_notified=False
        read,write=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK)
        try:
            self.process=subprocess.Popen([binary,'--config',str(self.config_file()),'--ready-fd',str(write)],pass_fds=(write,))
        except Exception:
            os.close(read);raise
        finally:os.close(write)
        self.ready_fd=read;self.attempts+=1
        self.desktop.compositor('lock-owner '+str(self.process.pid))
        print('madway: swaylock started',file=sys.stderr)

    def ensure(self,callback=None,emergency=False):
        if self.closed:
            if callback:callback(False)
            return
        if not emergency and not shutil.which('swaylock'):
            if callback:callback(False)
            raise RuntimeError('Install swaylock to lock the session; sleep was not requested')
        self.emergency |= emergency
        if callback:self.callbacks.append(callback)
        if not self.serial:
            self.serial=secrets.randbelow(0xfffffffe)+1
            self.deadline=time.monotonic()+10;self.error_reported=False
            self.attempts=0;self.retry_at=0
            self.desktop.compositor('lock-request '+str(self.serial))
        for key in ('desktop-menu','launcher','switcher','screenshot'):self.desktop.terminate(key)
        self.poll()

    def complete(self,success):
        callbacks,self.callbacks=self.callbacks,[]
        self.serial=0;self.emergency=False
        for callback in callbacks:
            try:callback(success)
            except Exception as error:print('madway: lock completion: '+str(error),file=sys.stderr)

    def poll(self):
        if self.closed:return False
        state=self.state();now=time.monotonic()
        if self.process is not None:
            if self.ready_fd>=0:
                try:
                    data=os.read(self.ready_fd,64)
                    if b'\n' in data:self.ready_notified=True
                    if data==b'' or self.ready_notified:self.close_ready()
                except BlockingIOError:pass
            if self.process.poll() is not None:
                self.close_ready();self.process=None;self.ready_notified=False
                self.retry_at=now+min(4,2**max(0,self.attempts-1))
        requested=self.serial and state.get('lock_request')==self.serial
        if requested and state.get('locked') and state.get('lock_ready'):
            pid=state.get('lock_client_pid',0)
            if pid and (self.process is None or pid!=self.process.pid or self.ready_notified):
                self.complete(True);self.attempts=0;self.error_reported=False
            elif self.emergency:
                # Black frames are sufficient to release logind's bounded delay.
                # Authentication UI recovery continues independently below.
                self.complete(True)
        if self.serial and now>self.deadline:
            self.complete(False)
            print('madway: locker readiness timed out; session remains protected',file=sys.stderr)
        if state.get('locked') and not state.get('lock_client_pid') and self.process is None and now>=self.retry_at and self.attempts<3:
            try:self.start()
            except Exception as error:
                self.attempts+=1;self.retry_at=now+min(4,2**self.attempts)
                if not self.error_reported:
                    print('madway: locker unavailable; session remains locked: '+str(error),file=sys.stderr)
                    self.error_reported=True
        if not state.get('locked') and not self.serial:
            self.attempts=0;self.error_reported=False
        return True

    def retry(self):
        if not self.serial and not self.state().get('lock_client_pid') and self.process is not None and self.process.poll() is None:
            self.process.terminate()
        self.attempts=0;self.retry_at=0;self.ensure()

    def close(self):
        self.closed=True;self.complete(False);self.close_ready()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
