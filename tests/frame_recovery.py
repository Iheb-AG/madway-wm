"""Fullscreen frame callbacks recover from commit failures without any input."""
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import tempfile
import time

repo=Path(__file__).resolve().parent.parent;os.chdir(repo)
with tempfile.TemporaryDirectory(prefix='madway-frame-recovery-') as tmp:
    root=Path(tmp)
    protocol='/usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml'
    subprocess.run(['wayland-scanner','client-header',protocol,str(root/'xdg-shell-client-protocol.h')],check=True)
    subprocess.run(['wayland-scanner','private-code',protocol,str(root/'protocol.c')],check=True)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True).split()
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-I'+str(root),'tests/video_client.c',str(root/'protocol.c'),'-o',str(root/'video-client'),*flags],check=True)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wlroots-0.20','wayland-server'],text=True).split()
    subprocess.run(['cc','-shared','-fPIC','-DWLR_USE_UNSTABLE','tests/frame_failure_probe.c','-o',str(root/'probe.so'),*flags,'-ldl'],check=True)
    for count,refresh in [(1,60000),(3,60000),(1000,60000),(1,100000)]:
        case=root/f'{count}-{refresh}';case.mkdir();runtime=case/'runtime';runtime.mkdir(mode=0o700)
        config=case/'config';(config/'madway').mkdir(parents=True)
        (config/'madway/settings.ini').write_text(f'[windows]\nanimate=false\n[workspaces]\nanimate=false\n[output:HEADLESS-1]\nmode=640x360@{refresh}\n')
        release=case/'release';trace=case/'frames.jsonl'
        env={**os.environ,'HOME':str(case),'XDG_CONFIG_HOME':str(config),'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'1','WLR_RENDERER':'pixman',
             'MADWAY_TEST_FRAME_FAILURES':str(count),'MADWAY_TEST_FRAME_RELEASE':str(release),'MADWAY_TEST_FRAME_TRACE':str(trace)}
        for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','MADWAY_NATIVE','MADWAY_SESSION','LD_PRELOAD']:env.pop(key,None)
        preload=(os.environ.get('MADWAY_TEST_LIBASAN','')+':'+str(root/'probe.so')).lstrip(':')
        logs=[];processes=[]
        def spawn(name,args,environment):
            log=(case/(name+'.log')).open('w');logs.append(log)
            process=subprocess.Popen(args,env=environment,stdout=log,stderr=log);processes.append(process);return process
        def text():return (case/'server.log').read_text()
        def frames():
            try:return [json.loads(line) for line in trace.read_text().splitlines()]
            except (OSError,ValueError):return []
        def wait(predicate,timeout=10):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                if predicate():return
                assert processes[0].poll() is None,text();time.sleep(.01)
            raise AssertionError(text()+'\n'+(case/'client.log').read_text())
        try:
            spawn('server',[os.environ.get('MADWAY_TEST_BINARY',str(repo/'build/madway'))],{**env,'LD_PRELOAD':preload})
            wait(lambda:'Listening on WAYLAND_DISPLAY=' in text())
            env['WAYLAND_DISPLAY']=re.search(r'Listening on WAYLAND_DISPLAY=(\S+)',text()).group(1)
            def core(command):
                path=runtime/('madway-'+env['WAYLAND_DISPLAY'])/'compositor.sock'
                with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:channel.sendto(command.encode(),str(path))
            client=spawn('client',[str(root/'video-client')],env)
            wait(lambda:any(row['failure'] for row in frames()))
            if count==1000:
                time.sleep(1.1);failed=[row for row in frames() if row['failure']]
                assert 4<=len(failed)<=12,('Retry loop is missing or unbounded',len(failed))
                core('prepare-sleep');time.sleep(.08);before=len(frames());time.sleep(.35)
                assert len(frames())==before,'Retried a sleeping output'
                release.touch();core('resume')
            wait(lambda:client.poll() is not None)
            assert client.returncode==0,(case/'client.log').read_text()
            data=frames();failed=[row for row in data if row['failure']]
            assert len(failed)==count if count<1000 else len(failed)>3
            assert data[-1]['success'] and 'FRAME 120 ' in (case/'client.log').read_text()
            assert 'Window mapped: fullscreen-frame-test' in text()
            print(f'PASS: {refresh/1000:g} Hz, {len(failed)} simulated commit failure(s); 120 fullscreen callbacks completed without mouse/keyboard activity.',flush=True)
        except BaseException:
            for path in case.glob('*.log'):print(path.name+'\n'+path.read_text())
            raise
        finally:
            for process in reversed(processes):
                if process.poll() is None:process.send_signal(signal.SIGTERM)
            for process in reversed(processes):
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            for log in logs:log.close()
