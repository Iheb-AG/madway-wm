"""Real KEY_MICMUTE -> XKB -> compositor -> worker with mocked WirePlumber."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
repo=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='madway-mic-key-') as tmp:
 root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700);config=root/'config';(config/'madway').mkdir(parents=True)
 (config/'madway/settings.ini').write_text('[session_effects]\nopening=false\n[notifications]\nenabled=true\n[desktop]\nicons=false\n[dock]\nenabled=true\ntray=false\n[panel]\nmetrics=false\n')
 binaries=root/'bin';binaries.mkdir();hardware=root/'mic.json';hardware.write_text('{"muted":false}')
 wpctl=binaries/'wpctl';wpctl.write_text('#!'+sys.executable+'\n'+'''import json,sys
from pathlib import Path
path=Path('''+repr(str(hardware))+''');state=json.loads(path.read_text());args=sys.argv[1:]
if args[0]=='get-volume':print('Volume: 0.65'+(' [MUTED]' if args[-1]=='@DEFAULT_AUDIO_SOURCE@' and state['muted'] else ''))
else:
 assert args==['set-mute','@DEFAULT_AUDIO_SOURCE@','toggle'];state['muted']=not state['muted'];path.write_text(json.dumps(state))
''');wpctl.chmod(0o700)
 flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
 subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','-Ibuild/protocols','tests/dock_probe.c','-o',str(root/'probe.so'),*flags,'-ldl'],cwd=repo,check=True)
 env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_RENDERER':'pixman','MADWAY_SESSION':'1','GDK_BACKEND':'wayland','GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery'),'MADWAY_DOCK_TEST':tmp,'PATH':str(binaries)+':'+os.environ['PATH']}
 for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(key,None)
 log_path=root/'server.log'
 with log_path.open('w') as log:
  server=subprocess.Popen([str(repo/'build/madway')],cwd=repo,env={**env,'LD_PRELOAD':str(root/'probe.so')},stdout=log,stderr=log)
  def wait(check):
   end=time.monotonic()+10
   while time.monotonic()<end:
    assert server.poll() is None,log_path.read_text()
    if check():return
    time.sleep(.02)
   raise AssertionError(log_path.read_text())
  try:
   wait(lambda:'Desktop layer mapped: madway-dock' in log_path.read_text())
   display=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',log_path.read_text())[1];directory=runtime/('madway-'+display)
   for code,muted in [(42,True),(43,False)]:
    (root/'command').write_text(str(code));wait(lambda:json.loads(hardware.read_text())['muted']==muted)
    wait(lambda:(directory/'media.json').exists() and json.loads((directory/'media.json').read_text()).get('kind')=='microphone' and json.loads((directory/'media.json').read_text()).get('muted')==muted)
   print('PASS: standard microphone Fn key toggles only the default input, confirms both states, and writes microphone OSD feedback.')
  finally:
   server.terminate()
   try:server.wait(timeout=5)
   except subprocess.TimeoutExpired:server.kill();server.wait()
