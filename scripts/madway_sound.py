"""Choose the first native login of a boot without affecting nested previews."""
import fcntl
import os
from pathlib import Path


def login_event(native,state_home=None,boot_file=Path('/proc/sys/kernel/random/boot_id')):
    if not native:return 'logon'
    try:boot=Path(boot_file).read_text().strip()
    except OSError:return 'logon'
    if not boot:return 'logon'
    directory=Path(state_home or os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'madway'
    try:
        directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(directory/'sound-boot',os.O_RDWR|os.O_CREAT|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'r+') as record:
            fcntl.flock(record,fcntl.LOCK_EX)
            previous=record.read().strip()
            if previous==boot:return 'logon'
            record.seek(0);record.write(boot+'\n');record.truncate();record.flush()
            return 'startup'
    except OSError:
        return 'logon'  # An unwritable state directory must not prevent login.
