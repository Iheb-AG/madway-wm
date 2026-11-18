"""Fake audio graph: exit isolation must never persist application mute state."""
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
 streams=[dict(index=i,client=i,sink=10,mute=i==2,properties={'application.name':name,'application.process.id':pid,'object.serial':str(i)})
          for i,name,pid in [(1,'Brave','123'),(2,'Muted player','123'),(3,'madway-session-sound','999'),(4,'Host music','456')]]
 sinks=[dict(index=10,name='speakers'),dict(index=11,name='headphones')]
 commands=[];callbacks=queue.Queue()
 def run(argv):
  commands.append(argv)
  if argv[1:4]==['--format=json','list','sink-inputs']:return json.dumps(streams)
  if argv[1:4]==['--format=json','list','sinks']:return json.dumps(sinks)
  if argv[1]=='load-module':
   assert argv[2]=='module-null-sink';name=argv[3].split('=',1)[1]
   sinks.append(dict(index=20,name=name));return '90\n'
  if argv[1]=='unload-module':
   assert argv[2]=='90';sinks[:]=[row for row in sinks if row['index']!=20]
   for row in streams:
    if row['sink']==20:row['sink']=10
   return ''
  assert argv[1]=='move-sink-input',argv
  sink=next(row['index'] for row in sinks if row['name']==argv[3]) if not argv[3].isdigit() and not argv[3].startswith('@') else 10
  next(row for row in streams if str(row['index'])==argv[2])['sink']=sink
  return ''
 desktop=SimpleNamespace(native=False,directory=root,GLib=SimpleNamespace(idle_add=lambda callback:callbacks.put(callback)))
 guard=module['PlaybackGuard'](desktop,run);guard.start(lambda:None)
 callbacks.get(timeout=2)();assert streams[0]['sink']==20 and streams[1]['sink']==10 and streams[2]['sink']==10 and streams[3]['sink']==10
 assert not streams[0]['mute'] and streams[1]['mute']
 # New app streams are isolated too, including a replacement after app closure.
 streams.append(dict(index=5,client=5,sink=10,mute=False,properties={'application.name':'New player','application.process.id':'123'}))
 end=time.monotonic()+2
 while streams[-1]['sink']!=20 and time.monotonic()<end:time.sleep(.01)
 assert streams[-1]['sink']==20 and not streams[-1]['mute']
 # Reused stream ID and a user-routed stream must not be rewritten on restore.
 streams[0]['properties']['object.serial']='999';streams[0]['sink']=11
 guard.close();assert not guard.thread.is_alive()
 assert streams[0]['sink']==11 and streams[-1]['sink']==10
 assert streams[1]['mute'] and not streams[0]['mute'] and not streams[-1]['mute']
 assert len(sinks)==2
 assert not any('mute' in part for argv in commands for part in argv)
 # Native isolation includes all playback, while the session sound stays audible.
 desktop.native=True;guard.start(lambda:None);callbacks.get(timeout=2)()
 assert streams[3]['sink']==20 and streams[2]['sink']==10
 streams[:]=[row for row in streams if row['index']!=4] # App closes before restore.
 guard.close();assert len(sinks)==2
 # Muting is never used, even when a player disappears before shutdown completes.
 assert not any('mute' in part for argv in commands for part in argv)
print('PASS: temporary exit routes, preserved mute state, new/closed/reused streams, nested host isolation, session-sound exemption and joined cleanup.')
