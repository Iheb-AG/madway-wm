# Desktop screenshots

These are actual captures of an isolated madway session using `grim`, with real
Kitty, Firefox, and madway settings windows. Firefox displays the local project
fixture in `tests/fixtures/overview.html`; the terminal runs the build/version
commands. A temporary HOME, Firefox profile, and plain background keep personal
data and ignored Longhorn assets out of the images. Session sounds are disabled.

- [Workstation](workstation.png)
- [Desktop utility menu](desktop-menu.png)

Regenerate from the repository root after building:

```sh
dbus-run-session -- python3 tests/capture_desktop.py
```

Requires Kitty, Firefox, grim, PyGObject/GTK/layer-shell, the desktop dependencies,
and Wayland client/server development files. The test-only capture probe arranges
the real windows and right-clicks the private desktop; it never injects host input.
