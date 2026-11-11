"""Fake stream graph: no host audio requests, capture, sink mute or process kills."""
import json
from pathlib import Path
import queue
import runpy
import tempfile
import time
from types import SimpleNamespace
module=runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway_playback.py'))
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);(root/'desktop.json').write_text(json.dumps({'all_windows':[{'pid':123}]}))
 streams=[dict(index=1,client=1,mute=False,properties={'application.name':'Brave','application.process.id':'123','object.serial':'10'}),dict(index=2,client=2,mute=True,properties={'application.name':'Muted player','application.process.id':'123'}),dict(index=3,client=3,mute=False,properties={'application.name':'madway-session-sound','application.process.id':'999'}),dict(index=4,client=4,mute=False,properties={'application.name':'Host music','application.process.id':'456'})]
 commands=[];callbacks=queue.Queue()
 def run(argv):
  commands.append(argv)
  if argv[-1]=='sink-inputs':return json.dumps(streams)
  assert argv[1]=='set-sink-input-mute'
  next(row for row in streams if str(row['index'])==argv[2])['mute']=argv[3]=='1'
  return ''
 desktop=SimpleNamespace(native=False,directory=root,GLib=SimpleNamespace(idle_add=lambda callback:callbacks.put(callback)))
 guard=module['PlaybackGuard'](desktop,run);guard.start(lambda:None)
 callbacks.get(timeout=2)();assert streams[0]['mute'] and streams[1]['mute'] and not streams[2]['mute'] and not streams[3]['mute']
 # A recording stream is never part of this graph. New playback stays isolated.
 streams.append(dict(index=5,client=5,mute=False,properties={'application.name':'New meeting sound','application.process.id':'123'}))
 end=time.monotonic()+2
 while not streams[-1]['mute'] and time.monotonic()<end:time.sleep(.02)
 assert streams[-1]['mute']
 # An index reused by a different stream must not have its mute state altered.
 streams[0]['properties']['object.serial']='999'
 guard.stop();guard.thread.join(timeout=3);assert not guard.thread.is_alive()
 assert streams[0]['mute'] and streams[1]['mute'] and not streams[-1]['mute']
 assert all('set-sink-mute' not in argv for argv in commands)
print('PASS: application-only exit isolation, session-sound exemption, new-stream protection, existing mute preservation, index reuse protection and cancellation restore.')
