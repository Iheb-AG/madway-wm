# Desktop files and drag-and-drop

Madway's desktop icon surface shows the XDG Desktop directory, normally
`~/Desktop`. It reads the directory on startup and watches for additions,
renames and removals made by other applications. A missing Desktop directory
is not created until a file action needs it. Hidden files are omitted.

Open **Settings → Desktop** to enable/disable icons, choose another directory
or set the icon size (24–64 px). Icons appear on the primary monitor; other
monitors still provide a desktop drop surface and the same right-click menu.
The surface stays below application windows and clear of panels/dock work areas.

Right-click empty desktop space and choose **Hide desktop icons** to hide the
file view. Right-click the empty background again and choose **Show desktop
icons** to restore it. The preference is saved, and files, folders and icon order
remain untouched. The same toggle is available in the panel's desktop menu.

| Action | Control |
| --- | --- |
| Open a file/folder | Double-click or keyboard activation |
| Create a folder/text file | Right-click empty desktop space |
| Rename an item | Right-click → Rename, or F2 |
| Copy/paste files | Right-click controls, or Ctrl+C / Ctrl+V |
| Remove an item | Right-click → Move to Trash, or Delete |
| Refresh | F5 or right-click → Refresh |
| Open a file manager | Right-click → Open Desktop folder |

Deletion uses the system Trash. If Trash is unavailable, the operation reports
an error; it never falls back to permanent deletion. Creating or renaming an
item refuses to overwrite an existing path. Copies with duplicate names receive
`(copy)`, `(copy 2)`, etc. File operations run outside the compositor and use a
worker thread in the desktop helper. Directory copies preserve symlinks and
stage incomplete copies in a hidden temporary directory before publishing them.
Interrupted processes can leave a hidden staging directory; the original
source remains intact.

Local files can be dragged from a file manager/application onto the desktop or
onto a folder icon. Desktop items can be dragged into applications that accept
`text/uri-list`. External drops copy by default when the source offers COPY;
MOVE is also negotiated when offered/selected. Unsupported filesystem moves
report an error rather than deleting the source. Remote URLs are not downloaded.

Dragging an icon within the desktop reorders the compact grid; order is stored
in `~/.config/madway/desktop-order.json`. Arbitrary pixel positioning is not
implemented. File copy/paste uses the Wayland clipboard's `text/uri-list` type.
Application-to-application text/image/file drags use the normal Wayland data
device protocol, with MIME types and accepted actions negotiated by the apps.

The compositor validates the initiating pointer-grab serial, forwards drag
focus across windows/outputs and renders the drag icon. Escape, locking, sleep
and workspace changes cancel an in-progress pointer drag before synthesizing
button releases, preventing an unintended drop. Desktop file menus are raised
above application windows and removed with their parent surface.

The standalone `madway-desktop` helper is started/stopped by `madway-shell`.
Preferences:

```ini
[desktop]
icons = true
folder =
icon_size = 40
```

Settings uses a compact form with flat square controls, one-pixel frames,
smaller category rows and an accent stripe for the selected category. Compound
numeric/dropdown controls have one outer frame. Theme colors are retained.

Validation uses a disposable home, Desktop, clipboard and Trash:

```sh
python3 tests/files.py
dbus-run-session -- python3 tests/desktop_files.py
```

These tests exercise actual pointer/keyboard input, native create/Trash menus,
clipboard copy/paste, URI drags in both directions, folder targets, popup stacking,
Escape and lock cancellation. They do not touch the user's Desktop or authenticate
against the host session. The desktop and compositor changes require reinstalling
and starting a new session.
