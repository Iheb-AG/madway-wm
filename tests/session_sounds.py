"""First native login per boot, private state and nested-session isolation."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import runpy
import tempfile

api=runpy.run_path(str(Path(__file__).resolve().parent.parent/'scripts/madway_sound.py'))
with tempfile.TemporaryDirectory(prefix='madway-sound-test-') as tmp:
    root=Path(tmp);boot=root/'boot';boot.write_text('boot-one\n');state=root/'state'
    event=lambda native=True:api['login_event'](native,state,boot)
    assert event(False)=='logon' and not state.exists()
    assert event()=='startup' and event()=='logon'
    record=state/'madway/sound-boot';assert record.stat().st_mode&0o077==0
    assert event(False)=='logon' and record.read_text().strip()=='boot-one'
    boot.write_text('boot-two\n')
    with ThreadPoolExecutor(max_workers=8) as pool:events=list(pool.map(lambda _:event(),range(8)))
    assert events.count('startup')==1 and events.count('logon')==7
    assert api['login_event'](True,root/'other-user',boot)=='startup'
    assert api['login_event'](True,state,root/'absent')=='logon'
    blocked=root/'not-a-directory';blocked.write_text('original')
    assert api['login_event'](True,blocked,boot)=='logon'
    record.unlink();record.symlink_to(blocked)
    assert event()=='logon' and blocked.read_text()=='original'
print('PASS: boot/startup versus logon, concurrent claims, nested isolation, private permissions and unavailable-state fallback.')
