# Desktop screenshots

These are actual captures of an isolated madway session using `grim`, with real
Kitty, Firefox, and madway settings windows. Firefox displays the local project
fixture in `tests/fixtures/overview.html`; the terminal runs the build/version
commands. A temporary HOME, Firefox profile, and plain background keep personal
data and ignored Longhorn assets out of the images. Session sounds are disabled.

- [Workstation](workstation.png)
- [Desktop utility menu](desktop-menu.png)
- [Panel audio mixer](panel-audio.png)
- [Compact application search](launcher.png)
- [Window switcher](switcher.png)
- [Left panel](panel-left.png)
- [Bottom panel](panel-bottom.png)
- [Compact Midnight settings](settings.png)
- [Desktop files](desktop-files.png)

The mixer capture uses deterministic mock speakers, microphone, and application
stream entries. These demonstrate the real GTK controls without reading or
changing host audio.

The Midnight settings and desktop-file captures come from the private desktop
file integration fixture. Its Desktop contains only a fixture folder and text
files, on a solid-color background. It uses no personal files or wallpaper.
Regenerate these two captures with `tests/desktop_files.py`; the outputs are
`build/settings-compact.png` and `build/desktop-icons.png`.

Regenerate the workstation, menu, mixer, launcher, switcher and panel captures
from the repository root after building:

```sh
dbus-run-session -- python3 tests/capture_desktop.py
```

Requires Kitty, Firefox, grim, PyGObject/GTK/layer-shell, the desktop dependencies,
and Wayland client/server development files. The test-only capture probe arranges
the real windows and right-clicks the private desktop; it never injects host input.
