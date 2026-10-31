"""File operations use only a disposable home/Desktop/Trash."""
import os
from pathlib import Path
import runpy
import tempfile

repo=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='madway-files-') as tmp:
    root=Path(tmp);os.environ.update(HOME=tmp,XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'))
    api=runpy.run_path(str(repo/'scripts/madway_files.py'))
    desktop=root/'Desktop';source=root/'source';source.mkdir()
    assert not desktop.exists()
    folder=api['create'](desktop,'Projects',True);assert folder.is_dir()
    text=api['create'](desktop,'Notes.txt');text.write_text('keep me')
    for name in ['../escape','.','..','bad/name','bad\0name','']:
        try:api['create'](desktop,name)
        except ValueError:pass
        else:raise AssertionError('Unsafe name accepted')
    try:api['create'](desktop,'Notes.txt')
    except FileExistsError:pass
    else:raise AssertionError('Existing file overwritten')
    assert text.read_text()=='keep me'
    second=api['create'](desktop,'Second.txt')
    try:api['rename'](text,'Second.txt')
    except Exception:pass
    else:raise AssertionError('Rename overwrote another file')
    assert text.read_text()=='keep me' and second.read_bytes()==b''
    renamed=api['rename'](text,'Renamed.txt');assert renamed.read_text()=='keep me' and not text.exists()
    original=source/'File.txt';original.write_text('original')
    copied=api['transfer']([original.as_uri()],desktop)[0];assert copied.read_text()=='original' and original.exists()
    duplicate=api['transfer']([original.as_uri()],desktop)[0];assert duplicate.name=='File (copy).txt'
    tree=source/'Tree';tree.mkdir();(tree/'inner.txt').write_text('tree')
    (tree/'link').symlink_to(original)
    clone=api['transfer']([tree.as_uri()],desktop)[0]
    assert (clone/'inner.txt').read_text()=='tree' and (clone/'link').is_symlink()
    try:api['transfer']([tree.as_uri()],tree/'child')
    except ValueError:pass
    else:raise AssertionError('Recursive self-copy accepted')
    assert not (tree/'child').exists()
    moved=api['transfer']([original.as_uri()],desktop,True)[0]
    assert not original.exists() and moved.read_text()=='original'
    assert api['transfer']([moved.as_uri()],desktop,True)==[moved]
    try:api['local_paths'](['https://example.invalid/file'])
    except ValueError:pass
    else:raise AssertionError('Non-local URI accepted')
    api['trash']([renamed]);assert not renamed.exists()
    assert any(p.read_text()=='keep me' for p in (root/'data/Trash/files').iterdir())
    assert not list(desktop.glob('.madway-copy-*'))
print('PASS: safe names, exclusive create/rename, duplicate copy, recursive folders/symlinks, self-copy rejection, move, private Trash and staging cleanup.')
