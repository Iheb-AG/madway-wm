# Changelog

## Unreleased

- Recover from failed output-frame commits without waiting for input. Restore
  damaged regions and retry per output with refresh-aware, bounded backoff;
  stop retries while sleeping/inactive and remove timers on output destruction.
  Fix fullscreen video/frame-callback stalls after transient DRM commit errors.

- Add persistent Show/Hide Desktop Icons actions to empty-space context menus,
  keeping Show available through the fallback menu while icons are hidden.

- Tighten Settings to a compact workstation form, flatten compound dropdown and
  numeric controls to one frame, and replace large category highlights with an
  accent stripe. Retain the selected theme's colors.
- Add desktop icons backed by the XDG Desktop folder, live directory updates,
  right-click create/rename/copy/paste/Trash actions, configurable icon size and
  directory, and grid reordering. Keep file menus above applications.
- Support native Wayland drag requests, validated pointer serials, drag icons
  and cross-surface focus. Add real URI file drops to/from the desktop and folder
  icons; cancel drags on Escape, lock, sleep and workspace changes.

- Fix clipped launcher results when filtering to a single match: move spacing
  outside Wofi's dynamically sized result viewport.

- Add an explicit slideshow enable/pause switch that retains the selected images
  and interval, stops/resumes the timer, and reports paused state.
- Drive workspace, window and dock motion from per-output frame events, removing
  the fixed 16 ms update cap. Use a softer shared curve and 420/360/240 ms defaults
  with legacy-default migration. Keep snapshots at native output scale and blend
  in newly rendered content on maximize/restore; reverse from the visible size.
- Keep workspace slides alive when menus close or non-exclusive layers redraw;
  still publish wallpaper mapping state for reliable background handoffs.

- Animate maximize/restore and minimize/restore with short cubic Bézier zooms,
  shrinking toward the dock edge. Add a separate Appearance toggle/duration and
  settle safely on interaction, workspace/output changes, unmap, lock and sleep.
- Give Settings more row/column spacing and padding, remove category separators,
  and place slider values beside their tracks. Remove inherited GTK menu margins
  so utility menus touch the panel on every edge.

- Animate workspace changes with per-output, clipped cubic Bézier slides while
  keeping panels and the dock fixed. Add an Appearance toggle and duration;
  cancel snapshots on interaction, output changes, lock and sleep.
- Add Keyboard and Mouse & touchpad settings with live XKB layout/repeat
  configuration and capability-checked libinput preferences. Enable native
  touchpad tap-to-click and tap dragging by default, including hotplugged devices.
- Keep dock tooltips inside output bounds. Copy every successful screenshot to
  the clipboard automatically, retaining saved files if clipboard copying fails.

- Replace the Alt+Tab text list with independently rendered window preview
  cards, including covered/minimized clients. Keep PNG snapshots private in the
  runtime directory and delete them on lock, unmap and session shutdown.
- Add icon-only (default) and application-name-only taskbar modes.
- Add wallpaper slideshows from a folder or selected images, configurable
  intervals, missing-image recovery and a mapped-background handoff across
  outputs. Pause rotation during lock/sleep and stop old timers on mode changes.

- Hide the Waybar dock behind maximized windows per output and reclaim its
  work area. Add edge reveal and cubic Bézier slide animation, interruption
  handling, output clipping and configurable animation/hide behavior.
- Expand taskbar entries directly after the workspace selector, keep Midnight
  title controls white on hover, and preserve open menus when taking screenshots
  through keyboard shortcuts.

- Integrate an existing Waybar dock with application icons and a StatusNotifier
  tray, configurable on four edges. Add foreign-toplevel window management with
  lock guards and metadata withdrawal. Keep every running application's
  icon/title in the top taskbar with click-to-minimize/focus/restore behavior.
- Add Gershwin Midnight across frames, panel, menus, settings, launcher and dock.
  Separate audio names, mute/default controls and sliders to prevent overlap.
- Add Print / Shift+Print / Ctrl+Print screenshots and menu controls using grim,
  slurp and wl-copy, private unique PNG files, selection cancellation and lock
  checks. Package the screenshot tools and Waybar through the installer.

- Add compact, scrollable panel entries for restoring minimized windows on the
  current workspace, including side panels. Use Konsole for terminal shortcuts,
  menu actions, and the launcher. Keep cascading menu columns at their natural
  heights, aligned above bottom panels, with transparent space between columns.

- Add ext-session-lock-v1 with swaylock/PAM authentication, Alt+L and menu controls,
  presentation-confirmed locking across outputs, exclusive input, fail-closed
  crash handling and supervised recovery. Pin authorized locker identities with
  pidfds. Lock before sleep by default and gate logind delay release on protected
  frames; retain an explicit unlocked-sleep preference.

- Show the account name in the panel by default, with configurable custom labels.
  Add native sleep through logind, configurable lid actions (suspend by default),
  docked internal-display blanking and restore, and sleep/VT resume repaint and
  focus recovery. Keep native sessions alive through temporary loss of all
  outputs. Test with fake logind, virtual switches and headless displays.

- Add a Gershwin/Eau desktop preset from the local reference: silver gradients,
  Inter text, blue selection, translucent 22px panel, rounded title bars and
  cached non-interactive window shadows. Include the original wallpaper locally
  while keeping the asset Git-ignored. Add functional minimize controls and
  Alt+Tab/Window-menu restore; retain existing theme profiles and settings.

- Add laptop battery percentage/charging status on every panel edge, a power
  details dropdown and configurable Power settings. Monitor batteries separately
  from the panel; send low/critical notifications with hysteresis and clear them
  on charging. Handle missing readings, multiple batteries and desktops without
  batteries using read-only power-supply data.

- Add a Demoscenes submenu backed by a local catalogue, exclusive scene selection,
  shared playback preferences and Git ignore rules for all local scene payloads.

- Port the demoscene to an optional native Wayland client with RGBA transparency,
  premultiplied blending, click-through input and borderless always-above policy.
  Add menu/settings/launcher/script controls, optional build/install support and
  isolated composition tests. Keep media local and audio opt-in.

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
