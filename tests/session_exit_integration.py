"""Real two-output rendering; every systemctl operation is a local rejecting stub."""
import configparser
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf
repo=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='madway-exit-integration-') as tmp:
    root=Path(tmp);runtime=root/'runtime';runtime.mkdir(mode=0o700);config=root/'config';(config/'madway').mkdir(parents=True)
    ini=config/'madway/settings.ini';ini.write_text('[appearance]\ntheme=argent-dark\n[dock]\nenabled=false\n[desktop]\nicons=false\n[notifications]\nenabled=false\n[panel]\nmetrics=false\n[wallpaper]\ntype=color\ncolor=#131820\n[session_effects]\nopening=true\nopening_ms=300\nmode=fade\nshader=crt\nduration_ms=300\n[output:HEADLESS-1]\nmode=800x600@100000\nx=0\ny=0\n[output:HEADLESS-2]\nmode=800x600@60000\nx=800\ny=0\n')
    binaries=root/'bin';binaries.mkdir();calls=root/'requests'
    stub=binaries/'systemctl';stub.write_text('#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\nwith Path('+repr(str(calls))+').open("a") as output:output.write(sys.argv[-1]+"\\n")\nprint("mock power request rejected",file=sys.stderr)\nsys.exit(1)\n');stub.chmod(0o700)
    audio_log=root/'audio.jsonl';power_log=root/'power.jsonl'
    sound=root/'tone.ogg';sound.write_bytes(b'mock audio')
    with ini.open('a') as out:out.write('\n[sounds]\nenabled=true\nlogon='+str(sound)+'\nlogout='+str(sound)+'\nshutdown='+str(sound)+'\n')
    player=binaries/'pw-play'
    player.write_text('#!'+sys.executable+'\n'+"import json,time\nfrom pathlib import Path\np=Path("+repr(str(audio_log))+")\nwith p.open('a') as f:f.write(json.dumps(dict(phase='start',time=time.monotonic()))+'\\n')\ntime.sleep(.55)\nwith p.open('a') as f:f.write(json.dumps(dict(phase='end',time=time.monotonic()))+'\\n')\n")
    player.chmod(0o700)
    stub.write_text(stub.read_text().replace('import sys\n','import sys,time\n').replace('print("mock power',"with Path("+repr(str(power_log))+").open('a') as f:f.write(str(time.monotonic())+'\\n')\nprint(\"mock power"))
    env={**os.environ,'HOME':tmp,'XDG_CONFIG_HOME':str(config),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),
        'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'2','WLR_RENDERER':'pixman','MADWAY_SESSION':'1',
        'GDK_BACKEND':'wayland','LIBGL_ALWAYS_SOFTWARE':'1','PATH':str(binaries)+':'+os.environ['PATH'],
        'GIO_USE_VFS':'local','DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(root/'no-system-bus'),'MADWAY_POWER_SUPPLY_PATH':str(root/'no-battery')}
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','MADWAY_NATIVE'):env.pop(key,None)
    log_path=root/'server.log'
    with log_path.open('w') as log:
        server=subprocess.Popen([os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],env=env,stdout=log,stderr=log)
        def text():return log_path.read_text()
        def wait(check,timeout=10):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                assert server.poll() is None,text()
                if check():return
                time.sleep(.02)
            raise AssertionError(text())
        try:
            wait(lambda:'desktop services ready' in text());env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text())[1]
            directory=runtime/('madway-'+env['WAYLAND_DISPLAY'])
            def send(name,**values):
                with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(json.dumps(dict(action=name,**values)).encode(),str(directory/'control.sock'))
            def read_calls():return calls.read_text().splitlines() if calls.exists() else []
            def center(output):
                path=root/'frame.png';subprocess.run(['grim','-o',output,str(path)],env=env,check=True,stdout=subprocess.DEVNULL)
                image=GdkPixbuf.Pixbuf.new_from_file(str(path));i=(image.get_height()//2)*image.get_rowstride()+image.get_width()//2*image.get_n_channels();return tuple(image.get_pixels()[i:i+3])
            wait(lambda:text().count('Desktop layer mapped: madway-panel')==2)
            def audio():return [json.loads(line) for line in audio_log.read_text().splitlines()] if audio_log.exists() else []
            wait(lambda:len(audio())>=2)
            opening_start=float(re.search(r'session opening started at ([0-9.]+)',text())[1])
            assert 0<=audio()[0]['time']-opening_start<.35
            wait(lambda:center('HEADLESS-1')==(19,24,32))
            cfg=configparser.ConfigParser(interpolation=None);cfg.read(ini)
            for index,(mode,shader) in enumerate([('fade','crt'),('shader','crt'),('shader','iris'),('shader','dissolve')]):
                cfg['session_effects'].update(mode=mode,shader=shader)
                with ini.open('w') as output:cfg.write(output)
                send('apply');time.sleep(.15);before=text().count('Desktop layer mapped: madway-session-exit')
                send('reboot');send('poweroff') # duplicates cannot start a second operation
                wait(lambda:len(read_calls())==index+1)
                wait(lambda:text().count('Desktop layer mapped: madway-session-exit')>=before+2)
                assert read_calls()[-1]=='reboot',read_calls()
                playback=audio()[-2:];start=float(re.findall(r'session closing started at ([0-9.]+)',text())[-1])
                assert playback[0]['phase']=='start' and 0<=playback[0]['time']-start<.35,playback
                power=float(power_log.read_text().splitlines()[-1]);assert playback[1]['time']<=power<playback[1]['time']+.3,playback
                wait(lambda:center('HEADLESS-1')==(19,24,32) and center('HEADLESS-2')==(19,24,32))
                if mode=='shader':assert 'session shader ready: '+shader in text(),text()
            before=len(read_calls());send('session-effect-preview',mode='shader',shader='iris',duration=300)
            time.sleep(1.8);assert len(read_calls())==before
            assert center('HEADLESS-1')==(19,24,32) and center('HEADLESS-2')==(19,24,32)
            assert 'Traceback' not in text(),text()
            send('logout');assert server.wait(timeout=8)==0,text()
            assert len(read_calls())==before
            print('PASS: opening/exit sounds begin with animation, playback overlaps visuals without replay, and simple fade and all three shaders render across 100/60 Hz outputs, duplicate exit requests collapse to one, mocked rejected power actions restore both desktops, previews perform no system action, and shader logout terminates only the private compositor.')
        finally:
            server.terminate()
            try:server.wait(timeout=6)
            except subprocess.TimeoutExpired:server.kill();server.wait()
