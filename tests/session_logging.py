"""Exercise native launcher disk failures with a fake compositor and /dev/full."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

repo=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='madway-log-test-') as tmp:
    root=Path(tmp);binaries=root/'bin';binaries.mkdir()
    shutil.copy2(repo/'scripts/madway-session',binaries/'madway-session')
    (binaries/'madway').write_text('#!/usr/bin/env python3\nimport json,os\nprint(json.dumps({"started":True,"native":os.environ.get("MADWAY_NATIVE")}))\n')
    (binaries/'madway').chmod(0o755)
    state=root/'state';(state/'madway').mkdir(parents=True)
    runtime=root/'runtime';runtime.mkdir(mode=0o700)
    env={**os.environ,'HOME':str(root),'XDG_STATE_HOME':str(state),'XDG_RUNTIME_DIR':str(runtime),
         'DBUS_SESSION_BUS_ADDRESS':'unix:path=/unused-madway-test-bus'}
    launch=[str(binaries/'madway-session'),'--native']
    # The previous set -e + first printf behaviour exits before exec on ENOSPC.
    old=subprocess.run(['/bin/sh','-c','set -e; exec >/dev/full 2>/dev/null; printf "session start\\n"; exit 99'],env=env)
    assert old.returncode not in (0,99)
    persistent=state/'madway/session.log'
    persistent.symlink_to('/dev/full')
    previous=state/'madway/session.previous.log';previous.write_text('last useful session')
    result=subprocess.run(launch,env=env,capture_output=True,text=True,check=True)
    fallback=runtime/'madway-logs/session.log'
    assert 'persistent log unavailable' in result.stderr
    assert '"started": true' in fallback.read_text() and '"native": "1"' in fallback.read_text()
    assert previous.read_text()=='last useful session'
    assert fallback.stat().st_mode & 0o077 == 0
    # If both locations fail, the compositor must still be executed.
    fallback.unlink();fallback.symlink_to('/dev/full')
    result=subprocess.run(launch,env=env,capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==dict(started=True,native='1')
    assert 'file logging unavailable' in result.stderr
    # A state path which cannot be a directory also uses the runtime log.
    blocked=root/'blocked';blocked.write_text('not a directory')
    fallback.unlink()
    subprocess.run(launch,env={**env,'XDG_STATE_HOME':str(blocked)},capture_output=True,text=True,check=True)
    assert '"started": true' in fallback.read_text()
    # Successful attempts remain private and keep one previous nonempty log.
    persistent.unlink()
    subprocess.run(launch,env=env,check=True)
    first=persistent.read_text()
    subprocess.run(launch,env=env,check=True)
    assert previous.read_text()==first and persistent.stat().st_mode & 0o077==0
print('PASS: ENOSPC reproduced; runtime fallback, no-file fallback, blocked directories and log rotation preserve compositor startup.')
