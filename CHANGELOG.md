# Changelog

## 0.1.0-alpha.1 — 2026-10-26

First experimental source release of madway. This preview is intended for
testing as a nested Wayland workstation inside an existing desktop.

### Included

- Native Wayland applications through xdg-shell, keyboard/pointer input,
  popups, and the standard clipboard data-device protocol.
- Master/stack tiling, floating windows, nine global workspaces, focus cycling,
  fullscreen, maximize/restore, and interactive move/resize.
- Space-saving decorations: title-free tiles, compact floating titles, square
  controls, and borderless fullscreen.
- Layer-shell support for desktop surfaces and interactive launchers.
- Mako notifications, Wofi application/command launchers, swaybg wallpaper,
  volume/brightness controls with indicators, and a GTK settings window.
- Configurable startup/logout/shutdown sounds with sound-file pickers.
- Alt shortcuts, Kitty terminal launching, and a private D-Bus session wrapper.
- Version reporting with `madway --version`.

### Defaults and dependencies

No personal wallpaper or audio files are distributed. Fresh settings use a
solid background and disable session sounds. Personal media stays outside Git.

Builds require wlroots 0.20 and the development dependencies documented in the
README. Desktop services use external programs, also listed there. Start the
complete desktop through `madway-session`, rather than the compositor alone.

### Validation

Build and isolated integration checks cover real Wayland clients, notifications,
wallpaper surfaces, launcher keyboard input/focus restoration, settings reload,
workspace/fullscreen/tiling behavior, and output resizing/removal. Media controls
and sound event integration use mocked hardware/playback commands.

### Known limits

- This alpha has not been validated as a primary standalone desktop session.
  No display-manager login entry is provided.
- No Xwayland, workspace panel, lock screen, or display-mode settings yet.
- Workspaces are global across outputs. Minimize/restore, clipboard persistence,
  and broader application compatibility need further work.
- Host desktops may intercept shortcuts in nested mode. Brightness requires
  suitable hardware and session access; external-monitor DDC is unsupported.
- Shutdown sounds triggered externally are best effort. The settings power-off
  action shuts down the entire computer, including in nested mode.
- Client-owned decorations and application toolbars remain client-controlled.

See [README.md](README.md) for installation, operation, and testing instructions.
