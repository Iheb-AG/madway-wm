"""Local desktop-file operations. Never overwrite or permanently delete an item."""
from pathlib import Path
import os
import shutil
import tempfile
from gi.repository import Gio,GLib


def desktop_directory(config=None):
    custom=config.get('desktop','folder',fallback='').strip() if config else ''
    if custom:return Path(custom).expanduser().absolute()
    special=GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
    path=Path(special) if special else Path.home()/'Desktop'
    return path if path!=Path.home() else Path.home()/'Desktop'


def child(directory,name):
    if not name or name in {'.','..'} or '/' in name or any(ord(c)<32 for c in name):
        raise ValueError('Enter a single file or folder name')
    return Path(directory)/name


def create(directory,name,folder=False):
    path=child(directory,name);path.parent.mkdir(parents=True,exist_ok=True)
    if folder:path.mkdir()
    else:
        with path.open('xb'):pass
    return path


def rename(path,name):
    path=Path(path);target=child(path.parent,name)
    if path==target:return target
    Gio.File.new_for_path(str(path)).move(Gio.File.new_for_path(str(target)),Gio.FileCopyFlags.NONE,None,None,None)
    return target


def trash(paths):
    for path in paths:Gio.File.new_for_path(str(path)).trash(None)


def local_paths(uris):
    result=[]
    for uri in dict.fromkeys(uris):
        path=Gio.File.new_for_uri(uri).get_path()
        if path is None:raise ValueError('Only local files can be dropped onto the desktop')
        item=Path(path)
        if not item.exists() and not item.is_symlink():raise FileNotFoundError(str(item))
        result.append(item)
    if not result:raise ValueError('No files were supplied')
    return result


def available(directory,name):
    target=Path(directory)/name
    if not target.exists() and not target.is_symlink():return target
    original=Path(name)
    for number in range(1,10001):
        suffix=' (copy)' if number==1 else f' (copy {number})'
        target=Path(directory)/(original.stem+suffix+original.suffix)
        if not target.exists() and not target.is_symlink():return target
    raise FileExistsError('Too many files with that name')


def transfer(uris,directory,move=False):
    sources=local_paths(uris);directory=Path(directory)
    # Validate the whole batch before changing anything.
    for source in sources:
        if source.is_dir() and not source.is_symlink() and directory.resolve().is_relative_to(source.resolve()):
            raise ValueError('A folder cannot be placed inside itself')
    directory.mkdir(parents=True,exist_ok=True)
    results=[]
    for source in sources:
        if move and source.parent.resolve()==directory.resolve():results.append(source);continue
        target=available(directory,source.name)
        if move:
            Gio.File.new_for_path(str(source)).move(Gio.File.new_for_path(str(target)),Gio.FileCopyFlags.NONE,None,None,None)
        else:
            # Keep an incomplete copy hidden; publish it only when complete.
            with tempfile.TemporaryDirectory(prefix='.madway-copy-',dir=directory) as staging:
                staged=Path(staging)/source.name
                if source.is_symlink():os.symlink(os.readlink(source),staged)
                elif source.is_dir():shutil.copytree(source,staged,symlinks=True)
                else:shutil.copy2(source,staged,follow_symlinks=False)
                Gio.File.new_for_path(str(staged)).move(Gio.File.new_for_path(str(target)),Gio.FileCopyFlags.NONE,None,None,None)
        results.append(target)
    return results
