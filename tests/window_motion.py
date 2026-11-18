"""Real application maps and maximize presets on private 100/60 Hz outputs."""
import configparser
import json
import os
from pathlib import Path
import re
import runpy
import socket
import subprocess
import sys
import tempfile
import time
os.environ['GIO_USE_VFS']='local' # Image decoding must not activate host GVfs services.
repo=Path(__file__).resolve().parent.parent
profiles=runpy.run_path(str(repo/'scripts/madway_motion_presets.py'))
with tempfile.TemporaryDirectory(prefix='madway-window-motion-') as tmp:
 root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700);config=root/'config';(config/'madway').mkdir(parents=True)
 ini=config/'madway/settings.ini';cfg=configparser.ConfigParser(interpolation=None)
 cfg.read_string('[appearance]\ntheme=black\n[windows]\nopen_animate=true\nopen_ms=600\nanimate=true\nclose_animate=false\n[panel]\nenabled=false\n[dock]\nenabled=false\n[desktop]\nicons=false\n[notifications]\nenabled=false\n[session_effects]\nopening=false\n[wallpaper]\ntype=color\ncolor=#102030\n[output:HEADLESS-1]\nmode=800x600@100000\nx=0\ny=0\n[output:HEADLESS-2]\nmode=800x600@60000\nx=800\ny=0\n')
 def save():
  with ini.open('w') as output:cfg.write(output)
 save()
 flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server','xkbcommon'],text=True).split()
 preload=root/'probe.so'
 subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','-Isrc','-I'+str(repo/'build/protocols'),str(repo/'tests/dock_probe.c'),'-o',str(preload),*flags,'-ldl'],cwd=repo,check=True)
 program=root/'app.py';program.write_text('''import cairo,gi,sys
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib,Gdk
GLib.set_prgname('org.madway.MotionFixture')
window=Gtk.Window(title=sys.argv[1]);window.set_decorated(False);window.set_default_size(400,260)
visual=window.get_screen().get_rgba_visual()
if visual:window.set_visual(visual)
provider=Gtk.CssProvider();provider.load_from_data(b'window { background: transparent; }')
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
canvas=Gtk.DrawingArea();window.add(canvas)
def draw(widget,cr):
 cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint();cr.set_operator(cairo.OPERATOR_OVER)
 cr.set_source_rgba(.8,.2,.4,.8);cr.rectangle(18,18,widget.get_allocated_width()-36,widget.get_allocated_height()-36);cr.fill()
canvas.connect('draw',draw);window.connect('destroy',Gtk.main_quit)
if len(sys.argv)>2 and sys.argv[2]=='fullscreen':window.fullscreen()
window.show_all();Gtk.main()
''')
 program.write_text(program.read_text().replace('window.show_all();Gtk.main()', '''window.show_all()
if len(sys.argv)>2 and sys.argv[2]=='dialog':
 def dialog():
  child=Gtk.Dialog(title='dialog-child',transient_for=window,modal=True);child.set_default_size(240,100)
  child.get_content_area().add(Gtk.Label(label='A normal application dialog'));child.show_all();return False
 GLib.timeout_add(200,dialog)
Gtk.main()'''))
 env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
      'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman','MADWAY_SESSION':'1',
      'GDK_BACKEND':'wayland','LIBGL_ALWAYS_SOFTWARE':'1','GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),
      'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery'),'MADWAY_DOCK_TEST':tmp,'MADWAY_MOTION_TEST':'1','MADWAY_FRAME_TEST':str(root/'frames.jsonl')}
 for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','LD_PRELOAD'):env.pop(key,None)
 processes=[];logs=[];directory=None
 def spawn(name,args,environment=env):
  log=(root/(name+'.log')).open('w');logs.append(log)
  process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
 def probe():
  try:return json.loads((root/'probe.json').read_text())
  except (OSError,ValueError):return {}
 def state():
  try:return json.loads((directory/'desktop.json').read_text())
  except (OSError,ValueError,TypeError):return {}
 def rows():return {row['title']:row for row in state().get('all_windows',[])}
 def wait(check,timeout=5):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   if check():return
   assert processes[0].poll() is None,(root/'server.log').read_text()
   time.sleep(.008)
  raise AssertionError((root/'server.log').read_text()+'\nPROBE '+str(probe()))
 def send(name,**values):
  with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
 def apply():save();send('apply');time.sleep(.12)
 def command(number):
  path=root/'command.tmp';path.write_text(str(number));path.replace(root/'command');wait(lambda:probe().get('command')==number)
 def move(x,y):
  (root/'point').write_text(f'{x} {y}');command(20 if probe().get('command')!=20 else 25)
 def sample():
  values=[];deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   value=probe();values.append(value)
   if not value.get('motion'):break
   time.sleep(.012)
  assert values and not values[-1].get('motion'),values[-1:]
  return [row for row in values if row.get('motion')]
 def stop(process,title):
  process.terminate();process.wait(timeout=3);wait(lambda:title not in rows() and not probe().get('motion'))
 try:
  spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':str(preload)})
  wait(lambda:'desktop services ready' in (root/'server.log').read_text(),10)
  env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',(root/'server.log').read_text())[1]
  directory=runtime/('madway-'+env['WAYLAND_DISPLAY']);wait(lambda:bool(probe()))
  move(200,150) # Explicitly launch on the 100 Hz head, not the initial cursor center.
  for name,(_,values) in profiles['OPENING'].items():
   cfg['windows'].update(values);cfg['windows'].update(open_preset=name,open_ms='600',open_animate='true');apply()
   client=spawn(name,[sys.executable,str(program),name]);wait(lambda:name in rows() and probe().get('motion'))
   assert rows()[name]['app_id']=='org.madway.MotionFixture' and not probe()['view_enabled']
   if name=='fade':
    import gi
    gi.require_version('GdkPixbuf','2.0')
    from gi.repository import GdkPixbuf
    current=probe();image=root/'alpha.png'
    subprocess.run(['grim','-o','HEADLESS-1',str(image)],env=env,check=True)
    pixels=GdkPixbuf.Pixbuf.new_from_file(str(image));x=current['motion_x']+current['motion_width']-6;y=current['motion_y']+current['motion_height']-6
    offset=y*pixels.get_rowstride()+x*pixels.get_n_channels();color=pixels.get_pixels()[offset:offset+3]
    assert max(abs(a-b) for a,b in zip(color,(16,32,48)))<=4,('Transparent window corner became opaque',list(color))
    assert probe()['motion'],'Alpha sample was captured after the animation'
   samples=sample();assert len(samples)>=10 and any(0<row['motion_opacity']<1 for row in samples)
   if name in ('soft','spring'):assert min(row['motion_width'] for row in samples)<390
   elif name=='fade':assert len({row['motion_width'] for row in samples})==1
   elif name=='rise':assert max(row['motion_y']-row['view_y'] for row in samples)>10
   elif name=='slide':assert min(row['motion_x']-row['view_x'] for row in samples)<-5
   assert probe()['view_enabled'];stop(client,name)
  print('PASS: all opening presets animate ordinary app IDs and restore the live surface.',flush=True)
  cfg['windows']['animate']='false';apply()
  independent=spawn('independent-open',[sys.executable,str(program),'independent-open']);wait(lambda:'independent-open' in rows() and probe()['motion'])
  sample();stop(independent,'independent-open');cfg['windows']['animate']='true'
  cfg['windows']['open_animate']='false';apply();wait(lambda:not probe()['open_enabled'])
  client=spawn('state-client',[sys.executable,str(program),'state-client']);wait(lambda:'state-client' in rows());time.sleep(.1);assert not probe().get('motion')
  cfg['windows'].update(profiles['OPENING']['soft'][1]);cfg['windows'].update(default_mode='tiled',open_animate='true',open_ms='600');apply()
  tile=spawn('tiled-open',[sys.executable,str(program),'tiled-open']);wait(lambda:'tiled-open' in rows() and probe()['motion'])
  assert not rows()['tiled-open']['floating'];sample();assert probe()['view_enabled'] and probe()['view_width']>700;stop(tile,'tiled-open')
  cfg['windows']['default_mode']='floating';apply()
  dialog=spawn('dialog-app',[sys.executable,str(program),'dialog-app','dialog']);wait(lambda:'dialog-child' in rows() and probe()['motion'])
  assert rows()['dialog-child']['floating'];sample();stop(dialog,'dialog-app')
  cfg['windows']['open_animate']='false';apply()
  print('PASS: tiled first-map reconfigure and transient application dialogs use the opening profile.',flush=True)
  for name,(_,values) in profiles['MAXIMIZE'].items():
   cfg['windows'].update(values);cfg['windows'].update(maximize_preset=name,maximize_ms='600');apply()
   send('window-maximize');wait(lambda:probe()['view_maximized'])
   if name=='instant':assert not probe()['motion']
   else:
    wait(lambda:probe()['motion']);samples=sample();assert len(samples)>=8
    if name=='dissolve':assert all(row['incoming'] for row in samples) and any(0<row['motion_opacity']<1 for row in samples)
    else:assert len({row['motion_width'] for row in samples})>8
   send('window-maximize');wait(lambda:not probe()['view_maximized'])
   if name!='instant':wait(lambda:probe()['motion']);sample()
   assert probe()['view_enabled']
  print('PASS: maximize/restore zoom, responsive, spring, dissolve and instant presets.',flush=True)
  cfg['windows'].update(maximize_style='zoom',maximize_curve='spring',maximize_ms='600');apply()
  send('window-maximize');wait(lambda:probe()['motion']);time.sleep(.1);before=probe()['motion_width']
  send('window-maximize');wait(lambda:not probe()['view_maximized'] and probe()['motion']);after=probe()['motion_width']
  assert abs(after-before)<100,('Reversal jumped',before,after);sample()
  cfg['windows'].update(open_animate='true',open_style='zoom',open_scale='75',open_ms='600',open_fade='true');apply()
  extra=spawn('click-open',[sys.executable,str(program),'click-open']);wait(lambda:'click-open' in rows() and probe()['motion'])
  move(probe()['view_x']+200,probe()['view_y']+130);command(21);command(22)
  wait(lambda:not probe()['motion']);assert probe()['view_enabled'];stop(extra,'click-open')
  extra=spawn('close-open',[sys.executable,str(program),'close-open']);wait(lambda:'close-open' in rows() and probe()['motion']);stop(extra,'close-open')
  extra=spawn('fullscreen-open',[sys.executable,str(program),'fullscreen-open','fullscreen']);wait(lambda:'fullscreen-open' in rows() and probe()['motion'])
  assert probe()['view_fullscreen'];samples=sample();assert len({row['motion_width'] for row in samples})==1
  stop(extra,'fullscreen-open')
  move(1100,180);cfg['windows'].update(profiles['OPENING']['soft'][1]);cfg['windows']['open_ms']='600';apply()
  extra=spawn('slow-head',[sys.executable,str(program),'slow-head']);wait(lambda:'slow-head' in rows() and probe()['motion'])
  assert rows()['slow-head']['output']=='HEADLESS-2';sample();stop(extra,'slow-head')
  trace=[json.loads(line) for line in (root/'frames.jsonl').read_text().splitlines()]
  active=[row for row in trace if row['motion'] and row['output']=='HEADLESS-1'];assert len(active)>100 and all(row['refresh']==100000 for row in active)
  assert sum(row['motion'] and row['output']=='HEADLESS-2' and row['refresh']==60000 for row in trace)>=20
  intervals=[b['time']-a['time'] for a,b in zip(active,active[1:]) if 0<b['time']-a['time']<.03]
  assert intervals and sum(intervals)/len(intervals)<.016,('100 Hz frame cadence lost',intervals[:20])
  print('PASS: opening disabled, smooth reversal, click-to-settle, close-during-open, fullscreen first-map fade and actual 100 Hz commit cadence.',flush=True)
 except BaseException:
  print((root/'server.log').read_text());raise
 finally:
  for process in reversed(processes):
   if process.poll() is None:
    process.terminate()
    try:process.wait(timeout=4)
    except subprocess.TimeoutExpired:process.kill();process.wait()
  for log in logs:log.close()
  target=os.environ.get('MADWAY_TEST_ARTIFACTS')
  if target:
   out=Path(target);out.mkdir(parents=True,exist_ok=True)
   for file in ('server.log','frames.jsonl'):
    if (root/file).exists():(out/file).write_text((root/file).read_text())
