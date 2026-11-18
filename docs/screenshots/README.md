# Desktop screenshots

These are actual `grim` captures of isolated madway sessions with Konsole,
Firefox and madway Settings. The current gallery features three modern profiles:

- [Argent · Midnight workstation](workstation.png)
- [Argent · Silver workstation](workstation-light.png)
- [Prism · Glass workstation](theme-glass.png)
- [Desktop utility menu](desktop-menu.png)
- [Panel audio mixer](panel-audio.png)
- [Application search and inline autocomplete](launcher.png)
- [Window switcher](switcher.png)
- [Left panel](panel-left.png)
- [Bottom panel](panel-bottom.png)
- [Midnight settings](settings.png)
- [Light settings](settings-light.png)
- [Opening/maximize animation settings](window-animations.png)
- [Playback settings](settings-audio.png)
- [Desktop files](desktop-files.png)

The browser displays `tests/fixtures/overview.html` from a temporary local HTTP
server; its palette follows the selected profile. Konsole runs the version and
source-listing commands. A generated gradient/curve background makes the Glass
transparency visible. This test-only background is not installed as a wallpaper.
Temporary homes, app profiles, XDG directories, a private D-Bus session and a
headless Wayland output keep personal data and ignored Longhorn assets out of
the images. Session sounds and notifications are disabled.

The audio mixer uses deterministic mock speakers, microphone and application
streams. Its real GTK controls never read or change host audio.

After building, regenerate the Midnight workstation, menu, mixer, launcher,
switcher and panel images:

```sh
dbus-run-session -- python3 tests/capture_desktop.py --theme argent-dark
```

Generate the other workstation variants in a build directory, then publish the
selected images:

```sh
dbus-run-session -- python3 tests/capture_desktop.py --theme argent --hero-only --output-dir build/screenshots-modern/silver
cp build/screenshots-modern/silver/workstation.png docs/screenshots/workstation-light.png
dbus-run-session -- python3 tests/capture_desktop.py --theme prism-glass --hero-only --output-dir build/screenshots-modern/glass
cp build/screenshots-modern/glass/workstation.png docs/screenshots/theme-glass.png
```

Requires Konsole, Firefox, grim, Pycairo, PyGObject/GTK/layer-shell, the desktop
runtime dependencies, and Wayland client/server development files. The test-only
probe arranges real windows, right-clicks the private desktop and types a launcher
query; it never injects input into the host session.

The separate Settings captures use `tests/desktop_extensions.py`:

```sh
MADWAY_TEST_THEME=argent-dark MADWAY_EXTENSION_UI=settings_redesign_ui.py MADWAY_TEST_ARTIFACTS="$PWD/build/settings-redesign-review" dbus-run-session -- python3 tests/desktop_extensions.py
```

Use `build/settings-redesign-review/settings-appearance.png` for `settings.png`;
repeat with `MADWAY_TEST_THEME=argent` for `settings-light.png`.
`tests/window_motion_settings_ui.py` generates `window-animations.png`, and
`tests/playback_ui.py` generates `settings-audio.png`, using the same harness and
`MADWAY_EXTENSION_UI` / `MADWAY_TEST_ARTIFACTS` variables. They contain fixture
configuration and fake audio devices only.

The desktop-file image comes from `tests/desktop_files.py`; its temporary Desktop
contains fixture folders and files on a solid background. The output is
`build/desktop-icons.png`.

Supplementary [XP](theme-xp.png) and [Vista](theme-vista.png) images use
`tests/theme_profiles_ui.py` with `MADWAY_TEST_THEME=windows-xp` or `windows-vista`
and `MADWAY_TEST_DOCK=1`. These contain no Microsoft media assets or personal
wallpaper. `tests/prism_glass_ui.py` separately validates real client alpha and
opaque labels, and saves its diagnostic capture under
`build/reference-settings-review/prism-glass.png`.
