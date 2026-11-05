"""Session exit orchestration. The renderer never executes a power operation."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

MODES={'none','fade','shader'}
SHADERS={'crt':'CRT standby','iris':'Iris close','dissolve':'Soft dissolve','vortex':'Event horizon','prism':'Prismatic fold','ripple':'Liquid lens','embers':'Ember dissolve','shutter':'Mechanical shutter','aurora':'Aurora veil'}


def options(config):
    mode=config.get('session_effects','mode',fallback='fade')
    shader=config.get('session_effects','shader',fallback='crt')
    try:duration=config.getint('session_effects','duration_ms',fallback=600)
    except ValueError:duration=600
    if mode not in MODES:mode='fade'
    if shader not in SHADERS:shader='crt'
    if not config.getboolean('motion','effects',fallback=True):mode='none'
    return mode,shader,min(1600,max(160,duration))


class SessionExitController:
    """One confirmed operation; rendering failures cannot strand the session."""
    def __init__(self,desktop):
        self.desktop=desktop;self.operation=None;self.token=None;self.watch=0;self.deadline=0;self.committing=False;self.process=None;self.sound_process=None;self.sound_started=False;self.visual_done=False;self.sound_deadline=0;self.opening_token=None;self.opening_event=None;self.opening_process=None
    def begin(self,operation):
        if operation not in ('logout','reboot','poweroff'):raise ValueError('Unknown session operation')
        if self.operation:return
        self.operation=operation;self.token=secrets.token_hex(16);self.committing=False;self.sound_started=False;self.visual_done=False;self.sound_process=None
        self.desktop.terminate('session-opening');self.opening_token=None
        self.desktop.terminate('sound-startup');self.desktop.terminate('sound-logon')
        mode,shader,duration=options(self.desktop.config)
        self.desktop.terminate('desktop-menu');self.desktop.terminate('session-preview');self.desktop.terminate('session-exit')
        if mode=='none':
            self.visual_done=True;self.started(self.token);self.wait_or_commit();return
        args=[sys.executable,str(Path(__file__).resolve()),'--operation',operation,'--mode',mode,'--shader',shader,'--duration',str(duration),'--token',self.token]
        try:process=self.desktop.spawn('session-exit',args)
        except OSError:process=None
        if process is None:
            self.visual_done=True;self.started(self.token);self.wait_or_commit();return
        self.process=process
        self.deadline=time.monotonic()+4.0+duration/1000
        self.watch=self.desktop.GLib.timeout_add(100,self.poll)
    def started(self,token):
        if not self.operation or self.sound_started or not secrets.compare_digest(str(token),self.token):return
        self.sound_started=True;self.sound_deadline=time.monotonic()+8
        event='logout' if self.operation=='logout' else 'shutdown'
        self.sound_process=self.desktop.sound(event)
        self.desktop.exit_sound_played=True
        if event=='shutdown':self.desktop.shutdown_played=True
    def wait_or_commit(self):
        if not self.visual_done:return
        if self.sound_process is not None and self.sound_process.poll() is None:
            if not self.watch:self.watch=self.desktop.GLib.timeout_add(25,self.poll)
            return
        self.commit()
    def opening(self,event):
        mode,shader,duration=options(self.desktop.config)
        if mode=='none' or not self.desktop.config.getboolean('session_effects','opening',fallback=True):self.desktop.sound(event);return
        self.opening_token=secrets.token_hex(16);self.opening_event=event
        try:duration=self.desktop.config.getint('session_effects','opening_ms',fallback=700)
        except ValueError:duration=700
        try:self.opening_process=self.desktop.spawn('session-opening',[sys.executable,str(Path(__file__).resolve()),'--opening','--mode',mode,'--shader',shader,'--duration',str(min(1600,max(160,duration))),'--token',self.opening_token])
        except OSError:self.opening_process=None
        token=self.opening_token;deadline=time.monotonic()+5
        def check():
            if self.opening_token!=token:return False
            if self.opening_process is not None and self.opening_process.poll()==77:
                self.opening_token=None;return False
            if self.opening_process is None or self.opening_process.poll() is not None or time.monotonic()>deadline:
                self.desktop.sound(self.opening_event);self.opening_token=None;return False
            return True
        self.desktop.GLib.timeout_add(100,check)
    def opening_started(self,token):
        if self.opening_token and secrets.compare_digest(str(token),self.opening_token):
            self.desktop.sound(self.opening_event);self.opening_token=None
    def poll(self):
        process=self.process
        try:state=json.loads((self.desktop.directory/'desktop.json').read_text())
        except (OSError,ValueError):state={}
        if state.get('locked') or state.get('sleeping'):
            self.watch=0;self.cancel();return False
        if process is not None and process.poll()==77:
            self.watch=0;self.cancel();return False
        if self.visual_done:
            if self.sound_process is not None and self.sound_process.poll() is None and time.monotonic()<self.sound_deadline:return True
            if self.sound_process is not None and self.sound_process.poll() is None:self.desktop.terminate('sound-logout' if self.operation=='logout' else 'sound-shutdown')
            self.watch=0
            try:self.commit()
            except Exception as error:self.desktop.notify('error','Session action unavailable',str(error))
            return False
        if process is None or process.poll() is not None or time.monotonic()>self.deadline:
            self.watch=0;self.desktop.terminate('session-exit')
            try:
                self.visual_done=True;self.started(self.token);self.wait_or_commit()
            except Exception as error:self.desktop.notify('error','Session action unavailable',str(error))
            return False
        return True
    def ready(self,token):
        if self.operation and not self.committing and secrets.compare_digest(str(token),self.token):
            try:state=json.loads((self.desktop.directory/'desktop.json').read_text())
            except (OSError,ValueError):state={}
            if state.get('locked') or state.get('sleeping'):self.cancel()
            else:
                self.visual_done=True;self.started(token);self.wait_or_commit()
    def commit(self):
        if not self.operation or self.committing:return
        self.committing=True
        if self.watch:self.desktop.GLib.source_remove(self.watch);self.watch=0
        operation=self.operation
        try:self.desktop.finish_session_operation(operation)
        except Exception:
            self.cancel();raise
        if operation!='logout':
            # Successful logind requests may take time. The visual helper has a
            # bounded hold; it cannot leave the desktop covered indefinitely.
            self.operation=None;self.token=None;self.committing=False
    def cancel(self):
        if self.watch:self.desktop.GLib.source_remove(self.watch);self.watch=0
        self.desktop.terminate('session-exit')
        if self.sound_started:
            self.desktop.terminate('sound-logout' if self.operation=='logout' else 'sound-shutdown')
            self.desktop.shutdown_played=False;self.desktop.exit_sound_played=False
        self.operation=None;self.token=None;self.committing=False;self.process=None;self.sound_started=False;self.sound_process=None
    def preview(self,mode,shader,duration,opening=False):
        if self.operation:return
        if mode not in ('fade','shader') or shader not in SHADERS:raise ValueError('Unknown session effect')
        self.desktop.terminate('session-preview')
        self.desktop.spawn('session-preview',[sys.executable,str(Path(__file__).resolve()),'--preview','--mode',mode,'--shader',shader,'--duration',str(min(1600,max(160,int(duration)))),*(['--opening'] if opening else [])])
    def close(self):self.cancel();self.desktop.terminate('session-preview');self.desktop.terminate('session-opening')


def render_main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation',choices=('logout','reboot','poweroff'),default='logout')
    parser.add_argument('--mode',choices=('fade','shader'),default='fade')
    parser.add_argument('--shader',choices=tuple(SHADERS),default='crt')
    parser.add_argument('--opening',action='store_true')
    parser.add_argument('--duration',type=int,default=600);parser.add_argument('--preview',action='store_true');parser.add_argument('--token',default='')
    args=parser.parse_args()
    if not args.preview and not args.token:parser.error('A live operation requires a controller token; use --preview to try an effect.')
    import runpy
    module=runpy.run_path(str(Path(__file__).with_name('madway_exit_ui.py')))
    return module['run'](args)


if __name__=='__main__':sys.exit(render_main())
