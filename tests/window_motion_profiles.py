"""Check actual C motion math/config and parity with Python preset preferences."""
import configparser
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
repo=Path(__file__).resolve().parent.parent
profiles=runpy.run_path(str(repo/'scripts/madway_motion_presets.py'))
flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon','gio-2.0'],text=True).split()
with tempfile.TemporaryDirectory(prefix='madway-motion-math-') as tmp:
 root=Path(tmp);binary=root/'motion-test'
 subprocess.run([os.environ.get('CC','cc'),'-std=gnu17','-Wall','-Wextra','-Werror','-DWLR_USE_UNSTABLE','-Isrc',
   '-ffunction-sections','-fdata-sections','tests/motion_profile_test.c','src/motion_profile.c','src/animation.c',
   '-o',str(binary),*flags,'-Wl,--gc-sections','-lm'],cwd=repo,check=True)
 subprocess.run([str(binary)],check=True)
 enums={'open_style':{'zoom':0,'fade':1,'rise':2,'slide':3},'maximize_style':{'zoom':0,'dissolve':1,'none':2},
        'open_curve':{'gentle':0,'responsive':1,'spring':2,'linear':3},'maximize_curve':{'gentle':0,'responsive':1,'spring':2,'linear':3}}
 for key,catalog in [('open_preset',profiles['OPENING']),('maximize_preset',profiles['MAXIMIZE'])]:
  for name,(_,values) in catalog.items():
   config=configparser.ConfigParser();config['windows']={key:name};path=root/'settings.ini'
   with path.open('w') as output:config.write(output)
   actual=json.loads(subprocess.check_output([str(binary),str(path)],text=True))
   for field,value in values.items():
    expected=enums[field][value] if field in enums else value=='true' if value in ('true','false') else int(value)
    assert actual[field]==expected,(name,field,actual[field],expected)
 defaults=runpy.run_path(str(repo/'scripts/madway-shell'))['DEFAULTS']
 config=configparser.ConfigParser();config.read_dict(defaults)
 stored=configparser.ConfigParser();stored.read_string('[windows]\nanimate=false\nanimation_ms=480\n')
 config.read_dict({'windows':dict(stored['windows'])});profiles['normalize'](config,stored)
 assert not config.getboolean('windows','open_animate') and config.getint('windows','maximize_ms')==480
 assert config.get('windows','maximize_preset')=='custom'
 stored['windows']['maximize_preset']='smooth'
 config=configparser.ConfigParser();config.read_dict(defaults);config.read_dict({'windows':dict(stored['windows'])});profiles['normalize'](config,stored)
 assert config.getint('windows','maximize_ms')==360,'Explicit preset should use its own timing'
print('PASS: every Settings preset matches native rendering defaults; legacy animation opt-out and custom durations are retained.')
