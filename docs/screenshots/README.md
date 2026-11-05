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

The Midnight settings capture shows the grouped, searchable settings browser.
Regenerate it on a private display:

```sh
MADWAY_EXTENSION_UI=settings_redesign_ui.py MADWAY_TEST_ARTIFACTS="$PWD/build/settings-redesign-review" dbus-run-session -- python3 tests/desktop_extensions.py
```

Use `build/settings-redesign-review/settings-appearance.png` for `settings.png`.
The desktop-file capture comes from `tests/desktop_files.py`, whose temporary
Desktop contains only fixture folders and files on a solid-color background;
its output is `build/desktop-icons.png`. Neither fixture uses personal wallpaper
or sound files.

Regenerate the workstation, menu, mixer, launcher, switcher and panel captures
from the repository root after building:

```sh
dbus-run-session -- python3 tests/capture_desktop.py
```

Requires Kitty, Firefox, grim, PyGObject/GTK/layer-shell, the desktop dependencies,
and Wayland client/server development files. The test-only capture probe arranges
the real windows and right-clicks the private desktop; it never injects host input.
