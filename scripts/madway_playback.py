"""Temporarily isolate exit audio without muting the output device or microphone."""
import json
import subprocess
import sys
import threading
import time


def command(argv):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=.8)
    if result.returncode:raise RuntimeError(result.stderr.strip() or 'Playback control unavailable')
    return result.stdout


def identity(row):
    props=row.get('properties',{})
    return tuple(str(value) for value in (row.get('client'),props.get('object.serial'),props.get('application.process.id'),props.get('application.name'),props.get('media.name')))


class PlaybackGuard:
    def __init__(self,desktop,run=command):
        self.desktop=desktop;self.run=run;self.thread=None;self.event=None

    def start(self,ready):
        previous=self.thread
        self.stop();event=threading.Event();self.event=event
        native=self.desktop.native
        try:state=json.loads((self.desktop.directory/'desktop.json').read_text())
        except (OSError,ValueError):state={}
        pids={str(row['pid']) for row in state.get('all_windows',[]) if isinstance(row.get('pid'),int) and row['pid']>0}
        def worker():
            if previous:previous.join()
            changed={};deadline=time.monotonic()+20
            def snapshot():return json.loads(self.run(['pactl','--format=json','list','sink-inputs']))
            def silence(rows):
                for row in rows:
                    props=row.get('properties',{})
                    if props.get('application.name')=='madway-session-sound':continue
                    if not native and str(props.get('application.process.id')) not in pids:continue
                    if row.get('mute'):continue
                    key=int(row['index'])
                    if event.is_set():break
                    self.run(['pactl','set-sink-input-mute',str(key),'1']);changed[key]=identity(row)
            try:
                try:silence(snapshot())
                except Exception as error:print('madway: exit playback isolation: '+str(error),file=sys.stderr)
                if not event.is_set():self.desktop.GLib.idle_add(ready)
                while not event.wait(.1) and time.monotonic()<deadline:
                    try:silence(snapshot())
                    except Exception:pass
            finally:
                try:
                    for row in snapshot():
                        key=int(row['index'])
                        if key in changed and identity(row)==changed[key] and row.get('mute'):
                            self.run(['pactl','set-sink-input-mute',str(key),'0'])
                except Exception as error:print('madway: restoring playback state: '+str(error),file=sys.stderr)
        self.thread=threading.Thread(target=worker,daemon=True);self.thread.start()

    def stop(self):
        if self.event:self.event.set()
