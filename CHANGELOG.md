# Changelog

## Unreleased

- Keep native startup working when persistent logs cannot be written (including
  ENOSPC): fall back to a private runtime log, then login-manager stdout/stderr.
  Preserve the last nonempty log and test disk-full and unwritable-path cases.

- Support all four panel edges with live configuration, compact side-panel buttons,
  correct output reservations, and inward-opening dropdowns.
- Add a per-window Keep above others toggle (modifier+A), including PiP over
  fullscreen apps, workspace visibility and pointer hit testing.
- Add tiled border/modifier resizing with per-output master splits and weighted
  stack heights; retain tiling, gaps and bounded neighbouring sizes.

- Add a visible modifier+Tab window switcher with reverse cycling, release-to-select
  and Escape cancellation; directional tile shortcuts; optional focus on hover.
- Add five shared frame/shell colour profiles and explicit solid-colour backgrounds.
- Add a validated .madway command language, CLI, and opt-in startup command files.

- Fix the native login entry's quoted executable path, which Plasma Login's
  session shell treated literally and rejected with exit status 127. Add a
  matching launcher regression and private rotating native-session logs.

- Add a live audio mixer with device/stream sliders, mute controls, and default
  input/output selection using pactl (PipeWire Pulse or PulseAudio).
- Open Applications and utility submenus beside their parent on hover, preserving
  keyboard navigation, and tighten the centered application/command search UI.

- Tighten shell padding and typography, adopt a black/grayscale palette, and use
  18px panels, 14px custom title bars, and 1px default tile gaps.
- Group Apps/Run/Settings under madway and give every panel control its own
  dropdown: workspaces, window actions, status, audio, clock, and session.

- Add a configurable compact multi-output top bar with workspace/title/status and
  utility controls, plus a shared desktop right-click menu.
- Add a staged/dry-run-aware CachyOS/Arch installer, native DRM/libinput session
  entry, activation-environment setup, and native VT switching. Hardware session
  validation remains open; the existing desktop is left installed.
- Add real application screenshots, capture automation, installation docs, and
  menu/panel/installer regression checks.

- Map each named nested pointer to its own output and refresh mappings after
  layout/hotplug changes, correcting clicks and drags reaching the wrong screen.
- Reuse unchanged compositor cursor images instead of rebuilding them for every
  background motion event. Nested outputs use software cursors to avoid host
  cursor-buffer queue exhaustion. Add primary-selection protocol support and
  forwarding.
- Add real parent/nested-client pointer and copy/paste regression coverage.

- Floating is now the default for new normal windows, with a configurable
  floating/tiled policy. Alt+T is an alternative to Alt+Space; the toggle restores
  fullscreen/maximized windows to floating instead of ignoring the request.
- Categorized settings with a compact compositor-owned title bar, default window
  policy, master ratio, Alt/Super modifier, keyboard repeat controls, notification
  options, media-key steps, and existing wallpaper/sound/session controls.
- Per-monitor enable/mode/refresh/position/scale/rotation settings with persistent
  profiles, output-management protocol support, hotplug handling, and recovery of
  windows from disabled/removed outputs. Physical hardware validation remains open.

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
