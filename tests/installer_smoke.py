"""Stage installation and validate launcher environments; never install on the host."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

repo=Path(__file__).resolve().parent.parent
installer=repo/'scripts/install-madway'
with tempfile.TemporaryDirectory(prefix='madway-installer-test-') as tmp:
    root=Path(tmp);stage=root/'stage';build=root/'build'
    args=[str(installer),'--destdir',str(stage),'--build-dir',str(build)]
    subprocess.run([*args,'--dry-run'],check=True,stdout=subprocess.DEVNULL)
    assert not stage.exists() and not build.exists()
    result=subprocess.run([*args,'--deps'],capture_output=True,text=True)
    assert result.returncode==2 and not stage.exists()
    subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
    binaries=stage/'usr/local/bin'
    for name in ('madway','madway-session','madway-shell','madway-panel','madway-script'):
        assert os.access(binaries/name,os.X_OK)
    entry=stage/'usr/share/wayland-sessions/madway.desktop'
    assert 'Exec=/usr/local/bin/madway-session --native' in entry.read_text()
    assert not any(path.suffix in ('.ogg','.mp3','.wav','.jpg','.flp') for path in stage.rglob('*'))
    if shutil.which('desktop-file-validate'):
        subprocess.run(['desktop-file-validate',str(entry)],check=True)
    fake=root/'fake-bin';fake.mkdir()
    shutil.copy2(binaries/'madway-session',fake/'madway-session')
    (fake/'madway').write_text('''#!/usr/bin/env python3
import json,os,sys
names=['WAYLAND_DISPLAY','WAYLAND_SOCKET','DISPLAY','WLR_BACKENDS','MADWAY_NATIVE','MADWAY_SESSION','XDG_CURRENT_DESKTOP','XDG_SESSION_TYPE']
print(json.dumps(dict(environment={name:os.environ.get(name) for name in names},arguments=sys.argv[1:])))
''')
    (fake/'madway').chmod(0o755)
    env=os.environ.copy();env.update(WAYLAND_DISPLAY='host-display',WAYLAND_SOCKET='123',DISPLAY=':456',
        WLR_BACKENDS='wayland',MADWAY_NATIVE='old-value',DBUS_SESSION_BUS_ADDRESS='unix:path=/tmp/madway-fake-user-bus')
    data=json.loads(subprocess.check_output([str(fake/'madway-session'),'--native','--version'],env=env,text=True))
    assert data['arguments']==['--version']
    assert all(data['environment'][name] is None for name in ('WAYLAND_DISPLAY','WAYLAND_SOCKET','DISPLAY'))
    assert data['environment']['WLR_BACKENDS']=='drm,libinput'
    assert data['environment']['MADWAY_NATIVE']=='1' and data['environment']['MADWAY_SESSION']=='1'
    assert data['environment']['XDG_CURRENT_DESKTOP']=='madway' and data['environment']['XDG_SESSION_TYPE']=='wayland'
    private_runtime=root/'runtime';private_runtime.mkdir(mode=0o700)
    no_bus={**env,'XDG_RUNTIME_DIR':str(private_runtime)};no_bus.pop('DBUS_SESSION_BUS_ADDRESS',None)
    data=json.loads(subprocess.check_output([str(fake/'madway-session'),'--native','--version'],env=no_bus,text=True))
    assert data['environment']['MADWAY_NATIVE']=='1'
    data=json.loads(subprocess.check_output([str(fake/'madway-session'),'--version'],env=env,text=True))
    assert data['environment']['MADWAY_NATIVE'] is None
    assert data['environment']['WAYLAND_DISPLAY']=='host-display'
    # Match Plasma Login's installed wayland-session script: exec $@.
    # It receives the complete Exec field as one argument, without shell eval.
    command=next(line[5:] for line in entry.read_text().splitlines() if line.startswith('Exec='))
    command=command.replace('/usr/local/bin',str(fake))+' --version'
    invoke=['/bin/sh','-c','exec $@','login-session']
    data=json.loads(subprocess.check_output([*invoke,command],env=env,text=True))
    assert data['environment']['MADWAY_NATIVE']=='1' and data['arguments']==['--version']
    broken='"'+str(fake/'madway-session')+'" --native --version'
    failure=subprocess.run([*invoke,broken],env=env,capture_output=True,text=True)
    assert failure.returncode==127, failure
    # Use only a fake compositor: this tests persistent logs without DRM/VT access.
    native_env={**env,'XDG_STATE_HOME':str(root/'state')}
    subprocess.run([str(fake/'madway-session'),'--native'],env=native_env,check=True)
    log=root/'state/madway/session.log'
    assert 'madway native session:' in log.read_text()
    assert '"MADWAY_NATIVE": "1"' in log.read_text()
    assert log.stat().st_mode & 0o077 == 0
    subprocess.run([str(fake/'madway-session'),'--native'],env=native_env,check=True)
    assert (log.parent/'session.previous.log').exists()
    invalid=subprocess.run([*args,'--dry-run','--prefix','/tmp/madway prefix'],capture_output=True,text=True)
    assert invalid.returncode==2
    print('PASS: login-manager Exec compatibility, quoted-path failure reproduced, and private native log rotation.')
print('PASS: dry run, staged native-session installation, no personal assets, and native/nested launcher environment separation.')
