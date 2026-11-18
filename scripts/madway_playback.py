"""Isolate exit playback by temporary routing, never persistent app mute changes."""
import json
import os
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

    def recover(self):
        """Remove only abandoned madway virtual outputs after an unclean exit."""
        if not self.desktop.native:return
        def worker():
            try:
                for sink in json.loads(self.run(['pactl','--format=json','list','sinks'])):
                    props=sink.get('properties',{})
                    if not sink.get('name','').startswith('madway_exit_'):continue
                    owner=int(props.get('madway.owner.pid',0))
                    if owner<=0:continue
                    try:os.kill(owner,0)
                    except ProcessLookupError:
                        module=sink.get('owner_module')
                        if isinstance(module,int):self.run(['pactl','unload-module',str(module)])
                    except PermissionError:pass
            except Exception as error:print('madway: exit audio recovery: '+str(error),file=sys.stderr)
        threading.Thread(target=worker,daemon=True).start()

    def start(self,ready):
        previous=self.thread
        self.stop();event=threading.Event();self.event=event
        native=self.desktop.native
        try:state=json.loads((self.desktop.directory/'desktop.json').read_text())
        except (OSError,ValueError):state={}
        pids={str(row['pid']) for row in state.get('all_windows',[]) if isinstance(row.get('pid'),int) and row['pid']>0}
        def worker():
            if previous:previous.join()
            changed={};deadline=time.monotonic()+20;module=None;sink_id=None
            name=f'madway_exit_{os.getpid()}_{time.monotonic_ns()}'
            def snapshot():return json.loads(self.run(['pactl','--format=json','list','sink-inputs']))
            def silence(rows):
                nonlocal module,sink_id
                eligible=[]
                for row in rows:
                    props=row.get('properties',{})
                    if props.get('application.name')=='madway-session-sound':continue
                    if not native and str(props.get('application.process.id')) not in pids:continue
                    if row.get('mute'):continue
                    if changed.get(int(row['index']),(None,))[0]==identity(row):continue
                    eligible.append(row)
                if not eligible or event.is_set():return
                if module is None:
                    # Moving to a disposable output avoids writing mute=true to
                    # Pulse/WirePlumber's per-application restore state when the
                    # application closes during the exit sound.
                    module=int(self.run(['pactl','load-module','module-null-sink','sink_name='+name,
                        f'sink_properties=device.description=madway-exit-isolation madway.owner.pid={os.getpid()} node.virtual=true priority.session=0']).strip())
                    limit=time.monotonic()+1
                    while True:
                        sinks=json.loads(self.run(['pactl','--format=json','list','sinks']))
                        target=next((row for row in sinks if row.get('name')==name),None)
                        if target:sink_id=target['index'];break
                        if event.wait(.02) or time.monotonic()>limit:raise RuntimeError('Temporary exit output did not appear')
                sinks={int(row['index']):row['name'] for row in json.loads(self.run(['pactl','--format=json','list','sinks']))}
                for row in eligible:
                    if event.is_set():break
                    original=sinks.get(int(row.get('sink',-1)),'@DEFAULT_SINK@')
                    if original==name:original='@DEFAULT_SINK@'
                    self.run(['pactl','move-sink-input',str(row['index']),name])
                    changed[int(row['index'])]=(identity(row),original)
            try:
                try:silence(snapshot())
                except Exception as error:print('madway: exit playback isolation: '+str(error),file=sys.stderr)
                if not event.is_set():self.desktop.GLib.idle_add(ready)
                while not event.wait(.1) and time.monotonic()<deadline:
                    try:silence(snapshot())
                    except Exception:pass
            finally:
                try:
                    sinks={row['name'] for row in json.loads(self.run(['pactl','--format=json','list','sinks']))}
                    for row in snapshot():
                        saved=changed.get(int(row['index']))
                        if not saved or identity(row)!=saved[0] or row.get('sink')!=sink_id:continue
                        target=saved[1] if saved[1] in sinks else '@DEFAULT_SINK@'
                        try:self.run(['pactl','move-sink-input',str(row['index']),target])
                        except Exception as error:print('madway: restoring playback route: '+str(error),file=sys.stderr)
                except Exception as error:print('madway: restoring playback state: '+str(error),file=sys.stderr)
                finally:
                    if module is not None:
                        try:self.run(['pactl','unload-module',str(module)])
                        except Exception as error:print('madway: removing exit output: '+str(error),file=sys.stderr)
        self.thread=threading.Thread(target=worker,daemon=True);self.thread.start()

    def stop(self):
        if self.event:self.event.set()

    def close(self):
        self.stop()
        # Do not let process teardown kill a daemon worker before it restores
        # routes/unloads its output. Device changes still have bounded timeouts.
        if self.thread:self.thread.join(timeout=4)
