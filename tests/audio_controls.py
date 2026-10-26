"""Exercise audio discovery and commands with fixtures; never contact host audio."""
import json
from pathlib import Path
import runpy

api = runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway-shell'))
commands = []
def run(argv):
    commands.append(argv)
    if argv[-1] == 'info':return json.dumps(dict(default_sink_name='speakers', default_source_name='mic'))
    if 'list' in argv:
        kind = argv[-1]
        return json.dumps([dict(index=7, name='speakers' if kind=='sinks' else 'mic', description='Fixture',
            properties={'application.name':'Player', 'media.name':'Track'},
            volume={'left':{'value_percent':'25%'},'right':{'value_percent':'75%'}},mute=False)])
    return ''
api['audio_snapshot'].__globals__['run'] = run
snapshot=api['audio_snapshot']()
assert len(snapshot)==4 and all(rows[0]['volume']==50 for _,rows in snapshot)
assert snapshot[0][1][0]['default'] and snapshot[1][1][0]['default']
for kind in ('sink','source','sink-input','source-output'):
    api['audio_control'](dict(kind=kind, id=7, operation='volume', value=190))
    assert commands[-1]==['pactl','set-'+kind+'-volume','7','100%']
    api['audio_control'](dict(kind=kind, id=7, operation='mute', value=True))
    assert commands[-1]==['pactl','set-'+kind+'-mute','7','1']
for kind in ('sink','source'):
    api['audio_control'](dict(kind=kind,id=7,operation='default'))
    assert commands[-1]==['pactl','set-default-'+kind,'7']
for message in (dict(kind='invalid', id=7, operation='volume', value=20),
                dict(kind='sink-input',id=7,operation='default'),
                dict(kind='sink',id='7;touch /tmp/no',operation='mute'),
                dict(kind='source',id=-1,operation='mute')):
    count=len(commands)
    try:api['audio_control'](message)
    except (ValueError,RuntimeError):pass
    else:raise AssertionError('Invalid audio command accepted')
    assert len(commands)==count
print('PASS: audio discovery, channel levels, defaults, device/app controls and input validation.')
