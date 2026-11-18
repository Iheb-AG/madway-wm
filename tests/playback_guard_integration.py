"""Real isolated PipeWire/Pulse server, virtual outputs only, no host audio."""
import json
import os
from pathlib import Path
import queue
import runpy
import subprocess
import tempfile
import time
import wave
from types import SimpleNamespace

repo=Path(__file__).resolve().parent.parent
api=runpy.run_path(str(repo/'scripts/madway_playback.py'))
with tempfile.TemporaryDirectory(prefix='madway-private-audio-') as tmp:
 root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700)
 env={**os.environ,'HOME':tmp,'GIO_USE_VFS':'local','XDG_RUNTIME_DIR':str(runtime),'PIPEWIRE_RUNTIME_DIR':str(runtime),
      'PULSE_SERVER':'unix:'+str(runtime/'pulse/native'),'XDG_CONFIG_HOME':str(root/'config'),
      'XDG_STATE_HOME':str(root/'state'),'XDG_CACHE_HOME':str(root/'cache'),
      'DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus')}
 for key in ('PIPEWIRE_REMOTE','PIPEWIRE_CONFIG_DIR','PIPEWIRE_CONFIG_NAME','PIPEWIRE_MODULE_DIR'):env.pop(key,None)
 processes=[]
 def run(argv):
  result=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=2)
  if result.returncode:raise RuntimeError(result.stderr)
  return result.stdout
 def wait(check):
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   try:
    result=check()
    if result:return result
   except (RuntimeError,ValueError):pass
   time.sleep(.03)
  raise AssertionError('Private audio graph timed out')
 with (root/'server.log').open('w') as log:
  try:
   processes.append(subprocess.Popen(['pipewire'],env=env,stdout=log,stderr=log))
   wait(lambda:(runtime/'pipewire-0').exists())
   processes.append(subprocess.Popen(['pipewire-pulse'],env=env,stdout=log,stderr=log))
   wait(lambda:run(['pactl','info']))
   # The policy profile supplies metadata/stream routing without ALSA, Bluetooth
   # or camera monitors: only our explicitly-created virtual sinks can exist.
   processes.append(subprocess.Popen(['wireplumber','--profile=policy'],env=env,stdout=log,stderr=log))
   original=int(run(['pactl','load-module','module-null-sink','sink_name=test_speakers']).strip())
   wait(lambda:run(['pactl','set-default-sink','test_speakers']) or True)
   sound=root/'silence.wav'
   with wave.open(str(sound),'wb') as out:
    out.setnchannels(2);out.setsampwidth(2);out.setframerate(48000);out.writeframes(bytes(48000*4*20))
   player=subprocess.Popen(['paplay','--device=test_speakers','--client-name=madway-test-player',str(sound)],env=env,stdout=log,stderr=log);processes.append(player)
   stream=wait(lambda:next(iter(json.loads(run(['pactl','--format=json','list','sink-inputs']))),None))
   callbacks=queue.Queue();desktop=SimpleNamespace(native=True,directory=root,GLib=SimpleNamespace(idle_add=lambda callback:callbacks.put(callback)))
   (root/'desktop.json').write_text('{}')
   guard=api['PlaybackGuard'](desktop,run);guard.start(lambda:None);callbacks.get(timeout=4)()
   sinks=json.loads(run(['pactl','--format=json','list','sinks']))
   temporary=next(row for row in sinks if row['name'].startswith('madway_exit_'))
   assert temporary['properties'].get('madway.owner.pid')==str(os.getpid()),temporary['properties']
   during=json.loads(run(['pactl','--format=json','list','sink-inputs']))[0]
   assert during['sink']==temporary['index'] and not during['mute'],during
   guard.close()
   after=json.loads(run(['pactl','--format=json','list','sink-inputs']))[0]
   assert after['sink']==stream['sink'] and not after['mute'],after
   assert not any(row['name'].startswith('madway_exit_') for row in json.loads(run(['pactl','--format=json','list','sinks'])))
   # Closed streams must not leave a remembered app mute or an orphan output.
   guard.start(lambda:None);callbacks.get(timeout=4)();player.terminate();player.wait(timeout=2);guard.close()
   assert not any(row['name'].startswith('madway_exit_') for row in json.loads(run(['pactl','--format=json','list','sinks'])))
   replacement=subprocess.Popen(['paplay','--client-name=madway-test-player',str(sound)],env=env,stdout=log,stderr=log);processes.append(replacement)
   restarted=wait(lambda:next(iter(json.loads(run(['pactl','--format=json','list','sink-inputs']))),None))
   assert not restarted['mute'] and restarted['sink']==stream['sink'],restarted
   run(['pactl','load-module','module-null-sink','sink_name=madway_exit_orphan',
       'sink_properties=device.description=madway-exit-isolation madway.owner.pid=99999999 priority.session=0'])
   guard.recover()
   wait(lambda:not any(r['name']=='madway_exit_orphan' for r in json.loads(run(['pactl','--format=json','list','sinks']))))
  except BaseException:
   print((root/'server.log').read_text());raise
  finally:
   if 'guard' in locals():guard.close()
   for process in reversed(processes):
    if process.poll() is None:
     process.terminate()
     try:process.wait(timeout=3)
     except subprocess.TimeoutExpired:process.kill();process.wait()
print('PASS: real private PipeWire routing isolation, unchanged application mute, cancellation restore, closed-stream cleanup and virtual-output removal.')
